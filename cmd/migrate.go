package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"devrag/conf"
	"devrag/internal/dao"
	"devrag/internal/server"
)

const migrateTimeout = 15 * time.Second

// runMigrate verifies that the database schema matches conf/schema.json (full column definitions, primary keys and indexes). Peewee owns the
// schema (D-10): this mode only reads, and exits non-zero on any drift.
func runMigrate() error {
	cfg, err := server.LoadConfig(confPath())
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), migrateTimeout)
	defer cancel()
	db, err := dao.OpenDB(ctx, cfg.MySQL)
	if err != nil {
		return fmt.Errorf("database: %w", err)
	}
	defer func() { _ = db.Close() }()
	return verifyAndReport(ctx, db, os.Stdout)
}

type settingReader interface {
	GetSetting(ctx context.Context, name string) (string, error)
}

func verifyAndReport(ctx context.Context, db interface {
	SchemaProvider() dao.SchemaProvider
	settingReader
}, out *os.File) error {
	def, err := dao.LoadSchemaDef(conf.SchemaJSON)
	if err != nil {
		return err
	}
	rep, err := dao.VerifySchema(ctx, db.SchemaProvider(), def)
	if err != nil {
		return err
	}
	if derr := rep.Err(); derr != nil {
		return derr
	}
	version, verr := db.GetSetting(ctx, "schema.version")
	if verr != nil && !errors.Is(verr, dao.ErrSettingNotFound) {
		return verr
	}
	if verr != nil {
		version = "unset"
	}
	_, _ = fmt.Fprintf(out, "schema OK: %d tables, schema.version=%s\n", rep.Tables, version)
	return nil
}
