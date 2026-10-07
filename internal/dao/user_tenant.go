package dao

import (
	"context"
	"errors"

	"gorm.io/gorm"

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
