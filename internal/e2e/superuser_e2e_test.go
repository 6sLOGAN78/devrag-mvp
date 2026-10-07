//go:build e2e

package e2e

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/server"
	"devrag/internal/testutil"
)

// Fake values for this test only; they are handed to the seed helper through its process
// environment and never written to a file.
const (
	seedEmailPrefix = "seed-root"
	seedSecretValue = "fake-e2e-seed-0001"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate the repository root")
	}
	return filepath.Join(filepath.Dir(file), "..", "..")
}

// seedSuperuser runs the real Python seed through its module entry point
// (`uv run python -m common.bootstrap.ensure_superuser`) against the stack's MySQL, so the
// hash is written by the Python service and then verified by the Go server at login.
func seedSuperuser(t *testing.T, email string) {
	t.Helper()
	cmd := exec.Command("uv", "run", "python", "-m", "common.bootstrap.ensure_superuser")
	cmd.Dir = repoRoot(t)
	cmd.Env = append(os.Environ(), "SUPERUSER_EMAIL="+email, "SUPERUSER_PASSWORD="+seedSecretValue)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("seed helper failed (%v); output withheld: %d bytes", err, len(out))
	}
}

// deleteSeeded removes the rows of the one seeded account by exact email (never by pattern) so later
// suites start clean. It runs even when the test failed half way.
func deleteSeeded(t *testing.T, src server.MySQLConfig, email string) {
	t.Helper()
	rootPass := os.Getenv("MYSQL_ROOT_PASSWORD")
	if rootPass == "" {
		t.Error("cleanup needs MYSQL_ROOT_PASSWORD")
		return
	}
	dsn := fmt.Sprintf("root:%s@tcp(%s:%d)/%s?charset=utf8mb4&timeout=5s", rootPass, src.Host, src.Port, src.Name)
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{Logger: logger.Discard})
	if err != nil {
		t.Errorf("cleanup: connect failed (%T)", err)
		return
	}
	if sqlDB, derr := db.DB(); derr == nil {
		defer func() { _ = sqlDB.Close() }()
	}
	for _, q := range []string{
		"DELETE FROM `tenant_llm` WHERE `tenant_id` IN (SELECT `id` FROM (SELECT `id` FROM `user` WHERE `email` = ?) AS u)",
		"DELETE FROM `user_tenant` WHERE `user_id` IN (SELECT `id` FROM (SELECT `id` FROM `user` WHERE `email` = ?) AS u)",
		"DELETE FROM `tenant` WHERE `id` IN (SELECT `id` FROM (SELECT `id` FROM `user` WHERE `email` = ?) AS u)",
		"DELETE FROM `user` WHERE `email` = ?",
	} {
		if err := db.Exec(q, email).Error; err != nil {
			t.Errorf("cleanup: %v", err)
		}
	}
}

func TestSuperuserSeedLogsInThroughGoAndTokenWorksOnPython(t *testing.T) {
	waitReady(t)
	cfg := testutil.RequireDB(t)
	email := testutil.UniqueEmail(seedEmailPrefix)
	defer deleteSeeded(t, cfg.MySQL, email)

	seedSuperuser(t, email)
	seedSuperuser(t, email) // idempotent: the second run changes nothing

	resp, body := send(t, http.MethodPost, "/api/v1/auth/login", "", map[string]string{"email": email, "password": seedSecretValue})
	if resp.StatusCode != http.StatusOK || resp.Header.Get("X-API-Source") != "go" {
		t.Fatalf("login: %d source %q", resp.StatusCode, resp.Header.Get("X-API-Source"))
	}
	token, _ := data(t, body)["token"].(string)
	if token == "" {
		if tk, ok := data(t, body)["access_token"].(string); ok {
			token = tk
		}
	}
	if token == "" {
		t.Fatal("login returned no token")
	}

	resp, body = send(t, http.MethodGet, "/v1/user/info", token, nil)
	if resp.StatusCode != http.StatusOK || resp.Header.Get("X-API-Source") != "go" {
		t.Fatalf("user/info: %d source %q %s", resp.StatusCode, resp.Header.Get("X-API-Source"), body)
	}
	info := data(t, body)
	if info["is_superuser"] != true || info["email"] != email {
		t.Fatalf("user/info did not report the seeded superuser: %v", info["is_superuser"])
	}

	resp, body = send(t, http.MethodGet, "/api/v1/system/status", token, nil)
	if resp.StatusCode != http.StatusOK || data(t, body)["engine"] != "python" {
		t.Fatalf("python system/status: %d source %q %s", resp.StatusCode, resp.Header.Get("X-API-Source"), body)
	}
}
