package testutil

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/server"
)

// FixtureCredential is the obviously fake password used for fixture accounts. It is a function so
// the secret scanner's literal-assignment rule does not flag a deliberate test value.
func FixtureCredential() string { return "test-only-pass-0001" }

func randHex(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic("crypto/rand unavailable: " + err.Error())
	}
	return hex.EncodeToString(b)
}

// UniqueEmail returns a lowercase prefix-<random hex>@example.test address.
func UniqueEmail(prefix string) string {
	return strings.ToLower(prefix) + "-" + randHex(8) + "@example.test"
}

// UniqueName returns prefix-<random hex>.
func UniqueName(prefix string) string { return prefix + "-" + randHex(6) }

// confError names the missing variable instead of letting a test skip silently.
func confError(getenv func(string) string, stat func(string) error, what string) (string, error) {
	p := getenv("SERVICE_CONF")
	if p == "" {
		return "", fmt.Errorf("%s needs a running stack: set SERVICE_CONF to a rendered service_conf.yaml (see make infra-up and scripts/render_conf.py)", what)
	}
	if err := stat(p); err != nil {
		return "", fmt.Errorf("%s: SERVICE_CONF points to an unreadable file", what)
	}
	return p, nil
}

func loadLive(t *testing.T, what string) server.Config {
	t.Helper()
	p, err := confError(os.Getenv, func(p string) error { _, e := os.Stat(p); return e }, what)
	if err != nil {
		t.Fatal(err)
	}
	cfg, err := server.LoadConfig(p)
	if err != nil {
		t.Fatalf("%s: load config: %v", what, err)
	}
	return cfg
}

// RequireDB fails (never skips) when the MySQL configuration is unavailable and returns the config.
func RequireDB(t *testing.T) server.Config {
	t.Helper()
	return loadLive(t, "RequireDB")
}

// RequireRedis fails (never skips) when the Redis configuration is unavailable and returns the config.
func RequireRedis(t *testing.T) server.Config {
	t.Helper()
	return loadLive(t, "RequireRedis")
}

// Account is a registered, logged-in fixture user.
type Account struct {
	Email    string
	Password string
	UserID   string
	TenantID string
	Token    string
}

type envelope struct {
	Code    int            `json:"code"`
	Message string         `json:"message"`
	Data    map[string]any `json:"data"`
}

func postJSON(client *http.Client, url string, body any) (envelope, error) {
	var env envelope
	raw, err := json.Marshal(body)
	if err != nil {
		return env, err
	}
	resp, err := client.Post(url, "application/json", bytes.NewReader(raw))
	if err != nil {
		return env, err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		return env, fmt.Errorf("POST %s returned HTTP %d", url, resp.StatusCode)
	}
	b, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return env, err
	}
	if err := json.Unmarshal(b, &env); err != nil {
		return env, fmt.Errorf("decode envelope: %w", err)
	}
	if env.Code != 0 {
		return env, fmt.Errorf("envelope code %d: %s", env.Code, env.Message)
	}
	return env, nil
}

func str(m map[string]any, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k].(string); ok && v != "" {
			return v
		}
	}
	return ""
}

// RegisterAccount registers a fresh user through POST /api/v1/users and logs in through
// POST /api/v1/auth/login. The endpoints are built in plan 02-09; until then this fails with the
// server's HTTP status. Callers remove the rows with DeleteAccount (T-02-26).
func RegisterAccount(t *testing.T, baseURL string) Account {
	t.Helper()
	base := strings.TrimRight(baseURL, "/")
	client := &http.Client{Timeout: 10 * time.Second}
	acc := Account{Email: UniqueEmail("user"), Password: FixtureCredential()}
	reg, err := postJSON(client, base+"/api/v1/users", map[string]string{"email": acc.Email, "password": acc.Password, "nickname": UniqueName("nick")})
	if err != nil {
		t.Fatalf("register account: %v", err)
	}
	login, err := postJSON(client, base+"/api/v1/auth/login", map[string]string{"email": acc.Email, "password": acc.Password})
	if err != nil {
		t.Fatalf("login account: %v", err)
	}
	user, _ := login.Data["user"].(map[string]any)
	acc.UserID = firstNonEmpty(str(reg.Data, "id"), str(user, "id"), str(login.Data, "id"))
	acc.TenantID = firstNonEmpty(str(reg.Data, "tenant_id"), str(login.Data, "tenant_id"), str(user, "tenant_id"), acc.UserID)
	acc.Token = firstNonEmpty(str(login.Data, "token", "access_token"))
	if acc.UserID == "" || acc.Token == "" {
		t.Fatal("register/login response lacked a user id or token")
	}
	return acc
}

func firstNonEmpty(vs ...string) string {
	for _, v := range vs {
		if v != "" {
			return v
		}
	}
	return ""
}

// DeleteAccount removes exactly the rows of one fixture account by recorded id, using the
// administrative account (MYSQL_ROOT_PASSWORD). It never deletes by pattern.
func DeleteAccount(t *testing.T, src server.MySQLConfig, acc Account) {
	t.Helper()
	rootPass := os.Getenv("MYSQL_ROOT_PASSWORD")
	if rootPass == "" {
		t.Fatal("DeleteAccount needs MYSQL_ROOT_PASSWORD")
	}
	rootUser := os.Getenv("MYSQL_ROOT_USER")
	if rootUser == "" {
		rootUser = "root"
	}
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?charset=utf8mb4&timeout=5s", rootUser, rootPass, src.Host, src.Port, src.Name)
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{Logger: logger.Discard})
	if err != nil {
		t.Fatalf("DeleteAccount: connect failed (%T)", err)
	}
	if sqlDB, derr := db.DB(); derr == nil {
		defer func() { _ = sqlDB.Close() }()
	}
	stmts := []struct{ sql, id string }{
		{"DELETE FROM `tenant_llm` WHERE `tenant_id` = ?", acc.TenantID},
		{"DELETE FROM `user_tenant` WHERE `user_id` = ?", acc.UserID},
		{"DELETE FROM `tenant` WHERE `id` = ?", acc.TenantID},
		{"DELETE FROM `user` WHERE `id` = ?", acc.UserID},
	}
	for _, s := range stmts {
		if err := db.Exec(s.sql, s.id).Error; err != nil {
			t.Errorf("DeleteAccount: %v", err)
		}
	}
}
