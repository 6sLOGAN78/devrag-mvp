package service

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// Counter is the Redis surface the limiter needs. dao.Redis satisfies it.
type Counter interface {
	Incr(ctx context.Context, key string, window time.Duration) (int64, time.Duration, error)
	Count(ctx context.Context, key string) (int64, time.Duration, error)
	Delete(ctx context.Context, key string) error
}

// RateLimitedError reports a limit that is currently exceeded.
type RateLimitedError struct {
	RetryAfter time.Duration
}

func (e *RateLimitedError) Error() string { return "too many requests" }

// Limiter is a Redis fixed-window limiter. It fails closed: when the counter store cannot be
// reached every call returns ErrUnavailable and the caller must refuse the request (D-29).
// Windows and maxima are passed by the caller from the RateLimit configuration.
type Limiter struct {
	c      Counter
	prefix string
}

// NewLimiter builds a limiter whose keys all start with prefix.
func NewLimiter(c Counter, prefix string) *Limiter { return &Limiter{c: c, prefix: prefix} }

func (l *Limiter) key(k string) string { return l.prefix + ":" + k }

func unavailable(err error) error { return fmt.Errorf("%w: rate limiter: %v", ErrUnavailable, err) }

func retryAfter(ttl, window time.Duration) time.Duration {
	if ttl <= 0 {
		return window
	}
	return ttl
}

// Hit counts one attempt and returns *RateLimitedError once the count exceeds max within window.
func (l *Limiter) Hit(ctx context.Context, key string, max int, window time.Duration) error {
	n, ttl, err := l.c.Incr(ctx, l.key(key), window)
	if err != nil {
		return unavailable(err)
	}
	if n > int64(max) {
		return &RateLimitedError{RetryAfter: retryAfter(ttl, window)}
	}
	return nil
}

// Check returns *RateLimitedError when max failures have already been recorded under key.
func (l *Limiter) Check(ctx context.Context, key string, max int) error {
	n, ttl, err := l.c.Count(ctx, l.key(key))
	if err != nil {
		return unavailable(err)
	}
	if n >= int64(max) {
		return &RateLimitedError{RetryAfter: retryAfter(ttl, 0)}
	}
	return nil
}

// Fail records one failure under key for window.
func (l *Limiter) Fail(ctx context.Context, key string, window time.Duration) error {
	if _, _, err := l.c.Incr(ctx, l.key(key), window); err != nil {
		return unavailable(err)
	}
	return nil
}

// Reset clears the counter under key.
func (l *Limiter) Reset(ctx context.Context, key string) error {
	if err := l.c.Delete(ctx, l.key(key)); err != nil {
		return unavailable(err)
	}
	return nil
}

// IsRateLimited reports whether err is a lockout and returns it.
func IsRateLimited(err error) (*RateLimitedError, bool) {
	var rl *RateLimitedError
	if errors.As(err, &rl) {
		return rl, true
	}
	return nil, false
}
