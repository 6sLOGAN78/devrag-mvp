//go:build e2e

package e2e

import (
	"bytes"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"devrag/internal/common"
	"devrag/internal/testutil"
)

func postBody(t *testing.T, path string, body map[string]string) (*http.Response, []byte) {
	t.Helper()
	raw, _ := json.Marshal(body)
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Post(baseURL()+path, "application/json", bytes.NewReader(raw))
	if err != nil {
		t.Fatalf("POST %s: %v", path, err)
	}
	defer resp.Body.Close()
	var buf bytes.Buffer
	_, _ = buf.ReadFrom(resp.Body)
	return resp, buf.Bytes()
}

func TestRegisterAndLoginThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)

	if acc.TenantID != acc.UserID {
		t.Errorf("tenant id %q must equal user id %q", acc.TenantID, acc.UserID)
	}
	if _, err := common.VerifyAccessToken(acc.Token, cfg.Security.SecretKey, common.AccessTokenMaxAge, time.Now()); err != nil {
		t.Errorf("login token does not verify: %v", err)
	}

	resp, body := postBody(t, "/api/v1/auth/login", map[string]string{"email": acc.Email, "password": acc.Password})
	if resp.StatusCode != http.StatusOK || resp.Header.Get("X-API-Source") != "go" {
		t.Fatalf("login: status %d source %q", resp.StatusCode, resp.Header.Get("X-API-Source"))
	}
	for _, banned := range []string{`"password"`, `"access_token"`, "pbkdf2"} {
		if strings.Contains(string(body), banned) {
			t.Errorf("login body contains %q", banned)
		}
	}
	found := false
	for _, c := range resp.Cookies() {
		if c.Name == "ragflow_auth" && c.HttpOnly {
			found = true
		}
	}
	if !found {
		t.Error("no HttpOnly ragflow_auth cookie")
	}
}

func TestLoginFailureIsGenericThroughIngress(t *testing.T) {
	waitReady(t)
	r1, b1 := postBody(t, "/api/v1/auth/login", map[string]string{"email": testutil.UniqueEmail("ghost"), "password": "wrong-password-1"})
	if r1.StatusCode != http.StatusUnauthorized || !strings.Contains(string(b1), "Email or password is incorrect") {
		t.Errorf("unexpected failure response %d %s", r1.StatusCode, b1)
	}
}
