//go:build integration

package router

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
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

type accountRig struct {
	engine *gin.Engine
	cfg    server.Config
	logs   *observer.ObservedLogs
	raw    *gorm.DB
	emails []string
	db     *dao.DB
}

func newAccountRig(t *testing.T, mutate func(*server.Config), redisDown bool) *accountRig {
	t.Helper()
	cfg := testutil.RequireDB(t)
	cfg.RateLimit.RegisterPerIP = 1000
	cfg.RateLimit.LoginPerIP = 1000
	cfg.Auth.RegisterEnabled = true
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
	sys := service.NewSystem(db, rd, db).WithRegisterEnabled(cfg.Auth.RegisterEnabled)
	acct := service.NewAccount(db, service.NewLimiter(rd, "test-"+testutil.UniqueName("http")), cfg)
	auth := service.NewAuth(db, cfg.Security.SecretKey, cfg.Security.TokenMaxAge)
	limiter := service.NewLimiter(rd, "test-"+testutil.UniqueName("prof"))
	e := NewEngine(cfg, zap.New(common.WrapRedacting(core)), handler.NewSystem(sys),
		WithAuth(auth), WithAccount(handler.NewAccount(acct, cfg.Security.TokenMaxAge)), WithSession(handler.NewUser(auth)),
		WithProfile(handler.NewSettings(service.NewUser(db, limiter, cfg)), handler.NewTenant(service.NewTenant(db))))
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
	return rig
}

func (r *accountRig) post(path string, body any, remote string, hdr map[string]string) *httptest.ResponseRecorder {
	var raw []byte
	switch b := body.(type) {
	case string:
		raw = []byte(b)
	default:
		raw, _ = json.Marshal(b)
	}
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	req.RemoteAddr = remote
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	return w
}

func (r *accountRig) register(t *testing.T, email string) {
	t.Helper()
	r.emails = append(r.emails, email)
	w := r.post("/api/v1/users", map[string]string{"email": email, "password": testutil.FixtureCredential(), "nickname": "nick"}, "198.51.100.9:1000", nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
}

func TestRegisterHandlerReturnsSafeDTO(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email := testutil.UniqueEmail("h")
	r.emails = append(r.emails, email)
	w := r.post("/api/v1/users", map[string]string{"email": email, "password": testutil.FixtureCredential(), "nickname": "nick"}, "198.51.100.9:1000", nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))
	var env struct {
		Code int            `json:"code"`
		Data map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	assert.Equal(t, 0, env.Code)
	assert.Equal(t, env.Data["id"], env.Data["tenant_id"])
	for _, banned := range []string{"password", "access_token", "$", testutil.FixtureCredential()} {
		assert.NotContains(t, w.Body.String(), banned)
	}
}

func TestRegisterHandlerRejectsBadBodies(t *testing.T) {
	r := newAccountRig(t, nil, false)
	big := `{"email":"a@example.test","password":"` + strings.Repeat("x", 2000) + `","nickname":"n"}`
	w := r.post("/api/v1/users", big, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusRequestEntityTooLarge, w.Code)
	assert.EqualValues(t, 400, decode(t, w).Code)
	assert.Equal(t, http.StatusBadRequest, r.post("/api/v1/users", "{not json", "198.51.100.9:1000", nil).Code)
	w = r.post("/api/v1/users", map[string]string{"email": "bad", "password": testutil.FixtureCredential(), "nickname": "n"}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.EqualValues(t, 101, decode(t, w).Code)
	assert.NotContains(t, w.Body.String(), testutil.FixtureCredential())
}

func TestRegisterDuplicateIsConflict(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email := testutil.UniqueEmail("dup")
	r.register(t, email)
	w := r.post("/api/v1/users", map[string]string{"email": email, "password": testutil.FixtureCredential(), "nickname": "n"}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusConflict, w.Code)
	assert.EqualValues(t, 409, decode(t, w).Code)
}

func TestRegistrationDisabledRefusesAndConfigReportsIt(t *testing.T) {
	r := newAccountRig(t, func(c *server.Config) { c.Auth.RegisterEnabled = false }, false)
	email := testutil.UniqueEmail("off")
	r.emails = append(r.emails, email)
	w := r.post("/api/v1/users", map[string]string{"email": email, "password": testutil.FixtureCredential(), "nickname": "n"}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusForbidden, w.Code)
	env := decode(t, w)
	assert.EqualValues(t, 403, env.Code)
	assert.Contains(t, strings.ToLower(env.Message), "registration")
	cw := do(r.engine, http.MethodGet, "/api/v1/system/config", nil)
	assert.Contains(t, cw.Body.String(), `"register_enabled":false`)
}

func TestConfigReportsRegisterEnabledTrue(t *testing.T) {
	r := newAccountRig(t, nil, false)
	assert.Contains(t, do(r.engine, http.MethodGet, "/api/v1/system/config", nil).Body.String(), `"register_enabled":true`)
}

func TestLoginSetsCookieAndReturnsToken(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email := testutil.UniqueEmail("cookie")
	r.register(t, email)
	w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var env struct {
		Data struct {
			Token    string         `json:"token"`
			TenantID string         `json:"tenant_id"`
			Role     string         `json:"role"`
			User     map[string]any `json:"user"`
			LLMID    *string        `json:"llm_id"`
			EmbdID   *string        `json:"embd_id"`
			RerankID *string        `json:"rerank_id"`
		} `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	_, err := common.VerifyAccessToken(env.Data.Token, r.cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now())
	require.NoError(t, err)
	assert.Equal(t, "owner", env.Data.Role)
	assert.NotEmpty(t, env.Data.TenantID)
	assert.NotNil(t, env.Data.LLMID)
	assert.NotNil(t, env.Data.EmbdID)
	assert.NotNil(t, env.Data.RerankID)
	assert.Equal(t, email, env.Data.User["email"])
	body := w.Body.String()
	for _, banned := range []string{`"password"`, `"access_token"`, "pbkdf2", "$"} {
		assert.NotContains(t, body, banned)
	}

	cookies := w.Result().Cookies()
	require.Len(t, cookies, 1)
	c := cookies[0]
	assert.Equal(t, "ragflow_auth", c.Name)
	assert.Equal(t, env.Data.Token, c.Value)
	assert.True(t, c.HttpOnly)
	assert.Equal(t, http.SameSiteLaxMode, c.SameSite)
	assert.Equal(t, "/", c.Path)
	assert.Equal(t, 2592000, c.MaxAge)
	assert.False(t, c.Secure, "plain HTTP request")

	// R-114: X-Forwarded-Proto is trusted only from a loopback peer (the Nginx in the same container).
	w = r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, "127.0.0.1:1000", map[string]string{"X-Forwarded-Proto": "https"})
	require.Equal(t, http.StatusOK, w.Code)
	assert.True(t, w.Result().Cookies()[0].Secure, "Secure when the proxy on loopback reports TLS")

	w = r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", map[string]string{"X-Forwarded-Proto": "https"})
	require.Equal(t, http.StatusOK, w.Code)
	assert.False(t, w.Result().Cookies()[0].Secure, "a forwarded scheme from a non-loopback peer is ignored")
}

func TestLoginFailuresAreByteIdentical(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email := testutil.UniqueEmail("same")
	r.register(t, email)
	dis := testutil.UniqueEmail("dis")
	r.register(t, dis)
	require.NoError(t, r.raw.Exec("UPDATE user SET status = '0' WHERE email = ?", dis).Error)
	a := r.post("/api/v1/auth/login", map[string]string{"email": testutil.UniqueEmail("ghost"), "password": "wrong-password-1"}, "198.51.100.9:1000", nil)
	b := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": "wrong-password-1"}, "198.51.100.9:1000", nil)
	c := r.post("/api/v1/auth/login", map[string]string{"email": dis, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	for _, w := range []*httptest.ResponseRecorder{a, b, c} {
		assert.Equal(t, http.StatusUnauthorized, w.Code)
		assert.Empty(t, w.Result().Cookies())
	}
	assert.Equal(t, a.Body.String(), b.Body.String())
	assert.Equal(t, a.Body.String(), c.Body.String())
	assert.Contains(t, a.Body.String(), "Email or password is incorrect")
}

func TestLoginLockoutReturns429WithRetryAfter(t *testing.T) {
	r := newAccountRig(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 5 }, false)
	email := testutil.UniqueEmail("lock")
	r.register(t, email)
	for i := 1; i <= 5; i++ {
		w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": "wrong-password-1"}, "198.51.100.9:1000", nil)
		require.Equal(t, http.StatusUnauthorized, w.Code, "failure %d", i)
	}
	w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": "wrong-password-1"}, "198.51.100.9:1000", nil)
	require.Equal(t, http.StatusTooManyRequests, w.Code)
	assert.EqualValues(t, 400, decode(t, w).Code, "429 maps to envelope code 400 (R-63)")
	assert.Regexp(t, `^\d+$`, w.Header().Get("Retry-After"))
}

func TestSpoofedForwardedHeadersDoNotEvadePerIPLimit(t *testing.T) {
	r := newAccountRig(t, func(c *server.Config) { c.RateLimit.LoginPerIP = 3 }, false)
	email := testutil.UniqueEmail("spoof")
	r.register(t, email)
	peer := "198.51.100.200:4000"
	statuses := []int{}
	for i := 0; i < 5; i++ {
		w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, peer, map[string]string{
			"X-Forwarded-For": "192.0.2." + string(rune('1'+i)), "X-Real-IP": "203.0.113." + string(rune('1'+i)),
		})
		statuses = append(statuses, w.Code)
	}
	assert.Equal(t, []int{200, 200, 200, 429, 429}, statuses, "rotating spoofed headers from a public peer must not reset the counter")
}

func TestFailsClosedWhenRedisIsDown(t *testing.T) {
	r := newAccountRig(t, nil, true)
	w := r.post("/api/v1/users", map[string]string{"email": testutil.UniqueEmail("down"), "password": testutil.FixtureCredential(), "nickname": "n"}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.EqualValues(t, 503, decode(t, w).Code)
	w = r.post("/api/v1/auth/login", map[string]string{"email": "a@example.test", "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	for _, leak := range []string{"redis", "dial", "127.0.0.1", "tcp"} {
		assert.NotContains(t, strings.ToLower(w.Body.String()), leak)
	}
}

func TestRequestLogNeverContainsBodiesOrPasswords(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email := testutil.UniqueEmail("log")
	r.register(t, email)
	r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	r.post("/api/v1/auth/login", map[string]string{"email": email, "password": "wrong-password-1"}, "198.51.100.9:1000", nil)
	require.NotEmpty(t, r.logs.All())
	for _, e := range r.logs.All() {
		line := e.Message
		for _, f := range e.Context {
			line += " " + f.Key + "=" + f.String
		}
		assert.NotContains(t, line, testutil.FixtureCredential())
		assert.NotContains(t, line, "wrong-password-1")
		assert.NotContains(t, line, "pbkdf2")
	}
}
