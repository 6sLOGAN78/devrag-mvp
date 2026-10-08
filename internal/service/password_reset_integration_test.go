//go:build integration

package service

import (
	"context"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

type recordingQueue struct {
	mu     sync.Mutex
	mails  []Mail
	accept bool
}

func (q *recordingQueue) Enqueue(m Mail) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.mails = append(q.mails, m)
	return q.accept
}

func (q *recordingQueue) sent() []Mail {
	q.mu.Lock()
	defer q.mu.Unlock()
	return append([]Mail(nil), q.mails...)
}

type resetEnv struct {
	*userEnv
	reset  *PasswordReset
	otp    *OTP
	queue  *recordingQueue
	raw    *redis.Client
	prefix string
}

const resetPassword = "reset-new-pass-0003"

func newResetEnv(t *testing.T, mutate func(*server.Config)) *resetEnv {
	t.Helper()
	u := newUserEnv(t, func(c *server.Config) {
		c.RateLimit.OTPPerIPPerHour = 1000
		c.RateLimit.OTPPerEmailPerHour = 1000
		c.Auth.OTPTTL = time.Minute
		if mutate != nil {
			mutate(c)
		}
	})
	rd := dao.OpenRedis(u.cfg.Redis)
	raw := redis.NewClient(&redis.Options{Addr: u.cfg.Redis.Host + ":" + strconv.Itoa(u.cfg.Redis.Port), Password: u.cfg.Redis.Password, DB: u.cfg.Redis.DB})
	prefix := "test-" + testutil.UniqueName("reset")
	otp := NewOTP(rd, prefix, u.cfg.Security.SecretKey, u.cfg.Auth.OTPTTL)
	q := &recordingQueue{accept: true}
	e := &resetEnv{userEnv: u, otp: otp, queue: q, raw: raw, prefix: prefix}
	e.reset = NewPasswordReset(u.db, u.svc.limiter, otp, q, u.cfg)
	t.Cleanup(func() {
		ks, _ := raw.Keys(context.Background(), prefix+"*").Result()
		for _, k := range ks {
			_ = raw.Del(context.Background(), k).Err()
		}
		_ = raw.Close()
		_ = rd.Close()
	})
	return e
}

// subjectOf resolves the account identity the service keys its limiters on, the way the service does.
func (e *resetEnv) subjectOf(t *testing.T, email string) string {
	t.Helper()
	canonical := common.CanonicalEmail(email)
	u, err := e.db.FindUserByEmail(context.Background(), canonical)
	if err != nil {
		return accountSubject(nil, canonical)
	}
	return accountSubject(u, canonical)
}

// clearInterval removes the one-per-interval counter so a test can request a second code for the
// same email at once; production never does this.
func (e *resetEnv) clearInterval(t *testing.T, email string) {
	t.Helper()
	require.NoError(t, e.svc.limiter.Reset(context.Background(), "otp:email:interval:"+emailKey(e.subjectOf(t, email))))
}

func (e *resetEnv) request(t *testing.T, email string) string {
	t.Helper()
	e.clearInterval(t, email)
	before := len(e.queue.sent())
	require.NoError(t, e.reset.RequestReset(context.Background(), email, "203.0.113.50"))
	for _, m := range e.queue.sent()[before:] {
		if c := sixDigits.FindString(m.Body); c != "" {
			return c
		}
	}
	return ""
}

func (e *resetEnv) otpKeyCount(t *testing.T) int {
	ks, err := e.raw.Keys(context.Background(), e.prefix+":otp:*").Result()
	require.NoError(t, err)
	return len(ks)
}

func (e *resetEnv) passwordOf(t *testing.T, id string) string {
	return deref(e.row(t, id).Password)
}

func TestRequestResetSendsOnlyToARealActiveAccount(t *testing.T) {
	e := newResetEnv(t, nil)
	real := testutil.UniqueEmail("real")
	e.register(t, real, testutil.FixtureCredential())
	inactive := testutil.UniqueEmail("off")
	p := e.register(t, inactive, testutil.FixtureCredential())
	require.NoError(t, e.raw.Ping(context.Background()).Err())
	require.NoError(t, e.userEnv.raw.Exec("UPDATE user SET status = '0' WHERE id = ?", p.ID).Error)
	unknown := testutil.UniqueEmail("ghost")

	code := e.request(t, real)
	require.Regexp(t, codeShape, code)
	assert.Equal(t, 1, len(e.queue.sent()))
	assert.Equal(t, strings.ToLower(real), e.queue.sent()[0].To, "the recipient is the stored account address")
	keys := e.otpKeyCount(t)

	require.NoError(t, e.reset.RequestReset(context.Background(), unknown, "203.0.113.50"))
	require.NoError(t, e.reset.RequestReset(context.Background(), inactive, "203.0.113.50"))
	assert.Equal(t, 1, len(e.queue.sent()), "nothing is sent for an unknown or inactive account")
	assert.Equal(t, keys+2, e.otpKeyCount(t), "unknown and inactive emails go through the same Redis work (decoy record)")
}

func TestRequestResetReturnValueIsTheSameForEveryEmail(t *testing.T) {
	e := newResetEnv(t, nil)
	real := testutil.UniqueEmail("same")
	e.register(t, real, testutil.FixtureCredential())
	errReal := e.reset.RequestReset(context.Background(), real, "203.0.113.51")
	errGhost := e.reset.RequestReset(context.Background(), testutil.UniqueEmail("ghost"), "203.0.113.51")
	assert.NoError(t, errReal)
	assert.NoError(t, errGhost)
	e.queue.accept = false
	assert.NoError(t, e.reset.RequestReset(context.Background(), real+"x", "203.0.113.51"))
	other := testutil.UniqueEmail("full")
	e.register(t, other, testutil.FixtureCredential())
	assert.NoError(t, e.reset.RequestReset(context.Background(), other, "203.0.113.51"), "a dropped message does not change the outcome")
}

func TestRequestResetValidatesTheEmail(t *testing.T) {
	e := newResetEnv(t, nil)
	for _, bad := range []string{"", "nope", "a@b", "Bob <bob@example.test>", "a@example.test\r\nBcc: x@example.test", strings.Repeat("a", 300) + "@example.test"} {
		err := e.reset.RequestReset(context.Background(), bad, "203.0.113.52")
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, "%.20q", bad)
	}
	assert.Empty(t, e.queue.sent())
}

func TestFullResetFlowByTicket(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("flow")
	p := e.register(t, email, testutil.FixtureCredential())
	oldToken := e.login(t, email, testutil.FixtureCredential()).Token
	code := e.request(t, email)

	ticket, err := e.reset.VerifyCode(ctx, " "+strings.ToUpper(email)+" ", code)
	require.NoError(t, err)
	require.NotEmpty(t, ticket)
	_, err = e.reset.VerifyCode(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid, "the code was consumed by verify")

	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: resetPassword}))
	stored := e.passwordOf(t, p.ID)
	assert.True(t, strings.HasPrefix(stored, "pbkdf2:sha256:600000$"))
	assert.True(t, common.VerifyPassword(resetPassword, stored))
	assert.False(t, common.VerifyPassword(testutil.FixtureCredential(), stored))
	assert.True(t, strings.HasPrefix(deref(e.row(t, p.ID).AccessToken), "INVALID_"), "the shared token is rewritten (D-08)")

	_, err = e.auth.ResolvePrincipal(ctx, oldToken, []string{AuthTypeJWT})
	assert.ErrorIs(t, err, ErrUnauthenticated, "the old token is dead")
	_, err = e.svc.Login(ctx, LoginInput{Email: email, Password: testutil.FixtureCredential(), ClientIP: "203.0.113.2"})
	assert.ErrorIs(t, err, ErrInvalidCredentials)
	fresh := e.login(t, email, resetPassword)
	_, err = e.auth.ResolvePrincipal(ctx, fresh.Token, []string{AuthTypeJWT})
	assert.NoError(t, err)

	err = e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: "yet-another-pass-9"})
	assert.ErrorIs(t, err, ErrTicketInvalid, "a ticket is single use")
	assert.True(t, common.VerifyPassword(resetPassword, e.passwordOf(t, p.ID)))
}

func TestResetWithTheCodeItselfFollowsTheDocumentedShape(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("doc")
	p := e.register(t, email, testutil.FixtureCredential())
	code := e.request(t, email)
	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Code: code, NewPassword: resetPassword}))
	assert.True(t, common.VerifyPassword(resetPassword, e.passwordOf(t, p.ID)))
	assert.ErrorIs(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Code: code, NewPassword: "yet-another-pass-9"}), ErrOTPInvalid)
}

func TestResetNeedsAGrant(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("nogrant")
	p := e.register(t, email, testutil.FixtureCredential())
	before := e.passwordOf(t, p.ID)
	assert.Error(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, NewPassword: resetPassword}))
	assert.Error(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: "made-up", NewPassword: resetPassword}))
	assert.Error(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Code: "123456", NewPassword: resetPassword}))
	assert.Equal(t, before, e.passwordOf(t, p.ID))
}

func TestACodeForAOneAccountCanNeverResetAnother(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	a, b := testutil.UniqueEmail("alice"), testutil.UniqueEmail("bob")
	pa := e.register(t, a, testutil.FixtureCredential())
	pb := e.register(t, b, testutil.FixtureCredential())
	beforeA, beforeB := e.passwordOf(t, pa.ID), e.passwordOf(t, pb.ID)
	codeA := e.request(t, a)
	_ = e.request(t, b)

	_, err := e.reset.VerifyCode(ctx, b, codeA)
	assert.ErrorIs(t, err, ErrOTPInvalid, "A's code does not verify for B's email")
	err = e.reset.ResetPassword(ctx, ResetInput{Email: b, Code: codeA, NewPassword: resetPassword})
	assert.Error(t, err)

	codeA = e.request2(t, a)
	ticketA, err := e.reset.VerifyCode(ctx, a, codeA)
	require.NoError(t, err)
	err = e.reset.ResetPassword(ctx, ResetInput{Email: b, Ticket: ticketA, NewPassword: resetPassword})
	assert.ErrorIs(t, err, ErrTicketInvalid, "A's ticket cannot reset B")
	assert.Equal(t, beforeB, e.passwordOf(t, pb.ID), "B is untouched")
	assert.Equal(t, beforeA, e.passwordOf(t, pa.ID), "and the misused ticket is burned")
	assert.ErrorIs(t, e.reset.ResetPassword(ctx, ResetInput{Email: a, Ticket: ticketA, NewPassword: resetPassword}), ErrTicketInvalid)
}

// request2 issues a code for an email whose per-email interval would block a second send in
// production; the service tests raise the limits, so this is the same call as request.
func (e *resetEnv) request2(t *testing.T, email string) string {
	t.Helper()
	e.clearInterval(t, email)
	before := len(e.queue.sent())
	require.NoError(t, e.reset.RequestReset(context.Background(), email, "203.0.113.50"))
	mails := e.queue.sent()
	require.Greater(t, len(mails), before)
	return sixDigits.FindString(mails[len(mails)-1].Body)
}

func TestResetEnforcesTheLengthRuleWithoutBurningTheTicket(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("len")
	p := e.register(t, email, testutil.FixtureCredential())
	ticket, err := e.reset.VerifyCode(ctx, email, e.request(t, email))
	require.NoError(t, err)
	for _, bad := range []string{"", "1234567", strings.Repeat("a", 129)} {
		var ve *ValidationError
		err := e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: bad})
		assert.ErrorAs(t, err, &ve, "%d characters", len(bad))
	}
	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: strings.Repeat("a", 128)}), "128 is allowed and the ticket still works")
	assert.True(t, common.VerifyPassword(strings.Repeat("a", 128), e.passwordOf(t, p.ID)))
}

func TestResetRemovesOutstandingCodesAndTickets(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("outstanding")
	e.register(t, email, testutil.FixtureCredential())
	ticket, err := e.reset.VerifyCode(ctx, email, e.request(t, email))
	require.NoError(t, err)
	pending := e.request2(t, email)
	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: resetPassword}))
	_, err = e.reset.VerifyCode(ctx, email, pending)
	assert.ErrorIs(t, err, ErrOTPInvalid, "a code requested before the reset no longer works")
	ks, err := e.raw.Keys(ctx, e.prefix+"*").Result()
	require.NoError(t, err)
	assert.Empty(t, ks, "no code or ticket of that user remains")
}

func TestResetClearsTheLoginLockout(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("lock")
	e.register(t, email, testutil.FixtureCredential())
	for i := 0; i < e.cfg.RateLimit.LoginFailuresPerEmail; i++ {
		_, _ = e.svc.Login(ctx, LoginInput{Email: email, Password: "wrong-password-1", ClientIP: "203.0.113.9"})
	}
	_, err := e.svc.Login(ctx, LoginInput{Email: email, Password: testutil.FixtureCredential(), ClientIP: "203.0.113.9"})
	require.Error(t, err, "locked out")
	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Code: e.request(t, email), NewPassword: resetPassword}))
	_, err = e.svc.Login(ctx, LoginInput{Email: email, Password: resetPassword, ClientIP: "203.0.113.9"})
	assert.NoError(t, err)
}

func TestParallelResetsWithOneTicketHaveOneWinner(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("par")
	e.register(t, email, testutil.FixtureCredential())
	ticket, err := e.reset.VerifyCode(ctx, email, e.request(t, email))
	require.NoError(t, err)
	var wg sync.WaitGroup
	var wins atomic.Int32
	start := make(chan struct{})
	for i := 0; i < 6; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			if e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: resetPassword}) == nil {
				wins.Add(1)
			}
		}()
	}
	close(start)
	wg.Wait()
	assert.EqualValues(t, 1, wins.Load())
}

func TestDecoyGrantSucceedsWithoutChangingAnything(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	ghost := testutil.UniqueEmail("ghost")
	code, err := e.otp.Issue(ctx, accountSubject(nil, ghost), "")
	require.NoError(t, err)
	ticket, err := e.reset.VerifyCode(ctx, ghost, code)
	require.NoError(t, err, "verify cannot tell a decoy from a real code")
	assert.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: ghost, Ticket: ticket, NewPassword: resetPassword}), "reset reports the same success")
	assert.EqualValues(t, 0, e.count(t, "user", "email", ghost))
}

func TestResetRefusesAnAccountDisabledAfterTheCode(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("late")
	p := e.register(t, email, testutil.FixtureCredential())
	ticket, err := e.reset.VerifyCode(ctx, email, e.request(t, email))
	require.NoError(t, err)
	before := e.passwordOf(t, p.ID)
	require.NoError(t, e.userEnv.raw.Exec("UPDATE user SET status = '0' WHERE id = ?", p.ID).Error)
	assert.ErrorIs(t, e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: ticket, NewPassword: resetPassword}), ErrTicketInvalid)
	assert.Equal(t, before, e.passwordOf(t, p.ID))
}

func TestServiceErrorsNeverContainTheCodeOrPassword(t *testing.T) {
	e := newResetEnv(t, nil)
	ctx := context.Background()
	email := testutil.UniqueEmail("err")
	e.register(t, email, testutil.FixtureCredential())
	code := e.request(t, email)
	_, err := e.reset.VerifyCode(ctx, email, wrongCode(code))
	require.Error(t, err)
	assert.NotContains(t, err.Error(), code)
	err = e.reset.ResetPassword(ctx, ResetInput{Email: email, Ticket: "tkt", NewPassword: resetPassword})
	require.Error(t, err)
	assert.NotContains(t, err.Error(), resetPassword)
}
