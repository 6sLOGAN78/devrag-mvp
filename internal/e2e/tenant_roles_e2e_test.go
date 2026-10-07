//go:build e2e

package e2e

import (
	"net/http"
	"strings"
	"sync"
	"testing"

	"devrag/internal/testutil"
)

func tenantUser(tenantID, userID string) string { return tenantUsers(tenantID) + "/" + userID }

func expectStatus(t *testing.T, what string, want int, method, path, token string, body any) string {
	t.Helper()
	code, out := status(t, method, path, token, body)
	if code != want {
		t.Errorf("%s: %s %s returned %d, want %d: %s", what, method, path, code, want, out)
	}
	return out
}

func tokenListed(t *testing.T, session, token string) bool {
	t.Helper()
	resp, body := send(t, http.MethodGet, tokensPath, session, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("list tokens: %d %s", resp.StatusCode, body)
	}
	return strings.Contains(string(body), token)
}

// inviteAndAccept makes target a normal member of the owner's tenant through the real routes.
func inviteAndAccept(t *testing.T, owner, target testutil.Account) {
	t.Helper()
	expectStatus(t, "invite", http.StatusOK, http.MethodPost, tenantUsers(owner.TenantID), owner.Token, map[string]string{"email": target.Email})
	expectStatus(t, "accept", http.StatusOK, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, target.Token, map[string]string{"action": "accept"})
}

func TestRoleChangeThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	member := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, member)
	other := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, other)
	stranger := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, stranger)
	pending := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, pending)
	inviteAndAccept(t, owner, member)
	inviteAndAccept(t, owner, other)
	expectStatus(t, "invite pending", http.StatusOK, http.MethodPost, tenantUsers(owner.TenantID), owner.Token, map[string]string{"email": pending.Email})
	path := tenantUser(owner.TenantID, member.UserID)

	// owner promotes then demotes; unknown body fields are ignored
	expectStatus(t, "promote", http.StatusOK, http.MethodPatch, path, owner.Token, map[string]any{"role": "admin", "user_id": other.UserID, "tenant_id": stranger.TenantID, "status": "0"})
	members := listMembers(t, owner.TenantID, owner.Token)
	if roleOf(members, member.UserID) != "admin" || roleOf(members, other.UserID) != "normal" {
		t.Fatalf("promotion must touch only the path's user: %v", members)
	}
	expectStatus(t, "demote", http.StatusOK, http.MethodPatch, path, owner.Token, map[string]string{"role": "normal"})
	if roleOf(listMembers(t, owner.TenantID, owner.Token), member.UserID) != "normal" {
		t.Error("demotion did not apply")
	}

	// owner can never be set, the owner row and a pending invitation cannot be targeted
	for _, role := range []string{"owner", "invite", "superuser", ""} {
		code, body := status(t, http.MethodPatch, path, owner.Token, map[string]string{"role": role})
		if code != http.StatusBadRequest {
			t.Errorf("role %q: %d %s", role, code, body)
		}
	}
	expectStatus(t, "missing role", http.StatusBadRequest, http.MethodPatch, path, owner.Token, map[string]string{})
	expectStatus(t, "non-string role", http.StatusBadRequest, http.MethodPatch, path, owner.Token, map[string]any{"role": 7})
	selfBody := expectStatus(t, "owner self-demotion", http.StatusBadRequest, http.MethodPatch, tenantUser(owner.TenantID, owner.UserID), owner.Token, map[string]string{"role": "normal"})
	if !strings.Contains(selfBody, "owner") {
		t.Errorf("owner refusal should be a clear message: %s", selfBody)
	}
	expectStatus(t, "pending target", http.StatusBadRequest, http.MethodPatch, tenantUser(owner.TenantID, pending.UserID), owner.Token, map[string]string{"role": "admin"})
	expectStatus(t, "absent target", http.StatusNotFound, http.MethodPatch, tenantUser(owner.TenantID, stranger.UserID), owner.Token, map[string]string{"role": "admin"})
	expectStatus(t, "oversized body", http.StatusRequestEntityTooLarge, http.MethodPatch, path, owner.Token, map[string]string{"role": "admin", "pad": strings.Repeat("x", 4000)})
	members = listMembers(t, owner.TenantID, owner.Token)
	if roleOf(members, owner.UserID) != "owner" || roleOf(members, pending.UserID) != "invite" || roleOf(members, member.UserID) != "normal" {
		t.Errorf("refusals must change nothing: %v", members)
	}

	// admin and normal callers are forbidden; stranger and pending invitee get the shared 404
	testutil.SetMemberRole(t, cfg.MySQL, owner.TenantID, other.UserID, "admin")
	expectStatus(t, "admin caller", http.StatusForbidden, http.MethodPatch, path, other.Token, map[string]string{"role": "admin"})
	expectStatus(t, "normal caller", http.StatusForbidden, http.MethodPatch, tenantUser(owner.TenantID, other.UserID), member.Token, map[string]string{"role": "normal"})
	randomBody := expectStatus(t, "random tenant", http.StatusNotFound, http.MethodPatch, tenantUser(randomHexID(), member.UserID), stranger.Token, map[string]string{"role": "admin"})
	strangerBody := expectStatus(t, "stranger", http.StatusNotFound, http.MethodPatch, path, stranger.Token, map[string]string{"role": "admin"})
	pendingBody := expectStatus(t, "pending invitee", http.StatusNotFound, http.MethodPatch, path, pending.Token, map[string]string{"role": "admin"})
	if strangerBody != randomBody || pendingBody != randomBody {
		t.Errorf("404 bodies differ: %s | %s | %s", randomBody, strangerBody, pendingBody)
	}
	expectStatus(t, "no credential", http.StatusUnauthorized, http.MethodPatch, path, "", map[string]string{"role": "admin"})
	if roleOf(listMembers(t, owner.TenantID, owner.Token), member.UserID) != "normal" {
		t.Error("forbidden callers changed a role")
	}
}

func TestRemoveWithdrawAndLeaveThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	a := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, a)
	b := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, b)
	c := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, c)
	stranger := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, stranger)
	path := tenantUsers(owner.TenantID)
	inviteAndAccept(t, owner, a)
	inviteAndAccept(t, owner, b)
	testutil.SetMemberRole(t, cfg.MySQL, owner.TenantID, b.UserID, "admin")
	token := createToken(t, a.Token) // a's own workspace token, must survive a's removal elsewhere

	// a member cannot remove someone else; naming another user is 403 and removes nobody
	expectStatus(t, "normal removes admin", http.StatusForbidden, http.MethodDelete, path, a.Token, map[string]string{"user_id": b.UserID})
	expectStatus(t, "normal removes owner", http.StatusForbidden, http.MethodDelete, path, a.Token, map[string]string{"user_id": owner.UserID})
	expectStatus(t, "admin removes normal", http.StatusForbidden, http.MethodDelete, path, b.Token, map[string]string{"user_id": a.UserID})
	expectStatus(t, "admin removes owner", http.StatusForbidden, http.MethodDelete, path, b.Token, map[string]string{"user_id": owner.UserID})
	if m := listMembers(t, owner.TenantID, owner.Token); len(m) != 3 {
		t.Fatalf("nobody may have been removed: %v", m)
	}
	// stranger: shared 404 whoever is named
	randomBody := expectStatus(t, "random tenant", http.StatusNotFound, http.MethodDelete, tenantUsers(randomHexID()), stranger.Token, map[string]string{"user_id": stranger.UserID})
	strangerBody := expectStatus(t, "stranger", http.StatusNotFound, http.MethodDelete, path, stranger.Token, map[string]string{"user_id": a.UserID})
	if strangerBody != randomBody {
		t.Errorf("404 bodies differ: %s | %s", randomBody, strangerBody)
	}
	expectStatus(t, "no credential", http.StatusUnauthorized, http.MethodDelete, path, "", map[string]string{"user_id": a.UserID})

	// the owner row can never be removed, by anyone, and the owner cannot leave
	expectStatus(t, "owner leaves", http.StatusBadRequest, http.MethodDelete, path, owner.Token, map[string]string{"user_id": owner.UserID})
	expectStatus(t, "owner: no user_id", http.StatusBadRequest, http.MethodDelete, path, owner.Token, map[string]string{})
	expectStatus(t, "owner: malformed body", http.StatusBadRequest, http.MethodDelete, path, owner.Token, map[string]any{"user_id": 5})
	expectStatus(t, "owner removes absent", http.StatusNotFound, http.MethodDelete, path, owner.Token, map[string]string{"user_id": stranger.UserID})
	expectStatus(t, "oversized body", http.StatusRequestEntityTooLarge, http.MethodDelete, path, owner.Token, map[string]string{"user_id": a.UserID, "pad": strings.Repeat("x", 4000)})
	if roleOf(listMembers(t, owner.TenantID, owner.Token), owner.UserID) != "owner" {
		t.Fatal("the owner row must remain")
	}

	// owner removes the admin; the removed admin's next request is a non-member request
	expectStatus(t, "owner removes admin", http.StatusOK, http.MethodDelete, path, owner.Token, map[string]string{"user_id": b.UserID})
	expectStatus(t, "removed admin lists", http.StatusNotFound, http.MethodGet, path, b.Token, nil)
	expectStatus(t, "removed admin invites", http.StatusNotFound, http.MethodPost, path, b.Token, map[string]string{"email": stranger.Email})
	expectStatus(t, "removed twice", http.StatusNotFound, http.MethodDelete, path, owner.Token, map[string]string{"user_id": b.UserID})
	if len(listMembers(t, b.TenantID, b.Token)) != 1 {
		t.Error("the removed member's own workspace must be untouched")
	}

	// the owner withdraws a pending invitation, which can be sent again
	expectStatus(t, "invite c", http.StatusOK, http.MethodPost, path, owner.Token, map[string]string{"email": c.Email})
	expectStatus(t, "withdraw c", http.StatusOK, http.MethodDelete, path, owner.Token, map[string]string{"user_id": c.UserID})
	if roleOf(listMembers(t, owner.TenantID, owner.Token), c.UserID) != "" {
		t.Error("the withdrawn invitation must be gone")
	}
	expectStatus(t, "c accepts a withdrawn invitation", http.StatusNotFound, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, c.Token, nil)
	expectStatus(t, "re-invite c", http.StatusOK, http.MethodPost, path, owner.Token, map[string]string{"email": c.Email})

	// a member leaves; a leave names only the caller
	expectStatus(t, "a leaves", http.StatusOK, http.MethodDelete, path, a.Token, map[string]string{"user_id": a.UserID})
	expectStatus(t, "a has left", http.StatusNotFound, http.MethodGet, path, a.Token, nil)
	if roleOf(listMembers(t, owner.TenantID, owner.Token), a.UserID) != "" {
		t.Error("the leaver must be gone")
	}
	// a's own workspace and its API token are unaffected by leaving another one
	if !tokenListed(t, a.Token, token.Token) {
		t.Error("a's own API token must survive a's removal from another workspace")
	}
	if m := listMembers(t, owner.TenantID, owner.Token); roleOf(m, owner.UserID) != "owner" || roleOf(m, c.UserID) != "invite" {
		t.Errorf("final membership: %v", m)
	}
}

func TestRacingRemovalsThroughIngressKeepTheOwner(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	member := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, member)
	inviteAndAccept(t, owner, member)
	path := tenantUsers(owner.TenantID)

	const n = 8
	codes := make([]int, n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			switch i % 4 {
			case 0:
				codes[i], _ = status(t, http.MethodDelete, path, owner.Token, map[string]string{"user_id": member.UserID})
			case 1:
				codes[i], _ = status(t, http.MethodDelete, path, member.Token, map[string]string{"user_id": member.UserID})
			case 2:
				codes[i], _ = status(t, http.MethodDelete, path, owner.Token, map[string]string{"user_id": owner.UserID})
			default:
				codes[i], _ = status(t, http.MethodPatch, tenantUser(owner.TenantID, owner.UserID), owner.Token, map[string]string{"role": "normal"})
			}
		}(i)
	}
	wg.Wait()
	removed := 0
	for i, c := range codes {
		switch i % 4 {
		case 0, 1:
			if c == http.StatusOK {
				removed++
			} else if c != http.StatusNotFound {
				t.Errorf("removal %d: %d", i, c)
			}
		default:
			if c != http.StatusBadRequest {
				t.Errorf("owner-row attempt %d: %d", i, c)
			}
		}
	}
	if removed != 1 {
		t.Errorf("exactly one of the racing removals wins, got %d: %v", removed, codes)
	}
	m := listMembers(t, owner.TenantID, owner.Token)
	if len(m) != 1 || roleOf(m, owner.UserID) != "owner" {
		t.Errorf("the owner alone must remain: %v", m)
	}
}

func TestMembershipMutationsRefuseAPIAndBetaCredentialsThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	member := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, member)
	inviteAndAccept(t, owner, member)
	created := createToken(t, owner.Token)
	for _, cred := range []string{created.Token, created.Beta} {
		for _, c := range []struct {
			method, path string
			body         any
		}{
			{http.MethodPatch, tenantUser(owner.TenantID, member.UserID), map[string]string{"role": "admin"}},
			{http.MethodDelete, tenantUsers(owner.TenantID), map[string]string{"user_id": member.UserID}},
		} {
			resp, body := send(t, c.method, c.path, cred, c.body)
			if resp.StatusCode != http.StatusUnauthorized || !isUnauthorized(body) {
				t.Errorf("%s %s with an API or beta credential: %d %s", c.method, c.path, resp.StatusCode, body)
			}
		}
	}
	if roleOf(listMembers(t, owner.TenantID, owner.Token), member.UserID) != "normal" {
		t.Error("a refused credential must not change membership")
	}
}
