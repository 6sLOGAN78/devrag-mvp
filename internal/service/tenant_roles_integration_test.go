//go:build integration

package service

import (
	"context"
	"errors"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/dao"
	"devrag/internal/testutil"
)

// teamFixture is an owner with an admin, a normal member, a pending invitee and a stranger.
type teamFixture struct {
	e                                                  *membersEnv
	owner, admin, normal, pending, stranger            testutil.Account
	ownerP, adminP, normalP, pendingP, strangerP       Principal
	ownerEmail, adminEmail, normalEmail, strangerEmail string
}

func newTeamFixture(t *testing.T, perWindow int) *teamFixture {
	t.Helper()
	e := newMembersEnv(t, perWindow)
	f := &teamFixture{e: e}
	// The principal is built the way the gate would: a session of the registered user. Every membership
	// decision reads the database, so no login (and its password hashing) is needed here; the token
	// path is covered end to end by the e2e tier.
	reg := func(prefix string) (testutil.Account, string, Principal) {
		email := testutil.UniqueEmail(prefix)
		u := e.register(t, email, testutil.FixtureCredential())
		return testutil.Account{UserID: u.ID, TenantID: u.ID, Email: email}, email, Principal{UserID: u.ID, TenantID: u.ID, Role: "owner", AuthType: AuthTypeJWT}
	}
	f.owner, f.ownerEmail, f.ownerP = reg("ro")
	f.admin, f.adminEmail, f.adminP = reg("ra")
	f.normal, f.normalEmail, f.normalP = reg("rn")
	f.pending, _, f.pendingP = reg("rp")
	f.stranger, f.strangerEmail, f.strangerP = reg("rs")
	e.join(t, f.admin.UserID, f.owner.UserID, "admin")
	e.join(t, f.normal.UserID, f.owner.UserID, "normal")
	e.invite(t, f.pending.UserID, f.owner.UserID, f.owner.UserID, "invite", "1")
	return f
}

func (f *teamFixture) role(t *testing.T, userID string) string {
	t.Helper()
	rows := f.e.rowsFor(t, f.owner.UserID, userID)
	if len(rows) == 0 {
		return ""
	}
	require.Len(t, rows, 1, "never a duplicate row")
	return rows[0].Role
}

func TestChangeRoleOwnerPromotesAndDemotes(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	require.NoError(t, f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "admin"))
	assert.Equal(t, "admin", f.role(t, f.normal.UserID))
	require.NoError(t, f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "normal"))
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
	require.NoError(t, f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.admin.UserID, "normal"))
	assert.Equal(t, "normal", f.role(t, f.admin.UserID))
	require.NoError(t, f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.admin.UserID, "normal"), "setting the same role again is harmless")
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))
}

func TestChangeRoleNonOwnersAreForbiddenAndStrangersNotFound(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	for name, p := range map[string]Principal{"admin": f.adminP, "normal": f.normalP} {
		err := f.e.tenant.ChangeRole(ctx, p, f.owner.TenantID, f.normal.UserID, "admin")
		assert.ErrorIs(t, err, ErrForbidden, name)
		assert.NotErrorIs(t, err, ErrNotFound, name)
		// the 403 does not depend on the body being valid
		assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, p, f.owner.TenantID, f.owner.UserID, "owner"), ErrForbidden, name+" owner")
	}
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
	for name, p := range map[string]Principal{"stranger": f.strangerP, "pending invitee": f.pendingP} {
		assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, p, f.owner.TenantID, f.normal.UserID, "admin"), ErrNotFound, name)
	}
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.strangerP, randomTenantID(), f.normal.UserID, "admin"), ErrNotFound)
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
}

func TestChangeRoleRefusesOwnerTargetOwnerRoleUnknownRolesAndPendingTargets(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	tenantID := f.owner.TenantID

	// the owner row cannot be targeted, not even by the owner (self-demotion bug of the reference, D-27)
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.owner.UserID, "normal"), ErrOwnerImmutable)
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.owner.UserID, "admin"), ErrOwnerImmutable)
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))

	// owner can never be set; invite can never be set; unknown or empty roles are refused
	for _, bad := range []string{"owner", "invite", "OWNER", "superuser", "", " admin", "admin ", "admin'--"} {
		err := f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.normal.UserID, bad)
		var ve *ValidationError
		assert.True(t, errors.As(err, &ve), "role %q: %v", bad, err)
	}
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
	assert.Equal(t, "admin", f.role(t, f.admin.UserID))

	// a pending invite is not a member: its role cannot be set
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.pending.UserID, "admin"), ErrInvitePending)
	assert.Equal(t, "invite", f.role(t, f.pending.UserID))

	// an absent target and a user of another tenant are not found; so are malformed ids
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.stranger.UserID, "admin"), ErrNotFound)
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, randomTenantID(), "admin"), ErrNotFound)
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, "", "admin"), ErrNotFound)
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, string(make([]byte, 300)), "admin"), ErrNotFound)
	assert.Empty(t, f.e.rowsFor(t, tenantID, f.stranger.UserID), "nothing was created for the stranger")
}

func TestChangeRoleIgnoresInactiveRows(t *testing.T) {
	f := newTeamFixture(t, 1000)
	gone := f.e.register(t, testutil.UniqueEmail("rg"), testutil.FixtureCredential())
	f.e.invite(t, gone.ID, f.owner.UserID, f.owner.UserID, "normal", "0")
	assert.ErrorIs(t, f.e.tenant.ChangeRole(context.Background(), f.ownerP, f.owner.TenantID, gone.ID, "admin"), ErrNotFound)
	assert.Equal(t, "normal", f.role(t, gone.ID), "an inactive row is untouched")
}

func TestChangeRoleCannotBeUsedFromAnotherTenantsOwnership(t *testing.T) {
	f := newTeamFixture(t, 1000)
	// the stranger owns their own tenant but is nobody in the owner's
	err := f.e.tenant.ChangeRole(context.Background(), f.strangerP, f.owner.TenantID, f.normal.UserID, "admin")
	assert.ErrorIs(t, err, ErrNotFound)
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
}

func TestRemoveMemberOwnerRemovesAdminNormalAndWithdrawsInvite(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	tenantID := f.owner.TenantID
	for _, id := range []string{f.admin.UserID, f.normal.UserID, f.pending.UserID} {
		require.NoError(t, f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, id))
		assert.Empty(t, f.e.rowsFor(t, tenantID, id))
	}
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))
	// the removed user's own workspace is untouched
	assert.Equal(t, "owner", f.e.rowsFor(t, f.normal.UserID, f.normal.UserID)[0].Role)
	// a withdrawn invitation can be sent again
	_, err := f.e.tenant.Invite(ctx, f.ownerP, tenantID, f.pending.Email)
	require.NoError(t, err)
	assert.Equal(t, "invite", f.role(t, f.pending.UserID))
	// removing twice is not found
	require.NoError(t, f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, f.pending.UserID))
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, f.pending.UserID), ErrNotFound)
}

func TestRemoveMemberMemberLeavesAndThenIsANonMember(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	tenantID := f.owner.TenantID
	for name, c := range map[string]struct {
		p  Principal
		id string
	}{"normal": {f.normalP, f.normal.UserID}, "admin": {f.adminP, f.admin.UserID}} {
		_, err := f.e.tenant.ListMembers(ctx, c.p, tenantID, 1, 10)
		require.NoError(t, err, name)
		require.NoError(t, f.e.tenant.RemoveMember(ctx, c.p, tenantID, c.id), name)
		assert.Empty(t, f.e.rowsFor(t, tenantID, c.id), name)
		// the very next request is a non-member request: same principal object, no cached membership
		_, err = f.e.tenant.ListMembers(ctx, c.p, tenantID, 1, 10)
		assert.ErrorIs(t, err, ErrNotFound, name)
		assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, c.p, tenantID, c.id), ErrNotFound, name+" leaving twice")
		_, err = f.e.tenant.Invite(ctx, c.p, tenantID, f.stranger.Email)
		assert.ErrorIs(t, err, ErrNotFound, name)
		// the leaver's own workspace still works
		own, err := f.e.tenant.ListMembers(ctx, c.p, c.id, 1, 10)
		require.NoError(t, err, name)
		assert.Len(t, own, 1)
	}
}

func TestRemoveMemberNonOwnerCannotRemoveSomeoneElse(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	tenantID := f.owner.TenantID
	for name, p := range map[string]Principal{"admin": f.adminP, "normal": f.normalP} {
		for _, target := range []string{f.normal.UserID, f.admin.UserID, f.pending.UserID, f.owner.UserID} {
			if (name == "admin" && target == f.admin.UserID) || (name == "normal" && target == f.normal.UserID) {
				continue
			}
			err := f.e.tenant.RemoveMember(ctx, p, tenantID, target)
			assert.ErrorIs(t, err, ErrForbidden, name+" removing "+target)
		}
	}
	for _, id := range []string{f.owner.UserID, f.admin.UserID, f.normal.UserID, f.pending.UserID} {
		assert.NotEmpty(t, f.e.rowsFor(t, tenantID, id), "nobody was removed")
	}
	// a stranger and a pending invitee get the shared 404, whoever they name
	for name, p := range map[string]Principal{"stranger": f.strangerP, "pending": f.pendingP} {
		for _, target := range []string{f.normal.UserID, f.owner.UserID, f.stranger.UserID, f.pending.UserID} {
			assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, p, tenantID, target), ErrNotFound, name)
		}
	}
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, f.strangerP, randomTenantID(), f.stranger.UserID), ErrNotFound)
	assert.NotEmpty(t, f.e.rowsFor(t, tenantID, f.pending.UserID), "the invitee cannot withdraw via DELETE")
}

func TestRemoveMemberOwnerRowIsNeverRemovable(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	tenantID := f.owner.TenantID
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, f.owner.UserID), ErrOwnerImmutable, "the owner cannot leave")
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))
	// an admin naming the owner is forbidden, not a silent self-removal
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, f.adminP, tenantID, f.owner.UserID), ErrForbidden)
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))
	assert.Equal(t, "admin", f.role(t, f.admin.UserID), "the admin was not removed in the owner's place")
	// an empty or malformed target is refused or not found, never a deletion
	err := f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, "")
	var ve *ValidationError
	assert.True(t, errors.As(err, &ve), "empty user_id: %v", err)
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, randomTenantID()), ErrNotFound)
	assert.Len(t, f.e.rowsFor(t, tenantID, f.owner.UserID), 1)
}

func TestRemoveMemberDoesNotDeleteTheTargetsOtherTenants(t *testing.T) {
	f := newTeamFixture(t, 1000)
	require.NoError(t, f.e.tenant.RemoveMember(context.Background(), f.ownerP, f.owner.TenantID, f.normal.UserID))
	assert.Len(t, f.e.rowsFor(t, f.normal.UserID, f.normal.UserID), 1, "the removed member's own owner row remains")
	assert.Len(t, f.e.rowsFor(t, f.stranger.UserID, f.stranger.UserID), 1)
}

func TestRacingRemovalsNeverDeleteTheOwnerRow(t *testing.T) {
	f := newTeamFixture(t, 100000)
	ctx := context.Background()
	tenantID := f.owner.TenantID
	var wg sync.WaitGroup
	const n = 16
	errs := make([]error, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			switch i % 4 {
			case 0:
				errs[i] = f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, f.owner.UserID)
			case 1:
				errs[i] = f.e.tenant.RemoveMember(ctx, f.adminP, tenantID, f.owner.UserID)
			case 2:
				errs[i] = f.e.tenant.ChangeRole(ctx, f.ownerP, tenantID, f.owner.UserID, "normal")
			default:
				errs[i] = f.e.tenant.RemoveMember(ctx, f.normalP, tenantID, f.owner.UserID)
			}
		}(i)
	}
	wg.Wait()
	for i, err := range errs {
		assert.Error(t, err, "call %d must be refused", i)
	}
	owners := 0
	for _, id := range []string{f.owner.UserID, f.admin.UserID, f.normal.UserID} {
		if f.role(t, id) == "owner" {
			owners++
		}
	}
	assert.Equal(t, 1, owners, "exactly one owner row remains")
	assert.Equal(t, "owner", f.role(t, f.owner.UserID))
}

func TestOwnerRemovesMemberWhileMemberLeavesLeavesConsistentState(t *testing.T) {
	for round := 0; round < 4; round++ {
		f := newTeamFixture(t, 100000)
		ctx := context.Background()
		tenantID := f.owner.TenantID
		var wg sync.WaitGroup
		var removeErr, leaveErr error
		start := make(chan struct{})
		wg.Add(2)
		go func() {
			defer wg.Done()
			<-start
			removeErr = f.e.tenant.RemoveMember(ctx, f.ownerP, tenantID, f.normal.UserID)
		}()
		go func() {
			defer wg.Done()
			<-start
			leaveErr = f.e.tenant.RemoveMember(ctx, f.normalP, tenantID, f.normal.UserID)
		}()
		close(start)
		wg.Wait()
		wins := 0
		for _, err := range []error{removeErr, leaveErr} {
			if err == nil {
				wins++
			} else {
				assert.ErrorIs(t, err, ErrNotFound)
			}
		}
		assert.Equal(t, 1, wins, "exactly one of the two removals succeeds (round %d)", round)
		assert.Empty(t, f.e.rowsFor(t, tenantID, f.normal.UserID), "the member is gone and not resurrected")
		assert.Equal(t, "owner", f.role(t, f.owner.UserID))
		assert.Equal(t, "admin", f.role(t, f.admin.UserID))
	}
}

func TestTwoRoleChangesOnTheSameRowEndInOneOfTheTwoRoles(t *testing.T) {
	for round := 0; round < 4; round++ {
		f := newTeamFixture(t, 100000)
		ctx := context.Background()
		var wg sync.WaitGroup
		start := make(chan struct{})
		errs := make([]error, 2)
		for i, role := range []string{"admin", "normal"} {
			wg.Add(1)
			go func(i int, role string) {
				defer wg.Done()
				<-start
				errs[i] = f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, role)
			}(i, role)
		}
		close(start)
		wg.Wait()
		assert.NoError(t, errs[0])
		assert.NoError(t, errs[1])
		got := f.role(t, f.normal.UserID)
		assert.Contains(t, []string{"admin", "normal"}, got)
		assert.Equal(t, "owner", f.role(t, f.owner.UserID))
	}
}

func TestRoleChangeRacingRemovalNeverResurrectsTheMember(t *testing.T) {
	for round := 0; round < 4; round++ {
		f := newTeamFixture(t, 100000)
		ctx := context.Background()
		var wg sync.WaitGroup
		start := make(chan struct{})
		var changeErr, removeErr error
		wg.Add(2)
		go func() {
			defer wg.Done()
			<-start
			changeErr = f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "admin")
		}()
		go func() {
			defer wg.Done()
			<-start
			removeErr = f.e.tenant.RemoveMember(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID)
		}()
		close(start)
		wg.Wait()
		assert.NoError(t, removeErr)
		if changeErr != nil {
			assert.ErrorIs(t, changeErr, ErrNotFound)
		}
		assert.Empty(t, f.e.rowsFor(t, f.owner.TenantID, f.normal.UserID), "removed means removed")
	}
}

func TestAcceptRacingWithdrawLeavesNoMemberAndNoDuplicate(t *testing.T) {
	for round := 0; round < 4; round++ {
		f := newTeamFixture(t, 100000)
		ctx := context.Background()
		var wg sync.WaitGroup
		start := make(chan struct{})
		var acceptErr, withdrawErr error
		wg.Add(2)
		go func() {
			defer wg.Done()
			<-start
			acceptErr = f.e.tenant.Respond(ctx, f.pendingP, f.owner.TenantID, InviteAccept)
		}()
		go func() {
			defer wg.Done()
			<-start
			withdrawErr = f.e.tenant.RemoveMember(ctx, f.ownerP, f.owner.TenantID, f.pending.UserID)
		}()
		close(start)
		wg.Wait()
		// Either the withdrawal ran first (accept finds no invitation: 404) or the accept ran first
		// (the owner then removes the new member). Both end with no row for the invitee.
		assert.NoError(t, withdrawErr, "the owner's removal always succeeds")
		if acceptErr != nil {
			assert.ErrorIs(t, acceptErr, ErrNotFound)
		}
		assert.Empty(t, f.e.rowsFor(t, f.owner.TenantID, f.pending.UserID), "round %d: no resurrected member", round)
		assert.Equal(t, "owner", f.role(t, f.owner.UserID))
	}
}

func TestRepeatedAcceptAndDeclineNeverDuplicateRows(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	require.NoError(t, f.e.tenant.Respond(ctx, f.pendingP, f.owner.TenantID, InviteAccept))
	for i := 0; i < 3; i++ {
		assert.ErrorIs(t, f.e.tenant.Respond(ctx, f.pendingP, f.owner.TenantID, InviteAccept), ErrNotFound)
	}
	assert.Equal(t, "normal", f.role(t, f.pending.UserID), "accepting gives normal, never owner")
}

func TestRoleChangeAndRemovalAreRateLimitedPerCaller(t *testing.T) {
	f := newTeamFixture(t, 3)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		require.NoError(t, f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "admin"))
	}
	err := f.e.tenant.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "normal")
	rl, limited := IsRateLimited(err)
	require.True(t, limited, "the fourth mutation in the window is refused: %v", err)
	assert.Positive(t, rl.RetryAfter)
	assert.Equal(t, "admin", f.role(t, f.normal.UserID), "a limited request changes nothing")
	err = f.e.tenant.RemoveMember(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID)
	_, limited = IsRateLimited(err)
	assert.True(t, limited)
	assert.NotEmpty(t, f.e.rowsFor(t, f.owner.TenantID, f.normal.UserID))
}

func TestMembershipMutationsWithoutLimiterFailClosed(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	svc := NewTenant(f.e.db)
	assert.ErrorIs(t, svc.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "admin"), ErrUnavailable)
	assert.ErrorIs(t, svc.RemoveMember(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID), ErrUnavailable)
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
}

func TestMembershipMutationsRefuseNonSessionPrincipals(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	api := f.ownerP
	api.AuthType = AuthTypeAPI
	assert.ErrorIs(t, f.e.tenant.ChangeRole(ctx, api, f.owner.TenantID, f.normal.UserID, "admin"), ErrForbidden)
	assert.ErrorIs(t, f.e.tenant.RemoveMember(ctx, api, f.owner.TenantID, f.normal.UserID), ErrForbidden)
	assert.Equal(t, "normal", f.role(t, f.normal.UserID))
}

func TestRoleChangeAndRemovalStoreFailureIsUnavailable(t *testing.T) {
	f := newTeamFixture(t, 1000)
	ctx := context.Background()
	closed := newClosedTenant(t, f.e)
	assert.ErrorIs(t, closed.ChangeRole(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID, "admin"), ErrUnavailable)
	err := closed.RemoveMember(ctx, f.ownerP, f.owner.TenantID, f.normal.UserID)
	assert.ErrorIs(t, err, ErrUnavailable)
	assert.NotContains(t, err.Error(), "SELECT")
}

// newClosedTenant is a tenant service whose database handle is already closed.
func newClosedTenant(t *testing.T, e *membersEnv) *Tenant {
	t.Helper()
	closed, err := dao.OpenDB(context.Background(), e.cfg.MySQL)
	require.NoError(t, err)
	require.NoError(t, closed.Close())
	return NewTenant(closed).WithInvites(e.tenant.limiter, e.tenant.limits)
}
