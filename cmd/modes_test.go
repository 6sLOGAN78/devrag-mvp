package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

func runArgs(t *testing.T, args ...string) (int, string, bool) {
	t.Helper()
	var buf bytes.Buffer
	ran := false
	code := execute(args, func() error { ran = true; return nil }, &buf)
	return code, buf.String(), ran
}

func TestAPIRunsItsRunFunction(t *testing.T) {
	code, out, ran := runArgs(t, "--api")
	assert.Equal(t, 0, code, out)
	assert.True(t, ran)
}

func TestAPIRunErrorExitsOne(t *testing.T) {
	var buf bytes.Buffer
	code := execute([]string{"--api"}, func() error { return errors.New("boom") }, &buf)
	assert.Equal(t, 1, code)
	assert.Contains(t, buf.String(), "boom")
}

func TestUnbuiltModesRefuseWithPhaseAndBlocker(t *testing.T) {
	cases := map[string][]string{
		"--admin":    {"admin", "Phase 8", "B-07"},
		"--ingestor": {"ingestor", "v2", "D-01", "B-07"},
		"--syncer":   {"syncer", "v2", "D-01", "B-07"},
		"--migrate":  {"migrate", "plan 01-11"},
	}
	for flagName, needles := range cases {
		code, out, ran := runArgs(t, flagName)
		assert.Equal(t, 2, code, flagName)
		assert.False(t, ran, flagName)
		for _, n := range needles {
			assert.Contains(t, out, n, flagName)
		}
		assert.NotContains(t, strings.ToLower(out), "not "+"implemented", flagName)
	}
}

func TestNoFlagAndTwoFlagsAreUsageErrors(t *testing.T) {
	for _, args := range [][]string{{}, {"--api", "--admin"}, {"--bogus"}} {
		code, out, ran := runArgs(t, args...)
		assert.Equal(t, 2, code, args)
		assert.False(t, ran)
		assert.Contains(t, out, "usage:")
	}
}

func TestRunAPIFailsOnMissingConfig(t *testing.T) {
	t.Setenv("SERVICE_CONF", filepath.Join(t.TempDir(), "absent.yaml"))
	err := runAPI()
	assert.Error(t, err)
}

func TestRunAPIFailsWhenSecretMissing(t *testing.T) {
	p := filepath.Join(t.TempDir(), "c.yaml")
	assert.NoError(t, os.WriteFile(p, []byte("mysql:\n  name: a\n"), 0o600))
	t.Setenv("SERVICE_CONF", p)
	err := runAPI()
	assert.ErrorContains(t, err, "mysql.user")
}
