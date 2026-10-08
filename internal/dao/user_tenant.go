package dao

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"devrag/internal/entity"
)

// FindOwnMembership returns the user's own-workspace membership (role owner).
func (d *DB) FindOwnMembership(ctx context.Context, userID string) (*entity.UserTenant, error) {
	var m entity.UserTenant
	err := d.gorm.WithContext(ctx).Where("user_id = ? AND role = ? AND status = ?", userID, "owner", "1").Take(&m).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &m, err
}

// MembershipRow is one membership of a user joined with its tenant and the tenant owner.
type MembershipRow struct {
	TenantID      string
	TenantName    *string
	OwnerNickname *string
	OwnerAvatar   *string
	Role          string
	CreateTime    *int64
}

// ListMemberships returns every active membership row of userID (any role, including the pending
// invitation role) with its tenant name and the tenant owner's public profile. The tenant must be
// active and the filter is on user_tenant.user_id, so only the caller's own rows are returned.
func (d *DB) ListMemberships(ctx context.Context, userID string) ([]MembershipRow, error) {
	const q = "SELECT ut.tenant_id AS tenant_id, t.name AS tenant_name, u.nickname AS owner_nickname, u.avatar AS owner_avatar, " +
		"ut.role AS role, ut.create_time AS create_time " +
		"FROM user_tenant ut " +
		"JOIN tenant t ON t.id = ut.tenant_id AND t.status = '1' " +
		"LEFT JOIN user_tenant o ON o.tenant_id = ut.tenant_id AND o.role = 'owner' AND o.status = '1' " +
		"LEFT JOIN user u ON u.id = o.user_id " +
		"WHERE ut.user_id = ? AND ut.status = '1' " +
		"ORDER BY ut.create_time, ut.id"
	var rows []MembershipRow
	if err := d.gorm.WithContext(ctx).Raw(q, userID).Scan(&rows).Error; err != nil {
		return nil, err
	}
	return rows, nil
}

var (
	// ErrAlreadyMember means the target already holds an active owner, admin or normal row in the tenant.
	ErrAlreadyMember = errors.New("already a member")
	// ErrAlreadyInvited means the target already has a pending invitation in the tenant.
	ErrAlreadyInvited = errors.New("already invited")
	// ErrNotPermitted means the caller's role, read inside the transaction, may not do this.
	ErrNotPermitted = errors.New("not permitted")
	// ErrOwnerRow means the target is (or is the caller as) the owner row, which never changes or leaves.
	ErrOwnerRow = errors.New("owner row")
	// ErrPendingRow means the target holds only a pending invitation, which has no role to change.
	ErrPendingRow = errors.New("pending invitation")
)

const (
	rolePending = "invite"
	roleNormal  = "normal"
)

// memberRoles are the roles that count as membership. The pending-invitation role is not among them
// (D-26): every membership lookup below filters on this list.
const memberRolesSQL = "('owner','admin','normal')"

// FindMemberRole returns the role of userID in tenantID when the user holds an active owner, admin or
// normal row in an active tenant. Anything else (no row, a pending invitation, an inactive row, an
// inactive tenant) is ErrNotFound, so callers cannot tell those cases apart.
func (d *DB) FindMemberRole(ctx context.Context, tenantID, userID string) (string, error) {
	const q = "SELECT ut.role FROM user_tenant ut JOIN tenant t ON t.id = ut.tenant_id AND t.status = '1' " +
		"WHERE ut.tenant_id = ? AND ut.user_id = ? AND ut.status = '1' AND ut.role IN " + memberRolesSQL + " " +
		"ORDER BY FIELD(ut.role, 'owner', 'admin', 'normal') LIMIT 1"
	var roles []string
	if err := d.gorm.WithContext(ctx).Raw(q, tenantID, userID).Scan(&roles).Error; err != nil {
		return "", err
	}
	if len(roles) == 0 {
		return "", ErrNotFound
	}
	return roles[0], nil
}

// MemberRow is one row of a tenant's member list: public profile fields only.
type MemberRow struct {
	UserID     string
	Nickname   string
	Email      string
	Avatar     *string
	Role       string
	CreateTime *int64
}

// ListTenantMembers returns one page of the tenant's active members, the owner first, then by join
// time. includePending adds pending invitations (role invite). Only the listed profile columns are
// selected, so no password hash, access token or internal column can reach a caller.
func (d *DB) ListTenantMembers(ctx context.Context, tenantID string, includePending bool, limit, offset int) ([]MemberRow, error) {
	roles := memberRolesSQL
	if includePending {
		roles = "('owner','admin','normal','invite')"
	}
	q := "SELECT ut.user_id AS user_id, u.nickname AS nickname, u.email AS email, u.avatar AS avatar, ut.role AS role, ut.create_time AS create_time " +
		"FROM user_tenant ut JOIN user u ON u.id = ut.user_id AND u.status = '1' " +
		"WHERE ut.tenant_id = ? AND ut.status = '1' AND ut.role IN " + roles + " " +
		"ORDER BY (ut.role = 'owner') DESC, ut.create_time, ut.id LIMIT ? OFFSET ?"
	var rows []MemberRow
	if err := d.gorm.WithContext(ctx).Raw(q, tenantID, limit, offset).Scan(&rows).Error; err != nil {
		return nil, err
	}
	return rows, nil
}

// FindActiveUserByEmail returns the active account with the given lowercase email, or ErrNotFound.
func (d *DB) FindActiveUserByEmail(ctx context.Context, email string) (*entity.User, error) {
	var u entity.User
	err := d.gorm.WithContext(ctx).Where("email = ? AND status = '1'", email).Take(&u).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &u, err
}

// CreateInvite inserts row (role invite) unless the target already has an active row in the tenant.
// No unique key exists on (tenant_id, user_id), so the tenant row is locked for the duration of the
// transaction and the caller's ownership and the target's state are re-read under that lock: two
// parallel invitations cannot both insert. It returns ErrNotFound when the tenant or the inviter's
// ownership has gone, ErrAlreadyMember or ErrAlreadyInvited otherwise.
func (d *DB) CreateInvite(ctx context.Context, inviterID string, row entity.UserTenant) error {
	return Transaction(ctx, d, func(tx *gorm.DB) error {
		var lock entity.Tenant
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Select("id").Where("id = ? AND status = '1'", row.TenantID).Take(&lock).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrNotFound
			}
			return fmt.Errorf("lock tenant: %T", err)
		}
		var owners int64
		if err := tx.Model(&entity.UserTenant{}).Where("tenant_id = ? AND user_id = ? AND role = 'owner' AND status = '1'", row.TenantID, inviterID).Count(&owners).Error; err != nil {
			return fmt.Errorf("check inviter: %T", err)
		}
		if owners == 0 {
			return ErrNotFound
		}
		var existing []string
		if err := tx.Model(&entity.UserTenant{}).Where("tenant_id = ? AND user_id = ? AND status = '1'", row.TenantID, row.UserID).Pluck("role", &existing).Error; err != nil {
			return fmt.Errorf("read target rows: %T", err)
		}
		for _, role := range existing {
			if role != rolePending {
				return ErrAlreadyMember
			}
		}
		if len(existing) > 0 {
			return ErrAlreadyInvited
		}
		if err := tx.Create(&row).Error; err != nil {
			return fmt.Errorf("insert invite: %T", err)
		}
		return nil
	})
}

// AcceptInvite turns the caller's pending invitation into a normal membership. The statement matches
// only a row with role invite, so an owner or admin row can never be changed (D-27); it reports
// whether a row changed. The tenant must be active.
func (d *DB) AcceptInvite(ctx context.Context, tenantID, userID string, now time.Time) (bool, error) {
	const q = "UPDATE user_tenant SET role = ?, update_time = ?, update_date = ? " +
		"WHERE tenant_id = ? AND user_id = ? AND role = ? AND status = '1' " +
		"AND EXISTS (SELECT 1 FROM (SELECT id FROM tenant WHERE id = ? AND status = '1') AS t) LIMIT 1"
	res := d.gorm.WithContext(ctx).Exec(q, roleNormal, now.UnixMilli(), now, tenantID, userID, rolePending, tenantID)
	return res.RowsAffected > 0, res.Error
}

// DeclineInvite deletes the caller's pending invitation and nothing else; it reports whether a row
// was removed.
func (d *DB) DeclineInvite(ctx context.Context, tenantID, userID string) (bool, error) {
	res := d.gorm.WithContext(ctx).Exec("DELETE FROM user_tenant WHERE tenant_id = ? AND user_id = ? AND role = ? AND status = '1' LIMIT 1", tenantID, userID, rolePending)
	return res.RowsAffected > 0, res.Error
}

const (
	roleAdmin = "admin"
	roleOwner = "owner"
)

// lockedTenantCaller locks the active tenant row for the rest of the transaction and returns the
// caller's membership role read under that lock. Every membership mutation starts here, so decisions
// are made on rows no concurrent mutation can change: ErrNotFound when the tenant or the caller's
// membership is gone.
func lockedTenantCaller(tx *gorm.DB, tenantID, callerID string) (string, error) {
	var lock entity.Tenant
	if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Select("id").Where("id = ? AND status = '1'", tenantID).Take(&lock).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return "", ErrNotFound
		}
		return "", fmt.Errorf("lock tenant: %T", err)
	}
	var roles []string
	if err := tx.Model(&entity.UserTenant{}).Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("tenant_id = ? AND user_id = ? AND status = '1' AND role IN ?", tenantID, callerID, []string{roleOwner, roleAdmin, roleNormal}).
		Pluck("role", &roles).Error; err != nil {
		return "", fmt.Errorf("read caller rows: %T", err)
	}
	best := ""
	for _, r := range roles {
		if r == roleOwner || (r == roleAdmin && best != roleOwner) || (r == roleNormal && best == "") {
			best = r
		}
	}
	if best == "" {
		return "", ErrNotFound
	}
	return best, nil
}

// lockedTargetRoles reads (and row-locks) the active roles of targetID in tenantID.
func lockedTargetRoles(tx *gorm.DB, tenantID, targetID string) ([]string, error) {
	var roles []string
	err := tx.Model(&entity.UserTenant{}).Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("tenant_id = ? AND user_id = ? AND status = '1'", tenantID, targetID).Pluck("role", &roles).Error
	if err != nil {
		return nil, fmt.Errorf("read target rows: %T", err)
	}
	return roles, nil
}

func hasRole(roles []string, want ...string) bool {
	for _, r := range roles {
		for _, w := range want {
			if r == w {
				return true
			}
		}
	}
	return false
}

// ChangeMemberRole sets an admin or normal member of tenantID to role (admin or normal). The caller's
// role and the target's rows are read inside one transaction under the tenant row lock; canManage
// decides from the caller's role (the generated permission table). The owner row and a pending
// invitation are refused (ErrOwnerRow, ErrPendingRow), an absent target is ErrNotFound, and the UPDATE
// itself only matches admin or normal rows, so the owner role can never be written or overwritten.
func (d *DB) ChangeMemberRole(ctx context.Context, tenantID, callerID, targetID, role string, now time.Time, canManage func(role string) bool) error {
	return Transaction(ctx, d, func(tx *gorm.DB) error {
		callerRole, err := lockedTenantCaller(tx, tenantID, callerID)
		if err != nil {
			return err
		}
		if !canManage(callerRole) {
			return ErrNotPermitted
		}
		roles, err := lockedTargetRoles(tx, tenantID, targetID)
		if err != nil {
			return err
		}
		switch {
		case hasRole(roles, roleOwner):
			return ErrOwnerRow
		case hasRole(roles, roleAdmin, roleNormal):
		case hasRole(roles, rolePending):
			return ErrPendingRow
		default:
			return ErrNotFound
		}
		err = tx.Exec("UPDATE user_tenant SET role = ?, update_time = ?, update_date = ? "+
			"WHERE tenant_id = ? AND user_id = ? AND status = '1' AND role IN ('admin','normal')",
			role, now.UnixMilli(), now, tenantID, targetID).Error
		if err != nil {
			return fmt.Errorf("update role: %T", err)
		}
		return nil
	})
}

// RemoveMember deletes one membership row of tenantID. targetID equal to callerID is leaving: allowed
// for admin and normal rows, ErrOwnerRow for the owner. Any other target needs canManage (owner) and
// may be an admin, a normal member or a pending invitation; the owner row is ErrOwnerRow. The DELETE
// matches only admin, normal and invite rows, so a racing request can never delete the owner row.
// All decisions use rows read under the tenant row lock in this transaction; a target already gone
// (including one removed by a racing request) is ErrNotFound.
func (d *DB) RemoveMember(ctx context.Context, tenantID, callerID, targetID string, canManage func(role string) bool) error {
	return Transaction(ctx, d, func(tx *gorm.DB) error {
		callerRole, err := lockedTenantCaller(tx, tenantID, callerID)
		if err != nil {
			return err
		}
		if targetID == callerID {
			if callerRole == roleOwner {
				return ErrOwnerRow
			}
		} else if !canManage(callerRole) {
			return ErrNotPermitted
		}
		roles, err := lockedTargetRoles(tx, tenantID, targetID)
		if err != nil {
			return err
		}
		if hasRole(roles, roleOwner) {
			return ErrOwnerRow
		}
		if !hasRole(roles, roleAdmin, roleNormal, rolePending) {
			return ErrNotFound
		}
		res := tx.Exec("DELETE FROM user_tenant WHERE tenant_id = ? AND user_id = ? AND status = '1' AND role IN ('admin','normal','invite')", tenantID, targetID)
		if res.Error != nil {
			return fmt.Errorf("delete member: %T", res.Error)
		}
		if res.RowsAffected == 0 {
			return ErrNotFound
		}
		return nil
	})
}
