//go:build e2e

package e2e

import (
	"context"
	"net/http"
	"strings"
	"testing"
	"time"

	"devrag/internal/testutil"
)

func authed(t *testing.T, method, path, token string, hdr map[string]string) (*http.Response, []byte) {
	t.Helper()
	req, err := http.NewRequestWithContext(context.Background(), method, baseURL()+path, nil)
	if err != nil {
		t.Fatal(err)
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := (&http.Client{Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}).Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	var sb strings.Builder
	buf := make([]byte, 4096)
	for {
		n, rerr := resp.Body.Read(buf)
		sb.Write(buf[:n])
		if rerr != nil {
			break
		}
	}
	return resp, []byte(sb.String())
}

func TestLoginProtectedCallLogoutThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)

	for _, p := range []string{"/v1/user/info", "/api/v1/system/version"} {
		resp, _ := authed(t, http.MethodGet, p, "", nil)
		if resp.StatusCode != http.StatusUnauthorized || resp.Header.Get("X-API-Source") != "go" {
			t.Errorf("%s without token: status %d source %q", p, resp.StatusCode, resp.Header.Get("X-API-Source"))
		}
		resp, body := authed(t, http.MethodGet, p, acc.Token, nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("%s with token: status %d %s", p, resp.StatusCode, body)
		}
	}
	// Public routes used by the container healthcheck stay public.
	for _, p := range []string{"/health", "/api/v1/system/healthz"} {
		if resp, _ := authed(t, http.MethodGet, p, "", nil); resp.StatusCode != http.StatusOK {
			t.Errorf("%s must stay public, got %d", p, resp.StatusCode)
		}
	}
	// Cookie-only unsafe request without a same-origin Origin is refused.
	req, _ := http.NewRequestWithContext(context.Background(), http.MethodPost, baseURL()+"/api/v1/auth/logout", nil)
	req.AddCookie(&http.Cookie{Name: "ragflow_auth", Value: acc.Token})
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Errorf("cookie-only logout without Origin: status %d, want 403", resp.StatusCode)
	}

	resp, body := authed(t, http.MethodPost, "/api/v1/auth/logout", acc.Token, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("logout: %d %s", resp.StatusCode, body)
	}
	for _, p := range []string{"/v1/user/info", "/api/v1/system/version"} {
		if resp, _ := authed(t, http.MethodGet, p, acc.Token, nil); resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("%s after logout: status %d, want 401", p, resp.StatusCode)
		}
	}
}
