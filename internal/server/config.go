// Package server loads and validates configuration for the Go server.
package server

import (
	"errors"
	"fmt"
	"net"
	"strconv"
	"strings"

	"github.com/spf13/viper"

	"devrag/internal/common"
)

// DefaultHTTPPort is the Go API port when go_api.http_port is absent.
const DefaultHTTPPort = 9384

// MySQLConfig holds MySQL connection settings.
type MySQLConfig struct {
	Name     string
	User     string
	Password string
	Host     string
	Port     int
}

// RedisConfig holds Redis/Valkey connection settings.
type RedisConfig struct {
	Host     string
	Port     int
	Password string
	DB       int
}

// Config is the typed service configuration shared with the Python engine.
type Config struct {
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
