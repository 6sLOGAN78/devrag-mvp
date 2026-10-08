package service

import (
	"context"
	"errors"

	"devrag/internal/common"
	"devrag/internal/dao"
)

const (
	roleAdminName  = "admin"
	roleNormalName = "normal"
)

var (
	// ErrOwnerImmutable means the request targets the owner row: it cannot change role, be removed or
	// leave (D-16, D-27). It is also what an owner gets for trying to demote or remove themselves.
	ErrOwnerImmutable = errors.New("the workspace owner cannot be demoted, removed or leave")
	// ErrInvitePending means the target has not accepted the invitation yet, so there is no role to change.
	ErrInvitePending = errors.New("that person has not accepted the invitation yet")
)

// canManageMembers is the generated permission table's answer for a role (never an ad-hoc role check).
func canManageMembers(role string) bool {
	return common.Allowed(role, teamArea, teamManageAction)
}

// hitMemberLimits counts one membership mutation per caller and per tenant (the login-class numbers).
// The limiter fails closed.
func (t *Tenant) hitMemberLimits(ctx context.Context, userID, tenantID string) error {
	if t.limiter == nil || t.limits.PerWindow <= 0 {
		return ErrUnavailable
	}
	if err := t.limiter.Hit(ctx, "member-user:"+userID, t.limits.PerWindow, t.limits.Window); err != nil {
		return err
	}
	return t.limiter.Hit(ctx, "member-tenant:"+tenantID, t.limits.PerWindow, t.limits.Window)
}

// mapMembershipError turns the DAO's transactional outcomes into service errors.
func mapMembershipError(what string, err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, dao.ErrNotFound):
		return ErrNotFound
	case errors.Is(err, dao.ErrNotPermitted):
		return ErrForbidden
	case errors.Is(err, dao.ErrOwnerRow):
		return ErrOwnerImmutable
	case errors.Is(err, dao.ErrPendingRow):
		return ErrInvitePending
	}
	return memberStoreFailure(what, err)
}

// ChangeRole sets a member of tenantID to admin or normal. Only the owner may (D-27, TEN-11): a
// non-member gets ErrNotFound, a member without the right ErrForbidden. The owner row and a pending
// invitation cannot be targeted, the role "owner" (or "invite", or anything unknown) can never be set,
// and the owner cannot demote themselves. The decision is repeated inside the transaction that writes.
func (t *Tenant) ChangeRole(ctx context.Context, p Principal, tenantID, targetUserID, role string) error {
	callerRole, err := t.memberRole(ctx, p, tenantID)
	if err != nil {
		return err
	}
	if !canManageMembers(callerRole) {
		return ErrForbidden
	}
	if role != roleAdminName && role != roleNormalName {
		return &ValidationError{Msg: "role must be admin or normal"}
	}
	if targetUserID == "" || len(targetUserID) > maxTenantIDLength {
		return ErrNotFound
	}
	if err := t.hitMemberLimits(ctx, p.UserID, tenantID); err != nil {
		return err
	}
	now := t.now().UTC()
	return mapMembershipError("change role", t.store.ChangeMemberRole(ctx, tenantID, p.UserID, targetUserID, role, now, canManageMembers))
}

// RemoveMember deletes targetUserID's membership row. A caller naming themselves leaves (any member
// except the owner, D-16); naming anyone else needs the owner right and may remove a member or withdraw
// a pending invitation. The owner row is never removable. A non-owner naming someone else is
// ErrForbidden, never a silent self-removal. A non-member gets ErrNotFound.
func (t *Tenant) RemoveMember(ctx context.Context, p Principal, tenantID, targetUserID string) error {
	callerRole, err := t.memberRole(ctx, p, tenantID)
	if err != nil {
		return err
	}
	if targetUserID == "" {
		return &ValidationError{Msg: "user_id is required"}
	}
	if targetUserID != p.UserID && !canManageMembers(callerRole) {
		return ErrForbidden
	}
	if len(targetUserID) > maxTenantIDLength {
		return ErrNotFound
	}
	if err := t.hitMemberLimits(ctx, p.UserID, tenantID); err != nil {
		return err
	}
	return mapMembershipError("remove member", t.store.RemoveMember(ctx, tenantID, p.UserID, targetUserID, canManageMembers))
}
