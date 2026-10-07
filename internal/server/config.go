// Package server loads and validates configuration for the Go server.
package server

import (
	"errors"
	"fmt"
	"math"
	"net"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/viper"

	"devrag/internal/common"
)

// DefaultHTTPPort is the Go API port when go_api.http_port is absent.
const DefaultHTTPPort = 9384

// MySQLConfig holds MySQL connection settings.
type MySQLConfig struct {
	Name     string
	User     string
	Password string `json:"-"`
	Host     string
	Port     int
}

// RedisConfig holds Redis/Valkey connection settings.
type RedisConfig struct {
	Host     string
	Port     int
	Password string `json:"-"`
	DB       int
}

const (
	// MinSecretKeyLength is the shortest accepted token-signing key (R-96).
	MinSecretKeyLength = 32
	// TokenMaxAge is the fixed access-token lifetime (D-11).
	TokenMaxAge = 30 * 24 * time.Hour
	// PasswordIterations is the PBKDF2 work factor (D-09).
	PasswordIterations = 600000
	maxOTPTTLSeconds   = 3600
	maxWindowSeconds   = 86400
)

// SecurityConfig holds the token-signing key shared with the Python engine.
type SecurityConfig struct {
	SecretKey          string `json:"-"`
	TokenMaxAge        time.Duration
	PasswordIterations int
}

// String masks the signing key.
func (s SecurityConfig) String() string {
	return fmt.Sprintf("SecurityConfig{secret_key=%s token_max_age=%s password_iterations=%d}", common.RedactedValue, s.TokenMaxAge, s.PasswordIterations)
}

// GoString keeps %#v from printing the key.
func (s SecurityConfig) GoString() string { return s.String() }

// AuthConfig holds registration, superuser and one-time-code settings (D-01, D-03).
type AuthConfig struct {
	RegisterEnabled   bool
	SuperuserEmail    string
	SuperuserPassword string `json:"-"`
	OTPTTL            time.Duration
}

// String masks the superuser password.
func (a AuthConfig) String() string {
	return fmt.Sprintf("AuthConfig{register_enabled=%t superuser_email=%s superuser_password=%s otp_ttl=%s}",
		a.RegisterEnabled, a.SuperuserEmail, common.RedactedValue, a.OTPTTL)
}

// GoString keeps %#v from printing the password.
func (a AuthConfig) GoString() string { return a.String() }

// MailConfig holds the SMTP relay used for reset codes (D-05).
type MailConfig struct {
	Host     string
	Port     int
	Security string
	Username string
	Password string `json:"-"`
	From     string
}

// String masks the SMTP password.
func (m MailConfig) String() string {
	return fmt.Sprintf("MailConfig{%s:%d security=%s username=%s password=%s from=%s}", m.Host, m.Port, m.Security, m.Username, common.RedactedValue, m.From)
}

// GoString keeps %#v from printing the password.
func (m MailConfig) GoString() string { return m.String() }

// ModelsConfig holds the optional default models seeded for new tenants (D-22).
type ModelsConfig struct {
	DefaultChatModel      string
	DefaultEmbeddingModel string
	DefaultRerankModel    string
	DefaultFactory        string
	DefaultBaseURL        string
}

// RateLimit holds every rate-limit number (D-29). Defaults are the R-94 production values.
type RateLimit struct {
	RegisterPerIP           int
	RegisterWindowSeconds   int
	LoginFailuresPerEmail   int
	LoginPerIP              int
	LoginWindowSeconds      int
	OTPEmailIntervalSeconds int
	OTPPerEmailPerHour      int
	OTPPerIPPerHour         int
	OTPWindowSeconds        int
}

// DefaultRateLimit returns the R-94 production numbers.
func DefaultRateLimit() RateLimit {
	return RateLimit{
		RegisterPerIP: 10, RegisterWindowSeconds: 3600,
		LoginFailuresPerEmail: 5, LoginPerIP: 30, LoginWindowSeconds: 900,
		OTPEmailIntervalSeconds: 60, OTPPerEmailPerHour: 5, OTPPerIPPerHour: 20, OTPWindowSeconds: 3600,
	}
}

// Config is the typed service configuration shared with the Python engine.
type Config struct {
	Security       SecurityConfig
	Auth           AuthConfig
	Mail           MailConfig
	Models         ModelsConfig
	RateLimit      RateLimit
	MySQL          MySQLConfig
	Redis          RedisConfig
	AllowedOrigins []string
	Log            common.LogConfig
	Host           string
	HTTPPort       int
}

// Addr is the listen address of the Go API.
func (c Config) Addr() string { return net.JoinHostPort(c.Host, strconv.Itoa(c.HTTPPort)) }

// String masks every secret.
func (c Config) String() string {
	return fmt.Sprintf("Config{mysql:%s@%s:%d/%s password=%s redis:%s:%d db=%d password=%s listen=%s}",
		c.MySQL.User, c.MySQL.Host, c.MySQL.Port, c.MySQL.Name, common.RedactedValue,
		c.Redis.Host, c.Redis.Port, c.Redis.DB, common.RedactedValue, c.Addr())
}

var placeholderKeys = map[string]bool{"changeme": true, "secret": true, "change-me": true, "ragflow": true}

// validSecretKey reports whether key is long enough and not a known placeholder or a repeated character.
func validSecretKey(key string) bool {
	if len(key) < MinSecretKeyLength || placeholderKeys[strings.ToLower(key)] {
		return false
	}
	return strings.Count(key, key[:1]) != len(key)
}

func boundedInt(v *viper.Viper, key string, def, lo, hi int) (int, error) {
	if !v.IsSet(key) || strings.TrimSpace(v.GetString(key)) == "" {
		return def, nil
	}
	n, err := strconv.Atoi(strings.TrimSpace(v.GetString(key)))
	if err != nil || n < lo || n > hi {
		return 0, fmt.Errorf("invalid value for config key: %s", key)
	}
	return n, nil
}

func loadPhase2(v *viper.Viper, cfg *Config) error {
	key := strings.TrimSpace(v.GetString("security.secret_key"))
	if !validSecretKey(key) {
		return fmt.Errorf("config key security.secret_key is missing, shorter than %d characters or a placeholder (run make init-env)", MinSecretKeyLength)
	}
	cfg.Security = SecurityConfig{SecretKey: key, TokenMaxAge: TokenMaxAge, PasswordIterations: PasswordIterations}
	cfg.Auth.RegisterEnabled = true
	if raw := strings.TrimSpace(v.GetString("auth.register_enabled")); raw != "" {
		enabled, err := strconv.ParseBool(raw)
		if err != nil {
			return errors.New("invalid value for config key: auth.register_enabled")
		}
		cfg.Auth.RegisterEnabled = enabled
	}
	cfg.Auth.SuperuserEmail = strings.TrimSpace(v.GetString("auth.superuser_email"))
	cfg.Auth.SuperuserPassword = v.GetString("auth.superuser_password")
	ttl, err := boundedInt(v, "auth.otp_ttl_seconds", 600, 1, maxOTPTTLSeconds)
	if err != nil {
		return err
	}
	cfg.Auth.OTPTTL = time.Duration(ttl) * time.Second
	port, err := boundedInt(v, "mail.port", 1025, 1, 65535)
	if err != nil {
		return err
	}
	cfg.Mail = MailConfig{
		Host: v.GetString("mail.host"), Port: port, Security: strings.TrimSpace(v.GetString("mail.security")),
		Username: v.GetString("mail.username"), Password: v.GetString("mail.password"), From: v.GetString("mail.from"),
	}
	switch cfg.Mail.Security {
	case "":
		cfg.Mail.Security = "none"
	case "none", "starttls", "tls":
	default:
		return errors.New("invalid value for config key: mail.security")
	}
	cfg.Models = ModelsConfig{
		DefaultChatModel: v.GetString("models.default_chat_model"), DefaultEmbeddingModel: v.GetString("models.default_embedding_model"),
		DefaultRerankModel: v.GetString("models.default_rerank_model"), DefaultFactory: v.GetString("models.default_factory"),
		DefaultBaseURL: v.GetString("models.default_base_url"),
	}
	return loadRateLimit(v, cfg)
}

func loadRateLimit(v *viper.Viper, cfg *Config) error {
	rl := DefaultRateLimit()
	fields := []struct {
		key string
		dst *int
		max int
	}{
		{"register_per_ip", &rl.RegisterPerIP, math.MaxInt32}, {"register_window_seconds", &rl.RegisterWindowSeconds, maxWindowSeconds},
		{"login_failures_per_email", &rl.LoginFailuresPerEmail, math.MaxInt32}, {"login_per_ip", &rl.LoginPerIP, math.MaxInt32},
		{"login_window_seconds", &rl.LoginWindowSeconds, maxWindowSeconds},
		{"otp_email_interval_seconds", &rl.OTPEmailIntervalSeconds, maxWindowSeconds},
		{"otp_per_email_per_hour", &rl.OTPPerEmailPerHour, math.MaxInt32}, {"otp_per_ip_per_hour", &rl.OTPPerIPPerHour, math.MaxInt32},
		{"otp_window_seconds", &rl.OTPWindowSeconds, maxWindowSeconds},
	}
	for _, f := range fields {
		n, err := boundedInt(v, "ratelimit."+f.key, *f.dst, 1, f.max)
		if err != nil {
			return err
		}
		*f.dst = n
	}
	cfg.RateLimit = rl
	return nil
}

func required(v *viper.Viper, key string) (string, error) {
	val := strings.TrimSpace(v.GetString(key))
	if val == "" {
		return "", fmt.Errorf("missing required config key: %s", key)
	}
	return val, nil
}

func requiredInt(v *viper.Viper, key string) (int, error) {
	raw, err := required(v, key)
	if err != nil {
		return 0, err
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("invalid value for config key: %s", key)
	}
	return n, nil
}

// LoadConfig reads the rendered service_conf.yaml (the same file the Python engine uses).
func LoadConfig(path string) (Config, error) {
	if path == "" {
		return Config{}, errors.New("config path is empty (set SERVICE_CONF)")
	}
	v := viper.New()
	v.SetConfigFile(path)
	v.SetConfigType("yaml")
	if err := v.ReadInConfig(); err != nil {
		return Config{}, fmt.Errorf("read config: %w", err)
	}
	var cfg Config
	var err error
	for _, step := range []func() error{
		func() (e error) { cfg.MySQL.Name, e = required(v, "mysql.name"); return },
		func() (e error) { cfg.MySQL.User, e = required(v, "mysql.user"); return },
		func() (e error) { cfg.MySQL.Password, e = required(v, "mysql.password"); return },
		func() (e error) { cfg.MySQL.Host, e = required(v, "mysql.host"); return },
		func() (e error) { cfg.MySQL.Port, e = requiredInt(v, "mysql.port"); return },
		func() (e error) { cfg.Redis.Host, e = required(v, "redis.host"); return },
		func() (e error) { cfg.Redis.Port, e = requiredInt(v, "redis.port"); return },
		func() (e error) { cfg.Redis.Password, e = required(v, "redis.password"); return },
	} {
		if err = step(); err != nil {
			return Config{}, err
		}
	}
	if err = loadPhase2(v, &cfg); err != nil {
		return Config{}, err
	}
	cfg.Redis.DB = v.GetInt("redis.db")
	for _, o := range strings.Split(v.GetString("cors.allowed_origins"), ",") {
		if o = strings.TrimSpace(o); o != "" {
			cfg.AllowedOrigins = append(cfg.AllowedOrigins, o)
		}
	}
	for _, o := range cfg.AllowedOrigins {
		if o == "*" {
			return Config{}, errors.New("cors.allowed_origins must be an explicit list; '*' is not allowed")
		}
	}
	cfg.Log = common.LogConfig{Dir: v.GetString("logging.dir"), Level: v.GetString("logging.level")}
	cfg.Host = v.GetString("go_api.host")
	if cfg.Host == "" {
		cfg.Host = "0.0.0.0"
	}
	cfg.HTTPPort = DefaultHTTPPort
	if v.IsSet("go_api.http_port") && strings.TrimSpace(v.GetString("go_api.http_port")) != "" {
		if cfg.HTTPPort, err = requiredInt(v, "go_api.http_port"); err != nil {
			return Config{}, err
		}
	}
	return cfg, nil
}
