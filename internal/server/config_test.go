package server

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

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
