package common

import (
	"encoding/json"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type passwordVector struct {
	ID       string `json:"id"`
	Password string `json:"password"`
	Hash     string `json:"hash"`
}

func loadPasswordVectors(t *testing.T) (pos, neg []passwordVector) {
	t.Helper()
	raw, err := os.ReadFile(fixturePath("password_vectors.json"))
	require.NoError(t, err)
	var f struct {
		Positive []passwordVector `json:"positive"`
		Negative []passwordVector `json:"negative"`
	}
	require.NoError(t, json.Unmarshal(raw, &f))
	require.NotEmpty(t, f.Positive)
	require.NotEmpty(t, f.Negative)
	return f.Positive, f.Negative
}

func TestVerifyPasswordSharedVectors(t *testing.T) {
	pos, neg := loadPasswordVectors(t)
	for _, v := range pos {
		t.Run("positive_"+v.ID, func(t *testing.T) {
			assert.True(t, VerifyPassword(v.Password, v.Hash))
		})
	}
	for _, v := range neg {
		t.Run("negative_"+v.ID, func(t *testing.T) {
			assert.False(t, VerifyPassword(v.Password, v.Hash))
		})
	}
}

func TestHashPasswordFormatAndRoundTrip(t *testing.T) {
	h, err := HashPassword("pw12345678")
	require.NoError(t, err)
	parts := strings.Split(h, "$")
	require.Len(t, parts, 3)
	assert.Equal(t, "pbkdf2:sha256:600000", parts[0])
	assert.Regexp(t, `^[A-Za-z0-9]{16}$`, parts[1])
	assert.Regexp(t, `^[0-9a-f]{64}$`, parts[2])
	assert.True(t, VerifyPassword("pw12345678", h))
	assert.False(t, VerifyPassword("pw12345679", h))
	h2, err := HashPassword("pw12345678")
	require.NoError(t, err)
	assert.NotEqual(t, h, h2)
}

func TestVerifyPasswordConcurrent(t *testing.T) {
	pos, _ := loadPasswordVectors(t)
	var wg sync.WaitGroup
	for i := 0; i < 6; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			assert.True(t, VerifyPassword(pos[0].Password, pos[0].Hash))
		}()
	}
	wg.Wait()
}

func TestValidatePasswordLength(t *testing.T) {
	assert.Error(t, ValidatePasswordLength(strings.Repeat("a", 7)))
	assert.NoError(t, ValidatePasswordLength(strings.Repeat("a", 8)))
	assert.NoError(t, ValidatePasswordLength(strings.Repeat("a", 128)))
	assert.Error(t, ValidatePasswordLength(strings.Repeat("a", 129)))
	assert.NoError(t, ValidatePasswordLength(strings.Repeat("密", 128)), "length counts characters")
}

func TestHashPasswordRejectsOverlong(t *testing.T) {
	_, err := HashPassword(strings.Repeat("a", 129))
	assert.Error(t, err)
}
