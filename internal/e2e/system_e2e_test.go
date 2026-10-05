//go:build e2e

// Package e2e holds tests that run against the live ingress (`make up` first).
package e2e

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"devrag/internal/common"
	"devrag/internal/testutil"
)

func baseURL() string {
	if v := os.Getenv("E2E_BASE_URL"); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "http://127.0.0.1:8080"
}

func do(t *testing.T, method, path string) (*http.Response, []byte) {
	t.Helper()
	req, err := http.NewRequestWithContext(context.Background(), method, baseURL()+path, nil)
	if err != nil {
		t.Fatal(err)
	}
	client := &http.Client{Timeout: 5 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	return resp, body
}

func waitReady(t *testing.T) {
	t.Helper()
	err := testutil.WaitUntil(context.Background(), 120*time.Second, time.Second, func() bool {
		client := &http.Client{Timeout: 3 * time.Second}
		for _, p := range []string{"/health", "/api/v1/system/healthz"} {
			resp, err := client.Get(baseURL() + p)
			if err != nil {
				return false
			}
			_ = resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				return false
			}
		}
		return true
	})
	if err != nil {
		t.Fatalf("stack not ready at %s (run `make up`): %v", baseURL(), err)
	}
}

func decode(t *testing.T, body []byte) common.Envelope {
	t.Helper()
	var env common.Envelope
	if err := json.Unmarshal(body, &env); err != nil {
		t.Fatalf("body is not an envelope: %v: %s", err, body)
	}
	return env
}

func TestIngressOwnership(t *testing.T) {
	waitReady(t)
	cases := map[string]string{
		"/health":                "go",
		"/api/v1/system/ping":    "go",
		"/api/v1/language":       "go",
		"/system/healthz":        "python",
		"/api/v1/system/healthz": "python",
		"/api/v1/system/status":  "python",
	}
	for path, owner := range cases {
		resp, body := do(t, http.MethodGet, path)
		if resp.StatusCode != http.StatusOK {
			t.Errorf("%s: status %d", path, resp.StatusCode)
		}
		if got := resp.Header.Get("X-API-Source"); got != owner {
			t.Errorf("%s: X-API-Source %q, want %q", path, got, owner)
		}
		if env := decode(t, body); env.Code != 0 {
			t.Errorf("%s: code %d", path, env.Code)
		}
	}
}

func TestEnvelopeOnErrors(t *testing.T) {
	waitReady(t)
	cases := []struct {
		method, path string
		status       int
		source       string
	}{
		{http.MethodGet, "/api/v1/e2e-missing-route", http.StatusNotFound, "python"},
		{http.MethodGet, "/v1/user/e2e-missing-route", http.StatusNotFound, "go"},
		{http.MethodPost, "/health", http.StatusMethodNotAllowed, "go"},
		{http.MethodPost, "/api/v1/system/healthz", http.StatusMethodNotAllowed, "python"},
	}
	for _, c := range cases {
		resp, body := do(t, c.method, c.path)
		if resp.StatusCode != c.status {
			t.Errorf("%s %s: status %d, want %d", c.method, c.path, resp.StatusCode, c.status)
		}
		if got := resp.Header.Get("X-API-Source"); got != c.source {
			t.Errorf("%s %s: source %q, want %q", c.method, c.path, got, c.source)
		}
		env := decode(t, body)
		if int(env.Code) != c.status || env.Data != nil {
			t.Errorf("%s %s: envelope %+v", c.method, c.path, env)
		}
		for _, leak := range []string{"panic", "goroutine", "Traceback"} {
			if strings.Contains(string(body), leak) {
				t.Errorf("%s %s: body leaks %q", c.method, c.path, leak)
			}
		}
	}
}
