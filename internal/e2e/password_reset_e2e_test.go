//go:build e2e

package e2e

import (
	"net/http"
	"strconv"
	"strings"
	"testing"

	"devrag/internal/testutil"
)

const (
	forgotPath = "/api/v1/auth/password/forgot/otp"
	verifyPath = "/api/v1/auth/password/forgot/otp/verify"
	resetPath  = "/api/v1/auth/password/reset"
	resetPass  = "reset-new-pass-0003"
)

func wrongCode(code string) string {
	if code == "000000" {
		return "000001"
	}
	return "000000"
}

func TestPasswordResetThroughIngressWithMailpit(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)
	defer testutil.DeleteMailFor(t, acc.Email)

	resp, body := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": acc.Email})
	if resp.StatusCode != http.StatusOK || resp.Header.Get("X-API-Source") != "go" {
		t.Fatalf("forgot: %d source %q %s", resp.StatusCode, resp.Header.Get("X-API-Source"), body)
	}
	if len(resp.Cookies()) != 0 {
		t.Errorf("forgot must not set a cookie: %v", resp.Cookies())
	}
	msg := testutil.WaitForMail(t, acc.Email)
	code := testutil.ExtractCode(t, msg)
	if msg.Subject != "Your devRag password reset code" {
		t.Errorf("subject %q", msg.Subject)
	}
	if strings.Contains(msg.Text, acc.Email) || strings.Contains(msg.Text, acc.Password) {
		t.Error("the message carries more than the code")
	}

	resp, body = send(t, http.MethodPost, verifyPath, "", map[string]string{"email": acc.Email, "otp": code})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("verify: %d %s", resp.StatusCode, body)
	}
	ticket, _ := data(t, body)["reset_ticket"].(string)
	if len(ticket) < 22 {
		t.Fatalf("no reset ticket in %s", body)
	}
	resp, body = send(t, http.MethodPost, resetPath, "", map[string]string{"email": acc.Email, "reset_ticket": ticket, "new_password": resetPass})
	if resp.StatusCode != http.StatusOK || len(resp.Cookies()) != 0 {
		t.Fatalf("reset: %d cookies %v %s", resp.StatusCode, resp.Cookies(), body)
	}
	if strings.Contains(string(body), resetPass) || strings.Contains(string(body), ticket) {
		t.Error("reset response echoes a secret")
	}
	// the old token is dead on Go and on Python (D-08)
	for _, p := range []string{"/v1/user/info", "/api/v1/system/status"} {
		if resp, _ = send(t, http.MethodGet, p, acc.Token, nil); resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("%s with the old token after reset: %d, want 401", p, resp.StatusCode)
		}
	}
	if resp, _ = send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": acc.Email, "password": acc.Password}); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("old password login: %d, want 401", resp.StatusCode)
	}
	resp, body = send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": acc.Email, "password": resetPass})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("new password login: %d", resp.StatusCode)
	}
	fresh, _ := data(t, body)["token"].(string)
	for _, p := range []string{"/v1/user/info", "/api/v1/system/status"} {
		if resp, _ = send(t, http.MethodGet, p, fresh, nil); resp.StatusCode != http.StatusOK {
			t.Errorf("%s with the new token: %d, want 200", p, resp.StatusCode)
		}
	}
	if resp, _ = send(t, http.MethodPost, resetPath, "", map[string]string{"email": acc.Email, "reset_ticket": ticket, "new_password": "yet-another-pass-9"}); resp.StatusCode != http.StatusBadRequest {
		t.Errorf("ticket replay: %d, want 400", resp.StatusCode)
	}
}

func TestForgotResponseForAnUnknownEmailIsByteIdenticalAndSendsNothing(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)
	defer testutil.DeleteMailFor(t, acc.Email)
	ghost := testutil.UniqueEmail("ghost")
	defer testutil.DeleteMailFor(t, ghost)

	realResp, realBody := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": acc.Email})
	ghostResp, ghostBody := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": ghost})
	if realResp.StatusCode != http.StatusOK || ghostResp.StatusCode != realResp.StatusCode {
		t.Fatalf("status real %d ghost %d", realResp.StatusCode, ghostResp.StatusCode)
	}
	if string(realBody) != string(ghostBody) {
		t.Errorf("bodies differ: %q vs %q", realBody, ghostBody)
	}
	testutil.WaitForMail(t, acc.Email)
	testutil.AssertNoMailFor(t, ghost)
}

func TestFiveWrongCodesInvalidateTheRealCodeThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)
	defer testutil.DeleteMailFor(t, acc.Email)
	if resp, body := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": acc.Email}); resp.StatusCode != http.StatusOK {
		t.Fatalf("forgot: %d %s", resp.StatusCode, body)
	}
	code := testutil.ExtractCode(t, testutil.WaitForMail(t, acc.Email))
	for i := 0; i < 5; i++ {
		if resp, _ := send(t, http.MethodPost, verifyPath, "", map[string]string{"email": acc.Email, "otp": wrongCode(code)}); resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("wrong code %d: %d, want 400", i+1, resp.StatusCode)
		}
	}
	if resp, _ := send(t, http.MethodPost, verifyPath, "", map[string]string{"email": acc.Email, "otp": code}); resp.StatusCode != http.StatusBadRequest {
		t.Errorf("the real code after five wrong tries: %d, want 400", resp.StatusCode)
	}
	if resp, _ := send(t, http.MethodPost, resetPath, "", map[string]string{"email": acc.Email, "otp": code, "new_password": resetPass}); resp.StatusCode != http.StatusBadRequest {
		t.Errorf("reset with the destroyed code: %d, want 400", resp.StatusCode)
	}
	if resp, _ := send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": acc.Email, "password": acc.Password}); resp.StatusCode != http.StatusOK {
		t.Errorf("the account is untouched: login %d", resp.StatusCode)
	}
}

func TestForgotIsRateLimitedPerEmailThroughIngress(t *testing.T) {
	waitReady(t)
	ghost := testutil.UniqueEmail("rl-ghost")
	if resp, _ := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": ghost}); resp.StatusCode != http.StatusOK {
		t.Fatalf("first request: %d", resp.StatusCode)
	}
	resp, _ := send(t, http.MethodPost, forgotPath, "", map[string]string{"email": ghost})
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("second request inside the interval: %d, want 429", resp.StatusCode)
	}
	if n, err := strconv.Atoi(resp.Header.Get("Retry-After")); err != nil || n <= 0 || n > 60 {
		t.Errorf("Retry-After %q", resp.Header.Get("Retry-After"))
	}
}
