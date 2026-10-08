//go:build integration

package router

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/dao"
	"devrag/internal/handler"
	"devrag/internal/service"
	"devrag/internal/testutil"
)

type teamRig struct {
	engine *gin.Engine
	db     *dao.DB
	raw    *gorm.DB
	emails []string
}

// newTeamRig serves the account, session and team routes over the real database. perWindow is the
// invite limit; redisDown points the limiter at a closed port.
func newTeamRig(t *testing.T, perWindow int, redisDown bool) *teamRig {
	t.Helper()
	cfg := testutil.RequireDB(t)
	cfg.RateLimit.RegisterPerIP, cfg.RateLimit.LoginPerIP = 1000, 1000
	cfg.Auth.RegisterEnabled = true
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db, err := dao.OpenDB(ctx, cfg.MySQL)
	require.NoError(t, err)
	rcfg := cfg.Redis
	rd := dao.OpenRedis(rcfg)
	inviteRedis := rd
	if redisDown {
		down := cfg.Redis
		down.Port = 1
		inviteRedis = dao.OpenRedis(down)
	}
	raw, err := gorm.Open(mysql.Open(dao.DSN(cfg.MySQL)), &gorm.Config{Logger: logger.Discard})
	require.NoError(t, err)
	sys := service.NewSystem(db, rd, db).WithRegisterEnabled(true)
	acct := service.NewAccount(db, service.NewLimiter(rd, "test-"+testutil.UniqueName("acct")), cfg)
	auth := service.NewAuth(db, cfg.Security.SecretKey, cfg.Security.TokenMaxAge)
	tenants := handler.NewTenant(service.NewTenant(db).WithInvites(
		service.NewLimiter(inviteRedis, "test-"+testutil.UniqueName("inv")), service.InviteLimits{PerWindow: perWindow, Window: time.Minute}))
	e := NewEngine(cfg, zap.NewNop(), handler.NewSystem(sys), WithAuth(auth),
		WithAccount(handler.NewAccount(acct, cfg.Security.TokenMaxAge)), WithSession(handler.NewUser(auth)), WithTeam(tenants))
	rig := &teamRig{engine: e, db: db, raw: raw}
	t.Cleanup(func() {
		for _, em := range rig.emails {
			var id string
			if raw.Raw("SELECT id FROM user WHERE email = ?", em).Scan(&id).Error == nil && id != "" {
				for _, q := range []string{"DELETE FROM user_tenant WHERE tenant_id = ?", "DELETE FROM user_tenant WHERE user_id = ?", "DELETE FROM tenant WHERE id = ?", "DELETE FROM user WHERE id = ?"} {
					_ = raw.Exec(q, id).Error
				}
			}
		}
		_ = db.Close()
		_ = rd.Close()
		if redisDown {
			_ = inviteRedis.Close()
		}
	})
	return rig
}

func (r *teamRig) do(method, path, token string, body any) *httptest.ResponseRecorder {
	var raw []byte
	if body != nil {
		raw, _ = json.Marshal(body)
	}
	req := httptest.NewRequest(method, path, bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	req.RemoteAddr = "198.51.100.9:1000"
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	return w
}

// account registers and logs in, returning the user id (also the tenant id) and the session token.
func (r *teamRig) account(t *testing.T) (email, id, token string) {
	t.Helper()
	email = testutil.UniqueEmail("tr")
	r.emails = append(r.emails, email)
	w := r.do(http.MethodPost, "/api/v1/users", "", map[string]string{"email": email, "password": testutil.FixtureCredential(), "nickname": "nick"})
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	w = r.do(http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": email, "password": testutil.FixtureCredential()})
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var env struct {
		Data struct {
			Token string `json:"token"`
			User  struct {
				ID string `json:"id"`
			} `json:"user"`
		} `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	require.NoError(t, r.raw.Raw("SELECT id FROM user WHERE email = ?", email).Scan(&id).Error)
	return email, id, env.Data.Token
}

func TestInviteIsRateLimitedWith429AndRetryAfter(t *testing.T) {
	r := newTeamRig(t, 2, false)
	_, id, token := r.account(t)
	path := "/api/v1/tenants/" + id + "/users"
	for i := 0; i < 2; i++ {
		w := r.do(http.MethodPost, path, token, map[string]string{"email": testutil.UniqueEmail("nobody")})
		require.Equal(t, http.StatusNotFound, w.Code, w.Body.String())
	}
	w := r.do(http.MethodPost, path, token, map[string]string{"email": testutil.UniqueEmail("nobody")})
	assert.Equal(t, http.StatusTooManyRequests, w.Code, w.Body.String())
	secs, err := strconv.Atoi(w.Header().Get("Retry-After"))
	require.NoError(t, err)
	assert.Positive(t, secs)
}

func TestInviteFailsClosedWith503WhenRedisIsDown(t *testing.T) {
	r := newTeamRig(t, 5, true)
	_, id, token := r.account(t)
	w := r.do(http.MethodPost, "/api/v1/tenants/"+id+"/users", token, map[string]string{"email": testutil.UniqueEmail("nobody")})
	assert.Equal(t, http.StatusServiceUnavailable, w.Code, w.Body.String())
	assert.NotContains(t, w.Body.String(), "redis")
}

func TestTeamRoutesAnswer503WhenTheDatabaseIsDown(t *testing.T) {
	r := newTeamRig(t, 5, false)
	_, id, token := r.account(t)
	require.NoError(t, r.db.Close())
	for _, c := range []struct{ method, path string }{
		{http.MethodGet, "/api/v1/tenants/" + id + "/users"},
		{http.MethodPost, "/api/v1/tenants/" + id + "/users"},
		{http.MethodPatch, "/api/v1/tenants/" + id},
		{http.MethodPatch, "/api/v1/tenants/" + id + "/users/" + id},
		{http.MethodDelete, "/api/v1/tenants/" + id + "/users"},
	} {
		w := r.do(c.method, c.path, token, map[string]string{"email": "a@example.test", "role": "admin", "user_id": id})
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, c.method+" "+w.Body.String())
		assert.NotContains(t, w.Body.String(), "sql")
	}
}

func TestTeamBodiesAreBoundedAndValidated(t *testing.T) {
	r := newTeamRig(t, 50, false)
	_, id, token := r.account(t)
	path := "/api/v1/tenants/" + id + "/users"
	big := map[string]string{"email": "a@example.test", "pad": string(bytes.Repeat([]byte("x"), 4000))}
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.do(http.MethodPost, path, token, big).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.do(http.MethodPatch, "/api/v1/tenants/"+id, token, big).Code)
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader([]byte("{not json")))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	r.engine.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.Equal(t, http.StatusBadRequest, r.do(http.MethodPatch, "/api/v1/tenants/"+id, token, map[string]string{"action": "promote"}).Code)
	assert.Equal(t, http.StatusBadRequest, r.do(http.MethodGet, path+"?page=abc", token, nil).Code)
	assert.Equal(t, http.StatusBadRequest, r.do(http.MethodGet, path+"?page_size=1000", token, nil).Code)
	assert.Equal(t, http.StatusOK, r.do(http.MethodGet, path, token, nil).Code)
}

func TestRoleChangeAndRemovalBodiesAreBoundedAndValidated(t *testing.T) {
	r := newTeamRig(t, 50, false)
	_, id, token := r.account(t)
	users := "/api/v1/tenants/" + id + "/users"
	one := users + "/" + id
	big := map[string]string{"role": "admin", "user_id": id, "pad": string(bytes.Repeat([]byte("x"), 4000))}
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.do(http.MethodPatch, one, token, big).Code)
	assert.Equal(t, http.StatusRequestEntityTooLarge, r.do(http.MethodDelete, users, token, big).Code)
	for _, method := range []string{http.MethodPatch, http.MethodDelete} {
		path := one
		if method == http.MethodDelete {
			path = users
		}
		req := httptest.NewRequest(method, path, bytes.NewReader([]byte("{not json")))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		r.engine.ServeHTTP(w, req)
		assert.Equal(t, http.StatusBadRequest, w.Code, method)
	}
	assert.Equal(t, http.StatusBadRequest, r.do(http.MethodPatch, one, token, map[string]any{"role": 7}).Code)
	assert.Equal(t, http.StatusBadRequest, r.do(http.MethodDelete, users, token, map[string]any{"user_id": 7}).Code)
	// the owner naming themselves is refused with a clear 400 and nothing changes
	w := r.do(http.MethodDelete, users, token, map[string]string{"user_id": id})
	assert.Equal(t, http.StatusBadRequest, w.Code, w.Body.String())
	w = r.do(http.MethodPatch, one, token, map[string]string{"role": "normal"})
	assert.Equal(t, http.StatusBadRequest, w.Code, w.Body.String())
	assert.Equal(t, http.StatusOK, r.do(http.MethodGet, users, token, nil).Code)
}

func TestRoleChangeAndRemovalAreRateLimitedWith429(t *testing.T) {
	r := newTeamRig(t, 2, false)
	_, id, token := r.account(t)
	for i := 0; i < 2; i++ {
		w := r.do(http.MethodPatch, "/api/v1/tenants/"+id+"/users/"+testutil.UniqueName("x"), token, map[string]string{"role": "admin"})
		require.Equal(t, http.StatusNotFound, w.Code, w.Body.String())
	}
	w := r.do(http.MethodDelete, "/api/v1/tenants/"+id+"/users", token, map[string]string{"user_id": testutil.UniqueName("x")})
	assert.Equal(t, http.StatusTooManyRequests, w.Code, w.Body.String())
	assert.NotEmpty(t, w.Header().Get("Retry-After"))
}

func TestRoleChangeFailsClosedWith503WhenRedisIsDown(t *testing.T) {
	r := newTeamRig(t, 5, true)
	_, id, token := r.account(t)
	w := r.do(http.MethodPatch, "/api/v1/tenants/"+id+"/users/"+testutil.UniqueName("x"), token, map[string]string{"role": "admin"})
	assert.Equal(t, http.StatusServiceUnavailable, w.Code, w.Body.String())
	w = r.do(http.MethodDelete, "/api/v1/tenants/"+id+"/users", token, map[string]string{"user_id": testutil.UniqueName("x")})
	assert.Equal(t, http.StatusServiceUnavailable, w.Code, w.Body.String())
}

// WR-06: an out-of-range page is a 400 envelope for the member list, never a 503 from an overflowed offset.
func TestOutOfRangePagesAreBadRequestsNotUnavailable(t *testing.T) {
	r := newTeamRig(t, 50, false)
	_, id, token := r.account(t)
	for _, base := range []string{"/api/v1/tenants/" + id + "/users"} {
		for _, q := range []string{"?page=9223372036854775807&page_size=100", "?page=100001&page_size=1", "?page=99999999999999999999", "?page=0", "?page=-5&page_size=10"} {
			w := r.do(http.MethodGet, base+q, token, nil)
			assert.Equal(t, http.StatusBadRequest, w.Code, base+q)
			assert.Contains(t, w.Body.String(), `"code":101`, base+q)
		}
		assert.Equal(t, http.StatusOK, r.do(http.MethodGet, base+"?page=100000&page_size=100", token, nil).Code, base)
	}
}
