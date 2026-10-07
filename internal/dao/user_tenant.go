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

// ListMemberships is not implemented yet.
func (d *DB) ListMemberships(context.Context, string) ([]MembershipRow, error) {
	return nil, errors.New("not implemented")
}
