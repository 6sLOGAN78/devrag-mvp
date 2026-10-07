//go:build e2e

package e2e

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
	"testing"

	"devrag/internal/testutil"
)

const tokensPath = "/api/v1/system/tokens"

// isUnauthorized reports whether body is the generic 401 envelope, whatever the JSON spacing (Go and
// Python serialise it differently).
func isUnauthorized(body []byte) bool {
	var env struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
		Data    any    `json:"data"`
	}
	return json.Unmarshal(body, &env) == nil && env.Code == 401 && env.Message == "unauthorized" && env.Data == nil
}

var (
	e2eAPIToken  = regexp.MustCompile(`^ragflow-[A-Za-z0-9_-]{43}$`)
	e2eBetaToken = regexp.MustCompile(`^[0-9a-f]{32}$`)
)

type tokenData struct {
	Token      string `json:"token"`
	Beta       string `json:"beta"`
	CreateTime int64  `json:"create_time"`
}

func createToken(t *testing.T, session string) tokenData {
	t.Helper()
	resp, body := send(t, http.MethodPost, tokensPath, session, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("create token: %d %s", resp.StatusCode, body)
	}
	var env struct {
		Data tokenData `json:"data"`
	}
	if err := json.Unmarshal(body, &env); err != nil {
		t.Fatal(err)
	}
	return env.Data
}

func TestAPITokenLifecycleThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	alice := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, alice)
	bob := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, bob)

	created := createToken(t, alice.Token)
	if !e2eAPIToken.MatchString(created.Token) || !e2eBetaToken.MatchString(created.Beta) || created.CreateTime == 0 {
		t.Fatalf("token shapes: %+v", created)
	}

	probe := "/api/v1/probe-" + testutil.UniqueName("p")
	if resp, body := send(t, http.MethodGet, probe, created.Token, nil); resp.StatusCode != http.StatusNotFound || resp.Header.Get("X-API-Source") != "python" {
		t.Errorf("API token on a Python api route: %d %s (want 404 from python: the gate passed)", resp.StatusCode, body)
	}
	if resp, body := send(t, http.MethodGet, probe, "ragflow-"+strings.Repeat("A", 43), nil); resp.StatusCode != http.StatusUnauthorized || !isUnauthorized(body) {
		t.Errorf("invalid API token: %d %s", resp.StatusCode, body)
	}

	// management routes accept only the session token
	for _, cred := range []string{created.Token, created.Beta} {
		for _, m := range []string{http.MethodGet, http.MethodPost} {
			if resp, body := send(t, m, tokensPath, cred, nil); resp.StatusCode != http.StatusUnauthorized || !isUnauthorized(body) {
				t.Errorf("%s %s with an API or beta credential: %d %s", m, tokensPath, resp.StatusCode, body)
			}
		}
	}

	// another tenant cannot delete it and learns nothing
	resp, foreign := send(t, http.MethodDelete, tokensPath+"/"+created.Token, bob.Token, nil)
	_, missing := send(t, http.MethodDelete, tokensPath+"/ragflow-"+strings.Repeat("B", 43), bob.Token, nil)
	if resp.StatusCode != http.StatusNotFound || string(foreign) != string(missing) {
		t.Errorf("foreign delete: %d %s versus missing %s", resp.StatusCode, foreign, missing)
	}
	if resp, _ := send(t, http.MethodGet, probe, created.Token, nil); resp.StatusCode != http.StatusNotFound {
		t.Errorf("the token must survive a foreign delete, got %d", resp.StatusCode)
	}

	// the owner deletes it; both engines stop accepting it at once
	if resp, body := send(t, http.MethodDelete, tokensPath+"/"+created.Token, alice.Token, nil); resp.StatusCode != http.StatusOK {
		t.Fatalf("owner delete: %d %s", resp.StatusCode, body)
	}
	if resp, body := send(t, http.MethodGet, probe, created.Token, nil); resp.StatusCode != http.StatusUnauthorized || !isUnauthorized(body) {
		t.Errorf("deleted token on python: %d %s", resp.StatusCode, body)
	}
	if resp, _ := send(t, http.MethodGet, "/api/v1/searchbots/probe-"+testutil.UniqueName("p"), created.Beta, nil); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("deleted beta value on go: %d", resp.StatusCode)
	}
}

func TestBetaCredentialOnGoBetaFamilyThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	acc := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, acc)
	created := createToken(t, acc.Token)

	path := "/api/v1/searchbots/probe-" + testutil.UniqueName("p")
	resp, body := send(t, http.MethodGet, path, created.Beta, nil)
	if resp.StatusCode != http.StatusNotFound || resp.Header.Get("X-API-Source") != "go" {
		t.Errorf("valid beta on a go beta route: %d %s (want 404 from go: gate passed, no handler until Phase 8)", resp.StatusCode, body)
	}
	for name, cred := range map[string]string{"wrong": strings.Repeat("0", 32), "empty": "", "short": "abc"} {
		resp, body := send(t, http.MethodGet, path, cred, nil)
		var env struct {
			Code int `json:"code"`
		}
		_ = json.Unmarshal(body, &env)
		if resp.StatusCode != http.StatusUnauthorized || env.Code != 401 {
			t.Errorf("%s beta: HTTP %d body %s (want 401 and code 401, never 200)", name, resp.StatusCode, body)
		}
	}
	if resp, _ := send(t, http.MethodGet, "/api/v1/probe-"+testutil.UniqueName("p"), created.Beta, nil); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("beta value on a python api route: %d", resp.StatusCode)
	}
}
