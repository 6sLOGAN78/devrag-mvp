package handler_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/handler"
	"devrag/internal/service"
)

func init() { gin.SetMode(gin.TestMode) }

const (
	testSecret   = "test-only-secret-key-not-real-0001"
	goodInner    = "0123456789abcdef0123456789abcdef"
	unauthorized = `{"code":401,"message":"unauthorized","data":null}`
	unavailable  = `{"code":503,"message":"service unavailable","data":null}`
	forbidden    = `{"code":403,"message":"forbidden","data":null}`
)

// memStore is a unit-tier AuthStore keyed by stored access token.
type memStore struct {
	byToken map[string]*entity.User
	err     error
	lookups int
	set     map[string]string
}

func (m *memStore) FindUserByAccessToken(_ context.Context, token string) (*entity.User, error) {
	m.lookups++
	if m.err != nil {
		return nil, m.err
	}
	if u, ok := m.byToken[token]; ok {
		return u, nil
	}
	// A real MySQL equality is case and trailing-space insensitive; emulate the collation.
	for k, u := range m.byToken {
		if strings.EqualFold(strings.TrimRight(k, " "), strings.TrimRight(token, " ")) {
			return u, nil
		}
	}
	return nil, dao.ErrNotFound
}

func (m *memStore) FindUserByID(_ context.Context, id string) (*entity.User, error) {
	for _, u := range m.byToken {
		if u.ID == id {
			return u, nil
		}
	}
	return nil, dao.ErrNotFound
}

func (m *memStore) FindOwnMembership(_ context.Context, userID string) (*entity.UserTenant, error) {
	return &entity.UserTenant{UserID: userID, TenantID: userID, Role: "owner"}, nil
}

func (m *memStore) FindTenant(_ context.Context, id string) (*entity.Tenant, error) {
	name := "Kingdom"
	return &entity.Tenant{ID: id, Name: &name}, nil
}

func (m *memStore) SetAccessToken(_ context.Context, userID, token string) error {
	if m.set == nil {
		m.set = map[string]string{}
	}
	m.set[userID] = token
	return nil
}

func ptr(s string) *string { return &s }

func newStore() *memStore {
	return &memStore{byToken: map[string]*entity.User{
		goodInner: {ID: "u1", Email: "u1@example.test", Nickname: "n", AccessToken: ptr(goodInner), Status: ptr("1")},
	}}
}

func sign(t *testing.T, inner, secret string, at time.Time) string {
	t.Helper()
	tok, err := common.DumpAccessToken(inner, secret, at)
	require.NoError(t, err)
	return tok
}

func rig(t *testing.T, store *memStore, origins ...string) *gin.Engine {
	t.Helper()
	svc := service.NewAuth(store, testSecret, common.AccessTokenMaxAge)
	e := gin.New()
	e.Use(handler.AuthGate(svc, origins))
	ok := func(c *gin.Context) {
		p, _ := handler.PrincipalFrom(c)
		common.OK(c, map[string]string{"user": p.UserID, "tenant": p.TenantID, "role": p.Role})
	}
	e.GET("/v1/user/info", ok)
	e.POST("/v1/user/setting", ok)
	e.GET("/health", ok)
	e.NoRoute(func(c *gin.Context) { common.Fail(c, http.StatusNotFound, common.CodeNotFound, "not found") })
	e.NoMethod(func(c *gin.Context) {
		common.Fail(c, http.StatusMethodNotAllowed, common.CodeMethodNotAllowed, "method not allowed")
	})
	e.HandleMethodNotAllowed = true
	return e
}

func call(e *gin.Engine, method, path string, hdr map[string]string, cookie string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, nil)
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	if cookie != "" {
		req.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: cookie})
	}
	w := httptest.NewRecorder()
	e.ServeHTTP(w, req)
	return w
}

func bearer(tok string) map[string]string { return map[string]string{"Authorization": "Bearer " + tok} }

func TestGateAcceptsBearerRawAndCookie(t *testing.T) {
	tok := sign(t, goodInner, testSecret, time.Now())
	e := rig(t, newStore())
	for name, w := range map[string]*httptest.ResponseRecorder{
		"bearer": call(e, "GET", "/v1/user/info", bearer(tok), ""),
		"raw":    call(e, "GET", "/v1/user/info", map[string]string{"Authorization": tok}, ""),
		"cookie": call(e, "GET", "/v1/user/info", nil, tok),
	} {
		assert.Equal(t, http.StatusOK, w.Code, name)
		assert.Contains(t, w.Body.String(), `"user":"u1"`, name)
		assert.Contains(t, w.Body.String(), `"role":"owner"`, name)
	}
}

func TestGateBadTokenClassesAre401WithoutDBLookup(t *testing.T) {
	now := time.Now()
	good := sign(t, goodInner, testSecret, now)
	classes := map[string]string{
		"empty":           "",
		"whitespace":      "   ",
		"31 chars":        sign(t, strings.Repeat("a", 31), testSecret, now),
		"INVALID_ prefix": sign(t, "INVALID_"+goodInner, testSecret, now),
		"expired":         sign(t, goodInner, testSecret, now.Add(-common.AccessTokenMaxAge-time.Hour)),
		"future dated":    sign(t, goodInner, testSecret, now.Add(48*time.Hour)),
		"tampered":        good[:len(good)-2] + "AA",
		"wrong secret":    sign(t, goodInner, "another-test-only-secret-key-0002", now),
		"not a token":     "not-a-token",
		"huge":            strings.Repeat("a", 5000),
	}
	for name, tok := range classes {
		store := newStore()
		w := call(rig(t, store), "GET", "/v1/user/info", bearer(tok), "")
		assert.Equal(t, http.StatusUnauthorized, w.Code, name)
		assert.Equal(t, unauthorized, w.Body.String(), name)
		assert.Zero(t, store.lookups, "%s must not reach the database", name)
	}
}

func TestGateRejectsStaleDisabledAndCaseVariantTokens(t *testing.T) {
	tok := sign(t, goodInner, testSecret, time.Now())

	rotated := newStore()
	rotated.byToken = map[string]*entity.User{"ffffffffffffffffffffffffffffffff": {ID: "u1", AccessToken: ptr("ffffffffffffffffffffffffffffffff"), Status: ptr("1")}}
	assert.Equal(t, http.StatusUnauthorized, call(rig(t, rotated), "GET", "/v1/user/info", bearer(tok), "").Code, "no row for the inner value")

	disabled := newStore()
	disabled.byToken[goodInner].Status = ptr("0")
	assert.Equal(t, http.StatusUnauthorized, call(rig(t, disabled), "GET", "/v1/user/info", bearer(tok), "").Code, "status 0")

	nullStatus := newStore()
	nullStatus.byToken[goodInner].Status = nil
	assert.Equal(t, http.StatusUnauthorized, call(rig(t, nullStatus), "GET", "/v1/user/info", bearer(tok), "").Code, "null status")

	// The database collation matches the upper-case inner value to the lower-case row; the service must not.
	upper := newStore()
	upper.byToken = map[string]*entity.User{strings.ToUpper(goodInner): {ID: "u1", AccessToken: ptr(strings.ToUpper(goodInner)), Status: ptr("1")}}
	assert.Equal(t, http.StatusUnauthorized, call(rig(t, upper), "GET", "/v1/user/info", bearer(tok), "").Code, "case-variant stored token")

	rewritten := newStore()
	rewritten.byToken = map[string]*entity.User{"INVALID_" + goodInner: {ID: "u1", AccessToken: ptr("INVALID_" + goodInner), Status: ptr("1")}}
	assert.Equal(t, http.StatusUnauthorized, call(rig(t, rewritten), "GET", "/v1/user/info", bearer(tok), "").Code, "logged-out row")
}

func TestHeaderWinsOverCookie(t *testing.T) {
	good := sign(t, goodInner, testSecret, time.Now())
	e := rig(t, newStore())
	assert.Equal(t, http.StatusUnauthorized, call(e, "GET", "/v1/user/info", bearer("garbage"), good).Code, "a bad header is not rescued by a good cookie")
	assert.Equal(t, http.StatusOK, call(e, "GET", "/v1/user/info", bearer(good), "garbage").Code, "a bad cookie is ignored when the header is valid")
}

func TestCookieIsOnlyHonouredOnJWTRoutes(t *testing.T) {
	good := sign(t, goodInner, testSecret, time.Now())
	svc := service.NewAuth(newStore(), testSecret, common.AccessTokenMaxAge)
	e := gin.New()
	e.Use(handler.AuthGate(svc, nil))
	e.GET("/api/v1/mcp", func(c *gin.Context) { common.OK(c, "reached") })
	assert.Equal(t, http.StatusUnauthorized, call(e, "GET", "/api/v1/mcp", nil, good).Code, "beta route never accepts the cookie, and beta resolution is not built yet")
	assert.Equal(t, http.StatusUnauthorized, call(e, "GET", "/api/v1/mcp", bearer(good), "").Code, "jwt credential is not an api or beta credential")
}

func TestCookieCSRFRule(t *testing.T) {
	good := sign(t, goodInner, testSecret, time.Now())
	e := rig(t, newStore())
	with := func(extra map[string]string) map[string]string {
		m := map[string]string{}
		for k, v := range extra {
			m[k] = v
		}
		return m
	}

	req := func(hdr map[string]string, cookie string) *httptest.ResponseRecorder {
		r := httptest.NewRequest("POST", "http://app.example.test/v1/user/setting", nil)
		for k, v := range hdr {
			r.Header.Set(k, v)
		}
		r.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: cookie})
		w := httptest.NewRecorder()
		e.ServeHTTP(w, r)
		return w
	}

	w := req(nil, good)
	assert.Equal(t, http.StatusForbidden, w.Code, "no Origin and no Referer")
	assert.Equal(t, forbidden, w.Body.String())
	assert.Equal(t, http.StatusForbidden, req(with(map[string]string{"Origin": "http://evil.test"}), good).Code, "foreign Origin")
	assert.Equal(t, http.StatusForbidden, req(with(map[string]string{"Origin": "null"}), good).Code, "opaque Origin")
	assert.Equal(t, http.StatusForbidden, req(with(map[string]string{"Referer": "http://evil.test/page"}), good).Code, "foreign Referer")
	assert.Equal(t, http.StatusOK, req(with(map[string]string{"Origin": "http://app.example.test"}), good).Code, "same-origin Origin")
	assert.Equal(t, http.StatusOK, req(with(map[string]string{"Referer": "http://app.example.test/page?x=1"}), good).Code, "same-origin Referer")
	assert.Equal(t, http.StatusOK, req(with(map[string]string{"Origin": "http://public.example.test:8088", "X-Forwarded-Host": "public.example.test:8088"}), good).Code, "proxy-provided host")
	assert.Equal(t, http.StatusForbidden, req(with(map[string]string{"Origin": "http://app.example.test:9999"}), good).Code, "same host, different port")

	// Bearer-authenticated requests are unaffected.
	assert.Equal(t, http.StatusOK, call(e, "POST", "/v1/user/setting", bearer(good), "").Code)
	// Safe methods never need an Origin.
	assert.Equal(t, http.StatusOK, call(e, "GET", "/v1/user/info", nil, good).Code)

	// An allow-listed origin passes even when it differs from the request host.
	e2 := rig(t, newStore(), "http://trusted.example.test")
	r := httptest.NewRequest("POST", "http://app.example.test/v1/user/setting", nil)
	r.Header.Set("Origin", "http://trusted.example.test")
	r.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: good})
	w = httptest.NewRecorder()
	e2.ServeHTTP(w, r)
	assert.Equal(t, http.StatusOK, w.Code)
}

func TestOptionsPreflightBypassesGate(t *testing.T) {
	e := rig(t, newStore())
	w := call(e, "OPTIONS", "/v1/user/info", map[string]string{"Origin": "http://x.test", "Access-Control-Request-Method": "GET"}, "")
	assert.NotEqual(t, http.StatusUnauthorized, w.Code)
}

func TestInfrastructureErrorsFailClosedWith503(t *testing.T) {
	tok := sign(t, goodInner, testSecret, time.Now())
	for name, err := range map[string]error{
		"closed":   errors.New("sql: database is closed"),
		"deadline": context.DeadlineExceeded,
		"refused":  errors.New("dial tcp 10.1.2.3:3306: connect: connection refused password=hunter2"),
	} {
		store := newStore()
		store.err = err
		w := call(rig(t, store), "GET", "/v1/user/info", bearer(tok), "")
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, name)
		assert.Equal(t, unavailable, w.Body.String(), name)
		for _, leak := range []string{"10.1.2.3", "3306", "hunter2", "closed"} {
			assert.NotContains(t, w.Body.String(), leak, name)
		}
	}
}

func TestUnknownPathIs401UnauthenticatedAnd404Authenticated(t *testing.T) {
	tok := sign(t, goodInner, testSecret, time.Now())
	e := rig(t, newStore())
	assert.Equal(t, unauthorized, call(e, "GET", "/nope", nil, "").Body.String())
	assert.Equal(t, http.StatusUnauthorized, call(e, "GET", "/v1/user/never-built", nil, "").Code, "unimplemented path under a protected prefix")
	w := call(e, "GET", "/nope", bearer(tok), "")
	assert.Equal(t, http.StatusNotFound, w.Code)
	assert.Equal(t, `{"code":404,"message":"not found","data":null}`, w.Body.String())
}

func TestPublicRoutesStayPublic(t *testing.T) {
	e := rig(t, newStore())
	assert.Equal(t, http.StatusOK, call(e, "GET", "/health", nil, "").Code)
	w := call(e, "POST", "/health", nil, "")
	assert.Equal(t, http.StatusMethodNotAllowed, w.Code, "public path keeps its 405")
}

func TestGateErrorsAreUniform(t *testing.T) {
	now := time.Now()
	unknownUser := sign(t, strings.Repeat("b", 32), testSecret, now)
	expired := sign(t, goodInner, testSecret, now.Add(-common.AccessTokenMaxAge-time.Hour))
	a := call(rig(t, newStore()), "GET", "/v1/user/info", bearer(unknownUser), "")
	b := call(rig(t, newStore()), "GET", "/v1/user/info", bearer(expired), "")
	c := call(rig(t, newStore()), "GET", "/v1/user/info", nil, "")
	assert.Equal(t, a.Body.String(), b.Body.String())
	assert.Equal(t, a.Body.String(), c.Body.String())
}

func TestLogoutServiceRewritesTokenToInvalidHex(t *testing.T) {
	store := newStore()
	svc := service.NewAuth(store, testSecret, common.AccessTokenMaxAge)
	require.NoError(t, svc.Logout(context.Background(), "u1"))
	got := store.set["u1"]
	require.True(t, strings.HasPrefix(got, "INVALID_"), got)
	assert.Regexp(t, `^INVALID_[0-9a-f]{32}$`, got)
	assert.False(t, common.ValidInner(got))
}
