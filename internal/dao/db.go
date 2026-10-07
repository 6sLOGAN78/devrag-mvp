// Package dao is the data-access layer. It issues queries only: the Python engine owns the
// schema, so no schema-changing call is ever made here (D-10).
package dao

import (
	"context"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"devrag/internal/server"
)

const (
	dialTimeout  = 2 * time.Second
	ioTimeout    = 2 * time.Second
	maxOpenConns = 10
	maxIdleConns = 5
	connLifetime = 5 * time.Minute
)

// DB wraps the GORM handle used by the service layer.
type DB struct {
	gorm *gorm.DB
}

// DSN builds the driver DSN. Timeouts make an unreachable server fail fast.
func DSN(cfg server.MySQLConfig) string {
	q := url.Values{}
	q.Set("charset", "utf8mb4")
	q.Set("parseTime", "True")
	q.Set("loc", "UTC")
	q.Set("timeout", dialTimeout.String())
	q.Set("readTimeout", ioTimeout.String())
	q.Set("writeTimeout", ioTimeout.String())
	addr := net.JoinHostPort(cfg.Host, strconv.Itoa(cfg.Port))
	return fmt.Sprintf("%s:%s@tcp(%s)/%s?%s", cfg.User, cfg.Password, addr, cfg.Name, q.Encode())
}

// OpenDB opens a pooled MySQL handle and verifies it with a bounded ping.
func OpenDB(ctx context.Context, cfg server.MySQLConfig) (*DB, error) {
	g, err := gorm.Open(mysql.Open(DSN(cfg)), &gorm.Config{Logger: logger.Discard, TranslateError: true})
	if err != nil {
		return nil, fmt.Errorf("open database: %w", sanitize(err))
	}
	sqlDB, err := g.DB()
	if err != nil {
		return nil, fmt.Errorf("database handle: %w", err)
	}
	sqlDB.SetMaxOpenConns(maxOpenConns)
	sqlDB.SetMaxIdleConns(maxIdleConns)
	sqlDB.SetConnMaxLifetime(connLifetime)
	d := &DB{gorm: g}
	if err := d.Ping(ctx); err != nil {
		_ = sqlDB.Close()
		return nil, err
	}
	return d, nil
}

// Ping checks connectivity within the caller's context.
func (d *DB) Ping(ctx context.Context) error {
	sqlDB, err := d.gorm.DB()
	if err != nil {
		return err
	}
	return sqlDB.PingContext(ctx)
}

// Close releases the pool.
func (d *DB) Close() error {
	sqlDB, err := d.gorm.DB()
	if err != nil {
		return err
	}
	return sqlDB.Close()
}

// sanitize keeps connection details (host, user, password) out of returned errors.
func sanitize(err error) error {
	return fmt.Errorf("%T", err)
}
