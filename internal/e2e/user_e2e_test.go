//go:build e2e

package e2e

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"devrag/internal/testutil"
)

const newPassword = "brand-new-pass-0002"

func send(t *testing.T, method, path, token string, body any) (*http.Response, []byte) {
	t.Helper()
	var rd io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		rd = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(context.Background(), method, baseURL()+path, rd)
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	out, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		t.Fatal(err)
	}
	return resp, out
}

func data(t *testing.T, body []byte) map[string]any {
	t.Helper()
	var env struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(body, &env); err != nil {
		t.Fatalf("decode %s: %v", body, err)
	}
	return env.Data
}

func noSecrets(t *testing.T, label string, body []byte) {
	t.Helper()
	for _, banned := range []string{`"password"`, "access_token", "pbkdf2", "INVALID_", testutil.FixtureCredential(), newPassword} {
		if strings.Contains(string(body), banned) {
			t.Errorf("%s response contains %q", label, banned)
		}
	}
}

func pngDataURL() string {
	b := append([]byte{0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}, bytes.Repeat([]byte{1}, 128)...)
	return "data:image/png;base64," + base64.StdEncoding.EncodeToString(b)
}

func TestProfilePasswordAndTenantsThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	testutil.InsertPendingInvite(t, cfg.MySQL, acc.UserID, owner.TenantID, owner.UserID)

	// profile
	resp, body := send(t, http.MethodPost, "/v1/user/setting", acc.Token, map[string]any{
		"nickname": "Edsger Dijkstra", "language": "zh", "avatar": pngDataURL(), "id": owner.UserID, "email": "x@example.test", "is_superuser": true,
	})
	if resp.StatusCode != http.StatusOK || resp.Header.Get("X-API-Source") != "go" {
		t.Fatalf("setting: %d source %q %s", resp.StatusCode, resp.Header.Get("X-API-Source"), body)
	}
	noSecrets(t, "setting", body)
	resp, body = send(t, http.MethodGet, "/v1/user/info", acc.Token, nil)
	info := data(t, body)
	if resp.StatusCode != http.StatusOK || info["nickname"] != "Edsger Dijkstra" || info["language"] != "zh" || info["avatar"] != pngDataURL() || info["id"] != acc.UserID {
		t.Errorf("info after setting: %d %v", resp.StatusCode, info)
	}
	if info["is_superuser"] != false {
		t.Errorf("is_superuser must not be settable: %v", info["is_superuser"])
	}
	noSecrets(t, "info", body)
	svg := "data:image/svg+xml;base64," + base64.StdEncoding.EncodeToString([]byte("<svg onload=alert(1)/>"))
	if resp, _ = send(t, http.MethodPost, "/v1/user/setting", acc.Token, map[string]string{"avatar": svg}); resp.StatusCode != http.StatusBadRequest {
		t.Errorf("svg avatar: status %d, want 400", resp.StatusCode)
	}

	// tenants
	resp, body = send(t, http.MethodGet, "/v1/user/tenant_info", acc.Token, nil)
	ti := data(t, body)
	if resp.StatusCode != http.StatusOK || ti["tenant_id"] != acc.TenantID {
		t.Errorf("tenant_info: %d %v", resp.StatusCode, ti)
	}
	noSecrets(t, "tenant_info", body)
	resp, body = send(t, http.MethodGet, "/v1/tenant/list", acc.Token, nil)
	var list struct {
		Data []map[string]any `json:"data"`
	}
	if err := json.Unmarshal(body, &list); err != nil || resp.StatusCode != http.StatusOK || len(list.Data) != 2 {
		t.Fatalf("tenant list: %d %s", resp.StatusCode, body)
	}
	roles := map[any]any{}
	for _, m := range list.Data {
		roles[m["role"]] = m["tenant_id"]
	}
	if roles["owner"] != acc.TenantID || roles["invite"] != owner.TenantID {
		t.Errorf("tenant list roles: %v", roles)
	}
	noSecrets(t, "tenant list", body)

	// password change: wrong current is 400 and keeps the session
	if resp, _ = send(t, http.MethodPost, "/v1/user/setting/password", acc.Token, map[string]string{"old_password": "wrong-current-pass", "new_password": newPassword}); resp.StatusCode != http.StatusBadRequest {
		t.Errorf("wrong current password: status %d, want 400", resp.StatusCode)
	}
	if resp, _ = send(t, http.MethodGet, "/v1/user/info", acc.Token, nil); resp.StatusCode != http.StatusOK {
		t.Fatalf("session lost after a failed change: %d", resp.StatusCode)
	}
	resp, body = send(t, http.MethodPost, "/v1/user/setting/password", acc.Token, map[string]string{"old_password": acc.Password, "new_password": newPassword})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("password change: %d %s", resp.StatusCode, body)
	}
	noSecrets(t, "password change", body)
	cleared := false
	for _, c := range resp.Cookies() {
		if c.Name == "ragflow_auth" && c.Value == "" && c.MaxAge < 0 {
			cleared = true
		}
	}
	if !cleared {
		t.Error("password change did not clear the ragflow_auth cookie")
	}
	// the old token is dead on Go and on Python
	for _, p := range []string{"/v1/user/info", "/api/v1/system/status"} {
		if resp, _ = send(t, http.MethodGet, p, acc.Token, nil); resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("%s with the old token after a password change: status %d, want 401", p, resp.StatusCode)
		}
	}
	if resp, _ = send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": acc.Email, "password": acc.Password}); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("old password login: status %d, want 401", resp.StatusCode)
	}
	resp, body = send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": acc.Email, "password": newPassword})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("new password login: %d", resp.StatusCode)
	}
	fresh, _ := data(t, body)["token"].(string)
	for _, p := range []string{"/v1/user/info", "/api/v1/system/status"} {
		if resp, _ = send(t, http.MethodGet, p, fresh, nil); resp.StatusCode != http.StatusOK {
			t.Errorf("%s with the new token: status %d, want 200", p, resp.StatusCode)
		}
	}
}

func TestProfileRoutesAreProtectedThroughIngress(t *testing.T) {
	waitReady(t)
	for _, rt := range []struct{ method, path string }{
		{http.MethodPost, "/v1/user/setting"}, {http.MethodPost, "/v1/user/setting/password"},
		{http.MethodGet, "/v1/user/tenant_info"}, {http.MethodGet, "/v1/tenant/list"},
	} {
		resp, body := send(t, rt.method, rt.path, "", map[string]string{})
		if resp.StatusCode != http.StatusUnauthorized || resp.Header.Get("X-API-Source") != "go" || !strings.Contains(string(body), `"code":401`) {
			t.Errorf("%s %s without a token: %d source %q %s", rt.method, rt.path, resp.StatusCode, resp.Header.Get("X-API-Source"), body)
		}
	}
}
