package router

import (
	"io"
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

// drain is a stand-in handler that consumes the body the way a JSON decoder would.
func drain(c *gin.Context) {
	if _, err := io.ReadAll(c.Request.Body); err != nil {
		common.Fail(c, http.StatusRequestEntityTooLarge, common.CodeBadRequest, "payload too large")
		return
	}
	common.OK(c, nil)
}

func limitEngine(t *testing.T) *gin.Engine {
	t.Helper()
	return healthy(t, WithExtraRoutes(func(e *gin.Engine) {
		e.POST("/api/v1/auth/login", drain)
		e.POST("/api/v1/system/tokens", drain)
		e.POST("/v1/user/setting", drain)
	}))
}

func post(e *gin.Engine, path string, size int, headers map[string]string, chunked bool) *httptest.ResponseRecorder {
	body := strings.NewReader(strings.Repeat("a", size))
	req := httptest.NewRequest(http.MethodPost, path, body)
	if chunked {
		req.ContentLength = -1
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	e.ServeHTTP(w, req)
	return w
}

// WR-04: the Go server enforces a small default body limit without Nginx in front, answers 413 in the
// envelope, and rejects a declared oversize before any handler or the auth gate sees the body.
func TestDefaultBodyLimitHoldsWithoutNginx(t *testing.T) {
	e := limitEngine(t)
	small := int(handler.DefaultBodyLimit)
	for _, chunked := range []bool{false, true} {
		w := post(e, "/api/v1/auth/login", small, nil, chunked)
		assert.Equal(t, http.StatusOK, w.Code, "a body at the limit is accepted (chunked=%v)", chunked)

		w = post(e, "/api/v1/auth/login", small+1, nil, chunked)
		require.Equal(t, http.StatusRequestEntityTooLarge, w.Code, "chunked=%v", chunked)
		got := decode(t, w)
		assert.Equal(t, int(common.CodeBadRequest), got.Code)
		assert.Equal(t, "payload too large", got.Message)
	}
}

func TestOversizeDeclaredBodyIsRefusedBeforeTheAuthGate(t *testing.T) {
	e := limitEngine(t)
	w := post(e, "/api/v1/system/tokens", int(handler.DefaultBodyLimit)+1, nil, false)
	assert.Equal(t, http.StatusRequestEntityTooLarge, w.Code, "no credential, still 413 and no body read")
	w = post(e, "/api/v1/system/tokens", 10, authed, false)
	assert.Equal(t, http.StatusOK, w.Code)
}

func TestSettingsRouteKeepsTheAvatarAllowance(t *testing.T) {
	e := limitEngine(t)
	assert.Equal(t, http.StatusOK, post(e, "/v1/user/setting", int(handler.MaxSettingBody), authed, false).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, post(e, "/v1/user/setting", int(handler.MaxSettingBody)+1, authed, false).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, post(e, "/v1/user/setting", int(handler.MaxSettingBody)+1, authed, true).Code)
}

func TestUnknownRoutesGetTheDefaultLimit(t *testing.T) {
	e := limitEngine(t)
	w := post(e, "/no/such/route", int(handler.DefaultBodyLimit)+1, nil, false)
	assert.Equal(t, http.StatusRequestEntityTooLarge, w.Code)
}
