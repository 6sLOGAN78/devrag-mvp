package testutil

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"testing"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/server"
)

var identPattern = regexp.MustCompile(`^[A-Za-z0-9_]{1,64}$`)

func quoteIdent(name string) (string, error) {
	if !identPattern.MatchString(name) {
		return "", fmt.Errorf("unsafe SQL identifier %q", name)
	}
	return "`" + name + "`", nil
}

// ScratchDB is a throwaway database holding structural copies of the source database's tables.
// It is created and dropped by the test; the source database is only read.
type ScratchDB struct {
	// Config connects to the scratch database with the administrative account.
	Config server.MySQLConfig
	admin  *gorm.DB
	quoted string
}

// NewScratchDB creates devrag_scratch_<random> with every table of src copied via CREATE TABLE ... LIKE.
// Administrative credentials come from MYSQL_ROOT_PASSWORD (and optional MYSQL_ROOT_USER, default root);
// host and port come from src. Credentials are never logged. The scratch database is dropped on cleanup.
func NewScratchDB(t *testing.T, src server.MySQLConfig) *ScratchDB {
	t.Helper()
	rootPass := os.Getenv("MYSQL_ROOT_PASSWORD")
	if rootPass == "" {
		t.Skip("MYSQL_ROOT_PASSWORD not set: scratch database tests need the administrative account")
	}
	rootUser := os.Getenv("MYSQL_ROOT_USER")
	if rootUser == "" {
		rootUser = "root"
	}
	var buf [6]byte
	if _, err := rand.Read(buf[:]); err != nil {
		t.Fatalf("random: %v", err)
	}
	name := "devrag_scratch_" + hex.EncodeToString(buf[:])
	qScratch, err := quoteIdent(name)
	if err != nil {
		t.Fatal(err)
	}
	qSrc, err := quoteIdent(src.Name)
	if err != nil {
		t.Fatal(err)
	}
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/?charset=utf8mb4&parseTime=True&loc=UTC&timeout=5s", rootUser, rootPass, src.Host, strconv.Itoa(src.Port))
	admin, err := gorm.Open(mysql.Open(dsn), &gorm.Config{Logger: logger.Discard})
	if err != nil {
		t.Fatalf("connect as administrative account failed (%T)", err)
	}
	s := &ScratchDB{admin: admin, quoted: qScratch}
	s.Config = server.MySQLConfig{Name: name, User: rootUser, Password: rootPass, Host: src.Host, Port: src.Port}
	t.Cleanup(func() {
		_ = admin.Exec("DROP DATABASE IF EXISTS " + qScratch).Error
		if sqlDB, derr := admin.DB(); derr == nil {
			_ = sqlDB.Close()
		}
	})
	if err := admin.Exec("CREATE DATABASE " + qScratch + " CHARACTER SET utf8mb4").Error; err != nil {
		t.Fatalf("create scratch database failed (%T)", err)
	}
	var tables []string
	if err := admin.Raw("SELECT table_name FROM information_schema.tables WHERE table_schema = ? AND table_type = 'BASE TABLE'", src.Name).Scan(&tables).Error; err != nil {
		t.Fatalf("list source tables failed (%T)", err)
	}
	for _, tbl := range tables {
		qt, err := quoteIdent(tbl)
		if err != nil {
			t.Fatal(err)
		}
		if err := admin.Exec("CREATE TABLE " + qScratch + "." + qt + " LIKE " + qSrc + "." + qt).Error; err != nil {
			t.Fatalf("copy table %s failed (%T)", tbl, err)
		}
	}
	return s
}

// Exec runs one statement inside the scratch database (the identifiers passed by tests are literals).
func (s *ScratchDB) Exec(sql string, args ...any) error {
	return s.admin.Exec(sql, args...).Error
}

// Qualified returns the scratch-database-qualified, quoted table name.
func (s *ScratchDB) Qualified(table string) (string, error) {
	qt, err := quoteIdent(table)
	if err != nil {
		return "", err
	}
	return s.quoted + "." + qt, nil
}
