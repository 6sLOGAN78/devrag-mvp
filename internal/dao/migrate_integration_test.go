//go:build integration

package dao

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/conf"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

func openCfg(t *testing.T, cfg server.MySQLConfig) *DB {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db, err := OpenDB(ctx, cfg)
	require.NoError(t, err)
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func liveConfig(t *testing.T) server.Config {
	t.Helper()
	cfg, err := server.LoadConfig(confPath())
	require.NoError(t, err)
	return cfg
}

func liveDef(t *testing.T) SchemaDef {
	t.Helper()
	def, err := LoadSchemaDef(conf.SchemaJSON)
	require.NoError(t, err)
	return def
}

func TestVerifySchemaPassesOnLiveDatabase(t *testing.T) {
	cfg := liveConfig(t)
	db := openCfg(t, cfg.MySQL)
	rep, err := VerifySchema(context.Background(), db.SchemaProvider(), liveDef(t))
	require.NoError(t, err)
	require.NoError(t, rep.Err())
	assert.Equal(t, 38, rep.Tables)
}

func TestVerifySchemaOnScratchCopyPositiveThenNegative(t *testing.T) {
	cfg := liveConfig(t)
	scratch := testutil.NewScratchDB(t, cfg.MySQL)
	db := openCfg(t, scratch.Config)
	ctx := context.Background()

	rep, err := VerifySchema(ctx, db.SchemaProvider(), liveDef(t))
	require.NoError(t, err)
	require.NoError(t, rep.Err(), "an unmodified copy must verify")

	doc, err := scratch.Qualified("document")
	require.NoError(t, err)
	require.NoError(t, scratch.Exec("ALTER TABLE "+doc+" DROP COLUMN kb_id"))

	rep, err = VerifySchema(ctx, db.SchemaProvider(), liveDef(t))
	require.NoError(t, err)
	require.Error(t, rep.Err())
	assert.Contains(t, rep.MissingCols, "document.kb_id")
	assert.ErrorContains(t, rep.Err(), "document.kb_id")
}

func TestMigrateBinaryExitsNonZeroOnDriftAndZeroOnLive(t *testing.T) {
	cfg := liveConfig(t)
	scratch := testutil.NewScratchDB(t, cfg.MySQL)
	bin := filepath.Join(t.TempDir(), "ragflow_server")
	build := exec.Command("go", "build", "-o", bin, "./cmd")
	build.Dir = "../.."
	out, err := build.CombinedOutput()
	require.NoError(t, err, string(out))

	// Config for the scratch database: same file, other mysql.name, administrative account via env.
	conf := filepath.Join(t.TempDir(), "scratch.yaml")
	require.NoError(t, os.WriteFile(conf, []byte(scratchYAML(cfg, scratch.Config)), 0o600))

	run := func(confFile string) (string, error) {
		c := exec.Command(bin, "--migrate")
		c.Env = append(os.Environ(), "SERVICE_CONF="+confFile)
		b, err := c.CombinedOutput()
		return string(b), err
	}
	// live database
	live, err := run(confPath())
	require.NoError(t, err, live)
	assert.Contains(t, live, "schema OK: 38 tables")

	// drifted scratch copy
	doc, err := scratch.Qualified("document")
	require.NoError(t, err)
	require.NoError(t, scratch.Exec("ALTER TABLE "+doc+" DROP COLUMN kb_id"))
	drift, err := run(conf)
	var ee *exec.ExitError
	require.ErrorAs(t, err, &ee, drift)
	assert.Equal(t, 1, ee.ExitCode())
	assert.Contains(t, drift, "document.kb_id")
}

// scratchYAML renders a minimal service config that points the binary at the scratch database.
func scratchYAML(live server.Config, s server.MySQLConfig) string {
	return fmt.Sprintf("mysql:\n  name: %q\n  user: %q\n  password: %q\n  host: %q\n  port: %d\nredis:\n  host: %q\n  port: %d\n  password: %q\nsecurity:\n  secret_key: %q\n",
		s.Name, s.User, s.Password, s.Host, s.Port, live.Redis.Host, live.Redis.Port, live.Redis.Password, live.Security.SecretKey)
}

// TestVerifySchemaDetectsDefinitionDriftOnScratchCopy is the WR-10 live check: each ALTER keeps the
// column in the same type family, which the old verifier accepted. Only the scratch database is altered.
func TestVerifySchemaDetectsDefinitionDriftOnScratchCopy(t *testing.T) {
	cfg := liveConfig(t)
	scratch := testutil.NewScratchDB(t, cfg.MySQL)
	db := openCfg(t, scratch.Config)
	ctx := context.Background()
	def := liveDef(t)

	user, err := scratch.Qualified("user")
	require.NoError(t, err)
	// Narrower password column (T-02-24): same family, different length.
	require.NoError(t, scratch.Exec("ALTER TABLE "+user+" MODIFY COLUMN password VARCHAR(64) NULL"))
	// Nullability flip on a NOT NULL column.
	require.NoError(t, scratch.Exec("ALTER TABLE "+user+" MODIFY COLUMN status VARCHAR(1) NOT NULL"))
	// Dropped unique index on email.
	require.NoError(t, scratch.Exec("ALTER TABLE "+user+" DROP INDEX user_email"))

	rep, err := VerifySchema(ctx, db.SchemaProvider(), def)
	require.NoError(t, err)
	require.Error(t, rep.Err())
	assert.Contains(t, rep.Err().Error(), "user.password")
	assert.Contains(t, rep.Err().Error(), "user.status")
	assert.Contains(t, rep.Err().Error(), "user missing index (email)")
}
