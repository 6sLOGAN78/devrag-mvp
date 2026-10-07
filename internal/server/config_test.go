package server

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const baseConf = `
go_api:
  host: 127.0.0.1
  http_port: 9999
mysql:
  name: rag
  user: u
  password: 'mysql-secret-value'
  host: db
  port: 3306
redis:
  host: cache
  port: 6379
  password: 'redis-secret-value'
  db: 1
cors:
  allowed_origins: 'http://a.test, http://b.test'
logging:
  dir: ''
  level: INFO
security:
  secret_key: 'fake-test-secret-key-0123456789abcdef-ZZ'
auth:
  register_enabled: '1'
  superuser_email: ''
  superuser_password: ''
  otp_ttl_seconds: 600
mail:
  host: mailpit
  port: 1025
  security: none
  username: ''
  password: ''
  from: no-reply@devrag.local
models:
  default_chat_model: ''
  default_embedding_model: ''
  default_rerank_model: ''
  default_factory: ''
  default_base_url: ''
ratelimit:
  register_per_ip: 10
  register_window_seconds: 3600
  login_failures_per_email: 5
  login_per_ip: 30
  login_window_seconds: 900
  otp_email_interval_seconds: 60
  otp_per_email_per_hour: 5
  otp_per_ip_per_hour: 20
  otp_window_seconds: 3600
`

func write(t *testing.T, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "service_conf.yaml")
	require.NoError(t, os.WriteFile(p, []byte(body), 0o600))
	return p
}

func TestLoadConfigFull(t *testing.T) {
	cfg, err := LoadConfig(write(t, baseConf))
	require.NoError(t, err)
	assert.Equal(t, 9999, cfg.HTTPPort)
	assert.Equal(t, "127.0.0.1:9999", cfg.Addr())
	assert.Equal(t, []string{"http://a.test", "http://b.test"}, cfg.AllowedOrigins)
	assert.Equal(t, "db", cfg.MySQL.Host)
	assert.Equal(t, 1, cfg.Redis.DB)
}

func TestLoadConfigDefaultPortAndEmptyCORS(t *testing.T) {
	body := strings.Replace(strings.Replace(baseConf, "  http_port: 9999\n", "", 1), "'http://a.test, http://b.test'", "''", 1)
	cfg, err := LoadConfig(write(t, body))
	require.NoError(t, err)
	assert.Equal(t, DefaultHTTPPort, cfg.HTTPPort)
	assert.Empty(t, cfg.AllowedOrigins)
}

func TestLoadConfigMissingSecretNamesKey(t *testing.T) {
	for key, needle := range map[string]string{"mysql.password": "  password: 'mysql-secret-value'\n", "redis.password": "  password: 'redis-secret-value'\n"} {
		_, err := LoadConfig(write(t, strings.Replace(baseConf, needle, "", 1)))
		require.Error(t, err, key)
		assert.Contains(t, err.Error(), key)
	}
}

func TestLoadConfigRejectsWildcardOrigin(t *testing.T) {
	_, err := LoadConfig(write(t, strings.Replace(baseConf, "'http://a.test, http://b.test'", "'*'", 1)))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "'*'")
}

func TestLoadConfigErrors(t *testing.T) {
	_, err := LoadConfig("")
	assert.Error(t, err)
	_, err = LoadConfig(filepath.Join(t.TempDir(), "absent.yaml"))
	assert.Error(t, err)
	_, err = LoadConfig(write(t, strings.Replace(baseConf, "port: 3306", "port: abc", 1)))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mysql.port")
}

func TestConfigStringMasksSecrets(t *testing.T) {
	cfg, err := LoadConfig(write(t, baseConf))
	require.NoError(t, err)
	s := cfg.String()
	assert.NotContains(t, s, "mysql-secret-value")
	assert.NotContains(t, s, "redis-secret-value")
	assert.Contains(t, s, "***")
}

const fakeKey = "fake-test-secret-key-0123456789abcdef-ZZ"

func TestLoadConfigPhase2SectionsTyped(t *testing.T) {
	cfg, err := LoadConfig(write(t, baseConf))
	require.NoError(t, err)
	assert.Equal(t, fakeKey, cfg.Security.SecretKey)
	assert.Equal(t, 30*24*time.Hour, cfg.Security.TokenMaxAge)
	assert.Equal(t, 600000, cfg.Security.PasswordIterations)
	assert.True(t, cfg.Auth.RegisterEnabled)
	assert.Equal(t, 600*time.Second, cfg.Auth.OTPTTL)
	assert.Equal(t, MailConfig{Host: "mailpit", Port: 1025, Security: "none", From: "no-reply@devrag.local"}, cfg.Mail)
	assert.Equal(t, ModelsConfig{}, cfg.Models)
}

func TestRateLimitDefaultsEqualR94Numbers(t *testing.T) {
	want := RateLimit{
		RegisterPerIP: 10, RegisterWindowSeconds: 3600, LoginFailuresPerEmail: 5, LoginPerIP: 30, LoginWindowSeconds: 900,
		OTPEmailIntervalSeconds: 60, OTPPerEmailPerHour: 5, OTPPerIPPerHour: 20, OTPWindowSeconds: 3600,
	}
	assert.Equal(t, want, DefaultRateLimit())
	cfg, err := LoadConfig(write(t, strings.Replace(baseConf, "ratelimit:", "unused_ratelimit:", 1)))
	require.NoError(t, err)
	assert.Equal(t, want, cfg.RateLimit, "absent section falls back to the R-94 defaults")
	cfg, err = LoadConfig(write(t, baseConf))
	require.NoError(t, err)
	assert.Equal(t, want, cfg.RateLimit)
}

func TestLoadConfigRejectsBadSecretKey(t *testing.T) {
	bad := []string{"", "fake-zq9-short", strings.Repeat("x", 31), "changeme", "secret", "change-me", "ragflow", "CHANGEME",
		strings.Repeat("a", 40), strings.Repeat("0", 64)}
	for _, b := range bad {
		body := strings.Replace(baseConf, "'"+fakeKey+"'", "'"+b+"'", 1)
		_, err := LoadConfig(write(t, body))
		require.Error(t, err, b)
		assert.Contains(t, err.Error(), "security.secret_key")
		if b == "fake-zq9-short" || b == strings.Repeat("a", 40) {
			assert.NotContains(t, err.Error(), b)
		}
	}
	_, err := LoadConfig(write(t, strings.Replace(baseConf, "security:\n  secret_key: '"+fakeKey+"'\n", "", 1)))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "security.secret_key")
}

func TestLoadConfigRegisterEnabledParsing(t *testing.T) {
	for raw, want := range map[string]bool{"1": true, "0": false, "true": true, "false": false, "TRUE": true} {
		cfg, err := LoadConfig(write(t, strings.Replace(baseConf, "register_enabled: '1'", "register_enabled: '"+raw+"'", 1)))
		require.NoError(t, err, raw)
		assert.Equal(t, want, cfg.Auth.RegisterEnabled, raw)
	}
	_, err := LoadConfig(write(t, strings.Replace(baseConf, "register_enabled: '1'", "register_enabled: 'maybe'", 1)))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "auth.register_enabled")
}

func TestLoadConfigOTPTTLBounds(t *testing.T) {
	for _, bad := range []string{"0", "-1", "3601", "abc"} {
		_, err := LoadConfig(write(t, strings.Replace(baseConf, "otp_ttl_seconds: 600", "otp_ttl_seconds: "+bad, 1)))
		require.Error(t, err, bad)
		assert.Contains(t, err.Error(), "auth.otp_ttl_seconds")
	}
	for _, ok := range []int{1, 3600} {
		cfg, err := LoadConfig(write(t, strings.Replace(baseConf, "otp_ttl_seconds: 600", fmt.Sprintf("otp_ttl_seconds: %d", ok), 1)))
		require.NoError(t, err)
		assert.Equal(t, time.Duration(ok)*time.Second, cfg.Auth.OTPTTL)
	}
}

func TestLoadConfigSMTPSecurityEnum(t *testing.T) {
	for _, ok := range []string{"none", "starttls", "tls"} {
		cfg, err := LoadConfig(write(t, strings.Replace(baseConf, "security: none", "security: "+ok, 1)))
		require.NoError(t, err, ok)
		assert.Equal(t, ok, cfg.Mail.Security)
	}
	_, err := LoadConfig(write(t, strings.Replace(baseConf, "security: none", "security: ssl3", 1)))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mail.security")
}

func TestLoadConfigRateLimitValidation(t *testing.T) {
	for _, key := range []string{"register_per_ip", "login_per_ip", "otp_per_email_per_hour", "login_failures_per_email"} {
		for _, bad := range []string{"0", "-5", "abc"} {
			body := strings.Replace(baseConf, "  "+key+": ", "  "+key+": "+bad+" #", 1)
			_, err := LoadConfig(write(t, body))
			require.Error(t, err, key+bad)
			assert.Contains(t, err.Error(), "ratelimit."+key)
		}
	}
	for _, key := range []string{"register_window_seconds", "login_window_seconds", "otp_window_seconds"} {
		_, err := LoadConfig(write(t, strings.Replace(baseConf, "  "+key+": ", "  "+key+": 86401 #", 1)))
		require.Error(t, err, key)
		assert.Contains(t, err.Error(), "ratelimit."+key)
		_, err = LoadConfig(write(t, strings.Replace(baseConf, "  "+key+": ", "  "+key+": 86400 #", 1)))
		require.NoError(t, err, key)
	}
}
