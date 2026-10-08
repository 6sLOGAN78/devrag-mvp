package handler_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/handler"
)

func guardRig(t *testing.T, origins ...string) (*gin.Engine, *int) {
	t.Helper()
	reached := new(int)
	e := gin.New()
	e.Use(handler.WriteGuard(origins))
	h := func(c *gin.Context) { *reached++; common.OK(c, nil) }
	e.POST("/api/v1/auth/login", h)
	e.POST("/api/v1/users", h)
	e.POST("/api/v1/auth/password/reset", h)
	e.POST("/api/v1/auth/logout", h)
	e.POST("/v1/user/setting", h)
	e.DELETE("/api/v1/system/tokens/:token", h)
	e.GET("/api/v1/language", h)
	return e, reached
}

func send(e *gin.Engine, method, path, body string, hdr map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Host = "app.example.test"
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	e.ServeHTTP(w, req)
	return w
}

const jsonBody = `{"email":"a@example.test","password":"fake-pass-0001"}`

// WR-05: a cross-site form post to a public state-changing endpoint is refused before the handler.
func TestPublicWritesRejectNonJSONContentTypes(t *testing.T) {
	for _, ct := range []string{"application/x-www-form-urlencoded", "text/plain", "text/plain;charset=UTF-8", "multipart/form-data; boundary=x", "application/xml", "application/jsonx", ""} {
		e, reached := guardRig(t)
		hdr := map[string]string{}
		if ct != "" {
			hdr["Content-Type"] = ct
		}
		for _, path := range []string{"/api/v1/auth/login", "/api/v1/users", "/api/v1/auth/password/reset"} {
			w := send(e, http.MethodPost, path, jsonBody, hdr)
			assert.Equal(t, http.StatusUnsupportedMediaType, w.Code, "%s with content type %q", path, ct)
			assert.Contains(t, w.Body.String(), `"code":400`)
		}
		assert.Zero(t, *reached, "no handler ran for content type %q", ct)
	}
}

func TestJSONContentTypeIsAcceptedWithParametersAndCase(t *testing.T) {
	for _, ct := range []string{"application/json", "application/json; charset=utf-8", "Application/JSON", "application/json;charset=UTF-8"} {
		e, reached := guardRig(t)
		w := send(e, http.MethodPost, "/api/v1/auth/login", jsonBody, map[string]string{"Content-Type": ct})
		assert.Equal(t, http.StatusOK, w.Code, ct)
		assert.Equal(t, 1, *reached)
	}
}

func TestAuthenticatedWritesWithABodyAlsoNeedJSON(t *testing.T) {
	e, reached := guardRig(t)
	w := send(e, http.MethodPost, "/v1/user/setting", `nickname=x`, map[string]string{"Content-Type": "application/x-www-form-urlencoded"})
	assert.Equal(t, http.StatusUnsupportedMediaType, w.Code)
	assert.Zero(t, *reached)
}

func TestBodylessWritesNeedNoContentType(t *testing.T) {
	e, reached := guardRig(t)
	assert.Equal(t, http.StatusOK, send(e, http.MethodPost, "/api/v1/auth/logout", "", nil).Code)
	assert.Equal(t, http.StatusOK, send(e, http.MethodDelete, "/api/v1/system/tokens/abc", "", nil).Code)
	assert.Equal(t, 2, *reached)
}

func TestReadsAreNotAffected(t *testing.T) {
	e, _ := guardRig(t)
	w := send(e, http.MethodGet, "/api/v1/language", "", map[string]string{"Origin": "https://evil.example"})
	assert.Equal(t, http.StatusOK, w.Code)
}

func TestPublicWritesApplyTheSameOriginPolicyAsCookieRequests(t *testing.T) {
	json := map[string]string{"Content-Type": "application/json"}
	with := func(origin string) map[string]string {
		return map[string]string{"Content-Type": "application/json", "Origin": origin}
	}
	e, reached := guardRig(t, "http://localhost:5173")
	for name, tc := range map[string]struct {
		hdr  map[string]string
		want int
	}{
		"no origin (non-browser client)": {json, http.StatusOK},
		"same origin":                    {with("http://app.example.test"), http.StatusOK},
		"allowed origin":                 {with("http://localhost:5173"), http.StatusOK},
		"cross site":                     {with("https://evil.example"), http.StatusForbidden},
		"opaque origin":                  {with("null"), http.StatusForbidden},
		"malformed origin":               {with("not a url"), http.StatusForbidden},
	} {
		before := *reached
		w := send(e, http.MethodPost, "/api/v1/auth/login", jsonBody, tc.hdr)
		require.Equal(t, tc.want, w.Code, name)
		if tc.want == http.StatusForbidden {
			assert.Equal(t, before, *reached, "%s: handler must not run", name)
			assert.Contains(t, w.Body.String(), `"code":403`)
		}
	}
}

func TestCrossSiteBodylessPublicWriteIsRefusedByOrigin(t *testing.T) {
	e, reached := guardRig(t)
	w := send(e, http.MethodPost, "/api/v1/auth/password/reset", "", map[string]string{"Origin": "https://evil.example", "Content-Type": "application/x-www-form-urlencoded"})
	assert.Equal(t, http.StatusForbidden, w.Code)
	assert.Zero(t, *reached)
}

func TestForwardedHostCountsOnlyFromALoopbackPeer(t *testing.T) {
	e, _ := guardRig(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", strings.NewReader(jsonBody))
	req.Host = "app.example.test"
	req.RemoteAddr = "203.0.113.9:4000"
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Origin", "https://evil.example")
	req.Header.Set("X-Forwarded-Host", "evil.example")
	w := httptest.NewRecorder()
	e.ServeHTTP(w, req)
	assert.Equal(t, http.StatusForbidden, w.Code, "a direct caller cannot pick the host it is compared with (R-115)")
}
