package dao

import (
	"context"
	"errors"
	"fmt"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"devrag/internal/entity"
)

// ErrTokenLimit means the tenant already holds the maximum number of API tokens.
var ErrTokenLimit = errors.New("api token limit reached")

// CreateAPIToken inserts row unless the tenant already owns maxPerTenant tokens. The tenant row is
// locked for the duration of the transaction, so concurrent creations for one tenant are serialised
// and the cap cannot be exceeded. The error text of a failed insert never carries the token value.
func (d *DB) CreateAPIToken(ctx context.Context, row entity.APIToken, maxPerTenant int) error {
	return Transaction(ctx, d, func(tx *gorm.DB) error {
		var lock entity.Tenant
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Select("id").Where("id = ?", row.TenantID).Take(&lock).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrNotFound
			}
			return fmt.Errorf("lock tenant: %T", err)
		}
		var n int64
		if err := tx.Model(&entity.APIToken{}).Where("tenant_id = ?", row.TenantID).Count(&n).Error; err != nil {
			return fmt.Errorf("count api tokens: %T", err)
		}
		if n >= int64(maxPerTenant) {
			return ErrTokenLimit
		}
		if err := tx.Create(&row).Error; err != nil {
			return fmt.Errorf("insert api token: %T", err)
		}
		return nil
	})
}

// ListAPITokens returns one page of the tenant's tokens, newest first. The tenant filter is part of
// every query, so no other tenant's row can be returned.
func (d *DB) ListAPITokens(ctx context.Context, tenantID string, limit, offset int) ([]entity.APIToken, error) {
	var rows []entity.APIToken
	err := d.gorm.WithContext(ctx).Where("tenant_id = ?", tenantID).
		Order("create_time DESC").Order("token").Limit(limit).Offset(offset).Find(&rows).Error
	return rows, err
}

// DeleteAPIToken removes the exact token of the tenant. The BINARY comparison keeps the match exact
// under MySQL's case-insensitive collation; the plain comparison keeps the index usable. It reports
// whether a row was removed.
func (d *DB) DeleteAPIToken(ctx context.Context, tenantID, token string) (bool, error) {
	res := d.gorm.WithContext(ctx).Where("tenant_id = ? AND token = ? AND BINARY token = ?", tenantID, token, token).Delete(&entity.APIToken{})
	return res.RowsAffected > 0, res.Error
}

// FindAPIToken looks one token up by its exact value (parameterised, no pattern matching).
func (d *DB) FindAPIToken(ctx context.Context, token string) (*entity.APIToken, error) {
	var row entity.APIToken
	err := d.gorm.WithContext(ctx).Where("token = ? AND BINARY token = ?", token, token).Take(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &row, err
}

// FindAPITokenByBeta looks one row up by its exact beta value (parameterised, no pattern matching).
func (d *DB) FindAPITokenByBeta(ctx context.Context, beta string) (*entity.APIToken, error) {
	var row entity.APIToken
	err := d.gorm.WithContext(ctx).Where("beta = ? AND BINARY beta = ?", beta, beta).Take(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &row, err
}
