//go:build integration

package service

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/testutil"
)

// membersEnv wires the tenant service with the invite limiter on a per-test Redis prefix.
type membersEnv struct {
	*tenantEnv
}

func newMembersEnv(t *testing.T, perWindow int) *membersEnv {
	t.Helper()
	e := newTenantEnv(t, nil)
	e.tenant = NewTenant(e.db).WithInvites(NewLimiter(e.svc.limiter.c, "test-"+testutil.UniqueName("inv")), InviteLimits{PerWindow: perWindow, Window: time.Minute})
	return &membersEnv{e}
}

func (e *membersEnv) rowsFor(t *testing.T, tenantID, userID string) []entity.UserTenant {
	t.Helper()
	var rows []entity.UserTenant
	require.NoError(t, e.raw.Where("tenant_id = ? AND user_id = ?", tenantID, userID).Find(&rows).Error)
	return rows
}

// join makes userID a member of tenantID with the given role (the role-change endpoint lands in plan 02-23).
func (e *membersEnv) join(t *testing.T, userID, tenantID, role string) {
	t.Helper()
	e.invite(t, userID, tenantID, tenantID, role, "1")
}

// randomTenantID is a well-formed 32-hex id that belongs to no tenant.
func randomTenantID() string { return strings.Repeat("a", 20) + testutil.UniqueName("")[1:] }

func TestListMembersForOwnerAdminAndNormal(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, adminEmail, normalEmail := testutil.UniqueEmail("lo"), testutil.UniqueEmail("la"), testutil.UniqueEmail("ln")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	admin := e.register(t, adminEmail, testutil.FixtureCredential())
	normal := e.register(t, normalEmail, testutil.FixtureCredential())
	e.join(t, admin.ID, owner.ID, "admin")
	e.join(t, normal.ID, owner.ID, "normal")

	for _, email := range []string{ownerEmail, adminEmail, normalEmail} {
		got, err := e.tenant.ListMembers(ctx, e.principal(t, email), owner.ID, 1, 100)
		require.NoError(t, err, email)
		require.Len(t, got, 3, email)
		assert.Equal(t, "owner", got[0].Role, "the owner row comes first")
		assert.Equal(t, owner.ID, got[0].UserID)
		assert.Equal(t, strings.ToLower(ownerEmail), got[0].Email)
		assert.NotEmpty(t, got[0].Nickname)
		assert.False(t, got[0].JoinedAt.IsZero())
	}
}

func TestListMembersIsNotFoundForStrangerInviteeAndRandomTenant(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	owner := e.register(t, testutil.UniqueEmail("so"), testutil.FixtureCredential())
	strangerEmail, inviteeEmail := testutil.UniqueEmail("ss"), testutil.UniqueEmail("si")
	e.register(t, strangerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	e.invite(t, invitee.ID, owner.ID, owner.ID, "invite", "1")

	_, errStranger := e.tenant.ListMembers(ctx, e.principal(t, strangerEmail), owner.ID, 1, 100)
	_, errInvitee := e.tenant.ListMembers(ctx, e.principal(t, inviteeEmail), owner.ID, 1, 100)
	_, errRandom := e.tenant.ListMembers(ctx, e.principal(t, strangerEmail), randomTenantID(), 1, 100)
	for name, err := range map[string]error{"stranger": errStranger, "invitee only": errInvitee, "random id": errRandom} {
		assert.ErrorIs(t, err, ErrNotFound, name)
		assert.NotErrorIs(t, err, ErrForbidden, name)
	}
	assert.Equal(t, errRandom.Error(), errStranger.Error())
	assert.Equal(t, errRandom.Error(), errInvitee.Error())
}

func TestListMembersIgnoresInactiveRowsAndHidesPendingFromNonOwners(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, normalEmail := testutil.UniqueEmail("po"), testutil.UniqueEmail("pn")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	normal := e.register(t, normalEmail, testutil.FixtureCredential())
	gone := e.register(t, testutil.UniqueEmail("pg"), testutil.FixtureCredential())
	pending := e.register(t, testutil.UniqueEmail("pp"), testutil.FixtureCredential())
	e.join(t, normal.ID, owner.ID, "normal")
	e.invite(t, gone.ID, owner.ID, owner.ID, "normal", "0")
	e.invite(t, pending.ID, owner.ID, owner.ID, "invite", "1")

	asOwner, err := e.tenant.ListMembers(ctx, e.principal(t, ownerEmail), owner.ID, 1, 100)
	require.NoError(t, err)
	roles := map[string]string{}
	for _, m := range asOwner {
		roles[m.UserID] = m.Role
	}
	assert.Equal(t, map[string]string{owner.ID: "owner", normal.ID: "normal", pending.ID: "invite"}, roles, "the owner also sees pending invitations; an inactive row is nobody")

	asNormal, err := e.tenant.ListMembers(ctx, e.principal(t, normalEmail), owner.ID, 1, 100)
	require.NoError(t, err)
	for _, m := range asNormal {
		assert.NotEqual(t, "invite", m.Role, "a member who is not the owner never sees pending invitations")
	}
	assert.Len(t, asNormal, 2)
}

func TestListMembersPaginationIsBounded(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail := testutil.UniqueEmail("pg")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	for i := 0; i < 2; i++ {
		u := e.register(t, testutil.UniqueEmail("pgm"), testutil.FixtureCredential())
		e.join(t, u.ID, owner.ID, "normal")
	}
	p := e.principal(t, ownerEmail)
	page1, err := e.tenant.ListMembers(ctx, p, owner.ID, 1, 2)
	require.NoError(t, err)
	page2, err := e.tenant.ListMembers(ctx, p, owner.ID, 2, 2)
	require.NoError(t, err)
	assert.Len(t, page1, 2)
	assert.Len(t, page2, 1)
	for _, bad := range [][2]int{{0, 10}, {1, 0}, {1, MaxMemberPageSize + 1}, {-1, 10}} {
		_, err := e.tenant.ListMembers(ctx, p, owner.ID, bad[0], bad[1])
		var ve *ValidationError
		assert.True(t, errors.As(err, &ve), "page %d size %d must be rejected", bad[0], bad[1])
	}
}

func TestInviteCreatesPendingRowAndInviteeSeesIt(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, inviteeEmail := testutil.UniqueEmail("io"), testutil.UniqueEmail("ii")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())

	got, err := e.tenant.Invite(ctx, e.principal(t, ownerEmail), owner.ID, "  "+strings.ToUpper(inviteeEmail)+" ")
	require.NoError(t, err)
	assert.Equal(t, invitee.ID, got.UserID)
	assert.Equal(t, "invite", got.Role)

	rows := e.rowsFor(t, owner.ID, invitee.ID)
	require.Len(t, rows, 1)
	assert.Equal(t, "invite", rows[0].Role)
	assert.Equal(t, owner.ID, rows[0].InvitedBy, "invited_by is the caller")
	require.NotNil(t, rows[0].Status)
	assert.Equal(t, "1", *rows[0].Status)

	list, err := e.tenant.ListMemberships(ctx, e.principal(t, inviteeEmail))
	require.NoError(t, err)
	var invited bool
	for _, m := range list {
		if m.TenantID == owner.ID && m.Role == "invite" {
			invited = true
		}
	}
	assert.True(t, invited, "the invitee's tenant list shows role invite")
}

func TestInviteErrorsAreDistinctAndNameNothingElse(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, memberEmail, invitedEmail := testutil.UniqueEmail("eo"), testutil.UniqueEmail("em"), testutil.UniqueEmail("ei")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	member := e.register(t, memberEmail, testutil.FixtureCredential())
	invited := e.register(t, invitedEmail, testutil.FixtureCredential())
	e.join(t, member.ID, owner.ID, "normal")
	e.invite(t, invited.ID, owner.ID, owner.ID, "invite", "1")
	p := e.principal(t, ownerEmail)

	cases := map[string]struct {
		email string
		want  error
	}{
		"self":            {ownerEmail, ErrInviteSelf},
		"already member":  {memberEmail, ErrAlreadyMember},
		"already invited": {invitedEmail, ErrAlreadyInvited},
		"unknown email":   {testutil.UniqueEmail("nobody"), ErrUserNotFound},
	}
	seen := map[string]string{}
	for name, c := range cases {
		_, err := e.tenant.Invite(ctx, p, owner.ID, c.email)
		require.ErrorIs(t, err, c.want, name)
		for _, secret := range []string{owner.ID, member.ID, invited.ID, "tenant"} {
			assert.NotContains(t, err.Error(), secret, name)
		}
		seen[err.Error()] = name
	}
	assert.Len(t, seen, 4, "the four refusals are distinguishable")
	assert.EqualValues(t, 1, len(e.rowsFor(t, owner.ID, member.ID)))
	assert.EqualValues(t, 1, len(e.rowsFor(t, owner.ID, invited.ID)))
}

func TestInviteRefusesInvalidEmailAndInactiveAccounts(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail := testutil.UniqueEmail("vo")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	inactiveEmail := testutil.UniqueEmail("vi")
	inactive := e.register(t, inactiveEmail, testutil.FixtureCredential())
	require.NoError(t, e.raw.Model(&entity.User{}).Where("id = ?", inactive.ID).Update("status", "0").Error)
	p := e.principal(t, ownerEmail)

	for _, bad := range []string{"", "   ", "no-at-sign", "a@b", strings.Repeat("a", 300) + "@example.test", "x@example.test, y@example.test"} {
		_, err := e.tenant.Invite(ctx, p, owner.ID, bad)
		var ve *ValidationError
		assert.True(t, errors.As(err, &ve), "%q must be a validation error", bad)
	}
	_, err := e.tenant.Invite(ctx, p, owner.ID, inactiveEmail)
	assert.ErrorIs(t, err, ErrUserNotFound, "a disabled account is as good as unknown (D-14: existing active accounts only)")
	assert.Empty(t, e.rowsFor(t, owner.ID, inactive.ID))
}

func TestOnlyTheOwnerMayInvite(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, adminEmail, normalEmail, strangerEmail, inviteeEmail := testutil.UniqueEmail("wo"), testutil.UniqueEmail("wa"), testutil.UniqueEmail("wn"), testutil.UniqueEmail("ws"), testutil.UniqueEmail("wi")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	admin := e.register(t, adminEmail, testutil.FixtureCredential())
	normal := e.register(t, normalEmail, testutil.FixtureCredential())
	e.register(t, strangerEmail, testutil.FixtureCredential())
	target := e.register(t, inviteeEmail, testutil.FixtureCredential())
	pendingEmail := testutil.UniqueEmail("wp")
	pending := e.register(t, pendingEmail, testutil.FixtureCredential())
	e.join(t, admin.ID, owner.ID, "admin")
	e.join(t, normal.ID, owner.ID, "normal")
	e.invite(t, pending.ID, owner.ID, owner.ID, "invite", "1")

	for _, email := range []string{adminEmail, normalEmail} {
		_, err := e.tenant.Invite(ctx, e.principal(t, email), owner.ID, inviteeEmail)
		assert.ErrorIs(t, err, ErrForbidden, email)
	}
	_, errStranger := e.tenant.Invite(ctx, e.principal(t, strangerEmail), owner.ID, inviteeEmail)
	_, errPending := e.tenant.Invite(ctx, e.principal(t, pendingEmail), owner.ID, inviteeEmail)
	_, errRandom := e.tenant.Invite(ctx, e.principal(t, strangerEmail), randomTenantID(), inviteeEmail)
	for name, err := range map[string]error{"stranger": errStranger, "pending invitee": errPending, "random tenant": errRandom} {
		assert.ErrorIs(t, err, ErrNotFound, name)
	}
	assert.Equal(t, errRandom.Error(), errStranger.Error())
	assert.Empty(t, e.rowsFor(t, owner.ID, target.ID), "no refused call created a row")

	apiPrincipal := e.principal(t, ownerEmail)
	apiPrincipal.AuthType = AuthTypeAPI
	_, err := e.tenant.Invite(ctx, apiPrincipal, owner.ID, inviteeEmail)
	assert.ErrorIs(t, err, ErrForbidden, "an API credential never manages the team")
}

func TestOwnerCannotInviteIntoAnotherTenant(t *testing.T) {
	e := newMembersEnv(t, 100)
	aEmail := testutil.UniqueEmail("xa")
	a := e.register(t, aEmail, testutil.FixtureCredential())
	b := e.register(t, testutil.UniqueEmail("xb"), testutil.FixtureCredential())
	target := e.register(t, testutil.UniqueEmail("xt"), testutil.FixtureCredential())
	_, err := e.tenant.Invite(context.Background(), e.principal(t, aEmail), b.ID, "unused@example.test")
	assert.ErrorIs(t, err, ErrNotFound, "being an owner elsewhere grants nothing here")
	_, err = e.tenant.Invite(context.Background(), e.principal(t, aEmail), b.ID, strings.ToLower(target.Email))
	assert.ErrorIs(t, err, ErrNotFound)
	assert.Empty(t, e.rowsFor(t, b.ID, target.ID))
	assert.Empty(t, e.rowsFor(t, a.ID, target.ID))
}

func TestParallelInvitesCreateExactlyOneRow(t *testing.T) {
	e := newMembersEnv(t, 1000)
	ownerEmail, inviteeEmail := testutil.UniqueEmail("po"), testutil.UniqueEmail("pi")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	p := e.principal(t, ownerEmail)

	const n = 12
	var wg sync.WaitGroup
	results := make([]error, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, results[i] = e.tenant.Invite(context.Background(), p, owner.ID, inviteeEmail)
		}(i)
	}
	wg.Wait()
	ok := 0
	for _, err := range results {
		switch {
		case err == nil:
			ok++
		default:
			assert.ErrorIs(t, err, ErrAlreadyInvited)
		}
	}
	assert.Equal(t, 1, ok, "exactly one request wins")
	assert.Len(t, e.rowsFor(t, owner.ID, invitee.ID), 1, "one row, no duplicates")
}

func TestInviteIsRateLimitedPerOwnerAndTenant(t *testing.T) {
	e := newMembersEnv(t, 3)
	ownerEmail := testutil.UniqueEmail("ro")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	p := e.principal(t, ownerEmail)
	for i := 0; i < 3; i++ {
		_, err := e.tenant.Invite(context.Background(), p, owner.ID, testutil.UniqueEmail("nobody"))
		require.ErrorIs(t, err, ErrUserNotFound)
	}
	_, err := e.tenant.Invite(context.Background(), p, owner.ID, testutil.UniqueEmail("nobody"))
	rl, limited := IsRateLimited(err)
	require.True(t, limited, "the fourth attempt inside the window is refused: %v", err)
	assert.Positive(t, rl.RetryAfter)
}

func TestInviteWithoutLimiterFailsClosed(t *testing.T) {
	e := newTenantEnv(t, nil)
	ownerEmail := testutil.UniqueEmail("nl")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	_, err := NewTenant(e.db).Invite(context.Background(), e.principal(t, ownerEmail), owner.ID, testutil.UniqueEmail("x"))
	assert.ErrorIs(t, err, ErrUnavailable)
}

func TestAcceptChangesInviteToNormalAndMemberListIncludesThem(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, inviteeEmail := testutil.UniqueEmail("ao"), testutil.UniqueEmail("ai")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	_, err := e.tenant.Invite(ctx, e.principal(t, ownerEmail), owner.ID, inviteeEmail)
	require.NoError(t, err)

	pi := e.principal(t, inviteeEmail)
	require.NoError(t, e.tenant.Respond(ctx, pi, owner.ID, InviteAccept))
	rows := e.rowsFor(t, owner.ID, invitee.ID)
	require.Len(t, rows, 1)
	assert.Equal(t, "normal", rows[0].Role)

	members, err := e.tenant.ListMembers(ctx, pi, owner.ID, 1, 100)
	require.NoError(t, err)
	assert.Len(t, members, 2)
	assert.ErrorIs(t, e.tenant.Respond(ctx, pi, owner.ID, InviteAccept), ErrNotFound, "twice is not found")
	assert.ErrorIs(t, e.tenant.Respond(ctx, pi, owner.ID, InviteDecline), ErrNotFound, "a member cannot decline into a deletion")
	assert.Len(t, e.rowsFor(t, owner.ID, invitee.ID), 1, "the row survives")
}

func TestAcceptFromStrangerOwnerOrAdminChangesNothing(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, adminEmail, strangerEmail := testutil.UniqueEmail("do"), testutil.UniqueEmail("da"), testutil.UniqueEmail("ds")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	admin := e.register(t, adminEmail, testutil.FixtureCredential())
	e.register(t, strangerEmail, testutil.FixtureCredential())
	e.join(t, admin.ID, owner.ID, "admin")

	for name, c := range map[string]struct{ email, tenant, userID string }{
		"stranger": {strangerEmail, owner.ID, ""},
		"owner":    {ownerEmail, owner.ID, owner.ID},
		"admin":    {adminEmail, owner.ID, admin.ID},
		"random":   {strangerEmail, randomTenantID(), ""},
	} {
		for _, action := range []string{InviteAccept, InviteDecline} {
			err := e.tenant.Respond(ctx, e.principal(t, c.email), c.tenant, action)
			assert.ErrorIs(t, err, ErrNotFound, name+" "+action)
		}
	}
	assert.Equal(t, "owner", e.rowsFor(t, owner.ID, owner.ID)[0].Role, "D-27: the owner is never demoted")
	assert.Equal(t, "admin", e.rowsFor(t, owner.ID, admin.ID)[0].Role, "D-27: an admin is never demoted")
}

func TestDeclineDeletesRowAndAllowsANewInvite(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, inviteeEmail := testutil.UniqueEmail("co"), testutil.UniqueEmail("ci")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	po := e.principal(t, ownerEmail)
	_, err := e.tenant.Invite(ctx, po, owner.ID, inviteeEmail)
	require.NoError(t, err)
	require.NoError(t, e.tenant.Respond(ctx, e.principal(t, inviteeEmail), owner.ID, InviteDecline))
	assert.Empty(t, e.rowsFor(t, owner.ID, invitee.ID))
	_, err = e.tenant.Invite(ctx, po, owner.ID, inviteeEmail)
	require.NoError(t, err, "after a decline a new invitation is possible")
	assert.Len(t, e.rowsFor(t, owner.ID, invitee.ID), 1)
}

func TestRespondRejectsUnknownAction(t *testing.T) {
	e := newMembersEnv(t, 100)
	email := testutil.UniqueEmail("ua")
	owner := e.register(t, email, testutil.FixtureCredential())
	err := e.tenant.Respond(context.Background(), e.principal(t, email), owner.ID, "promote")
	var ve *ValidationError
	assert.True(t, errors.As(err, &ve))
}

func TestInviteRoleNeverCountsAsMembershipForPermissions(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	ownerEmail, inviteeEmail := testutil.UniqueEmail("mo"), testutil.UniqueEmail("mi")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	e.invite(t, invitee.ID, owner.ID, owner.ID, "invite", "1")
	pi := e.principal(t, inviteeEmail)
	_, err := e.tenant.Invite(ctx, pi, owner.ID, ownerEmail)
	assert.ErrorIs(t, err, ErrNotFound)
	_, err = e.tenant.ListMembers(ctx, pi, owner.ID, 1, 10)
	assert.ErrorIs(t, err, ErrNotFound)
}

func TestStoreFailureIsUnavailableNotAnInternalError(t *testing.T) {
	e := newMembersEnv(t, 100)
	ctx := context.Background()
	email := testutil.UniqueEmail("sf")
	owner := e.register(t, email, testutil.FixtureCredential())
	p := e.principal(t, email)

	closed, err := dao.OpenDB(ctx, e.cfg.MySQL)
	require.NoError(t, err)
	require.NoError(t, closed.Close())
	svc := NewTenant(closed).WithInvites(e.tenant.limiter, e.tenant.limits)

	_, err = svc.ListMembers(ctx, p, owner.ID, 1, 10)
	assert.ErrorIs(t, err, ErrUnavailable)
	_, err = svc.Invite(ctx, p, owner.ID, testutil.UniqueEmail("x"))
	assert.ErrorIs(t, err, ErrUnavailable)
	assert.ErrorIs(t, svc.Respond(ctx, p, owner.ID, InviteAccept), ErrUnavailable)
	assert.NotContains(t, err.Error(), "SELECT", "only the error type is kept")
}
