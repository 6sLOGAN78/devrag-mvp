package common

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// RedactedValue replaces any sensitive value in log output.
const RedactedValue = "***"

var sensitiveKeys = []string{"password", "passwd", "pwd", "secret", "api_key", "apikey", "token", "authorization", "cookie"}

// redactedMarker replaces values that cannot be safely inspected.
const redactedMarker = "***unserialisable***"

// fragmentPattern matches key=value, key: value and "key": "value" forms for sensitive keys.
// Groups: 1 key (with optional quotes), 2 separator, 3 value (AWS4 signature line, or optional auth
// scheme + quoted run with escaped quotes or bare run). RE2 guarantees linear-time matching.
var fragmentPattern = regexp.MustCompile(`(?i)(["']?[\w-]*(?:password|passwd|pwd|secret|api[_-]?key|token|authorization)[\w-]*["']?)([ \t]*[=:][ \t]*)(AWS4-HMAC-SHA256[ \t]+[^\n]+|(?:(?:Bearer|Basic|Digest|Token|ApiKey|Api-Key|Negotiate)[ \t]+)?(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;&}]+))`)

// cookiePattern masks cookie and set-cookie values: a quoted value, otherwise everything to end of line.
var cookiePattern = regexp.MustCompile(`(?i)(["']?[\w-]*cookie[\w-]*["']?)([ \t]*[=:][ \t]*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\n]+)`)

// urlUserinfoPattern matches scheme://user:password@ (user may be empty, the password may contain @,
// the greedy class stops at the last @ of the authority) and keeps everything but the password.
var urlUserinfoPattern = regexp.MustCompile(`(?i)([a-z][a-z0-9+.-]*://[^\s:/@?#]*:)[^\s/?#]*(@)`)

const (
	// maxRedactInput bounds the text inspected by RedactString (parity with the Python engine).
	maxRedactInput = 64 * 1024
	// MaxLogField bounds untrusted fields such as request paths at the log site.
	MaxLogField     = 512
	truncatedMarker = "[truncated]"
)

// TruncateField bounds an untrusted, client-controlled value at the log site without splitting a rune.
func TruncateField(s string, limit int) string {
	if len(s) <= limit {
		return s
	}
	cut := limit
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut] + truncatedMarker
}

// IsSensitiveKey reports whether a log field key must have its value masked.
func IsSensitiveKey(key string) bool {
	lower := strings.ReplaceAll(strings.ToLower(key), "-", "_")
	for _, s := range sensitiveKeys {
		if strings.Contains(lower, s) {
			return true
		}
	}
	return false
}

// RedactString masks credentials (key=value fragments, auth headers, cookies, URL userinfo) inside free text.
func RedactString(s string) string {
	if len(s) > maxRedactInput {
		return RedactString(TruncateField(s, maxRedactInput-len(truncatedMarker)))
	}
	s = urlUserinfoPattern.ReplaceAllString(s, "${1}"+RedactedValue+"${2}")
	s = redactWith(cookiePattern, s)
	return redactWith(fragmentPattern, s)
}

func redactWith(re *regexp.Regexp, s string) string {
	return re.ReplaceAllStringFunc(s, func(m string) string {
		sub := re.FindStringSubmatch(m)
		val := sub[3]
		quote := ""
		if val != "" && (val[len(val)-1] == '"' || val[len(val)-1] == '\'') {
			quote = string(val[len(val)-1])
		}
		return sub[1] + sub[2] + quote + RedactedValue + quote
	})
}

// redactAny walks a decoded value, masking sensitive keys and scrubbing strings.
func redactAny(v any) any {
	switch t := v.(type) {
	case nil, bool, int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64, uintptr, float32, float64, time.Duration, time.Time:
		return v
	case string:
		return RedactString(t)
	case []byte:
		return RedactString(string(t))
	case error:
		return RedactString(t.Error())
	case map[string]any:
		out := make(map[string]any, len(t))
		for k, val := range t {
			if IsSensitiveKey(k) {
				out[k] = RedactedValue
			} else {
				out[k] = redactAny(val)
			}
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i, val := range t {
			out[i] = redactAny(val)
		}
		return out
	default:
		raw, err := json.Marshal(v)
		if err != nil {
			return redactedMarker
		}
		var decoded any
		if err := json.Unmarshal(raw, &decoded); err != nil {
			return redactedMarker
		}
		switch decoded.(type) {
		case map[string]any, []any, string, nil, bool, float64:
			return redactAny(decoded)
		}
		return redactedMarker
	}
}

// redactComplex renders a non-primitive field and returns redacted replacement fields.
func redactComplex(f zapcore.Field) []zapcore.Field {
	if f.Type == zapcore.ByteStringType || f.Type == zapcore.BinaryType {
		b, _ := f.Interface.([]byte)
		return []zapcore.Field{zap.String(f.Key, RedactString(string(b)))}
	}
	enc := zapcore.NewMapObjectEncoder()
	f.AddTo(enc)
	if f.Type == zapcore.InlineMarshalerType {
		out := make([]zapcore.Field, 0, len(enc.Fields))
		for k, v := range enc.Fields {
			if IsSensitiveKey(k) {
				out = append(out, zap.String(k, RedactedValue))
			} else {
				out = append(out, zap.Any(k, redactAny(v)))
			}
		}
		return out
	}
	return []zapcore.Field{zap.Any(f.Key, redactAny(enc.Fields[f.Key]))}
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
	out := make([]zapcore.Field, 0, len(fields))
	for _, f := range fields {
		switch {
		case IsSensitiveKey(f.Key):
			out = append(out, zap.String(f.Key, RedactedValue))
		case f.Type == zapcore.StringType:
			out = append(out, zap.String(f.Key, RedactString(f.String)))
		case f.Type == zapcore.ErrorType:
			if err, ok := f.Interface.(error); ok {
				out = append(out, zap.String(f.Key, RedactString(err.Error())))
			} else {
				out = append(out, f)
			}
		case isPrimitive(f.Type):
			out = append(out, f)
		default:
			out = append(out, redactComplex(f)...)
		}
	}
	return out
}

func isPrimitive(t zapcore.FieldType) bool {
	switch t {
	case zapcore.BoolType, zapcore.Int64Type, zapcore.Int32Type, zapcore.Int16Type, zapcore.Int8Type,
		zapcore.Uint64Type, zapcore.Uint32Type, zapcore.Uint16Type, zapcore.Uint8Type, zapcore.UintptrType,
		zapcore.Float64Type, zapcore.Float32Type, zapcore.DurationType, zapcore.TimeType, zapcore.TimeFullType,
		zapcore.Complex64Type, zapcore.Complex128Type, zapcore.SkipType, zapcore.NamespaceType:
		return true
	}
	return false
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
