package dao

import (
	"context"

	"gorm.io/gorm"
)

// Transaction runs fn inside a database transaction. A non-nil error from fn (or a panic) rolls
// every write made through tx back, and that error is returned to the caller; otherwise it commits.
func Transaction(ctx context.Context, db *DB, fn func(tx *gorm.DB) error) error {
	return db.gorm.WithContext(ctx).Transaction(fn)
}
