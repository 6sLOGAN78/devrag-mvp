package dao

import (
	"context"
	"errors"
	"time"

	"gorm.io/gorm"

	"devrag/internal/entity"
)

var (
	// ErrNotFound means no row matched.
	ErrNotFound = errors.New("not found")
	// ErrEmailTaken means the unique email index rejected the insert.
	ErrEmailTaken = errors.New("email already registered")
)

// NewAccount is everything registration writes in one transaction.
type NewAccount struct {
	User       entity.User
	Tenant     entity.Tenant
	Membership entity.UserTenant
	Models     []entity.TenantLLM
}

// CreateAccount inserts the user, tenant, owner membership and any tenant_llm rows atomically.
// Any failure rolls every insert back.
func (d *DB) CreateAccount(ctx context.Context, a NewAccount) error {
	return Transaction(ctx, d, func(tx *gorm.DB) error {
		if err := tx.Create(&a.User).Error; err != nil {
			if errors.Is(err, gorm.ErrDuplicatedKey) {
				return ErrEmailTaken
			}
			return err
		}
		if err := tx.Create(&a.Tenant).Error; err != nil {
			return err
		}
		if err := tx.Create(&a.Membership).Error; err != nil {
			return err
		}
		if len(a.Models) > 0 {
			return tx.Create(&a.Models).Error
		}
		return nil
	})
}

// FindUserByEmail looks a user up by canonical email (common.CanonicalEmail, applied by the caller).
// The column collation is case and accent insensitive, so collation-equal spellings find the same row.
func (d *DB) FindUserByEmail(ctx context.Context, email string) (*entity.User, error) {
	var u entity.User
	err := d.gorm.WithContext(ctx).Where("email = ?", email).Take(&u).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &u, err
}

// FindUserByID looks a user up by id.
func (d *DB) FindUserByID(ctx context.Context, id string) (*entity.User, error) {
	var u entity.User
	err := d.gorm.WithContext(ctx).Where("id = ?", id).Take(&u).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &u, err
}

// SwapAccessToken is a compare-and-swap on user.access_token: it writes next only when the column
// still equals old (NULL-safe). It reports whether this call won the swap.
func (d *DB) SwapAccessToken(ctx context.Context, userID string, old *string, next string) (bool, error) {
	res := d.gorm.WithContext(ctx).Model(&entity.User{}).
		Where("id = ? AND access_token <=> ?", userID, old).
		UpdateColumn("access_token", next)
	return res.RowsAffected == 1, res.Error
}

// TouchLastLogin records a successful login time.
func (d *DB) TouchLastLogin(ctx context.Context, userID string, at time.Time) error {
	return d.gorm.WithContext(ctx).Model(&entity.User{}).Where("id = ?", userID).UpdateColumn("last_login_time", at).Error
}

// FindUserByAccessToken returns the user whose stored access token equals token. MySQL equality is
// collation-based (case and trailing-space insensitive), so callers must re-compare the stored value.
func (d *DB) FindUserByAccessToken(ctx context.Context, token string) (*entity.User, error) {
	var u entity.User
	err := d.gorm.WithContext(ctx).Where("access_token = ?", token).Take(&u).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrNotFound
	}
	return &u, err
}

// SetAccessToken overwrites user.access_token unconditionally (logout writes an INVALID_ value).
func (d *DB) SetAccessToken(ctx context.Context, userID, token string) error {
	return d.gorm.WithContext(ctx).Model(&entity.User{}).Where("id = ?", userID).UpdateColumn("access_token", token).Error
}

// ProfileUpdate lists the profile columns a user may change; nil leaves a column untouched.
type ProfileUpdate struct {
	Nickname, Language, ColorSchema, Avatar *string
}

// UpdateProfile writes the supplied profile columns of one user in a single statement.
func (d *DB) UpdateProfile(ctx context.Context, userID string, u ProfileUpdate) error {
	cols := map[string]any{}
	for col, v := range map[string]*string{"nickname": u.Nickname, "language": u.Language, "color_schema": u.ColorSchema, "avatar": u.Avatar} {
		if v != nil {
			cols[col] = *v
		}
	}
	if len(cols) == 0 {
		return nil
	}
	now := time.Now().UTC()
	cols["update_time"] = now.UnixMilli()
	cols["update_date"] = now
	return d.gorm.WithContext(ctx).Model(&entity.User{}).Where("id = ?", userID).UpdateColumns(cols).Error
}

// ReplacePassword stores newHash and the replacement access token in one transaction, but only
// while the stored hash still equals oldHash. It reports whether the row was changed.
func (d *DB) ReplacePassword(ctx context.Context, userID, oldHash, newHash, token string) (bool, error) {
	swapped := false
	now := time.Now().UTC()
	err := Transaction(ctx, d, func(tx *gorm.DB) error {
		res := tx.Model(&entity.User{}).Where("id = ? AND password = ?", userID, oldHash).
			UpdateColumns(map[string]any{"password": newHash, "access_token": token, "update_time": now.UnixMilli(), "update_date": now})
		swapped = res.RowsAffected == 1
		return res.Error
	})
	return swapped && err == nil, err
}

// SetPassword stores newHash and the replacement access token in one transaction without comparing
// the old hash. Only a verified password-reset grant may call it. It reports whether a row changed.
func (d *DB) SetPassword(ctx context.Context, userID, newHash, token string) (bool, error) {
	changed := false
	now := time.Now().UTC()
	err := Transaction(ctx, d, func(tx *gorm.DB) error {
		res := tx.Model(&entity.User{}).Where("id = ?", userID).
			UpdateColumns(map[string]any{"password": newHash, "access_token": token, "update_time": now.UnixMilli(), "update_date": now})
		changed = res.RowsAffected == 1
		return res.Error
	})
	return changed && err == nil, err
}
