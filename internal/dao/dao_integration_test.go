//go:build integration

package dao

import (
	"context"
	"os"
	"regexp"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/server"
)

func confPath() string {
	if p := os.Getenv("SERVICE_CONF"); p != "" {
		return p
	}
	return "../../conf/service_conf.yaml"
}

func TestGetSettingReadsSchemaVersionWrittenByInit(t *testing.T) {
	cfg, err := server.LoadConfig(confPath())
	require.NoError(t, err)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db, err := OpenDB(ctx, cfg.MySQL)
	require.NoError(t, err)
	defer func() { _ = db.Close() }()

	v, err := db.GetSetting(ctx, "schema.version")
	require.NoError(t, err)
	assert.Regexp(t, regexp.MustCompile(`^\d{4}$`), v)

	_, err = db.GetSetting(ctx, "no.such.setting")
	assert.ErrorIs(t, err, ErrSettingNotFound)

	_, err = db.GetSetting(ctx, "schema.version' OR '1'='1")
	assert.ErrorIs(t, err, ErrSettingNotFound, "name is a bound parameter, not SQL")
}

func TestRedisPingLive(t *testing.T) {
	cfg, err := server.LoadConfig(confPath())
	require.NoError(t, err)
	rd := OpenRedis(cfg.Redis)
	defer func() { _ = rd.Close() }()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	assert.NoError(t, rd.Ping(ctx))
}

func TestOpenDBWrongPortFailsFast(t *testing.T) {
	cfg, err := server.LoadConfig(confPath())
	require.NoError(t, err)
	cfg.MySQL.Port = 1 // nothing listens here
	started := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, err = OpenDB(ctx, cfg.MySQL)
	require.Error(t, err)
	assert.Less(t, time.Since(started), 4*time.Second)
	assert.NotContains(t, err.Error(), cfg.MySQL.Password)
}
