//go:build integration

package dao

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"

	"devrag/internal/testutil"
)

func countSettings(t *testing.T, db *DB, prefix string) int64 {
	t.Helper()
	var n int64
	require.NoError(t, db.gorm.Table("system_settings").Where("name LIKE ?", prefix+"%").Count(&n).Error)
	return n
}

func insertTwo(tx *gorm.DB, prefix string) error {
	for _, suffix := range []string{"a", "b"} {
		row := map[string]any{"name": prefix + suffix, "source": "test", "data_type": "string", "value": "v"}
		if err := tx.Table("system_settings").Create(row).Error; err != nil {
			return err
		}
	}
	return nil
}

func TestTransactionRollsBack(t *testing.T) {
	scratch := testutil.NewScratchDB(t, liveConfig(t).MySQL)
	db := openCfg(t, scratch.Config)
	boom := errors.New("boom")
	err := Transaction(context.Background(), db, func(tx *gorm.DB) error {
		if err := insertTwo(tx, "tx.rollback."); err != nil {
			return err
		}
		return boom
	})
	assert.ErrorIs(t, err, boom)
	assert.Zero(t, countSettings(t, db, "tx.rollback."))
}

func TestTransactionCommitsWithoutError(t *testing.T) {
	scratch := testutil.NewScratchDB(t, liveConfig(t).MySQL)
	db := openCfg(t, scratch.Config)
	err := Transaction(context.Background(), db, func(tx *gorm.DB) error { return insertTwo(tx, "tx.commit.") })
	require.NoError(t, err)
	assert.EqualValues(t, 2, countSettings(t, db, "tx.commit."))
}
