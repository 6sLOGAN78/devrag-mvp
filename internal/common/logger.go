package common

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// RedactedValue replaces any sensitive value in log output.
const RedactedValue = "***"

var sensitiveKeys = []string{"password", "secret", "api_key", "apikey", "token", "authorization", "cookie"}

var fragmentPattern = regexp.MustCompile(`(?i)\b([a-z_]*(?:password|secret|api_key|apikey|token|authorization|cookie)[a-z_]*)\s*[=:]\s*("[^"]*"|'[^']*'|[^\s,;&]+)`)

// IsSensitiveKey reports whether a log field key must have its value masked.
func IsSensitiveKey(key string) bool {
	lower := strings.ToLower(key)
	for _, s := range sensitiveKeys {
		if strings.Contains(lower, s) {
			return true
		}
	}
	return false
}

// RedactString masks key=value fragments for sensitive keys inside free text.
func RedactString(s string) string {
	return fragmentPattern.ReplaceAllString(s, "${1}="+RedactedValue)
}

type redactingCore struct {
	zapcore.Core
}

func (r redactingCore) With(fields []zapcore.Field) zapcore.Core {
	return redactingCore{Core: r.Core.With(redactFields(fields))}
}

func (r redactingCore) Check(ent zapcore.Entry, ce *zapcore.CheckedEntry) *zapcore.CheckedEntry {
	if r.Enabled(ent.Level) {
		return ce.AddCore(ent, r)
	}
	return ce
}

func (r redactingCore) Write(ent zapcore.Entry, fields []zapcore.Field) error {
	ent.Message = RedactString(ent.Message)
	return r.Core.Write(ent, redactFields(fields))
}

func redactFields(fields []zapcore.Field) []zapcore.Field {
	out := make([]zapcore.Field, len(fields))
	for i, f := range fields {
		switch {
		case IsSensitiveKey(f.Key):
			out[i] = zap.String(f.Key, RedactedValue)
		case f.Type == zapcore.StringType:
			out[i] = zap.String(f.Key, RedactString(f.String))
		case f.Type == zapcore.ErrorType:
			if err, ok := f.Interface.(error); ok {
				out[i] = zap.String(f.Key, RedactString(err.Error()))
			} else {
				out[i] = f
			}
		default:
			out[i] = f
		}
	}
	return out
}

// WrapRedacting wraps a core so every entry is redacted before it is written.
func WrapRedacting(core zapcore.Core) zapcore.Core { return redactingCore{Core: core} }

// LogConfig selects log level and an optional directory for ragflow_go.log.
type LogConfig struct {
	Dir   string
	Level string
}

// LogFileName is the Go server log file inside LogConfig.Dir.
const LogFileName = "ragflow_go.log"

func parseLevel(s string) (zapcore.Level, error) {
	if s == "" {
		return zapcore.InfoLevel, nil
	}
	var lvl zapcore.Level
	if err := lvl.UnmarshalText([]byte(strings.ToLower(s))); err != nil {
		return zapcore.InfoLevel, fmt.Errorf("invalid logging.level %q", s)
	}
	return lvl, nil
}

// NewLogger builds a JSON logger writing to stdout and, when cfg.Dir is set, to a file.
// The returned cleanup closes the file.
func NewLogger(cfg LogConfig) (*zap.Logger, func(), error) {
	lvl, err := parseLevel(cfg.Level)
	if err != nil {
		return nil, nil, err
	}
	encCfg := zap.NewProductionEncoderConfig()
	encCfg.TimeKey = "ts"
	encCfg.EncodeTime = zapcore.ISO8601TimeEncoder
	enc := zapcore.NewJSONEncoder(encCfg)
	cores := []zapcore.Core{zapcore.NewCore(enc, zapcore.Lock(os.Stdout), lvl)}
	cleanup := func() {}
	if cfg.Dir != "" {
		if err := os.MkdirAll(cfg.Dir, 0o750); err != nil {
			return nil, nil, fmt.Errorf("create log dir: %w", err)
		}
		f, err := os.OpenFile(filepath.Join(cfg.Dir, LogFileName), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640) // #nosec G304 -- operator-configured directory
		if err != nil {
			return nil, nil, fmt.Errorf("open log file: %w", err)
		}
		cores = append(cores, zapcore.NewCore(enc, zapcore.AddSync(f), lvl))
		cleanup = func() { _ = f.Close() }
	}
	logger := zap.New(WrapRedacting(zapcore.NewTee(cores...)))
	return logger, cleanup, nil
}
