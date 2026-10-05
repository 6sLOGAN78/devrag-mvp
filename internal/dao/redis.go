package dao

import (
	"context"
	"fmt"
	"net"
	"strconv"

	"github.com/redis/go-redis/v9"

	"devrag/internal/server"
)

// Redis wraps the go-redis client with short timeouts.
type Redis struct {
	client *redis.Client
}

// OpenRedis builds a client; it does not dial until first use.
func OpenRedis(cfg server.RedisConfig) *Redis {
	return &Redis{client: redis.NewClient(&redis.Options{
		Addr:         net.JoinHostPort(cfg.Host, strconv.Itoa(cfg.Port)),
		Password:     cfg.Password,
		DB:           cfg.DB,
		DialTimeout:  dialTimeout,
		ReadTimeout:  ioTimeout,
		WriteTimeout: ioTimeout,
		MaxRetries:   -1,
	})}
}

// Ping checks connectivity within the caller's context.
func (r *Redis) Ping(ctx context.Context) error {
	if err := r.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("redis ping: %T", err)
	}
	return nil
}

// Close releases the client.
func (r *Redis) Close() error { return r.client.Close() }
