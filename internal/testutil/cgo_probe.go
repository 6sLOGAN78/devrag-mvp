//go:build cgo

package testutil

/*
static int add(int a, int b) { return a + b; }
*/
import "C"

// CAdd calls a trivial C function. It only proves the cgo build tier works on this host (B-11);
// no production code depends on it.
func CAdd(a, b int) int {
	return int(C.add(C.int(a), C.int(b)))
}
