package testutil

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWaitUntilReturnsWhenConditionHolds(t *testing.T) {
	var n atomic.Int32
	err := WaitUntil(context.Background(), 2*time.Second, time.Millisecond, func() bool { return n.Add(1) >= 3 })
	require.NoError(t, err)
	assert.GreaterOrEqual(t, n.Load(), int32(3))
}

func TestWaitUntilTimesOut(t *testing.T) {
	err := WaitUntil(context.Background(), 20*time.Millisecond, time.Millisecond, func() bool { return false })
	var to *ErrTimeout
	require.True(t, errors.As(err, &to))
	assert.Equal(t, 20*time.Millisecond, to.Timeout)
}

func TestWaitUntilHonoursCancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	assert.Error(t, WaitUntil(ctx, time.Minute, time.Millisecond, func() bool { return false }))
}
