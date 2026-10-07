package common

import (
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"testing"
)

type permissionFixture struct {
	Subjects             []string `json:"subjects"`
	NeverAllowedSubjects []string `json:"never_allowed_subjects"`
	Rows                 []struct {
		Area    string   `json:"area"`
		Action  string   `json:"action"`
		Allowed []string `json:"allowed"`
	} `json:"rows"`
	UnknownPairs [][2]string `json:"unknown_pairs"`
}

func loadPermissionFixture(t *testing.T) permissionFixture {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "test", "fixtures", "permission_cases.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var f permissionFixture
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	if len(f.Rows) != 10 {
		t.Fatalf("the docs matrix has 10 rows, fixture has %d", len(f.Rows))
	}
	return f
}

// The Python test_permissions_table.py walks the same fixture, so the two generated tables are
// proven identical through one independent oracle.
func TestAllowedMatchesSharedMatrix(t *testing.T) {
	f := loadPermissionFixture(t)
	for _, row := range f.Rows {
		for _, subject := range f.Subjects {
			want := slices.Contains(row.Allowed, subject)
			if got := Allowed(subject, row.Area, row.Action); got != want {
				t.Errorf("Allowed(%q, %q, %q) = %v, want %v", subject, row.Area, row.Action, got, want)
			}
		}
	}
}

func TestTeamAdminIsOwnerOnly(t *testing.T) {
	for _, subject := range []string{"admin", "normal", "api_token", "beta_token"} {
		if Allowed(subject, "team_admin", "manage_members") {
			t.Errorf("%s must not manage members (D-13)", subject)
		}
	}
	if !Allowed("owner", "team_admin", "manage_members") {
		t.Error("the owner manages members")
	}
}

func TestInviteAndUnknownRolesAreDeniedEverywhere(t *testing.T) {
	f := loadPermissionFixture(t)
	for _, subject := range f.NeverAllowedSubjects {
		for _, row := range f.Rows {
			if Allowed(subject, row.Area, row.Action) {
				t.Errorf("subject %q must be denied for %s/%s (D-26: a pending invitation is not membership)", subject, row.Area, row.Action)
			}
		}
	}
}

func TestUnknownAreaOrActionIsDenied(t *testing.T) {
	f := loadPermissionFixture(t)
	for _, pair := range f.UnknownPairs {
		for _, subject := range f.Subjects {
			if Allowed(subject, pair[0], pair[1]) {
				t.Errorf("Allowed(%q, %q, %q) must default to deny", subject, pair[0], pair[1])
			}
		}
	}
}

func TestPermissionRowsCoverTheSharedMatrixExactly(t *testing.T) {
	f := loadPermissionFixture(t)
	rows := PermissionRows()
	if len(rows) != len(f.Rows) {
		t.Fatalf("generated table has %d rows, oracle %d", len(rows), len(f.Rows))
	}
	for _, want := range f.Rows {
		found := false
		for _, got := range rows {
			if got.Area == want.Area && got.Action == want.Action {
				found = true
				a, b := slices.Clone(got.Allow), slices.Clone(want.Allowed)
				slices.Sort(a)
				slices.Sort(b)
				if !slices.Equal(a, b) {
					t.Errorf("%s/%s allow list %v, want %v", want.Area, want.Action, a, b)
				}
			}
		}
		if !found {
			t.Errorf("row %s/%s missing from the generated table", want.Area, want.Action)
		}
	}
}
