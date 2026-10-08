//go:build e2e

package e2e

// Fixtures for the registry-driven cross-tenant matrix (plan 02-25), the Go twin of
// test/testcases/_matrix_fixtures.py. The rows are read from conf/routes.yaml: every row with scope
// tenant and implemented true. A row with path parameters needs an entry in matrixBuilders, a row
// without needs an entry in matrixNoID; a row in neither fails the matrix (matrixCoverageProblems).

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"

	"devrag/internal/testutil"
)

const tokensRoute = "/api/v1/system/tokens"

type registryRow struct {
	Method      string   `yaml:"method"`
	Path        string   `yaml:"path"`
	Auth        string   `yaml:"auth"`
	Roles       []string `yaml:"roles"`
	Scope       string   `yaml:"scope"`
	Implemented bool     `yaml:"implemented"`
}

var placeholderRE = regexp.MustCompile(`\{(\w+)\}`)

func (r registryRow) key() string { return r.Method + " " + r.Path }

func (r registryRow) params() []string {
	var out []string
	for _, m := range placeholderRE.FindAllStringSubmatch(r.Path, -1) {
		out = append(out, m[1])
	}
	return out
}

func (r registryRow) hasRole(roles ...string) bool {
	for _, have := range r.Roles {
		for _, want := range roles {
			if have == want {
				return true
			}
		}
	}
	return false
}

func registryFile(t *testing.T) string {
	t.Helper()
	return filepath.Join(repoRoot(t), "conf", "routes.yaml")
}

// loadTenantRows reads the endpoints registry and returns the implemented rows with scope tenant.
func loadTenantRows(t *testing.T, path string) []registryRow {
	t.Helper()
	raw, err := os.ReadFile(path) // #nosec G304 -- the repository's own registry
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Endpoints []registryRow `yaml:"endpoints"`
	}
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	var rows []registryRow
	for _, e := range doc.Endpoints {
		if e.Scope == "tenant" && e.Implemented {
			e.Method = strings.ToUpper(e.Method)
			rows = append(rows, e)
		}
	}
	return rows
}

// matrixCoverageProblems names every registry row no fixture covers and every fixture entry matching no row.
func matrixCoverageProblems[B, N any](rows []registryRow, builders map[string]B, noID map[string]N) []string {
	var problems []string
	keys := map[string]bool{}
	for _, r := range rows {
		keys[r.key()] = true
		if len(r.params()) > 0 {
			if _, ok := builders[r.key()]; !ok {
				problems = append(problems, fmt.Sprintf("%s: scope tenant with path parameters %v has no fixture builder; add one to matrixBuilders in internal/e2e/matrix_fixtures_test.go", r.key(), r.params()))
			}
		} else if _, ok := noID[r.key()]; !ok {
			problems = append(problems, fmt.Sprintf("%s: scope tenant with no path parameter has no isolation check; add one to matrixNoID in internal/e2e/matrix_fixtures_test.go", r.key()))
		}
	}
	for k := range builders {
		if !keys[k] {
			problems = append(problems, k+": fixture entry matches no implemented scope-tenant row of conf/routes.yaml; fix or remove the key")
		}
	}
	for k := range noID {
		if !keys[k] {
			problems = append(problems, k+": fixture entry matches no implemented scope-tenant row of conf/routes.yaml; fix or remove the key")
		}
	}
	sort.Strings(problems)
	return problems
}

// answer is the (status, code, message) triple the matrix compares.
type answer struct {
	status  int
	code    any
	message any
}

func (a answer) String() string { return fmt.Sprintf("(%d, %v, %v)", a.status, a.code, a.message) }

func toAnswer(status int, body []byte) answer {
	var env map[string]any
	if json.Unmarshal(body, &env) != nil {
		text := string(body)
		if len(text) > 120 {
			text = text[:120]
		}
		return answer{status: status, message: text}
	}
	return answer{status: status, code: env["code"], message: env["message"]}
}

type sendOpts struct {
	query map[string]string
	extra map[string]any
}

// matrixCall sends one request: template placeholders replaced by ids, own body fields over extra (ids in other positions).
func matrixCall(t *testing.T, method, template, token string, ids map[string]string, own map[string]any, o sendOpts) (answer, string) {
	t.Helper()
	path := template
	for k, v := range ids {
		path = strings.ReplaceAll(path, "{"+k+"}", url.PathEscape(v))
	}
	if len(o.query) > 0 {
		q := url.Values{}
		for k, v := range o.query {
			q.Set(k, v)
		}
		path += "?" + q.Encode()
	}
	merged := map[string]any{}
	for k, v := range o.extra {
		merged[k] = v
	}
	for k, v := range own {
		merged[k] = v
	}
	var body any
	if len(merged) > 0 {
		body = merged
	}
	resp, out := send(t, method, path, token, body)
	return toAnswer(resp.StatusCode, out), string(out)
}

func randomValues(name string) []string {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		panic(err)
	}
	vals := []string{hex.EncodeToString(raw)} // a random 32-hex id
	if name == "token" {
		tok := make([]byte, 32)
		if _, err := rand.Read(tok); err != nil {
			panic(err)
		}
		vals = append(vals, "ragflow-"+base64.RawURLEncoding.EncodeToString(tok)[:43]) // a well-formed random token
	}
	return vals
}

// matrixWorld is tenant A with a populated workspace and every kind of outsider.
type matrixWorld struct {
	a, b, pending, admin, normal, victim, spare testutil.Account
	aTokens                                     []tokenData
	bAPIToken                                   string
}

func (w *matrixWorld) listTokens(t *testing.T, who testutil.Account) []map[string]any {
	t.Helper()
	resp, body := send(t, http.MethodGet, tokensRoute+"?page_size=100", who.Token, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("list tokens: %d %s", resp.StatusCode, body)
	}
	return envData[[]map[string]any](t, body)
}

func canonical(v any) string {
	raw, _ := json.Marshal(v)
	return string(raw)
}

func (w *matrixWorld) snapshotTokens(t *testing.T) string {
	t.Helper()
	list := w.listTokens(t, w.a)
	sort.Slice(list, func(i, j int) bool { return fmt.Sprint(list[i]["token"]) < fmt.Sprint(list[j]["token"]) })
	return canonical(list)
}

func (w *matrixWorld) snapshotMembers(t *testing.T) string {
	t.Helper()
	list := listMembers(t, w.a.TenantID, w.a.Token)
	sort.Slice(list, func(i, j int) bool { return fmt.Sprint(list[i]["id"]) < fmt.Sprint(list[j]["id"]) })
	return canonical(list)
}

// snapshot is everything of A's a cross-tenant call could touch, read as A and as the invited and joined users.
func (w *matrixWorld) snapshot(t *testing.T) map[string]string {
	t.Helper()
	memberships := map[string][]string{}
	for name, who := range map[string]testutil.Account{"pending": w.pending, "admin": w.admin, "normal": w.normal, "victim": w.victim} {
		resp, body := send(t, http.MethodGet, "/v1/tenant/list", who.Token, nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("tenant list: %d %s", resp.StatusCode, body)
		}
		var lines []string
		for _, m := range envData[[]map[string]any](t, body) {
			lines = append(lines, fmt.Sprint(m["tenant_id"], ":", m["role"]))
		}
		sort.Strings(lines)
		memberships[name] = lines
	}
	return map[string]string{"members": w.snapshotMembers(t), "tokens": w.snapshotTokens(t), "memberships": canonical(memberships)}
}

func (w *matrixWorld) aIdentifiers() []string {
	out := []string{w.a.TenantID, w.a.UserID, w.a.Email}
	for _, acc := range []testutil.Account{w.admin, w.normal, w.victim, w.pending} {
		out = append(out, acc.UserID, acc.Email)
	}
	for _, tok := range w.aTokens {
		out = append(out, tok.Token, tok.Beta)
	}
	return out
}

func sameSnapshot(a, b map[string]string) bool { return canonical(a) == canonical(b) }

// buildMatrixWorld registers the accounts through the real endpoints and builds A's workspace through the real API.
func buildMatrixWorld(t *testing.T) *matrixWorld {
	t.Helper()
	cfg := testutil.RequireDB(t)
	reg := func() testutil.Account {
		acc := testutil.RegisterAccount(t, baseURL())
		t.Cleanup(func() { testutil.DeleteAccount(t, cfg.MySQL, acc) })
		return acc
	}
	w := &matrixWorld{a: reg(), b: reg(), pending: reg(), admin: reg(), normal: reg(), victim: reg(), spare: reg()}
	users := tenantUsers(w.a.TenantID)
	for _, m := range []testutil.Account{w.admin, w.normal, w.victim} {
		inviteAndAccept(t, w.a, m)
	}
	expectStatus(t, "invite pending", http.StatusOK, http.MethodPost, users, w.a.Token, map[string]string{"email": w.pending.Email})
	expectStatus(t, "promote", http.StatusOK, http.MethodPatch, tenantUser(w.a.TenantID, w.admin.UserID), w.a.Token, map[string]string{"role": "admin"})
	w.aTokens = []tokenData{createToken(t, w.a.Token), createToken(t, w.a.Token)}
	w.bAPIToken = createToken(t, w.b.Token).Token
	return w
}

// matrixTarget replays one row against A's resource with arbitrary ids.
type matrixTarget struct {
	real map[string]string
	send func(t *testing.T, token string, ids map[string]string, o sendOpts) (answer, string)
}

func newTarget(method, template string, real map[string]string, own map[string]any) matrixTarget {
	return matrixTarget{real: real, send: func(t *testing.T, token string, ids map[string]string, o sendOpts) (answer, string) {
		t.Helper()
		return matrixCall(t, method, template, token, ids, own, o)
	}}
}

type matrixBuilder func(w *matrixWorld) matrixTarget

var matrixBuilders = map[string]matrixBuilder{
	"DELETE /api/v1/system/tokens/{token}": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodDelete, tokensRoute+"/{token}", map[string]string{"token": w.aTokens[0].Token}, nil)
	},
	"GET /api/v1/tenants/{tenant_id}/users": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodGet, "/api/v1/tenants/{tenant_id}/users", map[string]string{"tenant_id": w.a.TenantID}, nil)
	},
	"POST /api/v1/tenants/{tenant_id}/users": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodPost, "/api/v1/tenants/{tenant_id}/users", map[string]string{"tenant_id": w.a.TenantID}, map[string]any{"email": w.spare.Email})
	},
	"DELETE /api/v1/tenants/{tenant_id}/users": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodDelete, "/api/v1/tenants/{tenant_id}/users", map[string]string{"tenant_id": w.a.TenantID}, map[string]any{"user_id": w.victim.UserID})
	},
	"PATCH /api/v1/tenants/{tenant_id}": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodPatch, "/api/v1/tenants/{tenant_id}", map[string]string{"tenant_id": w.a.TenantID}, map[string]any{"action": "accept"})
	},
	"PATCH /api/v1/tenants/{tenant_id}/users/{user_id}": func(w *matrixWorld) matrixTarget {
		return newTarget(http.MethodPatch, "/api/v1/tenants/{tenant_id}/users/{user_id}",
			map[string]string{"tenant_id": w.a.TenantID, "user_id": w.victim.UserID}, map[string]any{"role": "admin"})
	},
}

func assertNoAData(t *testing.T, w *matrixWorld, text, what string) {
	t.Helper()
	for _, v := range w.aIdentifiers() {
		if v != "" && strings.Contains(text, v) {
			t.Errorf("%s contains a value that belongs to tenant A", what)
			return
		}
	}
}

func idsOf(t *testing.T, body []byte) []string {
	t.Helper()
	var out []string
	for _, m := range envData[[]map[string]any](t, body) {
		out = append(out, fmt.Sprint(m["token"]))
	}
	return out
}

func contains(list []string, v string) bool {
	for _, s := range list {
		if s == v {
			return true
		}
	}
	return false
}

var matrixNoID = map[string]func(t *testing.T, w *matrixWorld){
	// GET /api/v1/system/tokens: the list is the caller's tenant's, whatever id the request carries.
	"GET /api/v1/system/tokens": func(t *testing.T, w *matrixWorld) {
		before := w.snapshotTokens(t)
		created := createToken(t, w.b.Token)
		smuggle := "&tenant_id=" + w.a.TenantID + "&user_id=" + w.a.UserID + "&owner_id=" + w.a.UserID
		for label, who := range map[string]testutil.Account{"B": w.b, "the pending invitee": w.pending, "a member of A": w.victim, "an admin of A": w.admin} {
			for _, q := range []string{"", smuggle} {
				resp, body := send(t, http.MethodGet, tokensRoute+"?page_size=100"+q, who.Token, nil)
				if resp.StatusCode != http.StatusOK {
					t.Fatalf("list as %s: %d %s", label, resp.StatusCode, body)
				}
				assertNoAData(t, w, string(body), "the token list of "+label)
			}
		}
		if _, body := send(t, http.MethodGet, tokensRoute+"?page_size=100", w.b.Token, nil); !contains(idsOf(t, body), created.Token) {
			t.Errorf("B's own token is not in B's list")
		}
		if resp, _ := send(t, http.MethodGet, tokensRoute, w.bAPIToken, nil); resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("an API token must not list tokens, got %d", resp.StatusCode)
		}
		if after := w.snapshotTokens(t); after != before {
			t.Errorf("A's token list changed")
		}
	},
	// POST /api/v1/system/tokens: B creates in B's tenant only, whatever B sends.
	"POST /api/v1/system/tokens": func(t *testing.T, w *matrixWorld) {
		before := w.snapshotTokens(t)
		forced := "ragflow-" + strings.Repeat("Z", 43)
		extras := []struct {
			body  map[string]any
			query string
		}{
			{nil, ""},
			{map[string]any{"tenant_id": w.a.TenantID, "token": forced, "beta": strings.Repeat("0", 32), "dialog_id": w.a.UserID}, "?tenant_id=" + w.a.TenantID},
		}
		for _, e := range extras {
			resp, body := send(t, http.MethodPost, tokensRoute+e.query, w.b.Token, e.body)
			if resp.StatusCode != http.StatusOK {
				t.Fatalf("B creates a token: %d %s", resp.StatusCode, body)
			}
			created := envData[tokenData](t, body)
			if created.Token == forced {
				t.Errorf("a client-chosen token value must be ignored")
			}
			_, bList := send(t, http.MethodGet, tokensRoute+"?page_size=100", w.b.Token, nil)
			_, aList := send(t, http.MethodGet, tokensRoute+"?page_size=100", w.a.Token, nil)
			if !contains(idsOf(t, bList), created.Token) || contains(idsOf(t, aList), created.Token) {
				t.Errorf("the new token must be in B's list and not in A's")
			}
			if strings.Contains(string(body), w.a.TenantID) {
				t.Errorf("the create response names tenant A")
			}
		}
		if resp, _ := send(t, http.MethodPost, tokensRoute, w.bAPIToken, nil); resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("an API token must not create tokens, got %d", resp.StatusCode)
		}
		if after := w.snapshotTokens(t); after != before {
			t.Errorf("A's token list changed")
		}
	},
}
