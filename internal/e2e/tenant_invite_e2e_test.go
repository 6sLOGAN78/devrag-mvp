//go:build e2e

package e2e

import (
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"testing"

	"devrag/internal/testutil"
)

type memberJSON map[string]any

func tenantUsers(tenantID string) string { return "/api/v1/tenants/" + tenantID + "/users" }

func randomHexID() string { return strings.Repeat("c", 20) + testutil.UniqueName("")[1:] }

func envData[T any](t *testing.T, body []byte) T {
	t.Helper()
	var env struct {
		Code int `json:"code"`
		Data T   `json:"data"`
	}
	if err := json.Unmarshal(body, &env); err != nil {
		t.Fatalf("not an envelope: %v: %s", err, body)
	}
	return env.Data
}

func listMembers(t *testing.T, tenantID, token string) []memberJSON {
	t.Helper()
	resp, body := send(t, http.MethodGet, tenantUsers(tenantID), token, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("list members: %d %s", resp.StatusCode, body)
	}
	return envData[[]memberJSON](t, body)
}

func roleOf(members []memberJSON, userID string) string {
	for _, m := range members {
		if m["id"] == userID {
			s, _ := m["role"].(string)
			return s
		}
	}
	return ""
}

func status(t *testing.T, method, path, token string, body any) (int, string) {
	t.Helper()
	resp, out := send(t, method, path, token, body)
	return resp.StatusCode, string(out)
}

func TestMembersListAndNotFoundEquivalenceThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	stranger := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, stranger)
	invitee := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, invitee)
	admin := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, admin)
	testutil.InsertPendingInvite(t, cfg.MySQL, invitee.UserID, owner.TenantID, owner.UserID)
	testutil.InsertPendingInvite(t, cfg.MySQL, admin.UserID, owner.TenantID, owner.UserID)
	testutil.SetMemberRole(t, cfg.MySQL, owner.TenantID, admin.UserID, "admin")

	members := listMembers(t, owner.TenantID, owner.Token)
	if roleOf(members, owner.UserID) != "owner" || roleOf(members, admin.UserID) != "admin" || roleOf(members, invitee.UserID) != "invite" {
		t.Fatalf("owner list: %v", members)
	}
	allowed := map[string]bool{"id": true, "nickname": true, "email": true, "avatar": true, "role": true, "joined_time": true}
	for _, m := range members {
		for k := range m {
			if !allowed[k] {
				t.Errorf("member DTO leaks field %q: %v", k, m)
			}
		}
		for _, k := range []string{"id", "nickname", "email", "role"} {
			if s, _ := m[k].(string); s == "" {
				t.Errorf("member DTO lacks %q: %v", k, m)
			}
		}
	}
	raw, _ := json.Marshal(members)
	for _, banned := range []string{"password", "access_token", "token", "status", "invited_by", "pbkdf2"} {
		if strings.Contains(strings.ToLower(string(raw)), banned) {
			t.Errorf("member list contains %q", banned)
		}
	}
	if got := listMembers(t, owner.TenantID, admin.Token); roleOf(got, invitee.UserID) != "" || roleOf(got, owner.UserID) != "owner" {
		t.Errorf("an admin sees members but never pending invitations: %v", got)
	}

	// A stranger, an invitee-only user and a random id get byte-identical 404 answers.
	randomCode, randomBody := status(t, http.MethodGet, tenantUsers(randomHexID()), stranger.Token, nil)
	strangerCode, strangerBody := status(t, http.MethodGet, tenantUsers(owner.TenantID), stranger.Token, nil)
	inviteeCode, inviteeBody := status(t, http.MethodGet, tenantUsers(owner.TenantID), invitee.Token, nil)
	if randomCode != http.StatusNotFound || strangerCode != randomCode || inviteeCode != randomCode {
		t.Fatalf("statuses: random %d stranger %d invitee %d", randomCode, strangerCode, inviteeCode)
	}
	if strangerBody != randomBody || inviteeBody != randomBody {
		t.Errorf("bodies differ:\n random   %s\n stranger %s\n invitee  %s", randomBody, strangerBody, inviteeBody)
	}
	for _, bad := range []string{"%00", "..", "x' OR '1'='1", strings.Repeat("a", 300)} {
		if code, body := status(t, http.MethodGet, tenantUsers(bad), stranger.Token, nil); code != http.StatusNotFound && code != http.StatusBadRequest {
			t.Errorf("odd tenant id %q: %d %s", bad, code, body)
		}
	}
	if code, _ := status(t, http.MethodGet, tenantUsers(owner.TenantID), "", nil); code != http.StatusUnauthorized {
		t.Errorf("no credential: %d", code)
	}
	if code, _ := status(t, http.MethodGet, tenantUsers(owner.TenantID)+"?page_size=101", owner.Token, nil); code != http.StatusBadRequest {
		t.Errorf("unbounded page size must be refused, got %d", code)
	}
}

func TestInviteAcceptDeclineFlowThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	invitee := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, invitee)
	decliner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, decliner)
	stranger := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, stranger)
	path := tenantUsers(owner.TenantID)

	// owner invites by email; extra body fields are ignored (mass assignment)
	code, body := status(t, http.MethodPost, path, owner.Token, map[string]any{
		"email": strings.ToUpper(invitee.Email), "role": "owner", "tenant_id": stranger.TenantID, "status": "0", "invited_by": stranger.UserID, "user_id": stranger.UserID,
	})
	if code != http.StatusOK {
		t.Fatalf("invite: %d %s", code, body)
	}
	got := envData[memberJSON](t, []byte(body))
	if got["id"] != invitee.UserID || got["role"] != "invite" {
		t.Errorf("invite answer: %v", got)
	}
	members := listMembers(t, owner.TenantID, owner.Token)
	if roleOf(members, invitee.UserID) != "invite" || roleOf(members, stranger.UserID) != "" {
		t.Errorf("invite body fields must be ignored: %v", members)
	}
	if listMembers(t, stranger.TenantID, stranger.Token)[0]["id"] != stranger.UserID || len(listMembers(t, stranger.TenantID, stranger.Token)) != 1 {
		t.Error("the stranger's own tenant must be untouched")
	}

	// the refusals: self, already invited, unknown email, not an email
	selfCode, selfBody := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": owner.Email})
	dupCode, dupBody := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": invitee.Email})
	unkCode, unkBody := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": testutil.UniqueEmail("nobody")})
	badCode, _ := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": "not-an-email"})
	emptyCode, _ := status(t, http.MethodPost, path, owner.Token, nil)
	if selfCode != http.StatusConflict || dupCode != http.StatusConflict || unkCode != http.StatusNotFound || badCode != http.StatusBadRequest || emptyCode != http.StatusBadRequest {
		t.Fatalf("refusals: self %d dup %d unknown %d bad %d empty %d", selfCode, dupCode, unkCode, badCode, emptyCode)
	}
	if selfBody == dupBody || dupBody == unkBody || selfBody == unkBody {
		t.Errorf("the refusals must be distinguishable: %s | %s | %s", selfBody, dupBody, unkBody)
	}
	for _, b := range []string{selfBody, dupBody, unkBody} {
		for _, secret := range []string{owner.TenantID, invitee.TenantID, stranger.TenantID, "SQL", "gorm", "mysql"} {
			if strings.Contains(b, secret) {
				t.Errorf("refusal leaks %q: %s", secret, b)
			}
		}
	}

	// the invitee sees role invite in the tenant list, gets 404 on the member list, and accepts
	resp, listBody := send(t, http.MethodGet, "/v1/tenant/list", invitee.Token, nil)
	if resp.StatusCode != http.StatusOK || !strings.Contains(string(listBody), `"invite"`) {
		t.Errorf("tenant list should show the invitation: %d %s", resp.StatusCode, listBody)
	}
	if code, _ := status(t, http.MethodGet, path, invitee.Token, nil); code != http.StatusNotFound {
		t.Errorf("an invitee is not a member yet: %d", code)
	}
	if code, body := status(t, http.MethodPost, path, invitee.Token, map[string]string{"email": stranger.Email}); code != http.StatusNotFound {
		t.Errorf("an invitee cannot invite: %d %s", code, body)
	}
	if code, body := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, invitee.Token, map[string]string{"action": "promote"}); code != http.StatusBadRequest {
		t.Errorf("unknown action: %d %s", code, body)
	}
	if code, body := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, invitee.Token, nil); code != http.StatusOK {
		t.Fatalf("accept with no body: %d %s", code, body)
	}
	if roleOf(listMembers(t, owner.TenantID, invitee.Token), invitee.UserID) != "normal" {
		t.Error("after accept the invitee is a normal member")
	}
	if code, _ := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, invitee.Token, map[string]string{"action": "accept"}); code != http.StatusNotFound {
		t.Errorf("accepting twice: %d", code)
	}

	// a normal member cannot invite
	if code, _ := status(t, http.MethodPost, path, invitee.Token, map[string]string{"email": decliner.Email}); code != http.StatusForbidden {
		t.Errorf("normal member invite: %d, want 403", code)
	}
	// an admin cannot either
	testutil.SetMemberRole(t, cfg.MySQL, owner.TenantID, invitee.UserID, "admin")
	if code, _ := status(t, http.MethodPost, path, invitee.Token, map[string]string{"email": decliner.Email}); code != http.StatusForbidden {
		t.Errorf("admin invite: %d, want 403", code)
	}
	// D-27: accept called by an owner or admin changes nothing
	for _, who := range []testutil.Account{owner, invitee} {
		if code, _ := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, who.Token, map[string]string{"action": "accept"}); code != http.StatusNotFound {
			t.Errorf("accept by a non-invitee: %d", code)
		}
		if code, _ := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, who.Token, map[string]string{"action": "decline"}); code != http.StatusNotFound {
			t.Errorf("decline by a non-invitee: %d", code)
		}
	}
	members = listMembers(t, owner.TenantID, owner.Token)
	if roleOf(members, owner.UserID) != "owner" || roleOf(members, invitee.UserID) != "admin" {
		t.Errorf("roles must be untouched: %v", members)
	}
	if code, _ := status(t, http.MethodPatch, "/api/v1/tenants/"+randomHexID(), stranger.Token, nil); code != http.StatusNotFound {
		t.Errorf("accept on a random tenant: %d", code)
	}

	// decline deletes the row and allows a new invitation
	if code, body := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": decliner.Email}); code != http.StatusOK {
		t.Fatalf("second invite: %d %s", code, body)
	}
	if code, body := status(t, http.MethodPatch, "/api/v1/tenants/"+owner.TenantID, decliner.Token, map[string]string{"action": "decline"}); code != http.StatusOK {
		t.Fatalf("decline: %d %s", code, body)
	}
	if roleOf(listMembers(t, owner.TenantID, owner.Token), decliner.UserID) != "" {
		t.Error("declined invitation must be gone")
	}
	if code, body := status(t, http.MethodPost, path, owner.Token, map[string]string{"email": decliner.Email}); code != http.StatusOK {
		t.Errorf("re-invite after decline: %d %s", code, body)
	}
}

func TestParallelInvitesThroughIngressLeaveOneRow(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	invitee := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, invitee)

	const n = 8
	codes := make([]int, n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			resp, _ := send(t, http.MethodPost, tenantUsers(owner.TenantID), owner.Token, map[string]string{"email": invitee.Email})
			codes[i] = resp.StatusCode
		}(i)
	}
	wg.Wait()
	ok, conflict := 0, 0
	for _, c := range codes {
		switch c {
		case http.StatusOK:
			ok++
		case http.StatusConflict:
			conflict++
		}
	}
	if ok != 1 || conflict != n-1 {
		t.Errorf("parallel invites: %v (want one 200 and %d 409)", codes, n-1)
	}
	count := 0
	for _, m := range listMembers(t, owner.TenantID, owner.Token) {
		if m["id"] == invitee.UserID {
			count++
		}
	}
	if count != 1 {
		t.Errorf("%d rows for the invitee, want 1", count)
	}
}

func TestTeamRoutesRefuseAPIAndBetaCredentialsThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	invitee := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, invitee)
	created := createToken(t, owner.Token)

	for _, cred := range []string{created.Token, created.Beta} {
		for _, c := range []struct {
			method, path string
			body         any
		}{
			{http.MethodGet, tenantUsers(owner.TenantID), nil},
			{http.MethodPost, tenantUsers(owner.TenantID), map[string]string{"email": invitee.Email}},
			{http.MethodPatch, "/api/v1/tenants/" + owner.TenantID, nil},
		} {
			resp, body := send(t, c.method, c.path, cred, c.body)
			if resp.StatusCode != http.StatusUnauthorized || !isUnauthorized(body) {
				t.Errorf("%s %s with an API or beta credential: %d %s", c.method, c.path, resp.StatusCode, body)
			}
		}
	}
	if members := listMembers(t, owner.TenantID, owner.Token); roleOf(members, invitee.UserID) != "" {
		t.Error("a refused credential must not create an invitation")
	}
}

func TestInviteRateLimitThroughIngress(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	owner := testutil.RegisterAccount(t, baseURL())
	defer testutil.DeleteAccount(t, cfg.MySQL, owner)
	limit := cfg.RateLimit.LoginPerIP
	if limit <= 0 || limit > 300 {
		t.Fatalf("login-class limit %d is not practical to exhaust; lower it in the test configuration", limit)
	}
	var last int
	var retryAfter string
	for i := 0; i <= limit+1; i++ {
		resp, _ := send(t, http.MethodPost, tenantUsers(owner.TenantID), owner.Token, map[string]string{"email": testutil.UniqueEmail("nobody")})
		last = resp.StatusCode
		if last == http.StatusTooManyRequests {
			retryAfter = resp.Header.Get("Retry-After")
			break
		}
		if last != http.StatusNotFound {
			t.Fatalf("attempt %d: %d", i, last)
		}
	}
	if last != http.StatusTooManyRequests || retryAfter == "" {
		t.Errorf("invites must be rate limited: last %d Retry-After %q", last, retryAfter)
	}
}
