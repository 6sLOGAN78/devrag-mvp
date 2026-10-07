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
