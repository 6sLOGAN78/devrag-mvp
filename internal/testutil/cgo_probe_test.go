//go:build cgo

package testutil

import "testing"

func TestCgoMechanism(t *testing.T) {
	if got := CAdd(2, 40); got != 42 {
		t.Fatalf("CAdd(2, 40) = %d, want 42", got)
	}
}
