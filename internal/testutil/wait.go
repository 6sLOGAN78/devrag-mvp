// Package testutil holds helpers shared by Go tests. WaitUntil is the only polling site
// permitted in Go tests (D-30); it mirrors test/helpers/wait.py.
package testutil

import (
	"context"
	"fmt"
	"time"
)

// ErrTimeout is wrapped by the error WaitUntil returns when the condition never held.
type ErrTimeout struct {
	Timeout time.Duration
}

func (e *ErrTimeout) Error() string {
	return fmt.Sprintf("condition not met within %s", e.Timeout)
}

// WaitUntil polls fn every interval until it returns true, the timeout elapses or ctx is done.
// fn is evaluated once immediately.
func WaitUntil(ctx context.Context, timeout, interval time.Duration, fn func() bool) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if fn() {
			return nil
		}
		select {
		case <-ctx.Done():
			if fn() {
				return nil
			}
			return &ErrTimeout{Timeout: timeout}
		case <-ticker.C:
		}
	}
}
