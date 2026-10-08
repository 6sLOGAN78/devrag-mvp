//go:build e2e

package e2e

// The Go twin of test/testcases/test_cross_tenant_matrix.py (plan 02-25, TEN-01, TEN-02, success criterion 5):
// tenant B asking for tenant A's resource by A's real id receives exactly the (status, code, message) it receives
// for a random nonexistent id, and A's data is unchanged afterwards. Rows come from conf/routes.yaml.

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// realMixes yields every id set with at least one of A's real ids; the other placeholders are random.
func realMixes(params []string, real map[string]string) []map[string]string {
	var out []map[string]string
	for mask := 1; mask < 1<<len(params); mask++ {
		ids := map[string]string{}
		for i, p := range params {
			if mask&(1<<i) != 0 {
				ids[p] = real[p]
			} else {
				ids[p] = randomValues(p)[0]
			}
		}
		out = append(out, ids)
	}
	return out
}

func randomIDSets(params []string) []map[string]string {
	n := 1
	for _, p := range params {
		if l := len(randomValues(p)); l > n {
			n = l
		}
	}
	var sets []map[string]string
	for i := 0; i < n; i++ {
		ids := map[string]string{}
		for _, p := range params {
			vals := randomValues(p)
			ids[p] = vals[min(i, len(vals)-1)]
		}
		sets = append(sets, ids)
	}
	return sets
}

func TestCrossTenantRegistryCoverage(t *testing.T) {
	rows := loadTenantRows(t, registryFile(t))
	if len(rows) < 8 {
		t.Fatalf("the registry should list at least the eight Phase 2 scope-tenant rows, found %d", len(rows))
	}
	if problems := matrixCoverageProblems(rows, matrixBuilders, matrixNoID); len(problems) > 0 {
		t.Fatalf("rows without fixtures:\n%s", strings.Join(problems, "\n"))
	}
}

// registryWith writes a copy of the registry with synthetic endpoint rows appended.
func registryWith(t *testing.T, extra ...map[string]any) string {
	t.Helper()
	raw, err := os.ReadFile(registryFile(t))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	eps, _ := doc["endpoints"].([]any)
	for _, row := range extra {
		full := map[string]any{"owner": "go", "auth": "jwt", "roles": []string{"owner"}, "scope": "tenant", "implemented": true}
		for k, v := range row {
			full[k] = v
		}
		eps = append(eps, full)
	}
	doc["endpoints"] = eps
	out, err := yaml.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "routes.yaml")
	if err := os.WriteFile(path, out, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestCrossTenantGuardFailsRowsWithoutFixtures(t *testing.T) {
	withParam := loadTenantRows(t, registryWith(t, map[string]any{"method": "GET", "path": "/api/v1/synthetic/{thing_id}"}))
	problems := matrixCoverageProblems(withParam, matrixBuilders, matrixNoID)
	if len(problems) != 1 || !strings.Contains(problems[0], "GET /api/v1/synthetic/{thing_id}") || !strings.Contains(problems[0], "matrixBuilders") {
		t.Errorf("a row with path parameters and no builder must be flagged, got %v", problems)
	}
	noParam := loadTenantRows(t, registryWith(t, map[string]any{"method": "POST", "path": "/api/v1/synthetic"}))
	problems = matrixCoverageProblems(noParam, matrixBuilders, matrixNoID)
	if len(problems) != 1 || !strings.Contains(problems[0], "POST /api/v1/synthetic") || !strings.Contains(problems[0], "matrixNoID") {
		t.Errorf("a row without path parameters and no isolation check must be flagged, got %v", problems)
	}
	ignored := loadTenantRows(t, registryWith(t,
		map[string]any{"method": "GET", "path": "/api/v1/synthetic/{thing_id}", "implemented": false},
		map[string]any{"method": "GET", "path": "/api/v1/synthetic-other/{thing_id}", "scope": "none"},
	))
	if problems := matrixCoverageProblems(ignored, matrixBuilders, matrixNoID); len(problems) != 0 {
		t.Errorf("unimplemented and non-tenant rows are not matrix rows, got %v", problems)
	}
	stale := map[string]matrixBuilder{"GET /gone/{x}": matrixBuilders["PATCH /api/v1/tenants/{tenant_id}"]}
	for k, v := range matrixBuilders {
		stale[k] = v
	}
	if problems := matrixCoverageProblems(loadTenantRows(t, registryFile(t)), stale, matrixNoID); len(problems) != 1 || !strings.Contains(problems[0], "GET /gone/{x}") {
		t.Errorf("a stale fixture key must be flagged, got %v", problems)
	}
}

func TestCrossTenantMatrix(t *testing.T) {
	waitReady(t)
	rows := loadTenantRows(t, registryFile(t))
	if problems := matrixCoverageProblems(rows, matrixBuilders, matrixNoID); len(problems) > 0 {
		t.Fatalf("rows without fixtures:\n%s", strings.Join(problems, "\n"))
	}
	w := buildMatrixWorld(t)
	covered := 0
	for _, row := range rows {
		row := row
		params := row.params()
		t.Run(row.key(), func(t *testing.T) {
			covered++
			before := w.snapshot(t)
			if len(params) == 0 {
				matrixNoID[row.key()](t, w)
				if !sameSnapshot(w.snapshot(t), before) {
					t.Errorf("%s changed tenant A's data", row.key())
				}
				return
			}
			target := matrixBuilders[row.key()](w)
			outsiders(t, w, row, target)
			otherPositions(t, w, row, target)
			rolesWithoutTheRole(t, w, row, target)
			if !sameSnapshot(w.snapshot(t), before) {
				t.Errorf("%s changed tenant A's data", row.key())
			}
		})
	}
	t.Logf("cross-tenant matrix: %d registry rows covered (%d with ids, %d without)", covered, countWithParams(rows), len(rows)-countWithParams(rows))
	if covered != len(rows) {
		t.Errorf("covered %d of %d rows", covered, len(rows))
	}
}

func countWithParams(rows []registryRow) int {
	n := 0
	for _, r := range rows {
		if len(r.params()) > 0 {
			n++
		}
	}
	return n
}

// outsiders: a stranger, a pending invitee and B's API token get the nonexistent-id answer for every mix of real ids.
func outsiders(t *testing.T, w *matrixWorld, row registryRow, target matrixTarget) {
	t.Helper()
	callers := []struct{ label, token string }{{"stranger", w.b.Token}, {"b-api-token", w.bAPIToken}}
	if !row.hasRole("invite") { // PATCH /tenants/{id} is the pending invitee's own route: answering is its purpose
		callers = append(callers, struct{ label, token string }{"pending-invite", w.pending.Token})
	}
	for _, c := range callers {
		var baseline answer
		for i, ids := range randomIDSets(row.params()) {
			got, _ := target.send(t, c.token, ids, sendOpts{})
			if i == 0 {
				baseline = got
			} else if got != baseline {
				t.Errorf("%s as %s: the answer for a nonexistent id varies with the id: %v versus %v", row.key(), c.label, got, baseline)
			}
		}
		want := http.StatusNotFound
		if c.label == "b-api-token" && row.Auth == "jwt" {
			want = http.StatusUnauthorized // no tenant row accepts an API token: refused before any lookup
		}
		if baseline.status != want {
			t.Errorf("%s as %s: nonexistent id answered %v, want status %d", row.key(), c.label, baseline, want)
		}
		for _, ids := range realMixes(row.params(), target.real) {
			if got, _ := target.send(t, c.token, ids, sendOpts{}); got != baseline {
				t.Errorf("%s as %s with ids %v: %v differs from the nonexistent-id answer %v", row.key(), c.label, ids, got, baseline)
			}
		}
	}
}

// otherPositions: A's ids in query and body positions, and B's own tenant in the path, reach nothing of A's.
func otherPositions(t *testing.T, w *matrixWorld, row registryRow, target matrixTarget) {
	t.Helper()
	query := map[string]string{"tenant_id": w.a.TenantID, "user_id": w.victim.UserID, "token": w.aTokens[0].Token}
	body := map[string]any{"tenant_id": w.a.TenantID, "user_id": w.victim.UserID, "id": w.a.TenantID, "owner_id": w.a.UserID}
	baseline, _ := target.send(t, w.b.Token, randomIDSets(row.params())[0], sendOpts{})
	for _, o := range []sendOpts{{query: query}, {extra: body}, {query: query, extra: body}} {
		if got, _ := target.send(t, w.b.Token, target.real, o); got != baseline {
			t.Errorf("%s with A's ids in other positions: %v differs from %v", row.key(), got, baseline)
		}
	}
	if !contains(row.params(), "tenant_id") {
		return
	}
	random := map[string]string{}
	for _, p := range row.params() {
		random[p] = randomValues(p)[0]
	}
	for _, ids := range []map[string]string{withTenant(target.real, w.b.TenantID), withTenant(random, w.b.TenantID)} {
		for _, o := range []sendOpts{{}, {query: query, extra: body}} {
			got, text := target.send(t, w.b.Token, ids, o)
			if got.status >= 500 {
				t.Errorf("%s with B's own tenant: %v", row.key(), got)
			}
			assertNoAData(t, w, text, row.key()+" with B's own tenant")
		}
	}
}

func withTenant(ids map[string]string, tenantID string) map[string]string {
	out := map[string]string{}
	for k, v := range ids {
		out[k] = v
	}
	out["tenant_id"] = tenantID
	return out
}

// rolesWithoutTheRole: an admin or normal member of A lacking the route's role is refused (403, or 404 when nothing is pending).
func rolesWithoutTheRole(t *testing.T, w *matrixWorld, row registryRow, target matrixTarget) {
	t.Helper()
	if !contains(row.params(), "tenant_id") {
		return
	}
	tried := 0
	for role, who := range map[string]string{"admin": w.admin.Token, "normal": w.normal.Token} {
		if row.hasRole(role) {
			continue
		}
		want := http.StatusNotFound
		if row.hasRole("owner", "admin", "normal") {
			want = http.StatusForbidden
		}
		if got, _ := target.send(t, who, target.real, sendOpts{}); got.status != want {
			t.Errorf("%s as %s: %v, want status %d", row.key(), role, got, want)
		}
		tried++
	}
	if tried == 0 && !(row.hasRole("admin") && row.hasRole("normal")) {
		t.Errorf("%s: no authorisation variant ran", row.key())
	}
}
