package dao

import (
	"context"
	"errors"

	"gorm.io/gorm"

	"devrag/internal/entity"
)

// FindTenant returns a tenant by id.
func (d *DB) FindTenant(ctx context.Context, id string) (*entity.Tenant, error) {
	var t entity.Tenant
	err := d.gorm.WithContext(ctx).Where("id = ?", id).Take(&t).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &t, err
}
