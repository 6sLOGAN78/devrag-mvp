//go:build integration

package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/dao"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

func liveLimiter(t *testing.T) (*Limiter, *dao.Redis) {
	t.Helper()
	cfg := testutil.RequireRedis(t)
	rd := dao.OpenRedis(cfg.Redis)
	t.Cleanup(func() { _ = rd.Close() })
	return NewLimiter(rd, "test-"+testutil.UniqueName("rl")), rd
}

func TestLimiterLocksOutWithRetryAfter(t *testing.T) {
	l, _ := liveLimiter(t)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		require.NoError(t, l.Hit(ctx, "k", 3, time.Minute), "attempt %d is within the limit", i+1)
	}
	err := l.Hit(ctx, "k", 3, time.Minute)
	var rl *RateLimitedError
	require.ErrorAs(t, err, &rl)
	assert.Greater(t, rl.RetryAfter, time.Duration(0))
	assert.LessOrEqual(t, rl.RetryAfter, time.Minute)
	require.NoError(t, l.Hit(ctx, "other", 3, time.Minute), "a different key is unaffected")
}

func TestLimiterWindowExpires(t *testing.T) {
	l, _ := liveLimiter(t)
	ctx := context.Background()
	require.NoError(t, l.Hit(ctx, "k", 1, time.Second))
	require.Error(t, l.Hit(ctx, "k", 1, time.Second))
	err := testutil.WaitUntil(ctx, 10*time.Second, 100*time.Millisecond, func() bool {
		return l.Hit(ctx, "k", 1, time.Second) == nil
	})
	require.NoError(t, err, "counter must expire with its window")
}

func TestLimiterCounterAlwaysHasTTL(t *testing.T) {
	l, rd := liveLimiter(t)
	ctx := context.Background()
	require.NoError(t, l.Hit(ctx, "ttl", 5, 90*time.Second))
	count, ttl, err := rd.Count(ctx, l.key("ttl"))
	require.NoError(t, err)
	assert.EqualValues(t, 1, count)
	assert.Greater(t, ttl, time.Duration(0), "a counter without a TTL would lock out forever")
}

func TestLimiterFailureCountingAndReset(t *testing.T) {
	l, _ := liveLimiter(t)
	ctx := context.Background()
	for i := 0; i < 2; i++ {
		require.NoError(t, l.Check(ctx, "f", 2))
		require.NoError(t, l.Fail(ctx, "f", time.Minute))
	}
	var rl *RateLimitedError
	require.ErrorAs(t, l.Check(ctx, "f", 2), &rl, "two recorded failures lock a limit of two")
	require.NoError(t, l.Reset(ctx, "f"))
	require.NoError(t, l.Check(ctx, "f", 2))
}

func TestLimiterFailsClosedWhenRedisIsDown(t *testing.T) {
	cfg := testutil.RequireRedis(t)
	bad := cfg.Redis
	bad.Port = 1 // nothing listens here
	rd := dao.OpenRedis(bad)
	defer func() { _ = rd.Close() }()
	l := NewLimiter(rd, "test-down")
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	assert.ErrorIs(t, l.Hit(ctx, "k", 100, time.Minute), ErrUnavailable)
	assert.ErrorIs(t, l.Check(ctx, "k", 100), ErrUnavailable)
	assert.ErrorIs(t, l.Fail(ctx, "k", time.Minute), ErrUnavailable)
	var rl *RateLimitedError
	assert.False(t, errors.As(l.Hit(ctx, "k", 100, time.Minute), &rl), "an outage is not reported as a lockout")
}

func TestRateLimitConfigFeedsLimiter(t *testing.T) {
	// The limits are configuration, not constants: the defaults are the R-94 numbers.
	d := server.DefaultRateLimit()
	assert.Equal(t, 5, d.LoginFailuresPerEmail)
	assert.Equal(t, 30, d.LoginPerIP)
	assert.Equal(t, 10, d.RegisterPerIP)
}
