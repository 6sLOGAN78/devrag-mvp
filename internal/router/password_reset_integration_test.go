//go:build integration

package router

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/handler"
	"devrag/internal/server"
	"devrag/internal/service"
	"devrag/internal/testutil"
)

const (
	forgotPath = "/api/v1/auth/password/forgot/otp"
	verifyPath = "/api/v1/auth/password/forgot/otp/verify"
	resetPath  = "/api/v1/auth/password/reset"
	clientPeer = "198.51.100.9:1000"
)

var sixDigit = regexp.MustCompile(`\b\d{6}\b`)

type mailbox struct {
	mu    sync.Mutex
	mails []service.Mail
}

func (m *mailbox) Enqueue(x service.Mail) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.mails = append(m.mails, x)
	return true
}

func (m *mailbox) to(email string) []service.Mail {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []service.Mail
	for _, x := range m.mails {
		if strings.EqualFold(x.To, email) {
			out = append(out, x)
		}
	}
	return out
}

func (m *mailbox) total() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.mails)
}

func (m *mailbox) lastCode(t *testing.T, email string) string {
	t.Helper()
	got := m.to(email)
	require.NotEmpty(t, got, "no mail for the account")
	return sixDigit.FindString(got[len(got)-1].Body)
}

type resetRig struct {
	*accountRig
	box *mailbox
}

func newResetRig(t *testing.T, mutate func(*server.Config), redisDown bool) *resetRig {
	t.Helper()
	cfg := testutil.RequireDB(t)
	cfg.RateLimit.RegisterPerIP = 1000
	cfg.RateLimit.LoginPerIP = 1000
	cfg.RateLimit.OTPPerIPPerHour = 1000
	cfg.RateLimit.OTPPerEmailPerHour = 1000
	cfg.Auth.RegisterEnabled = true
	cfg.Auth.OTPTTL = time.Minute
	if mutate != nil {
		mutate(&cfg)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db, err := dao.OpenDB(ctx, cfg.MySQL)
	require.NoError(t, err)
	rcfg := cfg.Redis
	if redisDown {
		rcfg.Port = 1
	}
	rd := dao.OpenRedis(rcfg)
	raw, err := gorm.Open(mysql.Open(dao.DSN(cfg.MySQL)), &gorm.Config{Logger: logger.Discard})
	require.NoError(t, err)
	core, logs := observer.New(zapcore.DebugLevel)
	prefix := "test-" + testutil.UniqueName("pr")
	lim := service.NewLimiter(rd, prefix)
	box := &mailbox{}
	sys := service.NewSystem(db, rd, db).WithRegisterEnabled(true)
	acct := service.NewAccount(db, lim, cfg)
	auth := service.NewAuth(db, cfg.Security.SecretKey, cfg.Security.TokenMaxAge)
	otp := service.NewOTP(rd, prefix, cfg.Security.SecretKey, cfg.Auth.OTPTTL)
	pr := service.NewPasswordReset(db, lim, otp, box, cfg)
	e := NewEngine(cfg, zap.New(common.WrapRedacting(core)), handler.NewSystem(sys),
		WithAuth(auth), WithAccount(handler.NewAccount(acct, cfg.Security.TokenMaxAge)), WithSession(handler.NewUser(auth)),
		WithPasswordReset(handler.NewPasswordReset(pr)))
	rig := &accountRig{engine: e, cfg: cfg, logs: logs, raw: raw, db: db}
	t.Cleanup(func() {
		for _, em := range rig.emails {
			var id string
			if raw.Raw("SELECT id FROM user WHERE email = ?", em).Scan(&id).Error == nil && id != "" {
				for _, q := range []string{"DELETE FROM tenant_llm WHERE tenant_id = ?", "DELETE FROM user_tenant WHERE user_id = ?", "DELETE FROM tenant WHERE id = ?", "DELETE FROM user WHERE id = ?"} {
					_ = raw.Exec(q, id).Error
				}
			}
		}
		_ = db.Close()
		_ = rd.Close()
	})
	return &resetRig{accountRig: rig, box: box}
}

type reply struct {
	Code    int            `json:"code"`
	Message string         `json:"message"`
	Data    map[string]any `json:"data"`
}

func parse(t *testing.T, w *httptest.ResponseRecorder) reply {
	t.Helper()
	var r reply
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &r), w.Body.String())
	return r
}

func (r *resetRig) forgot(email, remote string, hdr map[string]string) *httptest.ResponseRecorder {
	return r.post(forgotPath, map[string]string{"email": email}, remote, hdr)
}

func (r *resetRig) newAccount(t *testing.T, prefix string) session {
	t.Helper()
	return r.signUp(t, prefix)
}

func TestForgotOTPIsByteIdenticalForRealAndUnknownEmails(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "real")
	real := r.forgot(s.email, clientPeer, nil)
	ghost := r.forgot(testutil.UniqueEmail("ghost"), clientPeer, nil)
	require.Equal(t, http.StatusOK, real.Code, real.Body.String())
	assert.Equal(t, real.Code, ghost.Code)
	assert.Equal(t, real.Body.String(), ghost.Body.String(), "same body, byte for byte")
	assert.Equal(t, real.Header().Get("Content-Type"), ghost.Header().Get("Content-Type"))
	assert.Equal(t, real.Header().Get("Cache-Control"), ghost.Header().Get("Cache-Control"))
	assert.Empty(t, real.Header().Values("Set-Cookie"))
	assert.Empty(t, ghost.Header().Values("Set-Cookie"))
	assert.Len(t, r.box.to(s.email), 1)
	assert.Equal(t, 1, r.box.total(), "nothing was sent for the unknown address")
	assert.NotContains(t, real.Body.String(), s.email)
}

func TestForgotOTPLatencyDoesNotRevealExistence(t *testing.T) {
	r := newResetRig(t, nil, false)
	var known, unknown []time.Duration
	for i := 0; i < 5; i++ {
		s := r.newAccount(t, "lat")
		began := time.Now()
		w := r.forgot(s.email, clientPeer, nil)
		known = append(known, time.Since(began))
		require.Equal(t, http.StatusOK, w.Code)
		began = time.Now()
		w = r.forgot(testutil.UniqueEmail("lat-ghost"), clientPeer, nil)
		unknown = append(unknown, time.Since(began))
		require.Equal(t, http.StatusOK, w.Code)
	}
	median := func(d []time.Duration) time.Duration {
		sort.Slice(d, func(i, j int) bool { return d[i] < d[j] })
		return d[len(d)/2]
	}
	diff := median(known) - median(unknown)
	if diff < 0 {
		diff = -diff
	}
	assert.Less(t, diff, 150*time.Millisecond, "known %v, unknown %v", median(known), median(unknown))
}

func TestForgotOTPMalformedEmailIsTheSame400ForEveryInput(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "mal")
	var bodies []string
	for _, bad := range []string{"", "nope", s.email + "\r\nBcc: x@example.test", "Alice <" + s.email + ">", "a@b"} {
		w := r.forgot(bad, clientPeer, nil)
		require.Equal(t, http.StatusBadRequest, w.Code, "%.30q", bad)
		assert.EqualValues(t, 101, parse(t, w).Code)
		bodies = append(bodies, w.Body.String())
	}
	for _, b := range bodies[1:] {
		assert.Equal(t, bodies[0], b)
	}
	assert.Equal(t, 400, r.post(forgotPath, "{not json", clientPeer, nil).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.post(forgotPath, `{"email":"`+strings.Repeat("a", 2000)+`"}`, clientPeer, nil).Code)
	assert.Equal(t, 0, r.box.total())
	req := httptest.NewRequest(http.MethodGet, forgotPath, nil)
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	assert.Equal(t, http.StatusMethodNotAllowed, w.Code)
}

func TestForgotOTPMailGoesOnlyToTheStoredAddress(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "to")
	w := r.post(forgotPath, map[string]any{"email": s.email, "to": "attacker@example.test", "cc": "attacker@example.test", "recipient": "attacker@example.test", "subject": "pwned"}, clientPeer, nil)
	require.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, 1, r.box.total())
	require.Len(t, r.box.to(s.email), 1)
	m := r.box.to(s.email)[0]
	assert.Equal(t, "Your devRag password reset code", m.Subject)
	assert.NotContains(t, m.Body, "attacker")
	assert.NotContains(t, m.Body, "pwned")
}

func TestForgotOTPIsPublicAndIgnoresCookiesAndOrigin(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "pub")
	plain := r.forgot(s.email, clientPeer, nil)
	require.Equal(t, http.StatusOK, plain.Code)
	r2 := r.forgot(testutil.UniqueEmail("pub2"), clientPeer, map[string]string{"Cookie": "ragflow_auth=" + s.token, "Origin": "https://evil.example", "Authorization": "Bearer not-a-token"})
	assert.Equal(t, http.StatusOK, r2.Code, "a public route never consults credentials")
	assert.Equal(t, plain.Body.String(), r2.Body.String())
	assert.Empty(t, r2.Header().Values("Set-Cookie"))
	login := r.post("/api/v1/auth/login", map[string]string{"email": s.email, "password": testutil.FixtureCredential()}, clientPeer, map[string]string{"Origin": "https://evil.example"})
	assert.NotEqual(t, http.StatusForbidden, login.Code, "login has no Origin check, the reset routes behave the same")
	for _, p := range []string{verifyPath, resetPath} {
		w := r.post(p, map[string]string{"email": s.email}, clientPeer, map[string]string{"Origin": "https://evil.example"})
		assert.NotEqual(t, http.StatusUnauthorized, w.Code, p)
		assert.NotEqual(t, http.StatusForbidden, w.Code, p)
		assert.Empty(t, w.Header().Values("Set-Cookie"), p)
	}
}

func TestEmailIntervalLimitReturns429WithRetryAfter(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "iv")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	w := r.forgot(s.email, clientPeer, nil)
	require.Equal(t, http.StatusTooManyRequests, w.Code)
	ra, err := strconv.Atoi(w.Header().Get("Retry-After"))
	require.NoError(t, err)
	assert.Greater(t, ra, 0)
	assert.LessOrEqual(t, ra, 60)
	ghost := testutil.UniqueEmail("iv-ghost")
	require.Equal(t, http.StatusOK, r.forgot(ghost, clientPeer, nil).Code)
	gw := r.forgot(ghost, clientPeer, nil)
	assert.Equal(t, http.StatusTooManyRequests, gw.Code, "an unknown email consumes the same limit")
	assert.Equal(t, w.Body.String(), gw.Body.String())
	assert.Equal(t, 1, r.box.total(), "a limited request sends nothing")
}

func TestEmailHourlyLimitReturns429(t *testing.T) {
	r := newResetRig(t, func(c *server.Config) {
		c.RateLimit.OTPEmailIntervalSeconds = 1
		c.RateLimit.OTPPerEmailPerHour = 2
		c.RateLimit.OTPWindowSeconds = 3600
	}, false)
	s := r.newAccount(t, "hr")
	accepted := 0
	var last *httptest.ResponseRecorder
	err := testutil.WaitUntil(context.Background(), 60*time.Second, 200*time.Millisecond, func() bool {
		last = r.forgot(s.email, clientPeer, nil)
		if last.Code == http.StatusOK {
			accepted++
			return accepted > 2
		}
		ra, _ := strconv.Atoi(last.Header().Get("Retry-After"))
		return ra > 60 // the hourly window, not the one-second interval
	})
	require.NoError(t, err)
	assert.Equal(t, 2, accepted, "exactly the configured number inside the window")
	assert.Equal(t, http.StatusTooManyRequests, last.Code)
	assert.Len(t, r.box.to(s.email), 2)
}

func TestIPLimitIsPerClientAddressAndIgnoresSpoofedHeaders(t *testing.T) {
	r := newResetRig(t, func(c *server.Config) { c.RateLimit.OTPPerIPPerHour = 3 }, false)
	for i := 0; i < 3; i++ {
		require.Equal(t, http.StatusOK, r.forgot(testutil.UniqueEmail("ip"), "198.51.100.77:1", nil).Code)
	}
	w := r.forgot(testutil.UniqueEmail("ip"), "198.51.100.77:2", nil)
	assert.Equal(t, http.StatusTooManyRequests, w.Code)
	assert.NotEmpty(t, w.Header().Get("Retry-After"))
	for name, hdr := range map[string]map[string]string{
		"x-forwarded-for":       {"X-Forwarded-For": "203.0.113.200"},
		"x-real-ip from remote": {"X-Real-IP": "203.0.113.201"},
	} {
		assert.Equal(t, http.StatusTooManyRequests, r.forgot(testutil.UniqueEmail("ip"), "198.51.100.77:3", hdr).Code, name)
	}
	assert.Equal(t, http.StatusOK, r.forgot(testutil.UniqueEmail("ip"), "198.51.100.78:1", nil).Code, "another address is unaffected")
	assert.Equal(t, http.StatusOK, r.forgot(testutil.UniqueEmail("ip"), "127.0.0.1:5", map[string]string{"X-Real-IP": "203.0.113.55"}).Code, "a loopback proxy may name the client")
}

func TestKnownAndUnknownRequestsBothConsumeTheIPLimit(t *testing.T) {
	r := newResetRig(t, func(c *server.Config) { c.RateLimit.OTPPerIPPerHour = 2 }, false)
	s := r.newAccount(t, "mix")
	require.Equal(t, http.StatusOK, r.forgot(s.email, "198.51.100.90:1", nil).Code)
	require.Equal(t, http.StatusOK, r.forgot(testutil.UniqueEmail("mix-ghost"), "198.51.100.90:1", nil).Code)
	assert.Equal(t, http.StatusTooManyRequests, r.forgot(testutil.UniqueEmail("mix-ghost"), "198.51.100.90:1", nil).Code)
}

func TestRedisOutageFailsClosedWithoutSending(t *testing.T) {
	r := newResetRig(t, nil, true)
	for _, p := range []string{forgotPath, verifyPath, resetPath} {
		w := r.post(p, map[string]string{"email": testutil.UniqueEmail("down"), "otp": "123456", "new_password": "reset-new-pass-0003", "reset_ticket": "x"}, clientPeer, nil)
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, p)
		assert.EqualValues(t, 503, parse(t, w).Code)
		assert.NotContains(t, w.Body.String(), "redis")
		assert.NotContains(t, w.Body.String(), "dial")
	}
	assert.Equal(t, 0, r.box.total(), "never a send without the limiter")
}

func TestFullResetThroughHTTP(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "http")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	code := r.box.lastCode(t, s.email)

	vw := r.post(verifyPath, map[string]string{"email": s.email, "otp": code}, clientPeer, nil)
	require.Equal(t, http.StatusOK, vw.Code, vw.Body.String())
	ticket, _ := parse(t, vw).Data["reset_ticket"].(string)
	require.GreaterOrEqual(t, len(ticket), 22)
	assert.Empty(t, vw.Header().Values("Set-Cookie"))
	assert.Equal(t, "no-store", vw.Header().Get("Cache-Control"))

	rw := r.post(resetPath, map[string]string{"email": s.email, "reset_ticket": ticket, "new_password": newCredential}, clientPeer, nil)
	require.Equal(t, http.StatusOK, rw.Code, rw.Body.String())
	assert.Empty(t, rw.Header().Values("Set-Cookie"), "reset creates no session and sets no cookie")
	assert.NotContains(t, rw.Body.String(), newCredential)
	assert.NotContains(t, rw.Body.String(), ticket)

	assert.Equal(t, http.StatusUnauthorized, r.call(http.MethodGet, "/v1/user/info", s.token, nil).Code, "the old token is dead on Go")
	assert.Equal(t, http.StatusUnauthorized, r.post("/api/v1/auth/login", map[string]string{"email": s.email, "password": testutil.FixtureCredential()}, clientPeer, nil).Code)
	lw := r.post("/api/v1/auth/login", map[string]string{"email": s.email, "password": newCredential}, clientPeer, nil)
	require.Equal(t, http.StatusOK, lw.Code)
	fresh, _ := parse(t, lw).Data["token"].(string)
	assert.Equal(t, http.StatusOK, r.call(http.MethodGet, "/v1/user/info", fresh, nil).Code)
	assert.Equal(t, http.StatusBadRequest, r.post(resetPath, map[string]string{"email": s.email, "reset_ticket": ticket, "new_password": "yet-another-pass-9"}, clientPeer, nil).Code, "replay fails")
}

func TestResetWithTheDocumentedOTPFieldAndGenericFailures(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "docs")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	code := r.box.lastCode(t, s.email)
	wrong := "000000"
	if code == wrong {
		wrong = "000001"
	}
	w := r.post(resetPath, map[string]string{"email": s.email, "otp": wrong, "new_password": newCredential}, clientPeer, nil)
	assert.Equal(t, http.StatusBadRequest, w.Code)
	short := r.post(resetPath, map[string]string{"email": s.email, "otp": code, "new_password": "short"}, clientPeer, nil)
	assert.Equal(t, http.StatusBadRequest, short.Code)
	assert.Contains(t, parse(t, short).Message, "8")
	w = r.post(resetPath, map[string]string{"email": s.email, "otp": code, "new_password": newCredential}, clientPeer, nil)
	assert.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assert.Equal(t, http.StatusBadRequest, r.post(resetPath, map[string]string{"email": s.email, "new_password": newCredential}, clientPeer, nil).Code)
}

func TestVerifyFailuresAreIdenticalForRealAndUnknownEmails(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "vf")
	ghost := testutil.UniqueEmail("vf-ghost")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	require.Equal(t, http.StatusOK, r.forgot(ghost, clientPeer, nil).Code)
	code := r.box.lastCode(t, s.email)
	wrong := "000000"
	if code == wrong {
		wrong = "000001"
	}
	for i := 1; i <= 7; i++ {
		a := r.post(verifyPath, map[string]string{"email": s.email, "otp": wrong}, clientPeer, nil)
		b := r.post(verifyPath, map[string]string{"email": ghost, "otp": wrong}, clientPeer, nil)
		c := r.post(verifyPath, map[string]string{"email": testutil.UniqueEmail("never-asked"), "otp": wrong}, clientPeer, nil)
		require.Equal(t, http.StatusBadRequest, a.Code, "attempt %d", i)
		assert.Equal(t, a.Code, b.Code)
		assert.Equal(t, a.Body.String(), b.Body.String(), "attempt %d: a real and a decoy record answer alike, including after the cap", i)
		assert.Equal(t, a.Body.String(), c.Body.String())
	}
	w := r.post(verifyPath, map[string]string{"email": s.email, "otp": code}, clientPeer, nil)
	assert.Equal(t, http.StatusBadRequest, w.Code, "five wrong tries destroyed the real code")
}

func TestResetBodyIsCappedAndIgnoresUnknownFields(t *testing.T) {
	r := newResetRig(t, nil, false)
	big := `{"email":"a@example.test","new_password":"` + strings.Repeat("x", 2000) + `"}`
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.post(resetPath, big, clientPeer, nil).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.post(verifyPath, big, clientPeer, nil).Code)
	s := r.newAccount(t, "mass")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	before := r.user(t, s.id)
	w := r.post(resetPath, map[string]any{"email": s.email, "otp": r.box.lastCode(t, s.email), "new_password": newCredential, "id": "other", "is_superuser": true, "access_token": "keep", "status": "0"}, clientPeer, nil)
	require.Equal(t, http.StatusOK, w.Code)
	after := r.user(t, s.id)
	assert.Equal(t, before.ID, after.ID)
	assert.Equal(t, before.IsSuperuser, after.IsSuperuser)
	assert.Equal(t, before.Status, after.Status)
	assert.True(t, strings.HasPrefix(*after.AccessToken, "INVALID_"))
}

func TestNoLogLineCarriesTheCodeTicketPasswordOrEmail(t *testing.T) {
	r := newResetRig(t, nil, false)
	s := r.newAccount(t, "log")
	require.Equal(t, http.StatusOK, r.forgot(s.email, clientPeer, nil).Code)
	code := r.box.lastCode(t, s.email)
	r.post(verifyPath, map[string]string{"email": s.email, "otp": "000000"}, clientPeer, nil)
	vw := r.post(verifyPath, map[string]string{"email": s.email, "otp": code}, clientPeer, nil)
	ticket, _ := parse(t, vw).Data["reset_ticket"].(string)
	require.NotEmpty(t, ticket)
	r.post(resetPath, map[string]string{"email": s.email, "reset_ticket": ticket, "new_password": newCredential}, clientPeer, nil)
	r.forgot(testutil.UniqueEmail("ghost-log"), clientPeer, nil)

	var sb strings.Builder
	for _, e := range r.logs.All() {
		sb.WriteString(e.Message)
		sb.WriteString(fmt.Sprint(e.ContextMap()))
		sb.WriteString("\n")
	}
	logs := sb.String()
	require.NotEmpty(t, logs)
	for name, secret := range map[string]string{"code": code, "ticket": ticket, "new password": newCredential, "email": s.email} {
		assert.NotContains(t, strings.ToLower(logs), strings.ToLower(secret), name)
	}
}
