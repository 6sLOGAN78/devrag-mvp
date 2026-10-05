package common

import (
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strconv"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func init() { gin.SetMode(gin.TestMode) }

func serve(h gin.HandlerFunc) *httptest.ResponseRecorder {
	r := gin.New()
	r.GET("/x", h)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/x", nil))
	return w
}

func TestOKEnvelopeKeyOrderAndStatus(t *testing.T) {
	w := serve(func(c *gin.Context) { OK(c, map[string]string{"a": "b"}) })
	assert.Equal(t, http.StatusOK, w.Code)
	assert.JSONEq(t, `{"code":0,"message":"","data":{"a":"b"}}`, w.Body.String())
	assert.Equal(t, `{"code":0,"message":"","data":{"a":"b"}}`, w.Body.String(), "key order must be code, message, data")
}

func TestFailEnvelopeCarriesStatusAndNullData(t *testing.T) {
	w := serve(func(c *gin.Context) { Fail(c, http.StatusNotFound, CodeNotFound, "not found") })
	assert.Equal(t, http.StatusNotFound, w.Code)
	assert.Equal(t, `{"code":404,"message":"not found","data":null}`, w.Body.String())
}

func TestFailWithDataKeepsPayload(t *testing.T) {
	w := serve(func(c *gin.Context) {
		FailWithData(c, http.StatusServiceUnavailable, CodeServiceUnavailable, "unavailable", gin.H{"status": "down"})
	})
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Equal(t, `{"code":503,"message":"unavailable","data":{"status":"down"}}`, w.Body.String())
}

func TestEnvelopeDoesNotHTMLEscape(t *testing.T) {
	w := serve(func(c *gin.Context) { OK(c, "a<b&c") })
	assert.Contains(t, w.Body.String(), "a<b&c")
}

func TestContentTypeIsJSON(t *testing.T) {
	w := serve(func(c *gin.Context) { OK(c, nil) })
	assert.Contains(t, w.Header().Get("Content-Type"), "application/json")
}

func TestRetCodesMatchPythonConstants(t *testing.T) {
	src, err := os.ReadFile("../../common/constants.py")
	require.NoError(t, err)
	re := regexp.MustCompile(`(?m)^\s+([A-Z_]+) = (\d+)$`)
	py := map[string]int{}
	for _, m := range re.FindAllStringSubmatch(string(src), -1) {
		n, _ := strconv.Atoi(m[2])
		py[m[1]] = n
	}
	want := map[string]RetCode{
		"SUCCESS": CodeSuccess, "NOT_EFFECTIVE": CodeNotEffective, "EXCEPTION_ERROR": CodeExceptionError,
		"ARGUMENT_ERROR": CodeArgumentError, "DATA_ERROR": CodeDataError, "OPERATING_ERROR": CodeOperatingError,
		"CONNECTION_ERROR": CodeConnectionError, "RUNNING": CodeRunning, "PERMISSION_ERROR": CodePermissionError,
		"AUTHENTICATION_ERROR": CodeAuthenticationError, "BAD_REQUEST": CodeBadRequest, "UNAUTHORIZED": CodeUnauthorized,
		"FORBIDDEN": CodeForbidden, "NOT_FOUND": CodeNotFound, "METHOD_NOT_ALLOWED": CodeMethodNotAllowed,
		"CONFLICT": CodeConflict, "SERVER_ERROR": CodeServerError, "SERVICE_UNAVAILABLE": CodeServiceUnavailable,
	}
	assert.Len(t, py, len(want), "Python RetCode member count")
	for name, code := range want {
		assert.Equal(t, py[name], int(code), name)
	}
}

func TestIdentifiersMatchPythonConstants(t *testing.T) {
	src, err := os.ReadFile("../../common/constants.py")
	require.NoError(t, err)
	for name, val := range map[string]string{"SERVICE_NAME": ServiceName, "INDEX_PREFIX": IndexPrefix, "BUCKET_NAME": BucketName, "NETWORK_NAME": NetworkName} {
		assert.Regexp(t, regexp.MustCompile(`(?m)^`+name+` = "`+regexp.QuoteMeta(val)+`"$`), string(src), name)
	}
}
