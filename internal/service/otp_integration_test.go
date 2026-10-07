//go:build integration

package service

import (
	"context"
	"encoding/base64"
	"errors"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/dao"
	"devrag/internal/testutil"
)

const otpTestSecret = "fake-otp-secret-0123456789-abcdefghij"

var codeShape = regexp.MustCompile(`^\d{6}$`)

// countingBackend counts the attempts that reached the comparison step.
type countingBackend struct {
	*dao.Redis
	compared atomic.Int32
}

func (c *countingBackend) OTPAttempt(ctx context.Context, key string, max int) (string, string, int64, bool, error) {
	v, o, n, found, err := c.Redis.OTPAttempt(ctx, key, max)
	if found {
		c.compared.Add(1)
	}
	return v, o, n, found, err
}

type otpRig struct {
	otp    *OTP
	be     *countingBackend
	raw    *redis.Client
	prefix string
}

func newOTPRig(t *testing.T, ttl time.Duration) *otpRig {
	t.Helper()
	cfg := testutil.RequireRedis(t)
	rd := dao.OpenRedis(cfg.Redis)
	raw := redis.NewClient(&redis.Options{Addr: cfg.Redis.Host + ":" + strconv.Itoa(cfg.Redis.Port), Password: cfg.Redis.Password, DB: cfg.Redis.DB})
	prefix := "test-" + testutil.UniqueName("otp")
	be := &countingBackend{Redis: rd}
	r := &otpRig{otp: NewOTP(be, prefix, otpTestSecret, ttl), be: be, raw: raw, prefix: prefix}
	t.Cleanup(func() {
		for _, k := range r.keys(t) {
			_ = raw.Del(context.Background(), k).Err()
		}
		_ = raw.Close()
		_ = rd.Close()
	})
	return r
}

func (r *otpRig) keys(t *testing.T) []string {
	t.Helper()
	ks, err := r.raw.Keys(context.Background(), r.prefix+"*").Result()
	require.NoError(t, err)
	return ks
}

func (r *otpRig) otpKeys(t *testing.T) []string {
	var out []string
	for _, k := range r.keys(t) {
		if strings.HasPrefix(k, r.prefix+":otp:") {
			out = append(out, k)
		}
	}
	return out
}

func wrongCode(good string) string {
	if good == "000000" {
		return "000001"
	}
	return "000000"
}

func TestGeneratedCodesAreSixDigitsAndUniform(t *testing.T) {
	counts := make([]int, 10)
	leadingZero := 0
	const n = 4000
	for i := 0; i < n; i++ {
		c, err := generateCode()
		require.NoError(t, err)
		require.Regexp(t, codeShape, c)
		counts[c[0]-'0']++
		if c[0] == '0' {
			leadingZero++
		}
	}
	for d, got := range counts {
		assert.InDelta(t, n/10, got, 120, "first digit %d is about 10%% of codes (no modulo bias, zero padded)", d)
	}
	assert.Greater(t, leadingZero, 0, "codes are zero padded")
}

func TestIssueStoresOnlyAKeyedHashWithTTL(t *testing.T) {
	r := newOTPRig(t, 600*time.Second)
	ctx := context.Background()
	email := "  Alice." + testutil.UniqueName("x") + "@Example.TEST "
	code, err := r.otp.Issue(ctx, email, "user-1")
	require.NoError(t, err)
	require.Regexp(t, codeShape, code)

	ks := r.otpKeys(t)
	require.Len(t, ks, 1)
	assert.NotContains(t, strings.ToLower(ks[0]), "example.test", "the email is not part of the key")
	h, err := r.raw.HGetAll(ctx, ks[0]).Result()
	require.NoError(t, err)
	assert.Regexp(t, `^[0-9a-f]{32}:[0-9a-f]{64}$`, h["v"], "salt:hex(HMAC-SHA256)")
	assert.NotContains(t, h["v"], code)
	for k, v := range h {
		assert.NotContains(t, v, code, "field %s must not hold the plain code", k)
	}
	assert.Equal(t, "0", h["a"])
	assert.Equal(t, "user-1", h["u"])
	ttl, err := r.raw.PTTL(ctx, ks[0]).Result()
	require.NoError(t, err)
	assert.Greater(t, ttl, 590*time.Second)
	assert.LessOrEqual(t, ttl, 600*time.Second)

	owner, err := r.otp.Verify(ctx, strings.ToLower(strings.TrimSpace(email)), code)
	require.NoError(t, err, "the email is trimmed and lowercased before keying")
	assert.Equal(t, "user-1", owner)
}

func TestSameCodeHashesDifferentlyPerSaltAndSecret(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	other := NewOTP(r.be, r.prefix, "another-fake-secret-0123456789-abcdefgh", time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("salt")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	_, err = other.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid, "a different server secret cannot verify the stored hash")
}

func TestVerifyConsumesTheCodeOnce(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("once")
	code, err := r.otp.Issue(ctx, email, "u1")
	require.NoError(t, err)
	owner, err := r.otp.Verify(ctx, email, code)
	require.NoError(t, err)
	assert.Equal(t, "u1", owner)
	_, err = r.otp.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid, "single use")
	assert.Empty(t, r.otpKeys(t))
}

func TestVerifyRejectsMalformedAndUnknown(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	for _, c := range []string{"", "12345", "1234567", "abcdef", "12345 ", "１２３４５６"} {
		_, err := r.otp.Verify(ctx, testutil.UniqueEmail("m"), c)
		assert.ErrorIs(t, err, ErrOTPInvalid, "%q", c)
	}
}

func TestFifthWrongAttemptDestroysTheCode(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("five")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	for i := 1; i <= 4; i++ {
		_, err := r.otp.Verify(ctx, email, wrongCode(code))
		require.ErrorIs(t, err, ErrOTPInvalid)
		require.Len(t, r.otpKeys(t), 1, "still alive after %d wrong tries", i)
	}
	_, err = r.otp.Verify(ctx, email, wrongCode(code))
	require.ErrorIs(t, err, ErrOTPInvalid)
	assert.Empty(t, r.otpKeys(t), "the fifth wrong try destroys the code")
	_, err = r.otp.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid, "the right code no longer works")
}

func TestFifthTryMayStillBeCorrect(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("fifth")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	for i := 0; i < 4; i++ {
		_, _ = r.otp.Verify(ctx, email, wrongCode(code))
	}
	_, err = r.otp.Verify(ctx, email, code)
	assert.NoError(t, err)
}

func TestNewRequestReplacesTheOldCodeAndResetsAttempts(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("replace")
	first, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	for i := 0; i < 4; i++ {
		_, _ = r.otp.Verify(ctx, email, wrongCode(first))
	}
	var second string
	for i := 0; i < 20 && (second == "" || second == first); i++ {
		second, err = r.otp.Issue(ctx, email, "u")
		require.NoError(t, err)
	}
	require.NotEqual(t, first, second)
	require.Len(t, r.otpKeys(t), 1, "one live code per email")
	_, err = r.otp.Verify(ctx, email, first)
	assert.ErrorIs(t, err, ErrOTPInvalid, "the replaced code fails")
	for i := 0; i < 3; i++ {
		_, _ = r.otp.Verify(ctx, email, wrongCode(second))
	}
	_, err = r.otp.Verify(ctx, email, second)
	assert.NoError(t, err, "attempts start again for the new code")
}

func TestParallelGuessesNeverExceedFiveComparisons(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("race")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	var wg sync.WaitGroup
	start := make(chan struct{})
	var ok atomic.Int32
	for i := 0; i < 80; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			if _, err := r.otp.Verify(ctx, email, wrongCode(code)); err == nil {
				ok.Add(1)
			}
		}()
	}
	close(start)
	wg.Wait()
	assert.EqualValues(t, 0, ok.Load())
	assert.LessOrEqual(t, r.be.compared.Load(), int32(5), "at most five guesses are ever compared")
	assert.Empty(t, r.otpKeys(t))
	_, err = r.otp.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid)
}

func TestParallelCorrectVerifyHasExactlyOneWinner(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	for round := 0; round < 10; round++ {
		email := testutil.UniqueEmail("win")
		code, err := r.otp.Issue(ctx, email, "u")
		require.NoError(t, err)
		var wg sync.WaitGroup
		start := make(chan struct{})
		var wins atomic.Int32
		for i := 0; i < 5; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				<-start
				if _, err := r.otp.Verify(ctx, email, code); err == nil {
					wins.Add(1)
				}
			}()
		}
		close(start)
		wg.Wait()
		require.EqualValues(t, 1, wins.Load(), "round %d: a code is single use even under parallel requests", round)
	}
}

func TestCodeExpiresAfterItsTTL(t *testing.T) {
	r := newOTPRig(t, time.Second)
	ctx := context.Background()
	email := testutil.UniqueEmail("ttl")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	require.NoError(t, testutil.WaitUntil(ctx, 15*time.Second, 100*time.Millisecond, func() bool { return len(r.otpKeys(t)) == 0 }), "the key disappears")
	_, err = r.otp.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid)
}

func TestEveryKeyHasATTL(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("ttlall")
	_, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	_, err = r.otp.IssueTicket(ctx, email, "u", time.Minute)
	require.NoError(t, err)
	ks := r.keys(t)
	require.GreaterOrEqual(t, len(ks), 3)
	for _, k := range ks {
		ttl, err := r.raw.PTTL(ctx, k).Result()
		require.NoError(t, err)
		assert.Greater(t, ttl, time.Duration(0), "key %s has a TTL", k)
	}
}

func TestTicketIsRandomHashedAndBoundToTheEmail(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("tk")
	t1, err := r.otp.IssueTicket(ctx, email, "u1", time.Minute)
	require.NoError(t, err)
	raw, err := base64.RawURLEncoding.DecodeString(t1)
	require.NoError(t, err)
	assert.GreaterOrEqual(t, len(raw), 16, "at least 128 bits")
	for _, k := range r.keys(t) {
		assert.NotContains(t, k, t1, "tickets are stored by hash, never in clear")
		v, _ := r.raw.Get(ctx, k).Result()
		assert.NotContains(t, v, t1)
	}
	t2, err := r.otp.IssueTicket(ctx, testutil.UniqueEmail("tk2"), "u2", time.Minute)
	require.NoError(t, err)
	assert.NotEqual(t, t1, t2)

	owner, err := r.otp.ConsumeTicket(ctx, email, t1)
	require.NoError(t, err)
	assert.Equal(t, "u1", owner)
	_, err = r.otp.ConsumeTicket(ctx, email, t1)
	assert.ErrorIs(t, err, ErrTicketInvalid, "single use")
}

func TestTicketOfOneEmailCannotBeUsedForAnother(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	a, b := testutil.UniqueEmail("a"), testutil.UniqueEmail("b")
	ta, err := r.otp.IssueTicket(ctx, a, "ua", time.Minute)
	require.NoError(t, err)
	_, err = r.otp.ConsumeTicket(ctx, b, ta)
	assert.ErrorIs(t, err, ErrTicketInvalid)
	_, err = r.otp.ConsumeTicket(ctx, a, ta)
	assert.ErrorIs(t, err, ErrTicketInvalid, "a mismatched use burns the ticket")
}

func TestTicketRejectsGarbageAndExpires(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("tg")
	for _, bad := range []string{"", "x", strings.Repeat("A", 43), strings.Repeat("A", 5000), "../../etc", "a b"} {
		_, err := r.otp.ConsumeTicket(ctx, email, bad)
		assert.ErrorIs(t, err, ErrTicketInvalid, "%.10q", bad)
	}
	tk, err := r.otp.IssueTicket(ctx, email, "u", time.Second)
	require.NoError(t, err)
	require.NoError(t, testutil.WaitUntil(ctx, 15*time.Second, 100*time.Millisecond, func() bool { return len(r.keys(t)) == 0 }))
	_, err = r.otp.ConsumeTicket(ctx, email, tk)
	assert.ErrorIs(t, err, ErrTicketInvalid)
}

func TestNewTicketReplacesTheUsersEarlierOne(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("tr")
	first, err := r.otp.IssueTicket(ctx, email, "u", time.Minute)
	require.NoError(t, err)
	second, err := r.otp.IssueTicket(ctx, email, "u", time.Minute)
	require.NoError(t, err)
	_, err = r.otp.ConsumeTicket(ctx, email, first)
	assert.ErrorIs(t, err, ErrTicketInvalid)
	_, err = r.otp.ConsumeTicket(ctx, email, second)
	assert.NoError(t, err)
}

func TestRevokeRemovesCodeAndTickets(t *testing.T) {
	r := newOTPRig(t, time.Minute)
	ctx := context.Background()
	email := testutil.UniqueEmail("rv")
	code, err := r.otp.Issue(ctx, email, "u")
	require.NoError(t, err)
	tk, err := r.otp.IssueTicket(ctx, email, "u", time.Minute)
	require.NoError(t, err)
	require.NoError(t, r.otp.Revoke(ctx, email, "u"))
	assert.Empty(t, r.keys(t), "nothing outstanding for that user remains")
	_, err = r.otp.Verify(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid)
	_, err = r.otp.ConsumeTicket(ctx, email, tk)
	assert.ErrorIs(t, err, ErrTicketInvalid)
}

func TestRedisOutageIsUnavailableNotInvalid(t *testing.T) {
	cfg := testutil.RequireRedis(t)
	bad := cfg.Redis
	bad.Port = 1
	rd := dao.OpenRedis(bad)
	defer func() { _ = rd.Close() }()
	o := NewOTP(rd, "test-"+testutil.UniqueName("down"), otpTestSecret, time.Minute)
	ctx := context.Background()
	_, err := o.Issue(ctx, "a@example.test", "u")
	assert.True(t, errors.Is(err, ErrUnavailable), "issue: %v", err)
	_, err = o.Verify(ctx, "a@example.test", "123456")
	assert.True(t, errors.Is(err, ErrUnavailable), "verify: %v", err)
	_, err = o.IssueTicket(ctx, "a@example.test", "u", time.Minute)
	assert.True(t, errors.Is(err, ErrUnavailable))
	_, err = o.ConsumeTicket(ctx, "a@example.test", strings.Repeat("A", ticketLength))
	assert.True(t, errors.Is(err, ErrUnavailable))
}
