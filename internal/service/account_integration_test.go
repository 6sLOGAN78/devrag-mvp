//go:build integration

package service

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

type accountEnv struct {
	svc *Account
	cfg server.Config
	raw *gorm.DB
	db  *dao.DB
	ids []string // user ids to remove
}

// newAccountEnv builds the service against the live MySQL and Valkey. Per-IP limits are raised so
// tests do not share counters; the limiter prefix is unique per test.
func newAccountEnv(t *testing.T, mutate func(*server.Config)) *accountEnv {
	t.Helper()
	cfg := testutil.RequireDB(t)
	cfg.RateLimit.RegisterPerIP = 1000
	cfg.RateLimit.LoginPerIP = 1000
	cfg.Models = server.ModelsConfig{}
	cfg.Auth.RegisterEnabled = true
	if mutate != nil {
		mutate(&cfg)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db, err := dao.OpenDB(ctx, cfg.MySQL)
	require.NoError(t, err)
	rd := dao.OpenRedis(cfg.Redis)
	raw, err := gorm.Open(mysql.Open(dao.DSN(cfg.MySQL)), &gorm.Config{Logger: logger.Discard})
	require.NoError(t, err)
	e := &accountEnv{svc: NewAccount(db, NewLimiter(rd, "test-"+testutil.UniqueName("acct")), cfg), cfg: cfg, raw: raw, db: db}
	t.Cleanup(func() {
		for _, id := range e.ids {
			for _, tbl := range []struct{ sql string }{
				{"DELETE FROM tenant_llm WHERE tenant_id = ?"}, {"DELETE FROM user_tenant WHERE user_id = ?"},
				{"DELETE FROM tenant WHERE id = ?"}, {"DELETE FROM user WHERE id = ?"},
			} {
				_ = raw.Exec(tbl.sql, id).Error
			}
		}
		_ = db.Close()
		_ = rd.Close()
	})
	return e
}

func (e *accountEnv) register(t *testing.T, email, password string) Profile {
	t.Helper()
	p, err := e.svc.Register(context.Background(), RegisterInput{Email: email, Password: password, Nickname: testutil.UniqueName("nick"), ClientIP: "203.0.113.1"})
	require.NoError(t, err)
	e.ids = append(e.ids, p.ID)
	return p
}

func (e *accountEnv) count(t *testing.T, table, col, val string) int64 {
	t.Helper()
	var n int64
	require.NoError(t, e.raw.Table(table).Where(col+" = ?", val).Count(&n).Error)
	return n
}

func TestRegisterCreatesUserTenantAndOwnerRow(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("reg")
	p := e.register(t, strings.ToUpper(email), testutil.FixtureCredential())
	assert.Equal(t, strings.ToLower(email), p.Email, "email is stored lowercase")
	assert.Equal(t, p.ID, p.TenantID, "tenant id equals user id")

	var u entity.User
	require.NoError(t, e.raw.First(&u, "id = ?", p.ID).Error)
	require.NotNil(t, u.Password)
	assert.True(t, strings.HasPrefix(*u.Password, "pbkdf2:sha256:600000$"))
	assert.True(t, common.VerifyPassword(testutil.FixtureCredential(), *u.Password))

	var tn entity.Tenant
	require.NoError(t, e.raw.First(&tn, "id = ?", p.ID).Error)
	assert.Empty(t, tn.LLMID)
	assert.Empty(t, tn.EmbdID)
	assert.Empty(t, tn.RerankID)
	assert.NotEmpty(t, tn.ParserIds)
	assert.EqualValues(t, 0, e.count(t, "tenant_llm", "tenant_id", p.ID), "no provider configured, no tenant_llm rows")

	var ut entity.UserTenant
	require.NoError(t, e.raw.First(&ut, "user_id = ?", p.ID).Error)
	assert.Equal(t, "owner", ut.Role)
	assert.Equal(t, p.ID, ut.InvitedBy)
	assert.Equal(t, p.ID, ut.TenantID)
	assert.EqualValues(t, 1, e.count(t, "user_tenant", "user_id", p.ID))
}

func TestRegisterSeedsConfiguredDefaultModels(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) {
		c.Models = server.ModelsConfig{DefaultChatModel: "chat-x", DefaultEmbeddingModel: "embed-x", DefaultRerankModel: "rerank-x", DefaultFactory: "OpenAI", DefaultBaseURL: "http://models.invalid/v1"}
	})
	p := e.register(t, testutil.UniqueEmail("models"), testutil.FixtureCredential())
	var tn entity.Tenant
	require.NoError(t, e.raw.First(&tn, "id = ?", p.ID).Error)
	assert.Equal(t, "chat-x@OpenAI", tn.LLMID)
	assert.Equal(t, "embed-x@OpenAI", tn.EmbdID)
	assert.Equal(t, "rerank-x@OpenAI", tn.RerankID)
	assert.EqualValues(t, 3, e.count(t, "tenant_llm", "tenant_id", p.ID))
}

func TestRegisterRollsBackWhenThirdInsertFails(t *testing.T) {
	e := newAccountEnv(t, nil)
	userID, membershipID := strings.Repeat("a", 31)+"1", strings.Repeat("b", 31)+"2"
	seq := []string{userID, membershipID}
	e.svc.newID = func() string { id := seq[0]; seq = seq[1:]; return id }
	// A foreign user_tenant row owns the membership id, so the third insert fails for real.
	require.NoError(t, e.raw.Exec("INSERT INTO user_tenant (id, user_id, tenant_id, invited_by, role, status) VALUES (?, 'x', 'x', 'x', 'normal', '1')", membershipID).Error)
	t.Cleanup(func() { _ = e.raw.Exec("DELETE FROM user_tenant WHERE id = ?", membershipID).Error })

	_, err := e.svc.Register(context.Background(), RegisterInput{Email: testutil.UniqueEmail("rb"), Password: testutil.FixtureCredential(), Nickname: "rollback", ClientIP: "203.0.113.2"})
	require.Error(t, err)
	assert.NotContains(t, err.Error(), membershipID, "no SQL or ids in the error")
	assert.EqualValues(t, 0, e.count(t, "user", "id", userID), "user insert rolled back")
	assert.EqualValues(t, 0, e.count(t, "tenant", "id", userID), "tenant insert rolled back")
	assert.EqualValues(t, 1, e.count(t, "user_tenant", "id", membershipID), "only the pre-existing foreign row remains")
}

func TestRegisterValidation(t *testing.T) {
	e := newAccountEnv(t, nil)
	good := testutil.FixtureCredential()
	cases := []struct {
		name string
		in   RegisterInput
	}{
		{"password 7", RegisterInput{Email: testutil.UniqueEmail("v"), Password: "1234567", Nickname: "n"}},
		{"password 129", RegisterInput{Email: testutil.UniqueEmail("v"), Password: strings.Repeat("a", 129), Nickname: "n"}},
		{"bad email", RegisterInput{Email: "not-an-email", Password: good, Nickname: "n"}},
		{"display-name email", RegisterInput{Email: "Bob <bob@example.test>", Password: good, Nickname: "n"}},
		{"empty nickname", RegisterInput{Email: testutil.UniqueEmail("v"), Password: good, Nickname: "  "}},
		{"nickname 65", RegisterInput{Email: testutil.UniqueEmail("v"), Password: good, Nickname: strings.Repeat("n", 65)}},
	}
	for _, c := range cases {
		c.in.ClientIP = "203.0.113.3"
		_, err := e.svc.Register(context.Background(), c.in)
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, c.name)
	}
	for _, pw := range []string{"12345678", strings.Repeat("a", 128)} {
		e.register(t, testutil.UniqueEmail("edge"), pw)
	}
}

func TestRegisterDuplicateEmail(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("dup")
	e.register(t, email, testutil.FixtureCredential())
	_, err := e.svc.Register(context.Background(), RegisterInput{Email: strings.ToUpper(email), Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.4"})
	assert.ErrorIs(t, err, ErrEmailTaken)
}

func TestRegisterRefusedWhenSwitchOff(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.Auth.RegisterEnabled = false })
	email := testutil.UniqueEmail("off")
	_, err := e.svc.Register(context.Background(), RegisterInput{Email: email, Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.5"})
	assert.ErrorIs(t, err, ErrRegistrationDisabled)
	assert.EqualValues(t, 0, e.count(t, "user", "email", strings.ToLower(email)))
}

func TestRegisterRateLimitedPerIP(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.RegisterPerIP = 2 })
	for i := 0; i < 2; i++ {
		e.register(t, testutil.UniqueEmail("rl"), testutil.FixtureCredential())
	}
	_, err := e.svc.Register(context.Background(), RegisterInput{Email: testutil.UniqueEmail("rl"), Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.1"})
	var rl *RateLimitedError
	assert.ErrorAs(t, err, &rl)
}

func login(e *accountEnv, email, password string) (LoginResult, error) {
	return e.svc.Login(context.Background(), LoginInput{Email: email, Password: password, ClientIP: "198.51.100.20"})
}

func TestLoginIssuesVerifiableTokenAndReusesIt(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("login")
	p := e.register(t, email, testutil.FixtureCredential())

	first, err := login(e, email, testutil.FixtureCredential())
	require.NoError(t, err)
	inner, err := common.VerifyAccessToken(first.Token, e.cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now())
	require.NoError(t, err)
	assert.True(t, common.ValidInner(inner))
	assert.Equal(t, p.ID, first.Profile.ID)
	assert.Equal(t, p.ID, first.Profile.TenantID)
	assert.Equal(t, "owner", first.Role)

	second, err := login(e, strings.ToUpper(email), testutil.FixtureCredential())
	require.NoError(t, err)
	inner2, err := common.VerifyAccessToken(second.Token, e.cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now())
	require.NoError(t, err)
	assert.Equal(t, inner, inner2, "D-10: the stored valid token is reused")

	var u entity.User
	require.NoError(t, e.raw.First(&u, "id = ?", p.ID).Error)
	require.NotNil(t, u.AccessToken)
	assert.Equal(t, inner, *u.AccessToken)
}

func TestLoginReplacesInvalidatedToken(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("inv")
	p := e.register(t, email, testutil.FixtureCredential())
	require.NoError(t, e.raw.Exec("UPDATE user SET access_token = ? WHERE id = ?", "INVALID_"+strings.Repeat("0", 32), p.ID).Error)
	res, err := login(e, email, testutil.FixtureCredential())
	require.NoError(t, err)
	inner, err := common.VerifyAccessToken(res.Token, e.cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now())
	require.NoError(t, err)
	assert.False(t, strings.HasPrefix(inner, "INVALID_"))
}

func TestParallelFirstLoginsConvergeOnOneToken(t *testing.T) {
	// Each attempt is counted before it is checked (WR-01), so the per-account cap would refuse some of
	// eight simultaneous logins; this test is about token convergence, so the cap is out of its way.
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 100 })
	email := testutil.UniqueEmail("par")
	p := e.register(t, email, testutil.FixtureCredential())
	const n = 8
	inners := make([]string, n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			res, err := login(e, email, testutil.FixtureCredential())
			if err != nil {
				return
			}
			inners[i], _ = common.VerifyAccessToken(res.Token, e.cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now())
		}()
	}
	wg.Wait()
	var u entity.User
	require.NoError(t, e.raw.First(&u, "id = ?", p.ID).Error)
	require.NotNil(t, u.AccessToken)
	for i, in := range inners {
		assert.Equal(t, *u.AccessToken, in, "login %d must return the single stored token", i)
	}
}

func TestLoginFailuresAreIndistinguishable(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("gen")
	p := e.register(t, email, testutil.FixtureCredential())
	disabled := testutil.UniqueEmail("dis")
	dp := e.register(t, disabled, testutil.FixtureCredential())
	require.NoError(t, e.raw.Exec("UPDATE user SET status = '0' WHERE id = ?", dp.ID).Error)
	_ = p

	_, errUnknown := login(e, testutil.UniqueEmail("nobody"), "wrong-password-1")
	_, errWrong := login(e, email, "wrong-password-1")
	_, errDisabled := login(e, disabled, testutil.FixtureCredential())
	for _, err := range []error{errUnknown, errWrong, errDisabled} {
		require.ErrorIs(t, err, ErrInvalidCredentials)
	}
	assert.Equal(t, errUnknown.Error(), errWrong.Error())
	assert.Equal(t, errUnknown.Error(), errDisabled.Error())
	assert.Equal(t, "Email or password is incorrect", ErrInvalidCredentials.Error())
}

func TestLoginDoesComparableWorkForUnknownAccounts(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("tim")
	e.register(t, email, testutil.FixtureCredential())
	median := func(email string) time.Duration {
		var ds []time.Duration
		for i := 0; i < 5; i++ {
			s := time.Now()
			_, _ = e.svc.Login(context.Background(), LoginInput{Email: email, Password: "wrong-password-1", ClientIP: "198.51.100." + string(rune('1'+i))})
			ds = append(ds, time.Since(s))
		}
		for i := range ds {
			for j := i + 1; j < len(ds); j++ {
				if ds[j] < ds[i] {
					ds[i], ds[j] = ds[j], ds[i]
				}
			}
		}
		return ds[2]
	}
	known := median(email)
	unknown := median(testutil.UniqueEmail("ghost"))
	assert.Greater(t, unknown, known/2, "an unknown email must pay for a hash verification (known %s, unknown %s)", known, unknown)
}

func TestLoginLockoutPerEmail(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 3 })
	email := testutil.UniqueEmail("lock")
	e.register(t, email, testutil.FixtureCredential())
	for i := 0; i < 3; i++ {
		_, err := login(e, email, "wrong-password-1")
		require.ErrorIs(t, err, ErrInvalidCredentials, "failure %d", i+1)
	}
	_, err := login(e, email, "wrong-password-1")
	var rl *RateLimitedError
	require.ErrorAs(t, err, &rl)
	assert.Greater(t, rl.RetryAfter, time.Duration(0))
	_, err = login(e, email, testutil.FixtureCredential())
	assert.ErrorAs(t, err, &rl, "the lock holds even for the right password")

	other := testutil.UniqueEmail("lock2")
	e.register(t, other, testutil.FixtureCredential())
	_, err = login(e, other, testutil.FixtureCredential())
	assert.NoError(t, err, "another email is unaffected")
}

func TestLoginLockoutPerIP(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginPerIP = 2 })
	email := testutil.UniqueEmail("ip")
	e.register(t, email, testutil.FixtureCredential())
	in := LoginInput{Email: email, Password: testutil.FixtureCredential(), ClientIP: "192.0.2.77"}
	for i := 0; i < 2; i++ {
		_, err := e.svc.Login(context.Background(), in)
		require.NoError(t, err)
	}
	_, err := e.svc.Login(context.Background(), in)
	var rl *RateLimitedError
	assert.ErrorAs(t, err, &rl)
}

func TestLoginFailsClosedWhenRedisIsDown(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("down")
	e.register(t, email, testutil.FixtureCredential())
	bad := e.cfg.Redis
	bad.Port = 1
	rd := dao.OpenRedis(bad)
	defer func() { _ = rd.Close() }()
	svc := NewAccount(e.db, NewLimiter(rd, "test-down"), e.cfg)
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	_, err := svc.Login(ctx, LoginInput{Email: email, Password: testutil.FixtureCredential(), ClientIP: "198.51.100.30"})
	assert.True(t, errors.Is(err, ErrUnavailable), "the right password must not log in while the limiter is blind: %v", err)
	_, err = svc.Register(ctx, RegisterInput{Email: testutil.UniqueEmail("down2"), Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "198.51.100.30"})
	assert.ErrorIs(t, err, ErrUnavailable)
}

// WR-01: the failure counter is reserved atomically before the password is checked, so a burst of
// parallel wrong guesses is verified at most LoginFailuresPerEmail times, against real Valkey.
func TestParallelWrongGuessesNeverExceedTheFailureCap(t *testing.T) {
	const cap, burst = 3, 24
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = cap })
	email := testutil.UniqueEmail("burst")
	e.register(t, email, testutil.FixtureCredential())
	var wrong, limited, other atomic.Int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < burst; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			_, err := login(e, email, "wrong-password-1")
			var rl *RateLimitedError
			switch {
			case errors.Is(err, ErrInvalidCredentials):
				wrong.Add(1)
			case errors.As(err, &rl):
				limited.Add(1)
			default:
				other.Add(1)
			}
		}()
	}
	close(start)
	wg.Wait()
	assert.EqualValues(t, cap, wrong.Load(), "exactly the cap of guesses reached the password check")
	assert.EqualValues(t, burst-cap, limited.Load())
	assert.Zero(t, other.Load())
}
