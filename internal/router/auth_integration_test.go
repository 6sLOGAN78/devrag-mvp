//go:build integration

package router

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/handler"
	"devrag/internal/testutil"
)

const peer = "198.51.100.9:1000"

// session registers and logs a fresh account and returns its email and token.
func (r *accountRig) session(t *testing.T) (email, token string) {
	t.Helper()
	email = testutil.UniqueEmail("gate")
	r.register(t, email)
	w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, peer, nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var env struct {
		Data struct {
			Token string `json:"token"`
		} `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	require.NotEmpty(t, env.Data.Token)
	return email, env.Data.Token
}

func (r *accountRig) req(method, path, origin string, hdr map[string]string, cookie string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, "http://app.example.test"+path, strings.NewReader(""))
	req.RemoteAddr = peer
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	if cookie != "" {
		req.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: cookie})
	}
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	return w
}

func TestUserInfoReturnsSafeDTO(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email, tok := r.session(t)
	w := r.req(http.MethodGet, "/v1/user/info", "", map[string]string{"Authorization": "Bearer " + tok}, "")
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var env struct {
		Data map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	for _, k := range []string{"id", "nickname", "email", "avatar", "language", "color_schema", "tenant_id", "tenant_name", "role", "is_superuser"} {
		assert.Contains(t, env.Data, k)
	}
	assert.Equal(t, email, env.Data["email"])
	assert.Equal(t, "owner", env.Data["role"])
	assert.Equal(t, false, env.Data["is_superuser"])
	assert.Len(t, env.Data, 10, "no extra fields")
	for _, banned := range []string{"password", "access_token", "pbkdf2", tok} {
		assert.NotContains(t, w.Body.String(), banned)
	}
}

func TestLogoutInvalidatesTokenEverywhereAndClearsCookie(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email, tok := r.session(t)
	hdr := map[string]string{"Authorization": "Bearer " + tok}
	require.Equal(t, http.StatusOK, r.req(http.MethodGet, "/v1/user/info", "", hdr, "").Code)

	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodPost, "/api/v1/auth/logout", "", nil, "").Code, "logout requires authentication")

	w := r.req(http.MethodPost, "/api/v1/auth/logout", "", hdr, "")
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	cookies := w.Result().Cookies()
	require.Len(t, cookies, 1)
	assert.Equal(t, handler.AuthCookieName, cookies[0].Name)
	assert.Equal(t, -1, cookies[0].MaxAge, "Max-Age=0 on the wire")
	assert.Contains(t, w.Header().Get("Set-Cookie"), "Max-Age=0")
	assert.True(t, cookies[0].HttpOnly)

	var stored string
	require.NoError(t, r.raw.Raw("SELECT access_token FROM user WHERE email = ?", email).Scan(&stored).Error)
	assert.Regexp(t, `^INVALID_[0-9a-f]{32}$`, stored)

	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/v1/user/info", "", hdr, "").Code, "old token via header")
	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/v1/user/info", "", nil, tok).Code, "old token via cookie")
	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/api/v1/system/version", "", hdr, "").Code)
}

func TestCookieAuthenticatedLogoutNeedsSameOrigin(t *testing.T) {
	r := newAccountRig(t, nil, false)
	_, tok := r.session(t)
	assert.Equal(t, http.StatusForbidden, r.req(http.MethodPost, "/api/v1/auth/logout", "", nil, tok).Code, "no Origin")
	assert.Equal(t, http.StatusForbidden, r.req(http.MethodPost, "/api/v1/auth/logout", "http://evil.test", nil, tok).Code, "foreign Origin")
	assert.Equal(t, http.StatusOK, r.req(http.MethodPost, "/api/v1/auth/logout", "http://app.example.test", nil, tok).Code, "same origin")
	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/v1/user/info", "", nil, tok).Code)
}

func TestDisabledUserIsRejectedImmediately(t *testing.T) {
	r := newAccountRig(t, nil, false)
	email, tok := r.session(t)
	hdr := map[string]string{"Authorization": "Bearer " + tok}
	require.Equal(t, http.StatusOK, r.req(http.MethodGet, "/v1/user/info", "", hdr, "").Code)
	require.NoError(t, r.raw.Exec("UPDATE user SET status = '0' WHERE email = ?", email).Error)
	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/v1/user/info", "", hdr, "").Code)
}

func TestClosedDatabaseFailsClosedWith503ButMalformedTokenStays401(t *testing.T) {
	r := newAccountRig(t, nil, false)
	_, tok := r.session(t)
	require.NoError(t, r.db.Close())
	hdr := map[string]string{"Authorization": "Bearer " + tok}
	w := r.req(http.MethodGet, "/v1/user/info", "", hdr, "")
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Equal(t, `{"code":503,"message":"service unavailable","data":null}`, w.Body.String())
	assert.Equal(t, http.StatusUnauthorized, r.req(http.MethodGet, "/v1/user/info", "", map[string]string{"Authorization": "Bearer junk"}, "").Code)
}

func TestRequestLogsOfAuthenticatedCallsHoldNoCredentials(t *testing.T) {
	r := newAccountRig(t, nil, false)
	_, tok := r.session(t)
	r.req(http.MethodGet, "/v1/user/info", "", map[string]string{"Authorization": "Bearer " + tok}, tok)
	r.req(http.MethodPost, "/api/v1/auth/logout", "", map[string]string{"Authorization": "Bearer " + tok}, "")
	for _, e := range r.logs.All() {
		line := e.Message
		for _, f := range e.Context {
			line += " " + f.Key + "=" + f.String
		}
		assert.NotContains(t, line, tok)
		assert.NotContains(t, strings.ToLower(line), "bearer")
	}
}
