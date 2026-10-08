package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

const (
	// MaxMemberPageSize bounds one page of the member list.
	MaxMemberPageSize = 100
	// InviteAccept and InviteDecline are the two answers to a pending invitation (D-15).
	InviteAccept  = "accept"
	InviteDecline = "decline"

	teamArea         = "team_admin"
	teamManageAction = "manage_members"
	pendingRole      = "invite"
	// maxTenantIDLength is the length of a tenant id; a longer value cannot name a tenant.
	maxTenantIDLength = 32
)

var (
	// ErrNotFound is the one answer for every tenant the caller cannot see: a nonexistent id, a tenant
	// the caller does not belong to, and a tenant where the caller only holds a pending invitation. The
	// text never varies, so the cases are indistinguishable (R-93, T-02-102).
	ErrNotFound = errors.New("not found")
	// ErrInviteSelf means the owner tried to invite themselves.
	ErrInviteSelf = errors.New("you cannot invite yourself")
	// ErrAlreadyMember means the target already belongs to this workspace.
	ErrAlreadyMember = errors.New("this person is already a member")
	// ErrAlreadyInvited means the target already has a pending invitation to this workspace.
	ErrAlreadyInvited = errors.New("this person has already been invited")
	// ErrUserNotFound means no active account has that email (D-14: existing accounts only; R-107).
	ErrUserNotFound = errors.New("no active account with that email")
)

// InviteLimits bounds invitation attempts per caller and per tenant within a window (R-107, T-02-105).
type InviteLimits struct {
	PerWindow int
	Window    time.Duration
}

// InviteLimitsFrom uses the login-class numbers of the RateLimit configuration (plan 02-04).
func InviteLimitsFrom(rl server.RateLimit) InviteLimits {
	return InviteLimits{PerWindow: rl.LoginPerIP, Window: window(rl.LoginWindowSeconds)}
}

// WithInvites enables invitations: attempts are counted in limiter, keyed by the caller's user id and by
// the tenant id. The limiter fails closed, so a Redis outage refuses the invitation.
func (t *Tenant) WithInvites(limiter *Limiter, limits InviteLimits) *Tenant {
	t.limiter, t.limits = limiter, limits
	return t
}

// Member is one entry of a tenant's member list. Role "invite" marks a pending invitation (shown to the
// owner only).
type Member struct {
	UserID, Nickname, Email, Avatar, Role string
	JoinedAt                              time.Time
}

func toMember(r dao.MemberRow) Member {
	m := Member{UserID: r.UserID, Nickname: r.Nickname, Email: r.Email, Avatar: deref(r.Avatar), Role: r.Role}
	if r.CreateTime != nil {
		m.JoinedAt = time.UnixMilli(*r.CreateTime).UTC()
	}
	return m
}

// memberRole returns the caller's membership role in tenantID, or ErrNotFound. The role is read from
// the database in this request; the tenant id is only a lookup key. A pending invitation is not
// membership (D-26).
func (t *Tenant) memberRole(ctx context.Context, p Principal, tenantID string) (string, error) {
	if p.AuthType != AuthTypeJWT || p.UserID == "" {
		return "", ErrForbidden
	}
	if tenantID == "" || len(tenantID) > maxTenantIDLength {
		return "", ErrNotFound
	}
	role, err := t.store.FindMemberRole(ctx, tenantID, p.UserID)
	if errors.Is(err, dao.ErrNotFound) {
		return "", ErrNotFound
	}
	if err != nil {
		return "", memberStoreFailure("read membership", err)
	}
	return role, nil
}

// memberStoreFailure turns an unexpected persistence error into ErrUnavailable (HTTP 503). Only the error type
// is kept, never its text, which could carry SQL or values.
func memberStoreFailure(what string, err error) error {
	return fmt.Errorf("%w: %s: %T", ErrUnavailable, what, err)
}

// ListMembers returns one page (page is 1-based) of the tenant's members to any active member. Only the
// owner also sees pending invitations. A non-member gets ErrNotFound.
func (t *Tenant) ListMembers(ctx context.Context, p Principal, tenantID string, page, pageSize int) ([]Member, error) {
	if page < 1 || pageSize < 1 || pageSize > MaxMemberPageSize {
		return nil, &ValidationError{Msg: "invalid page or page_size"}
	}
	role, err := t.memberRole(ctx, p, tenantID)
	if err != nil {
		return nil, err
	}
	rows, err := t.store.ListTenantMembers(ctx, tenantID, role == "owner", pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, memberStoreFailure("list members", err)
	}
	out := make([]Member, 0, len(rows))
	for _, r := range rows {
		out = append(out, toMember(r))
	}
	return out, nil
}

func (t *Tenant) hitInviteLimits(ctx context.Context, userID, tenantID string) error {
	if t.limiter == nil || t.limits.PerWindow <= 0 {
		return ErrUnavailable
	}
	if err := t.limiter.Hit(ctx, "invite-user:"+userID, t.limits.PerWindow, t.limits.Window); err != nil {
		return err
	}
	return t.limiter.Hit(ctx, "invite-tenant:"+tenantID, t.limits.PerWindow, t.limits.Window)
}

// Invite adds a pending invitation (role invite) for an existing active account, by email. Only the
// owner may invite (D-13): a non-member gets ErrNotFound, a member without the right ErrForbidden. The
// stored role is always "invite" and the inviter the caller; nothing else comes from the request.
func (t *Tenant) Invite(ctx context.Context, p Principal, tenantID, email string) (Member, error) {
	role, err := t.memberRole(ctx, p, tenantID)
	if err != nil {
		return Member{}, err
	}
	if !common.Allowed(role, teamArea, teamManageAction) {
		return Member{}, ErrForbidden
	}
	if err := t.hitInviteLimits(ctx, p.UserID, tenantID); err != nil {
		return Member{}, err
	}
	email = common.CanonicalEmail(email)
	if !validEmail(email) {
		return Member{}, &ValidationError{Msg: "a valid email address is required"}
	}
	target, err := t.store.FindActiveUserByEmail(ctx, email)
	if errors.Is(err, dao.ErrNotFound) {
		return Member{}, ErrUserNotFound
	}
	if err != nil {
		return Member{}, memberStoreFailure("find invitee", err)
	}
	if target.ID == p.UserID {
		return Member{}, ErrInviteSelf
	}
	now := t.now().UTC()
	ms := now.UnixMilli()
	active := "1"
	row := entity.UserTenant{
		ID: t.newID(), UserID: target.ID, TenantID: tenantID, InvitedBy: p.UserID, Role: pendingRole, Status: &active,
		CreateTime: &ms, CreateDate: &now, UpdateTime: &ms, UpdateDate: &now,
	}
	if err := t.store.CreateInvite(ctx, p.UserID, row); err != nil {
		switch {
		case errors.Is(err, dao.ErrNotFound):
			return Member{}, ErrNotFound
		case errors.Is(err, dao.ErrAlreadyMember):
			return Member{}, ErrAlreadyMember
		case errors.Is(err, dao.ErrAlreadyInvited):
			return Member{}, ErrAlreadyInvited
		}
		return Member{}, memberStoreFailure("create invitation", err)
	}
	return Member{UserID: target.ID, Nickname: target.Nickname, Email: target.Email, Avatar: deref(target.Avatar), Role: pendingRole, JoinedAt: now}, nil
}

// Respond accepts (role invite becomes normal) or declines (the row is deleted) the caller's own pending
// invitation. Only a row with role invite can change: every other state, including the caller owning or
// administering the tenant, is ErrNotFound and changes nothing (D-27).
func (t *Tenant) Respond(ctx context.Context, p Principal, tenantID, action string) error {
	if action != InviteAccept && action != InviteDecline {
		return &ValidationError{Msg: "action must be accept or decline"}
	}
	if p.AuthType != AuthTypeJWT || p.UserID == "" {
		return ErrForbidden
	}
	if tenantID == "" || len(tenantID) > maxTenantIDLength {
		return ErrNotFound
	}
	var changed bool
	var err error
	if action == InviteAccept {
		changed, err = t.store.AcceptInvite(ctx, tenantID, p.UserID, t.now().UTC())
	} else {
		changed, err = t.store.DeclineInvite(ctx, tenantID, p.UserID)
	}
	if err != nil {
		return memberStoreFailure("answer invitation", err)
	}
	if !changed {
		return ErrNotFound
	}
	return nil
}
