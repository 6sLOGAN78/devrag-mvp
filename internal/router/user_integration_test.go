//go:build integration

package router

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/entity"
	"devrag/internal/testutil"
)

const newCredential = "brand-new-pass-0002"

type session struct {
	email, token, id string
}

func (r *accountRig) signUp(t *testing.T, prefix string) session {
	t.Helper()
	email := testutil.UniqueEmail(prefix)
	r.register(t, email)
	w := r.post("/api/v1/auth/login", map[string]string{"email": email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
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
	return session{email: email, token: env.Data.Token, id: env.Data.User.ID}
}

func (r *accountRig) call(method, path, token string, body any) *httptest.ResponseRecorder {
	var raw []byte
	switch b := body.(type) {
	case nil:
	case string:
		raw = []byte(b)
	default:
		raw, _ = json.Marshal(b)
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

func (r *accountRig) user(t *testing.T, id string) entity.User {
	t.Helper()
	var u entity.User
	require.NoError(t, r.raw.First(&u, "id = ?", id).Error)
	return u
}

func pngURL(n int) string {
	b := append([]byte{0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}, bytes.Repeat([]byte{1}, n)...)
	return "data:image/png;base64," + base64.StdEncoding.EncodeToString(b)
}

// assertNoSecrets is the DTO leak check applied to every response of this plan.
func assertNoSecrets(t *testing.T, label string, w *httptest.ResponseRecorder, tokens ...string) {
	t.Helper()
	body := w.Body.String()
	for _, banned := range []string{`"password"`, "access_token", "pbkdf2", "INVALID_", testutil.FixtureCredential(), newCredential} {
		assert.NotContains(t, body, banned, label)
	}
	for _, tok := range tokens {
		if tok != "" {
			assert.NotContains(t, body, tok, label)
		}
	}
	assert.NotContains(t, strings.Join(w.Header().Values("Set-Cookie"), ";"), "password", label)
}

func TestSettingUpdatesOnlyTheAllowedFieldsOfTheCaller(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me, other := r.signUp(t, "me"), r.signUp(t, "other")
	beforeMe, beforeOther := r.user(t, me.id), r.user(t, other.id)

	w := r.call(http.MethodPost, "/v1/user/setting", me.token, map[string]any{
		"nickname": "Grace Hopper", "language": "zh", "color_schema": "Dark",
		"id": other.id, "tenant_id": other.id, "email": "hijack@example.test", "is_superuser": true, "status": "0",
		"password": "attacker-chosen-pass", "access_token": "attacker-token", "user_id": other.id, "role": "admin",
	})
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assertNoSecrets(t, "setting", w, me.token)

	afterMe, afterOther := r.user(t, me.id), r.user(t, other.id)
	assert.Equal(t, "Grace Hopper", afterMe.Nickname)
	assert.Equal(t, "zh", *afterMe.Language)
	assert.Equal(t, "Dark", *afterMe.ColorSchema)
	assert.Equal(t, beforeMe.ID, afterMe.ID)
	assert.Equal(t, beforeMe.Email, afterMe.Email)
	assert.Equal(t, beforeMe.IsSuperuser, afterMe.IsSuperuser)
	assert.Equal(t, beforeMe.Status, afterMe.Status)
	assert.Equal(t, beforeMe.Password, afterMe.Password)
	assert.Equal(t, beforeMe.AccessToken, afterMe.AccessToken)
	assert.Equal(t, beforeOther, afterOther, "another user's row is untouched")
	assert.Equal(t, http.StatusOK, r.call(http.MethodGet, "/v1/user/info", me.token, nil).Code, "the session survives a profile edit")
}

func TestSettingValidationErrorsAre400WithoutInternals(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "val")
	before := r.user(t, me.id)
	for name, body := range map[string]any{
		"language":     map[string]string{"language": "fr"},
		"nickname":     map[string]string{"nickname": strings.Repeat("x", 65)},
		"colour":       map[string]string{"color_schema": "Neon"},
		"empty":        map[string]string{},
		"not json":     "{nope",
		"avatar svg":   map[string]string{"avatar": "data:image/svg+xml;base64," + base64.StdEncoding.EncodeToString([]byte("<svg onload=alert(1)/>"))},
		"avatar html":  map[string]string{"avatar": "data:image/png;base64," + base64.StdEncoding.EncodeToString([]byte("<html><script>x</script></html>"))},
		"avatar big":   map[string]string{"avatar": pngURL(256*1024 + 1)},
		"avatar a url": map[string]string{"avatar": "https://evil.example.test/a.png"},
	} {
		w := r.call(http.MethodPost, "/v1/user/setting", me.token, body)
		assert.Equal(t, http.StatusBadRequest, w.Code, name+" "+w.Body.String())
		assert.EqualValues(t, 101, decode(t, w).Code, name)
		for _, leak := range []string{"script", "gorm", "sql", "panic", "goroutine"} {
			assert.NotContains(t, strings.ToLower(w.Body.String()), leak, name)
		}
	}
	assert.Equal(t, before, r.user(t, me.id), "nothing was written")
}

func TestSettingBodyCapIs400KB(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "cap")
	big := `{"nickname":"` + strings.Repeat("a", 401*1024) + `"}`
	w := r.call(http.MethodPost, "/v1/user/setting", me.token, big)
	assert.Equal(t, http.StatusRequestEntityTooLarge, w.Code)
	assert.EqualValues(t, 400, decode(t, w).Code)
	// a maximum-size avatar fits inside the cap
	w = r.call(http.MethodPost, "/v1/user/setting", me.token, map[string]string{"avatar": pngURL(256*1024 - 8)})
	assert.Equal(t, http.StatusOK, w.Code, w.Body.String())
}

func TestAvatarRoundTripsThroughInfoAsPlainData(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "avi")
	url := pngURL(512)
	require.Equal(t, http.StatusOK, r.call(http.MethodPost, "/v1/user/setting", me.token, map[string]string{"avatar": url}).Code)
	w := r.call(http.MethodGet, "/v1/user/info", me.token, nil)
	require.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Header().Get("Content-Type"), "application/json")
	var env struct {
		Data struct {
			Avatar string `json:"avatar"`
		} `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &env))
	assert.Equal(t, url, env.Data.Avatar)
	require.Equal(t, http.StatusOK, r.call(http.MethodPost, "/v1/user/setting", me.token, map[string]string{"avatar": ""}).Code)
	assert.Empty(t, r.user(t, me.id).Avatar)
}

func TestPasswordChangeFlowSignsEveryDeviceOut(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "pw")
	second := r.post("/api/v1/auth/login", map[string]string{"email": me.email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	require.Equal(t, http.StatusOK, second.Code)
	require.Equal(t, http.StatusOK, r.call(http.MethodGet, "/v1/user/info", me.token, nil).Code)

	// wrong current password: 400, not 401, the session survives
	w := r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": "wrong-current-pass", "new_password": newCredential})
	assert.Equal(t, http.StatusBadRequest, w.Code, w.Body.String())
	assert.Empty(t, w.Result().Cookies())
	assert.Equal(t, http.StatusOK, r.call(http.MethodGet, "/v1/user/info", me.token, nil).Code)
	// length rules
	for _, pw := range []string{"abcdefg", strings.Repeat("a", 129)} {
		w = r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": testutil.FixtureCredential(), "new_password": pw})
		assert.Equal(t, http.StatusBadRequest, w.Code)
	}

	w = r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": testutil.FixtureCredential(), "new_password": newCredential})
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assertNoSecrets(t, "password change", w, me.token)
	cookies := w.Result().Cookies()
	require.Len(t, cookies, 1)
	assert.Equal(t, "ragflow_auth", cookies[0].Name)
	assert.Empty(t, cookies[0].Value)
	assert.Negative(t, cookies[0].MaxAge, "the cookie is expired")
	assert.True(t, cookies[0].HttpOnly)
	assert.Equal(t, "no-store", w.Header().Get("Cache-Control"))

	assert.Equal(t, http.StatusUnauthorized, r.call(http.MethodGet, "/v1/user/info", me.token, nil).Code, "the old token is dead")
	stale := r.post("/api/v1/auth/login", map[string]string{"email": me.email, "password": testutil.FixtureCredential()}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusUnauthorized, stale.Code, "the old password fails")
	fresh := r.post("/api/v1/auth/login", map[string]string{"email": me.email, "password": newCredential}, "198.51.100.9:1000", nil)
	assert.Equal(t, http.StatusOK, fresh.Code)
}

func TestPasswordChangeBodyCapAndMassAssignment(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me, other := r.signUp(t, "pwcap"), r.signUp(t, "pwoth")
	beforeOther := r.user(t, other.id)
	w := r.call(http.MethodPost, "/v1/user/setting/password", me.token, `{"old_password":"`+strings.Repeat("a", 3*1024)+`","new_password":"x"}`)
	assert.Equal(t, http.StatusRequestEntityTooLarge, w.Code)

	// ids in the body never select another account
	w = r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]any{
		"old_password": testutil.FixtureCredential(), "new_password": newCredential, "id": other.id, "user_id": other.id, "email": other.email,
	})
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assert.Equal(t, beforeOther, r.user(t, other.id), "another account is untouched")
	// the other account's token is still valid
	assert.Equal(t, http.StatusOK, r.call(http.MethodGet, "/v1/user/info", other.token, nil).Code)
}

func TestPasswordChangeIsRateLimitedPerUser(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "pwrl")
	for i := 0; i < r.cfg.RateLimit.LoginFailuresPerEmail; i++ {
		w := r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": "wrong-current-pass", "new_password": newCredential})
		require.Equal(t, http.StatusBadRequest, w.Code)
	}
	w := r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": testutil.FixtureCredential(), "new_password": newCredential})
	assert.Equal(t, http.StatusTooManyRequests, w.Code)
	assert.EqualValues(t, 400, decode(t, w).Code)
	assert.Regexp(t, `^\d+$`, w.Header().Get("Retry-After"))
}

func TestPasswordsNeverAppearInRequestLogs(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me := r.signUp(t, "pwlog")
	r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": "wrong-current-pass", "new_password": newCredential})
	r.call(http.MethodPost, "/v1/user/setting/password", me.token, map[string]string{"old_password": testutil.FixtureCredential(), "new_password": newCredential})
	require.NotEmpty(t, r.logs.All())
	sawRequest := false
	for _, e := range r.logs.All() {
		line := e.Message
		for _, f := range e.Context {
			line += " " + f.Key + "=" + f.String
		}
		if strings.Contains(line, "/v1/user/setting/password") {
			sawRequest = true
		}
		for _, secret := range []string{testutil.FixtureCredential(), newCredential, "wrong-current-pass", me.token} {
			assert.NotContains(t, line, secret)
		}
	}
	assert.True(t, sawRequest, "the request line itself was logged")
}

func TestTenantInfoAndListReturnOnlyTheCallersOwnData(t *testing.T) {
	r := newAccountRig(t, nil, false)
	me, owner, stranger := r.signUp(t, "tm"), r.signUp(t, "to"), r.signUp(t, "ts")
	ms := int64(1_700_000_000_000)
	status := "1"
	require.NoError(t, r.raw.Create(&entity.UserTenant{ID: testutil.UniqueName("ut"), UserID: me.id, TenantID: owner.id, InvitedBy: owner.id, Role: "invite", Status: &status, CreateTime: &ms}).Error)

	w := r.call(http.MethodGet, "/v1/user/tenant_info", me.token, nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assertNoSecrets(t, "tenant_info", w, me.token)
	var info struct {
		Data map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &info))
	assert.Equal(t, me.id, info.Data["tenant_id"])
	for _, k := range []string{"llm_id", "embd_id", "rerank_id", "asr_id", "img2txt_id", "tts_id"} {
		v, present := info.Data[k]
		assert.True(t, present, k)
		assert.IsType(t, "", v, k)
	}
	assert.NotContains(t, w.Body.String(), owner.id)
	assert.NotContains(t, w.Body.String(), stranger.id)

	w = r.call(http.MethodGet, "/v1/tenant/list", me.token, nil)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	assertNoSecrets(t, "tenant list", w, me.token)
	var list struct {
		Data []map[string]any `json:"data"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &list))
	require.Len(t, list.Data, 2)
	roles := map[string]string{}
	for _, m := range list.Data {
		roles[m["role"].(string)] = m["tenant_id"].(string)
		assert.NotContains(t, m, "email", "no other user's email in a membership")
	}
	assert.Equal(t, me.id, roles["owner"])
	assert.Equal(t, owner.id, roles["invite"])
	assert.NotContains(t, w.Body.String(), stranger.id)
}

func TestEveryProfileRouteRequiresAuthentication(t *testing.T) {
	r := newAccountRig(t, nil, false)
	for _, rt := range []struct{ method, path string }{
		{http.MethodPost, "/v1/user/setting"}, {http.MethodPost, "/v1/user/setting/password"},
		{http.MethodGet, "/v1/user/tenant_info"}, {http.MethodGet, "/v1/tenant/list"},
	} {
		w := r.call(rt.method, rt.path, "", "{}")
		assert.Equal(t, http.StatusUnauthorized, w.Code, rt.path)
		assert.Equal(t, `{"code":401,"message":"unauthorized","data":null}`, w.Body.String())
		w = r.call(rt.method, rt.path, "garbage-token", "{}")
		assert.Equal(t, http.StatusUnauthorized, w.Code, rt.path)
	}
}
