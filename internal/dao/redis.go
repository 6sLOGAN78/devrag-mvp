package dao

import (
	"context"
	"errors"
	"fmt"
	"net"
	"strconv"
	"time"

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

// Incr increments a fixed-window counter and returns the new count and the remaining TTL. INCR,
// EXPIRE NX and PTTL run in one MULTI/EXEC so a crash cannot leave a counter without a TTL; NX
// keeps the window anchored at the first hit.
func (r *Redis) Incr(ctx context.Context, key string, window time.Duration) (int64, time.Duration, error) {
	pipe := r.client.TxPipeline()
	incr := pipe.Incr(ctx, key)
	pipe.ExpireNX(ctx, key, window)
	ttl := pipe.PTTL(ctx, key)
	if _, err := pipe.Exec(ctx); err != nil {
		return 0, 0, fmt.Errorf("redis incr: %T", err)
	}
	return incr.Val(), ttl.Val(), nil
}

// Count reads a counter without changing it. A missing key counts zero.
func (r *Redis) Count(ctx context.Context, key string) (int64, time.Duration, error) {
	pipe := r.client.Pipeline()
	get := pipe.Get(ctx, key)
	ttl := pipe.PTTL(ctx, key)
	if _, err := pipe.Exec(ctx); err != nil && !errors.Is(err, redis.Nil) {
		return 0, 0, fmt.Errorf("redis get: %T", err)
	}
	n, err := get.Int64()
	if err != nil && !errors.Is(err, redis.Nil) {
		return 0, 0, fmt.Errorf("redis get: %T", err)
	}
	return n, ttl.Val(), nil
}

// Delete removes a key.
func (r *Redis) Delete(ctx context.Context, key string) error {
	if err := r.client.Del(ctx, key).Err(); err != nil {
		return fmt.Errorf("redis del: %T", err)
	}
	return nil
}
