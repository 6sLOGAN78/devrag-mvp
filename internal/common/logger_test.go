package common

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
)

func observed() (*zap.Logger, *observer.ObservedLogs) {
	core, logs := observer.New(zapcore.DebugLevel)
	return zap.New(WrapRedacting(core)), logs
}

func TestSensitiveFieldKeysMasked(t *testing.T) {
	l, logs := observed()
	l.Info("hello", zap.String("password", "p1"), zap.String("api_key", "k1"), zap.String("Authorization", "Bearer zzz"),
		zap.String("token", "t1"), zap.String("secret", "s1"), zap.String("cookie", "c1"), zap.String("user", "bob"))
	m := logs.All()[0].ContextMap()
	for _, k := range []string{"password", "api_key", "Authorization", "token", "secret", "cookie"} {
		assert.Equal(t, RedactedValue, m[k], k)
	}
	assert.Equal(t, "bob", m["user"])
}

func TestMessageFragmentsMasked(t *testing.T) {
	l, logs := observed()
	l.Warn("login failed password=abc user=bob token: xyz")
	msg := logs.All()[0].Message
	assert.NotContains(t, msg, "abc")
	assert.NotContains(t, msg, "xyz")
	assert.Contains(t, msg, "user=bob")
}

func TestStringFieldFragmentAndErrorMasked(t *testing.T) {
	l, logs := observed()
	l.Error("boom", zap.String("dsn", "host=db secret=hunter2"), zap.Error(assert.AnError))
	l.Error("boom2", zap.Error(os.ErrNotExist))
	m := logs.All()[0].ContextMap()
	assert.NotContains(t, m["dsn"], "hunter2")
}

func TestWithFieldsRedacted(t *testing.T) {
	l, logs := observed()
	l.With(zap.String("api_key", "k")).Info("x")
	assert.Equal(t, RedactedValue, logs.All()[0].ContextMap()["api_key"])
}

func TestNewLoggerWritesRedactedFile(t *testing.T) {
	dir := t.TempDir()
	l, cleanup, err := NewLogger(LogConfig{Dir: dir, Level: "info"})
	require.NoError(t, err)
	l.Info("request", zap.String("password", "pw"))
	l.Debug("dropped")
	_ = l.Sync() // stdout may reject fsync; the file content is asserted below
	cleanup()
	raw, err := os.ReadFile(filepath.Join(dir, LogFileName))
	require.NoError(t, err)
	var rec map[string]any
	require.NoError(t, json.Unmarshal(raw, &rec))
	assert.Equal(t, RedactedValue, rec["password"])
	assert.NotContains(t, string(raw), "dropped")
}

func TestNewLoggerRejectsBadLevel(t *testing.T) {
	_, _, err := NewLogger(LogConfig{Level: "loud"})
	assert.Error(t, err)
}

type vector struct {
	ID      string   `json:"id"`
	Input   string   `json:"input"`
	Secrets []string `json:"secrets"`
	Keep    []string `json:"keep"`
}

func loadVectors(t *testing.T) []vector {
	t.Helper()
	raw, err := os.ReadFile("../../test/fixtures/log_redaction_vectors.json") // log_redaction_vectors.json
	require.NoError(t, err)
	var vs []vector
	require.NoError(t, json.Unmarshal(raw, &vs))
	require.GreaterOrEqual(t, len(vs), 22)
	return vs
}

func TestSharedRedactionVectors(t *testing.T) {
	for _, v := range loadVectors(t) {
		t.Run(v.ID, func(t *testing.T) {
			l, logs := observed()
			out := RedactString(v.Input)
			l.Warn(v.Input)
			msg := logs.All()[0].Message
			for _, o := range []string{out, msg} {
				for _, s := range v.Secrets {
					assert.NotContains(t, o, s)
				}
				for _, k := range v.Keep {
					assert.Contains(t, o, k)
				}
			}
		})
	}
}

func TestStructuredFieldsRedacted(t *testing.T) {
	l, logs := observed()
	l.Info("x",
		zap.Any("cfg", map[string]any{"password": "hunter2-fake", "ok": "fine"}),
		zap.Strings("args", []string{"password=hunter2-fake"}),
		zap.Reflect("req", struct{ Token string }{"abc-fake"}),
		zap.ByteString("raw", []byte("secret=zzz-fake")))
	m := logs.All()[0].ContextMap()
	dumped := fmt.Sprintf("%v", m)
	for _, s := range []string{"hunter2-fake", "abc-fake", "zzz-fake"} {
		assert.NotContains(t, dumped, s)
	}
	assert.Contains(t, dumped, "fine")
}

type secretHolder struct {
	User     string
	Password string `json:"-"`
}

func TestJSONTaggedPasswordNotSerialised(t *testing.T) {
	l, logs := observed()
	l.Info("cfg", zap.Reflect("cfg", secretHolder{User: "app", Password: "hunter2-fake"}))
	assert.NotContains(t, fmt.Sprintf("%v", logs.All()[0].ContextMap()), "hunter2-fake")
}

func TestHostileInputRedactsLinearly(t *testing.T) {
	for name, in := range map[string]string{
		"a_run":        strings.Repeat("a", 100000),
		"token_repeat": strings.Repeat("token", 20000),
		"pw_equals":    strings.Repeat("password=", 12000),
		"scheme":       strings.Repeat("a://", 25000),
	} {
		t.Run(name, func(t *testing.T) {
			started := time.Now()
			RedactString(in)
			assert.Less(t, time.Since(started), 2*time.Second)
		})
	}
}

func TestTruncateFieldKeepsRunesIntact(t *testing.T) {
	out := TruncateField(strings.Repeat("é", 400), 511)
	assert.True(t, utf8.ValidString(out))
	assert.True(t, strings.HasSuffix(out, "[truncated]"))
	assert.Equal(t, "/health", TruncateField("/health", MaxLogField))
}

func TestRedactorCoversOTPAndTicketFields(t *testing.T) {
	for _, in := range []string{`otp=424242`, `{"otp":"424242"}`, `reset_ticket=abcDEF123_-xyz`, `"reset_ticket": "abcDEF123_-xyz"`, `ticket: abcDEF123_-xyz`} {
		out := RedactString(in)
		assert.NotContains(t, out, "424242", in)
		assert.NotContains(t, out, "abcDEF123", in)
		assert.Contains(t, out, RedactedValue)
	}
	assert.True(t, IsSensitiveKey("otp"))
	assert.True(t, IsSensitiveKey("reset_ticket"))
}
