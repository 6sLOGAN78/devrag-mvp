package router

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
	"gopkg.in/yaml.v3"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
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

const stubToken = "test-only-router-token-0000000001"

// stubResolver is a unit-tier PrincipalResolver that accepts one fixed fake token.
type stubResolver struct{ err error }

func (r stubResolver) ResolvePrincipal(_ context.Context, credential string, _ []string) (service.Principal, error) {
	if r.err != nil {
		return service.Principal{}, r.err
	}
	if credential == stubToken {
		return service.Principal{UserID: "u1", TenantID: "u1", Role: "owner", AuthType: "jwt"}, nil
	}
	return service.Principal{}, service.ErrUnauthenticated
}

var authed = map[string]string{"Authorization": "Bearer " + stubToken}

type env struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data"`
}

func build(t *testing.T, db, rd service.Pinger, st service.SettingsReader, origins []string, opts ...Option) (*gin.Engine, *observer.ObservedLogs) {
	t.Helper()
	core, logs := observer.New(zapcore.DebugLevel)
	svc := service.NewSystem(db, rd, st)
	opts = append([]Option{WithAuth(stubResolver{})}, opts...)
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
		"/api/v1/system/config":  `{"engine":"go","api_version":"v1","service":"ragflow_server","register_enabled":true}`,
		"/api/v1/system/version": `{"version":"` + common.AppVersion + `","schema_version":"0002"}`,
		"/api/v1/language":       `{"engine":"go"}`,
	}
	for path, want := range cases {
		w := do(e, http.MethodGet, path, authed)
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
		assert.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, "/api/v1/system/version", nil).Code, name+" unauthenticated")
		w := do(e, http.MethodGet, "/api/v1/system/version", authed)
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, name)
		assert.Equal(t, 503, decode(t, w).Code, name)
		assert.Equal(t, "go", w.Header().Get("X-API-Source"))
		assert.NotContains(t, w.Body.String(), "host=db")
	}
}

func TestNotFoundAndMethodNotAllowedEnvelopes(t *testing.T) {
	e := healthy(t)
	w := do(e, http.MethodGet, "/nope", nil)
	assert.Equal(t, http.StatusUnauthorized, w.Code, "default deny: unknown path is 401 without credentials")
	assert.Equal(t, `{"code":401,"message":"unauthorized","data":null}`, w.Body.String())
	w = do(e, http.MethodGet, "/nope", authed)
	assert.Equal(t, http.StatusNotFound, w.Code)
	assert.Equal(t, `{"code":404,"message":"not found","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))

	w = do(e, http.MethodPost, "/health", nil)
	assert.Equal(t, http.StatusMethodNotAllowed, w.Code)
	assert.Equal(t, `{"code":405,"message":"method not allowed","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))

	w = do(e, http.MethodGet, "/health/", authed)
	assert.Equal(t, http.StatusNotFound, w.Code, "no trailing-slash redirect")
	assert.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, "/health/", nil).Code, "unregistered path is not public")
}

func TestPanicReturnsEnvelopeWithoutPanicText(t *testing.T) {
	e, logs := build(t, pinger{}, pinger{}, settings{}, nil, WithExtraRoutes(func(e *gin.Engine) {
		e.GET("/boom", func(*gin.Context) { panic("secret internals 0xdeadbeef") })
	}))
	w := do(e, http.MethodGet, "/boom", authed)
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

func TestRequestLogTruncatesLongPath(t *testing.T) {
	e, logs := build(t, pinger{}, pinger{}, settings{}, nil)
	w := do(e, http.MethodGet, "/"+strings.Repeat("a", 8192), authed)
	assert.Equal(t, http.StatusNotFound, w.Code)
	entry := logs.FilterMessage("request").All()[0].ContextMap()
	path, ok := entry["path"].(string)
	require.True(t, ok)
	assert.True(t, strings.HasSuffix(path, "[truncated]"))
	assert.Equal(t, common.MaxLogField+len("[truncated]"), len(path))
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
	Auth  string `yaml:"auth"`
	// PublicUntilPhase records a deliberate unauthenticated exposure (WR-05).
	PublicUntilPhase *int `yaml:"public_until_phase"`
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

func TestUnmarkedAuthRoutesNeverAnswer200Unauthenticated(t *testing.T) {
	raw, err := os.ReadFile("../../conf/routes.yaml")
	require.NoError(t, err)
	var doc struct {
		Routes []routeEntry `yaml:"routes"`
	}
	require.NoError(t, yaml.Unmarshal(raw, &doc))
	e := healthy(t)
	checked := 0
	for _, r := range doc.Routes {
		if r.Owner != "go" || r.Match != "exact" || r.Auth == "" || r.Auth == "none" {
			continue
		}
		checked++
		w := do(e, http.MethodGet, r.Path, nil)
		if w.Code == http.StatusOK {
			assert.NotNil(t, r.PublicUntilPhase, "%s is auth=%s, answers 200 unauthenticated, and has no public_until_phase marker", r.Path, r.Auth)
		}
	}
	assert.GreaterOrEqual(t, checked, 2)
}

func TestVersionRequiresAuthentication(t *testing.T) {
	e := healthy(t)
	w := do(e, http.MethodGet, "/api/v1/system/version", nil)
	assert.Equal(t, http.StatusUnauthorized, w.Code)
	assert.Equal(t, `{"code":401,"message":"unauthorized","data":null}`, w.Body.String())
	assert.Equal(t, "go", w.Header().Get("X-API-Source"))
	assert.Equal(t, http.StatusOK, do(e, http.MethodGet, "/api/v1/system/version", authed).Code)
}

func TestEngineWithoutResolverDeniesEveryProtectedRoute(t *testing.T) {
	core, _ := observer.New(zapcore.DebugLevel)
	e := NewEngine(server.Config{}, zap.New(core), handler.NewSystem(service.NewSystem(pinger{}, pinger{}, settings{value: "0002"})))
	assert.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, "/api/v1/system/version", authed).Code)
	assert.Equal(t, http.StatusOK, do(e, http.MethodGet, "/health", nil).Code)
}

func TestInfrastructureErrorFromResolverIs503Not401(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{value: "0002"}, nil, WithAuth(stubResolver{err: errors.New("sql: database is closed")}))
	w := do(e, http.MethodGet, "/api/v1/system/version", authed)
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Equal(t, `{"code":503,"message":"service unavailable","data":null}`, w.Body.String())
}

func TestRequestLogNeverContainsCredentials(t *testing.T) {
	e, logs := build(t, pinger{}, pinger{}, settings{value: "0002"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/system/version", nil)
	req.Header.Set("Authorization", "Bearer "+stubToken)
	req.AddCookie(&http.Cookie{Name: handler.AuthCookieName, Value: "cookie-secret-value-0001"})
	e.ServeHTTP(httptest.NewRecorder(), req)
	require.NotEmpty(t, logs.All())
	for _, entry := range logs.All() {
		line := entry.Message
		for k, v := range entry.ContextMap() {
			line += " " + k + "=" + fmt.Sprint(v)
		}
		for _, secret := range []string{stubToken, "cookie-secret-value-0001", "Bearer", "Authorization"} {
			assert.NotContains(t, line, secret)
		}
	}
}

// fullEngine registers every Go handler the production binary registers, with nil services:
// unauthenticated probes never reach a handler body.
func fullEngine(t *testing.T) *gin.Engine {
	t.Helper()
	e, _ := build(t, pinger{}, pinger{}, settings{value: "0002"}, nil,
		WithAccount(handler.NewAccount(nil, time.Hour)), WithSession(handler.NewUser(nil)),
		WithProfile(handler.NewSettings(nil), handler.NewTenant(nil)), WithPasswordReset(handler.NewPasswordReset(nil)),
		WithTokens(handler.NewToken(nil)), WithTeam(handler.NewTenant(nil)))
	return e
}

type endpointRow struct {
	Method      string `yaml:"method"`
	Path        string `yaml:"path"`
	Owner       string `yaml:"owner"`
	Auth        string `yaml:"auth"`
	Implemented bool   `yaml:"implemented"`
}

func loadEndpoints(t *testing.T) []endpointRow {
	t.Helper()
	raw, err := os.ReadFile("../../conf/routes.yaml")
	require.NoError(t, err)
	var doc struct {
		Endpoints []endpointRow `yaml:"endpoints"`
	}
	require.NoError(t, yaml.Unmarshal(raw, &doc))
	require.NotEmpty(t, doc.Endpoints)
	return doc.Endpoints
}

func ginPath(p string) string {
	return regexp.MustCompile(`\{([a-z_]+)\}`).ReplaceAllString(p, ":$1")
}

// TestEveryEngineRouteIsDeclaredAndGated iterates the real engine's routes (default-deny enumeration).
func TestEveryEngineRouteIsDeclaredAndGated(t *testing.T) {
	e := fullEngine(t)
	declared := map[string]endpointRow{}
	for _, r := range loadEndpoints(t) {
		if r.Owner == "go" {
			declared[r.Method+" "+ginPath(r.Path)] = r
		}
	}
	engine := map[string]bool{}
	var undeclared []string
	for _, r := range e.Routes() {
		key := r.Method + " " + r.Path
		engine[key] = true
		row, ok := declared[key]
		if !ok || !row.Implemented {
			undeclared = append(undeclared, key)
			continue
		}
		if row.Auth == "none" {
			continue
		}
		w := do(e, r.Method, strings.NewReplacer(":token", "t", ":tenant_id", "t", ":user_id", "u").Replace(r.Path), nil)
		assert.Equal(t, http.StatusUnauthorized, w.Code, key)
		assert.Equal(t, `{"code":401,"message":"unauthorized","data":null}`, w.Body.String(), key)
	}
	assert.Empty(t, undeclared, "engine routes without an implemented registry row")
	for key, row := range declared {
		if row.Implemented {
			assert.True(t, engine[key], "registry row %s is marked implemented but the engine has no such route", key)
		}
	}
	t.Logf("enumerated %d engine routes, %d undeclared", len(e.Routes()), len(undeclared))
}

func TestUndeclaredHandlerWouldBeCaught(t *testing.T) {
	e, _ := build(t, pinger{}, pinger{}, settings{}, nil, WithExtraRoutes(func(e *gin.Engine) {
		e.GET("/v1/user/sneaky", func(c *gin.Context) { common.OK(c, "leak") })
	}))
	assert.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, "/v1/user/sneaky", nil).Code, "a handler without a row is denied by default")
	declared := map[string]bool{}
	for _, r := range loadEndpoints(t) {
		declared[r.Method+" "+ginPath(r.Path)] = true
	}
	found := false
	for _, r := range e.Routes() {
		if !declared[r.Method+" "+r.Path] {
			found = true
		}
	}
	assert.True(t, found, "the enumeration predicate must flag a route that has no registry row")
}

func TestEveryGoFamilyIsDeniedUnlessPublic(t *testing.T) {
	raw, err := os.ReadFile("../../conf/routes.yaml")
	require.NoError(t, err)
	var doc struct {
		Routes []routeEntry `yaml:"routes"`
	}
	require.NoError(t, yaml.Unmarshal(raw, &doc))
	e := fullEngine(t)
	checked := 0
	for _, r := range doc.Routes {
		if r.Owner != "go" || r.Auth == "none" {
			continue
		}
		path := r.Path
		if r.Match == "prefix" {
			path += "prefixprobe-0b8f3c1e"
		}
		checked++
		assert.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, path, nil).Code, "%s %s", r.Match, r.Path)
	}
	assert.GreaterOrEqual(t, checked, 8)
}

// fakeTokenStore is a unit-tier TokenStore: it holds no rows, so every delete is not-found.
type fakeTokenStore struct{}

func (fakeTokenStore) CreateAPIToken(context.Context, entity.APIToken, int) error { return nil }
func (fakeTokenStore) ListAPITokens(context.Context, string, int, int) ([]entity.APIToken, error) {
	return nil, nil
}
func (fakeTokenStore) DeleteAPIToken(context.Context, string, string) (bool, error) {
	return false, nil
}

type fakeCounter struct{}

func (fakeCounter) Incr(context.Context, string, time.Duration) (int64, time.Duration, error) {
	return 1, time.Hour, nil
}
func (fakeCounter) Count(context.Context, string) (int64, time.Duration, error) { return 0, 0, nil }
func (fakeCounter) Delete(context.Context, string) error                        { return nil }

func tokenEngine(t *testing.T) (*gin.Engine, *observer.ObservedLogs) {
	t.Helper()
	svc := service.NewToken(fakeTokenStore{}, service.NewLimiter(fakeCounter{}, "t"), service.DefaultTokenLimits())
	return build(t, pinger{}, pinger{}, settings{}, nil, WithTokens(handler.NewToken(svc)))
}

func allLogText(logs *observer.ObservedLogs) string {
	var b strings.Builder
	for _, entry := range logs.All() {
		b.WriteString(entry.Message)
		for k, v := range entry.ContextMap() {
			b.WriteString(" " + k + "=" + fmt.Sprint(v))
		}
		b.WriteString("\n")
	}
	return b.String()
}

func TestTokenDeleteLogsTheRouteTemplateNotTheToken(t *testing.T) {
	const secret = "ragflow-test-only-path-token-0000000000000000"
	e, logs := tokenEngine(t)
	for name, c := range map[string]struct {
		method string
		hdr    map[string]string
		status int
	}{
		"authenticated delete":   {http.MethodDelete, authed, http.StatusNotFound},
		"unauthenticated delete": {http.MethodDelete, nil, http.StatusUnauthorized},
		"method not allowed":     {http.MethodGet, authed, http.StatusMethodNotAllowed},
	} {
		w := do(e, c.method, "/api/v1/system/tokens/"+secret, c.hdr)
		assert.Equal(t, c.status, w.Code, name)
	}
	text := allLogText(logs)
	assert.NotContains(t, text, secret)
	assert.NotContains(t, text, "path-token")
	assert.Contains(t, text, "/api/v1/system/tokens/:token", "the route template is what gets logged")
	entry := logs.FilterMessage("request").All()[0].ContextMap()
	assert.Equal(t, "/api/v1/system/tokens/:token", entry["path"])
}

func TestRequestLogRedactsTokenAndBetaFields(t *testing.T) {
	core, logs := observer.New(zapcore.DebugLevel)
	log := zap.New(common.WrapRedacting(core))
	log.Info("created", zap.String("token", "ragflow-test-only-0001"), zap.String("beta", "0123456789abcdef0123456789abcdef"),
		zap.String("detail", `body {"token":"ragflow-test-only-0002","beta":"fedcba9876543210fedcba9876543210"} authorization: Bearer ragflow-test-only-0003`))
	text := allLogText(logs)
	for _, secret := range []string{"ragflow-test-only-0001", "0123456789abcdef0123456789abcdef", "ragflow-test-only-0002", "fedcba9876543210fedcba9876543210", "ragflow-test-only-0003"} {
		assert.NotContains(t, text, secret)
	}
}
