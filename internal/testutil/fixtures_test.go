package testutil

import (
	"errors"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestUniqueEmailIsUniqueAndLowercase(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 1000; i++ {
		e := UniqueEmail("Alice")
		require.False(t, seen[e], "duplicate %s", e)
		seen[e] = true
		assert.Equal(t, strings.ToLower(e), e)
		assert.True(t, strings.HasPrefix(e, "alice-"))
		assert.True(t, strings.HasSuffix(e, "@example.test"))
	}
}

func TestUniqueNameIsUnique(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 1000; i++ {
		n := UniqueName("kb")
		require.False(t, seen[n])
		seen[n] = true
	}
}

func TestConfErrorNamesTheVariable(t *testing.T) {
	_, err := confError(func(string) string { return "" }, func(string) error { return nil }, "RequireDB")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "SERVICE_CONF")

	_, err = confError(func(string) string { return "/x/y.yaml" }, func(string) error { return errors.New("nope") }, "RequireRedis")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "SERVICE_CONF")

	p, err := confError(func(string) string { return "/x/y.yaml" }, func(string) error { return nil }, "RequireDB")
	require.NoError(t, err)
	assert.Equal(t, "/x/y.yaml", p)
}
