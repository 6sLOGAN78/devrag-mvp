package common

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type emailVector struct {
	ID        string `json:"id"`
	Input     string `json:"input"`
	Canonical string `json:"canonical"`
	NewOK     bool   `json:"new_ok"`
}

func loadEmailVectors(t *testing.T) []emailVector {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "test", "fixtures", "email_canonical_vectors.json"))
	require.NoError(t, err)
	var f struct {
		Canonical []emailVector `json:"canonical"`
	}
	require.NoError(t, json.Unmarshal(raw, &f))
	require.NotEmpty(t, f.Canonical)
	return f.Canonical
}

func TestCanonicalEmailSharedVectors(t *testing.T) {
	for _, v := range loadEmailVectors(t) {
		t.Run(v.ID, func(t *testing.T) {
			assert.Equal(t, v.Canonical, CanonicalEmail(v.Input))
			assert.Equal(t, v.Canonical, CanonicalEmail(CanonicalEmail(v.Input)), "canonicalisation is idempotent")
			if v.Canonical != "" {
				assert.Equal(t, v.NewOK, NewAccountEmailChars(v.Canonical))
			}
		})
	}
}
