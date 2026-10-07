package common

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type policyCase struct {
	Method    string `json:"method"`
	Path      string `json:"path"`
	Auth      string `json:"auth"`
	Owner     string `json:"owner"`
	Scope     string `json:"scope"`
	Preflight bool   `json:"preflight"`
}

func loadPolicyCases(t *testing.T) []policyCase {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "test", "fixtures", "route_policy_cases.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var doc struct {
		Cases []policyCase `json:"cases"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	if len(doc.Cases) < 13 {
		t.Fatalf("expected at least 13 shared cases, got %d", len(doc.Cases))
	}
	return doc.Cases
}

func TestPolicyForSharedCases(t *testing.T) {
	for _, c := range loadPolicyCases(t) {
		got := PolicyFor(c.Method, c.Path)
		if got.Auth != c.Auth || got.Owner != c.Owner || got.Scope != c.Scope || got.Preflight != c.Preflight {
			t.Errorf("%s %q: got %+v, want auth=%s owner=%s scope=%s preflight=%v", c.Method, c.Path, got, c.Auth, c.Owner, c.Scope, c.Preflight)
		}
	}
}

func TestPolicyForUnmatchedIsDeniedNeverPublic(t *testing.T) {
	for _, p := range []string{"/unknown", "/", "", "/nope/deeper/still", "/api"} {
		if got := PolicyFor("GET", p); got.Auth != "jwt" {
			t.Errorf("path %q resolved to auth %q, want jwt (default deny)", p, got.Auth)
		}
	}
}
