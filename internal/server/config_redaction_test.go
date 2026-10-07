package server

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"

	"devrag/internal/common"
)

func TestConfigPasswordsNeverSerialised(t *testing.T) {
	cfg := Config{
		MySQL: MySQLConfig{Name: "db", User: "app", Password: "mysql-pw-not-real", Host: "mysql", Port: 3306},
		Redis: RedisConfig{Host: "valkey", Port: 6379, Password: "redis-pw-not-real"},
	}
	raw, err := json.Marshal(cfg)
	require.NoError(t, err)
	assert.NotContains(t, string(raw), "mysql-pw-not-real")
	assert.NotContains(t, string(raw), "redis-pw-not-real")

	core, logs := observer.New(zapcore.DebugLevel)
	l := zap.New(common.WrapRedacting(core))
	l.Info("config", zap.Any("cfg", cfg), zap.Reflect("raw", cfg.MySQL))
	dumped := ""
	for k, v := range logs.All()[0].ContextMap() {
		raw, _ := json.Marshal(v)
		dumped += k + string(raw)
	}
	assert.NotContains(t, dumped, "mysql-pw-not-real")
	assert.NotContains(t, dumped, "redis-pw-not-real")
}

func TestPhase2SecretsNeverDumped(t *testing.T) {
	cfg := Config{
		Security: SecurityConfig{SecretKey: "fake-sec-key-redaction-0123456789abcdef", PasswordIterations: 600000},
		Auth:     AuthConfig{SuperuserEmail: "root@example.test", SuperuserPassword: "fake-su-pw-redaction"},
		Mail:     MailConfig{Host: "mailpit", Password: "fake-smtp-pw-redaction"},
	}
	secrets := []string{"fake-sec-key-redaction", "fake-su-pw-redaction", "fake-smtp-pw-redaction"}
	raw, err := json.Marshal(cfg)
	require.NoError(t, err)
	dumps := []string{
		string(raw), cfg.String(), fmt.Sprintf("%+v", cfg), fmt.Sprintf("%v", cfg), fmt.Sprintf("%#v", cfg.Security),
		fmt.Sprintf("%+v", cfg.Security), fmt.Sprintf("%+v", cfg.Auth), fmt.Sprintf("%+v", cfg.Mail), fmt.Sprintf("%v", &cfg),
	}
	for _, d := range dumps {
		for _, secret := range secrets {
			assert.NotContains(t, d, secret)
		}
	}
	assert.Contains(t, cfg.String(), common.RedactedValue)
}
