package handler_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
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

const (
	apiTokenOne  = "ragflow-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
	betaTokenOne = "0123456789abcdef0123456789abcdef"
	apiTokenTwo  = "ragflow-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
	notFoundBody = `{"code":404,"message":"token not found","data":null}`
)

// tokenMem is a unit-tier token store. Like MySQL's default collation it matches case-insensitively,
// so the service must still compare exactly.
type tokenMem struct {
	mu      sync.Mutex
	rows    []entity.APIToken
	err     error
	lookups int
}

func (m *tokenMem) find(match func(entity.APIToken) bool) (*entity.APIToken, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.lookups++
	if m.err != nil {
		return nil, m.err
	}
	for i := range m.rows {
		if match(m.rows[i]) {
			r := m.rows[i]
			return &r, nil
		}
	}
	return nil, dao.ErrNotFound
}

func (m *tokenMem) FindAPIToken(_ context.Context, token string) (*entity.APIToken, error) {
	return m.find(func(r entity.APIToken) bool { return strings.EqualFold(r.Token, token) })
}

func (m *tokenMem) FindAPITokenByBeta(_ context.Context, beta string) (*entity.APIToken, error) {
	return m.find(func(r entity.APIToken) bool { return r.Beta != nil && strings.EqualFold(*r.Beta, beta) })
}

func (m *tokenMem) CreateAPIToken(_ context.Context, row entity.APIToken, maxPerTenant int) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	n := 0
	for _, r := range m.rows {
		if r.TenantID == row.TenantID {
			n++
		}
	}
	if n >= maxPerTenant {
		return dao.ErrTokenLimit
	}
	m.rows = append(m.rows, row)
	return nil
}

func (m *tokenMem) ListAPITokens(_ context.Context, tenantID string, limit, offset int) ([]entity.APIToken, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []entity.APIToken
	for i := len(m.rows) - 1; i >= 0; i-- {
		if m.rows[i].TenantID == tenantID {
			out = append(out, m.rows[i])
		}
	}
	if offset >= len(out) {
		return nil, nil
	}
	out = out[offset:]
	if limit < len(out) {
		out = out[:limit]
	}
	return out, nil
}

func (m *tokenMem) DeleteAPIToken(_ context.Context, tenantID, token string) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for i, r := range m.rows {
		if r.TenantID == tenantID && r.Token == token {
			m.rows = append(m.rows[:i], m.rows[i+1:]...)
			return true, nil
		}
	}
	return false, nil
}

type memCounter struct {
	mu sync.Mutex
	n  map[string]int64
}

func (c *memCounter) Incr(_ context.Context, key string, window time.Duration) (int64, time.Duration, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.n == nil {
		c.n = map[string]int64{}
	}
	c.n[key]++
	return c.n[key], window, nil
}

func (c *memCounter) Count(_ context.Context, key string) (int64, time.Duration, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.n[key], 0, nil
}

func (c *memCounter) Delete(_ context.Context, key string) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.n, key)
	return nil
}

type tokenRig struct {
	engine *gin.Engine
	users  *memStore
	tokens *tokenMem
	access string
}

func newTokenRig(t *testing.T) *tokenRig {
	t.Helper()
	users := newStore()
	users.byToken["ffffffffffffffffffffffffffffff00"] = &entity.User{ID: "u2", Email: "u2@example.test", AccessToken: ptr("ffffffffffffffffffffffffffffff00"), Status: ptr("1")}
	beta := betaTokenOne
	now := int64(1_700_000_000_000)
	tokens := &tokenMem{rows: []entity.APIToken{{TenantID: "u1", Token: apiTokenOne, Beta: &beta, CreateTime: &now}}}
	auth := service.NewAuth(users, testSecret, common.AccessTokenMaxAge).WithTokens(tokens)
	mgmt := handler.NewToken(service.NewToken(tokens, service.NewLimiter(&memCounter{}, "t"), service.DefaultTokenLimits()))

	e := gin.New()
	e.HandleMethodNotAllowed = true
	e.Use(handler.AuthGate(auth, nil))
	ok := func(c *gin.Context) {
		p, _ := handler.PrincipalFrom(c)
		common.OK(c, map[string]string{"user": p.UserID, "tenant": p.TenantID, "type": p.AuthType})
	}
	// The real beta handlers arrive in Phase 8; these routes carry the policy of their path family.
	e.GET("/api/v1/probe-api", ok)             // /api/ prefix: api policy
	e.GET("/api/v1/searchbots/probe-beta", ok) // beta policy
	e.GET("/v1/user/info", ok)                 // jwt policy
	e.POST("/api/v1/system/tokens", mgmt.Create)
	e.GET("/api/v1/system/tokens", mgmt.List)
	e.DELETE("/api/v1/system/tokens/:token", mgmt.Delete)
	e.NoRoute(func(c *gin.Context) { common.Fail(c, http.StatusNotFound, common.CodeNotFound, "not found") })
	return &tokenRig{engine: e, users: users, tokens: tokens, access: sign(t, goodInner, testSecret, time.Now())}
}

func (r *tokenRig) do(method, path string, hdr map[string]string, cookie, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	if cookie != "" {
		req.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: cookie})
	}
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	return w
}

func TestAPITokenAuthenticatesApiRoutesAsTheOwningTenant(t *testing.T) {
	r := newTokenRig(t)
	w := r.do("GET", "/api/v1/probe-api", bearer(apiTokenOne), "", "")
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assert.Contains(t, w.Body.String(), `"tenant":"u1"`)
	assert.Contains(t, w.Body.String(), `"type":"api"`)
	raw := r.do("GET", "/api/v1/probe-api", map[string]string{"Authorization": apiTokenOne}, "", "")
	assert.Equal(t, http.StatusOK, raw.Code, "raw Authorization value works like Bearer")
	viaAccess := r.do("GET", "/api/v1/probe-api", bearer(r.access), "", "")
	assert.Equal(t, http.StatusOK, viaAccess.Code, "an access token also passes api routes")
	assert.Contains(t, viaAccess.Body.String(), `"type":"jwt"`)
}

func TestAPITokenNeverReachesJwtOnlyRoutes(t *testing.T) {
	r := newTokenRig(t)
	for _, cred := range []string{apiTokenOne, betaTokenOne} {
		for _, p := range []struct{ method, path string }{
			{"GET", "/v1/user/info"}, {"GET", "/api/v1/system/tokens"}, {"POST", "/api/v1/system/tokens"},
			{"DELETE", "/api/v1/system/tokens/" + apiTokenOne},
		} {
			w := r.do(p.method, p.path, bearer(cred), "", "")
			assert.Equal(t, http.StatusUnauthorized, w.Code, "%s %s", p.method, p.path)
			assert.Equal(t, unauthorized, w.Body.String())
		}
	}
	assert.Len(t, r.tokens.rows, 1, "no token was minted or deleted by an API or beta credential")
}

func TestDeletedTokenStopsWorkingImmediately(t *testing.T) {
	r := newTokenRig(t)
	require.Equal(t, http.StatusOK, r.do("GET", "/api/v1/probe-api", bearer(apiTokenOne), "", "").Code)
	w := r.do("DELETE", "/api/v1/system/tokens/"+apiTokenOne, bearer(r.access), "", "")
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	for _, p := range []struct{ path, cred string }{{"/api/v1/probe-api", apiTokenOne}, {"/api/v1/searchbots/probe-beta", betaTokenOne}, {"/api/v1/searchbots/probe-beta", apiTokenOne}} {
		got := r.do("GET", p.path, bearer(p.cred), "", "")
		assert.Equal(t, http.StatusUnauthorized, got.Code, p.path)
		assert.Equal(t, unauthorized, got.Body.String())
	}
}

func TestBetaTokenIsAcceptedOnlyOnBetaRoutes(t *testing.T) {
	r := newTokenRig(t)
	w := r.do("GET", "/api/v1/searchbots/probe-beta", bearer(betaTokenOne), "", "")
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assert.Contains(t, w.Body.String(), `"tenant":"u1"`)
	assert.Contains(t, w.Body.String(), `"type":"beta"`)
	for _, path := range []string{"/api/v1/probe-api", "/v1/user/info"} {
		got := r.do("GET", path, bearer(betaTokenOne), "", "")
		assert.Equal(t, http.StatusUnauthorized, got.Code, path)
	}
	// beta routes also accept an access token and an API token (reference behaviour, R-117)
	assert.Equal(t, http.StatusOK, r.do("GET", "/api/v1/searchbots/probe-beta", bearer(apiTokenOne), "", "").Code)
	assert.Equal(t, http.StatusOK, r.do("GET", "/api/v1/searchbots/probe-beta", bearer(r.access), "", "").Code)
}

func TestEveryBetaFailureIsHTTP401WithTheGenericEnvelope(t *testing.T) {
	r := newTokenRig(t)
	cases := map[string]map[string]string{
		"wrong":          bearer(strings.Repeat("a", 32)),
		"empty bearer":   {"Authorization": "Bearer "},
		"blank":          {"Authorization": "   "},
		"absent":         nil,
		"short":          bearer(betaTokenOne[:31]),
		"long":           bearer(betaTokenOne + "0"),
		"over long":      bearer(strings.Repeat("a", 5000)),
		"api look-alike": bearer("ragflow-nope"),
	}
	for name, hdr := range cases {
		w := r.do("GET", "/api/v1/searchbots/probe-beta", hdr, "", "")
		assert.Equal(t, http.StatusUnauthorized, w.Code, name)
		assert.Equal(t, unauthorized, w.Body.String(), name)
		var env struct {
			Code int `json:"code"`
		}
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
		assert.Equal(t, 401, env.Code, "%s: the body code is 401 too, never 0", name)
	}
}

func TestCookieIsNeverHonouredForApiOrBetaRoutes(t *testing.T) {
	r := newTokenRig(t)
	for _, path := range []string{"/api/v1/probe-api", "/api/v1/searchbots/probe-beta"} {
		for _, cookie := range []string{r.access, apiTokenOne, betaTokenOne} {
			w := r.do("GET", path, nil, cookie, "")
			assert.Equal(t, http.StatusUnauthorized, w.Code, path)
		}
	}
}

func TestMalformedCredentialsAreRejectedBeforeAnyTokenLookup(t *testing.T) {
	r := newTokenRig(t)
	for name, cred := range map[string]string{
		"wrong prefix":  "token-" + strings.Repeat("A", 43),
		"over 255":      "ragflow-" + strings.Repeat("A", 250),
		"over 1024":     "ragflow-" + strings.Repeat("A", 2000),
		"empty":         "",
		"non-alnum 32":  strings.Repeat("-", 32),
		"percent":       "%" + strings.Repeat("a", 31),
		"sql like":      "ragflow-%",
		"sql injection": "ragflow-' OR '1'='1",
	} {
		for _, path := range []string{"/api/v1/probe-api", "/api/v1/searchbots/probe-beta"} {
			w := r.do("GET", path, bearer(cred), "", "")
			assert.Equal(t, http.StatusUnauthorized, w.Code, "%s on %s", name, path)
		}
	}
	// "%" and "-" runs match the beta shape check only when they are 32 alnum characters; none above is.
	assert.Zero(t, r.tokens.lookups, "no token lookup for values that cannot be tokens")
}

func TestCaseVariantTokensAreRefusedDespiteCollationMatch(t *testing.T) {
	r := newTokenRig(t)
	assert.Equal(t, http.StatusUnauthorized, r.do("GET", "/api/v1/probe-api", bearer(strings.ToLower(apiTokenOne)), "", "").Code)
	assert.Equal(t, http.StatusUnauthorized, r.do("GET", "/api/v1/searchbots/probe-beta", bearer(strings.ToUpper(betaTokenOne)), "", "").Code)
}

func TestTokenLookupFailureIs503Not401(t *testing.T) {
	r := newTokenRig(t)
	r.tokens.err = errors.New("sql: database is closed")
	for _, p := range []struct{ path, cred string }{{"/api/v1/probe-api", apiTokenOne}, {"/api/v1/searchbots/probe-beta", betaTokenOne}} {
		w := r.do("GET", p.path, bearer(p.cred), "", "")
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, p.path)
		assert.Equal(t, unavailable, w.Body.String())
		assert.NotContains(t, w.Body.String(), "database")
	}
}

func TestSessionManagesOwnTokensThroughDTOs(t *testing.T) {
	r := newTokenRig(t)
	auth := bearer(r.access)
	created := r.do("POST", "/api/v1/system/tokens", auth, "", "")
	require.Equal(t, http.StatusOK, created.Code, created.Body.String())
	var env struct {
		Code int            `json:"code"`
		Data map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(created.Body.Bytes(), &env))
	assert.Equal(t, 0, env.Code)
	assert.Contains(t, env.Data, "token")
	assert.Contains(t, env.Data, "beta")
	assert.Contains(t, env.Data, "create_time")
	assert.NotContains(t, env.Data, "dialog_id")
	assert.NotContains(t, env.Data, "tenant_id", "the tenant comes from the principal and is not echoed")
	assert.Equal(t, "no-store", created.Header().Get("Cache-Control"))

	// a body naming another tenant is ignored
	r.do("POST", "/api/v1/system/tokens", auth, "", `{"tenant_id":"someone-else","token":"ragflow-chosen"}`)
	for _, row := range r.tokens.rows {
		assert.Equal(t, "u1", row.TenantID)
		assert.NotEqual(t, "ragflow-chosen", row.Token)
	}

	listed := r.do("GET", "/api/v1/system/tokens", auth, "", "")
	require.Equal(t, http.StatusOK, listed.Code)
	var list struct {
		Data []map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(listed.Body.Bytes(), &list))
	assert.Len(t, list.Data, 3)
	assert.Equal(t, "no-store", listed.Header().Get("Cache-Control"))
	assert.Equal(t, http.StatusBadRequest, r.do("GET", "/api/v1/system/tokens?page_size=100000", auth, "", "").Code)
	assert.Equal(t, http.StatusBadRequest, r.do("GET", "/api/v1/system/tokens?page=0", auth, "", "").Code)
	assert.Equal(t, http.StatusBadRequest, r.do("GET", "/api/v1/system/tokens?page=abc", auth, "", "").Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.do("POST", "/api/v1/system/tokens", auth, "", strings.Repeat("a", 5000)).Code)
	assert.Equal(t, http.StatusBadRequest, r.do("POST", "/api/v1/system/tokens", auth, "", "[1,2").Code)
}

func TestForeignAndMissingTokenDeletesAreIdentical404(t *testing.T) {
	r := newTokenRig(t)
	// A session of the second tenant u2: sign its stored value.
	other := bearer(sign(t, "ffffffffffffffffffffffffffffff00", testSecret, time.Now()))
	foreign := r.do("DELETE", "/api/v1/system/tokens/"+apiTokenOne, other, "", "")
	missing := r.do("DELETE", "/api/v1/system/tokens/"+apiTokenTwo, other, "", "")
	assert.Equal(t, http.StatusNotFound, foreign.Code)
	assert.Equal(t, http.StatusNotFound, missing.Code)
	assert.Equal(t, notFoundBody, foreign.Body.String())
	assert.Equal(t, foreign.Body.String(), missing.Body.String())
	assert.Len(t, r.tokens.rows, 1, "nothing changed")
	assert.Equal(t, http.StatusOK, r.do("GET", "/api/v1/probe-api", bearer(apiTokenOne), "", "").Code, "the owner's token still works")
	listed := r.do("GET", "/api/v1/system/tokens", other, "", "")
	assert.JSONEq(t, `{"code":0,"message":"","data":[]}`, listed.Body.String(), "u2 sees none of u1's tokens")
}
