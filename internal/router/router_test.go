package router

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
	"gopkg.in/yaml.v3"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/handler"
	"devrag/internal/server"
	"devrag/internal/service"
)

func init() { gin.SetMode(gin.TestMode) }

type pinger struct{ err error }

func (p pinger) Ping(context.Context) error { return p.err }

type blockingPinger struct{}

func (blockingPinger) Ping(ctx context.Context) error { <-ctx.Done(); return ctx.Err() }

type settings struct {
	value string
	err   error
}

func (s settings) GetSetting(context.Context, string) (string, error) { return s.value, s.err }

type env struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data"`
}

func build(t *testing.T, db, rd service.Pinger, st service.SettingsReader, origins []string, opts ...Option) (*gin.Engine, *observer.ObservedLogs) {
	t.Helper()
	core, logs := observer.New(zapcore.DebugLevel)
	svc := service.NewSystem(db, rd, st)
	return NewEngine(server.Config{AllowedOrigins: origins}, zap.New(common.WrapRedacting(core)), handler.NewSystem(svc), opts...), logs
}

func healthy(t *testing.T, opts ...Option) *gin.Engine {
	e, _ := build(t, pinger{}, pinger{}, settings{value: "0002"}, nil, opts...)
	return e
}

func do(e *gin.Engine, method, path string, hdr map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, nil)
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	e.ServeHTTP(w, req)
	return w
}

func decode(t *testing.T, w *httptest.ResponseRecorder) env {
	t.Helper()
	var out env
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &out), w.Body.String())
	return out
}

func TestFiveRoutesReturnEnvelopeWithSource(t *testing.T) {
	e := healthy(t)
	cases := map[string]string{
		"/health":                `{"status":"ok","engine":"go","checks":{"database":{"status":"ok","elapsed_ms":0},"redis":{"status":"ok","elapsed_ms":0}}}`,
		"/api/v1/system/ping":    `"pong"`,
		"/api/v1/system/config":  `{"engine":"go","api_version":"v1","service":"ragflow_server"}`,
		"/api/v1/system/version": `{"version":"` + common.AppVersion + `","schema_version":"0002"}`,
		"/api/v1/language":       `{"engine":"go"}`,
	}
	for path, want := range cases {
		w := do(e, http.MethodGet, path, nil)
		assert.Equal(t, http.StatusOK, w.Code, path)
		assert.Equal(t, "go", w.Header().Get("X-API-Source"), path)
		got := decode(t, w)
		assert.Equal(t, 0, got.Code, path)
		assert.JSONEq(t, want, string(got.Data), path)
	}
}

func TestHealthDownReports503WithoutLeakingDetails(t *testing.T) {
	e, _ := build(t, pinger{err: errors.New("dial tcp 10.1.2.3:3306: refused password=hunter2")}, pinger{}, settings{}, nil)
	w := do(e, http.MethodGet, "/health", nil)
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	got := decode(t, w)
	assert.Equal(t, 503, got.Code)
	var data service.HealthData
	require.NoError(t, json.Unmarshal(got.Data, &data))
	assert.Equal(t, "down", data.Status)
	assert.Equal(t, "down", data.Checks.Database.Status)
	assert.Equal(t, "ok", data.Checks.Redis.Status)
	for _, leak := range []string{"10.1.2.3", "3306", "hunter2", "refused"} {
		assert.NotContains(t, w.Body.String(), leak)
	}
}

func TestHealthProbesAreCappedAtTwoSeconds(t *testing.T) {
	e, _ := build(t, blockingPinger{}, blockingPinger{}, settings{}, nil)
	w := do(e, http.MethodGet, "/health", nil)
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	var data service.HealthData
	require.NoError(t, json.Unmarshal(decode(t, w).Data, &data))
	assert.GreaterOrEqual(t, data.Checks.Database.ElapsedMS, int64(1900))
	assert.Less(t, data.Checks.Database.ElapsedMS, int64(2600))
	assert.Less(t, data.Checks.Redis.ElapsedMS, int64(2600), "probes run concurrently")
}

func TestVersionUnavailableWhenSettingMissingOrDBDown(t *testing.T) {
	for name, st := range map[string]settings{"down": {err: errors.New("conn refused host=db")}, "missing": {err: dao.ErrSettingNotFound}} {
		e, _ := build(t, pinger{}, pinger{}, st, nil)
		w := do(e, http.MethodGet, "/api/v1/system/version", nil)
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, name)
		assert.Equal(t, 503, decode(t, w).Code, name)
		assert.Equal(t, "go", w.Header().Get("X-API-Source"))
		assert.NotContains(t, w.Body.String(), "host=db")
	}
}

func TestNotFoundAndMethodNotAllowedEnvelopes(t *testing.T) {
	e := healthy(t)
	w := do(e, http.MethodGet, "/nope", nil)
	assert.Equal(t, http.StatusNotFound, w.Code)
	assert.Equal(t, `{"code":404,"message":"not found","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))

	w = do(e, http.MethodPost, "/health", nil)
	assert.Equal(t, http.StatusMethodNotAllowed, w.Code)
	assert.Equal(t, `{"code":405,"message":"method not allowed","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))

	w = do(e, http.MethodGet, "/health/", nil)
	assert.Equal(t, http.StatusNotFound, w.Code, "no trailing-slash redirect")
}

func TestPanicReturnsEnvelopeWithoutPanicText(t *testing.T) {
	e, logs := build(t, pinger{}, pinger{}, settings{}, nil, WithExtraRoutes(func(e *gin.Engine) {
		e.GET("/boom", func(*gin.Context) { panic("secret internals 0xdeadbeef") })
	}))
	w := do(e, http.MethodGet, "/boom", nil)
	assert.Equal(t, http.StatusInternalServerError, w.Code)
	assert.Equal(t, `{"code":500,"message":"internal error","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))
	assert.NotContains(t, w.Body.String(), "deadbeef")
	assert.Equal(t, 1, logs.FilterMessage("panic recovered").Len())
}

func TestRequestLogFields(t *testing.T) {
	e, logs := build(t, pinger{}, pinger{}, settings{}, nil)
	do(e, http.MethodGet, "/api/v1/system/ping?token=abc", nil)
	entry := logs.FilterMessage("request").All()[0].ContextMap()
	assert.Equal(t, "GET", entry["method"])
	assert.Equal(t, "/api/v1/system/ping", entry["path"])
	assert.EqualValues(t, 200, entry["status"])
	assert.Contains(t, entry, "duration_ms")
}

func TestCORSAllowedOriginEchoed(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, []string{"http://ok.test"})
	w := do(e, http.MethodGet, "/api/v1/system/ping", map[string]string{"Origin": "http://ok.test"})
	assert.Equal(t, "http://ok.test", w.Header().Get("Access-Control-Allow-Origin"))
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))
}

func TestCORSDisallowedOriginGetsNoHeader(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, []string{"http://ok.test"})
	w := do(e, http.MethodGet, "/api/v1/system/ping", map[string]string{"Origin": "http://evil.test"})
	assert.Empty(t, w.Header().Get("Access-Control-Allow-Origin"))
	assert.Equal(t, http.StatusOK, w.Code)
}

func TestCORSEmptyAllowListAddsNothing(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, nil)
	w := do(e, http.MethodGet, "/api/v1/system/ping", map[string]string{"Origin": "http://ok.test"})
	assert.Empty(t, w.Header().Get("Access-Control-Allow-Origin"))
}

func TestCORSPreflight(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, []string{"http://ok.test"})
	hdr := map[string]string{"Origin": "http://ok.test", "Access-Control-Request-Method": "GET"}
	w := do(e, http.MethodOptions, "/api/v1/system/ping", hdr)
	assert.Equal(t, http.StatusNoContent, w.Code)
	assert.Equal(t, "http://ok.test", w.Header().Get("Access-Control-Allow-Origin"))
	assert.NotEmpty(t, w.Header().Get("Access-Control-Allow-Methods"))
	assert.NotEmpty(t, w.Header().Get("Access-Control-Allow-Headers"))
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))

	hdr["Origin"] = "http://evil.test"
	w = do(e, http.MethodOptions, "/api/v1/system/ping", hdr)
	assert.Empty(t, w.Header().Get("Access-Control-Allow-Origin"))
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))
}

func TestWildcardNeverEmitted(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, []string{"http://ok.test"})
	for _, origin := range []string{"http://ok.test", "http://evil.test", "*"} {
		w := do(e, http.MethodGet, "/health", map[string]string{"Origin": origin})
		assert.NotEqual(t, "*", w.Header().Get("Access-Control-Allow-Origin"))
	}
}

type routeEntry struct {
	Owner string `yaml:"owner"`
	Match string `yaml:"match"`
	Path  string `yaml:"path"`
}

func TestRegisteredRoutesBelongToGoEntriesInRoutesYAML(t *testing.T) {
	raw, err := os.ReadFile("../../conf/routes.yaml")
	require.NoError(t, err)
	var doc struct {
		Routes []routeEntry `yaml:"routes"`
	}
	require.NoError(t, yaml.Unmarshal(raw, &doc))
	var goEntries, pyEntries []routeEntry
	for _, r := range doc.Routes {
		if r.Owner == "go" {
			goEntries = append(goEntries, r)
		} else {
			pyEntries = append(pyEntries, r)
		}
	}
	owned := func(entries []routeEntry, path string) bool {
		for _, r := range entries {
			if (r.Match == "exact" && r.Path == path) || (r.Match == "prefix" && !strings.HasPrefix(r.Path, "/api/") && strings.HasPrefix(path, r.Path)) {
				return true
			}
		}
		return false
	}
	routes := healthy(t).Routes()
	require.Len(t, routes, 5)
	for _, r := range routes {
		assert.True(t, owned(goEntries, r.Path), "route %s is not a Go entry in routes.yaml", r.Path)
		for _, py := range pyEntries {
			assert.False(t, py.Match == "exact" && py.Path == r.Path, "route %s belongs to a Python entry", r.Path)
		}
		if strings.HasPrefix(r.Path, "/api/v1/system/") {
			assert.Contains(t, []string{"/api/v1/system/ping", "/api/v1/system/config", "/api/v1/system/version"}, r.Path)
		}
	}
}
