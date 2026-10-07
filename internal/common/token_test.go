package common

import (
	"bytes"
	"compress/zlib"
	"crypto/hmac"
	"crypto/sha1" //nolint:gosec // itsdangerous wire format mandates HMAC-SHA1
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type tokenVector struct {
	ID         string `json:"id"`
	Token      string `json:"token"`
	Now        int64  `json:"now"`
	Expect     string `json:"expect"`
	Inner      string `json:"inner"`
	InnerValid *bool  `json:"inner_valid"`
}

type tokenVectorFile struct {
	Secret   string        `json:"secret"`
	Inner    string        `json:"inner"`
	MaxAge   int64         `json:"max_age"`
	SignedAt int64         `json:"signed_at"`
	Vectors  []tokenVector `json:"vectors"`
}

func fixturePath(name string) string {
	return filepath.Join("..", "..", "test", "fixtures", name)
}

func loadTokenVectors(t *testing.T) tokenVectorFile {
	t.Helper()
	raw, err := os.ReadFile(fixturePath("access_token_vectors.json"))
	require.NoError(t, err)
	var f tokenVectorFile
	require.NoError(t, json.Unmarshal(raw, &f))
	require.GreaterOrEqual(t, len(f.Vectors), 18)
	return f
}

func TestVerifyAccessTokenSharedVectors(t *testing.T) {
	f := loadTokenVectors(t)
	for _, v := range f.Vectors {
		t.Run(v.ID, func(t *testing.T) {
			got, err := VerifyAccessToken(v.Token, f.Secret, time.Duration(f.MaxAge)*time.Second, time.Unix(v.Now, 0))
			if v.Expect == "ok" {
				require.NoError(t, err)
				assert.Equal(t, v.Inner, got)
				require.NotNil(t, v.InnerValid)
				assert.Equal(t, *v.InnerValid, ValidInner(got))
				return
			}
			require.Error(t, err)
			assert.Empty(t, got)
		})
	}
}

func TestVerifyAccessTokenErrorKinds(t *testing.T) {
	f := loadTokenVectors(t)
	byID := map[string]tokenVector{}
	for _, v := range f.Vectors {
		byID[v.ID] = v
	}
	maxAge := time.Duration(f.MaxAge) * time.Second
	verify := func(id string) error {
		v := byID[id]
		_, err := VerifyAccessToken(v.Token, f.Secret, maxAge, time.Unix(v.Now, 0))
		return err
	}
	assert.ErrorIs(t, verify("expired_by_one_second"), ErrExpired)
	assert.ErrorIs(t, verify("future_timestamp"), ErrExpired)
	assert.ErrorIs(t, verify("tampered_payload"), ErrBadSignature)
	assert.ErrorIs(t, verify("tampered_signature"), ErrBadSignature)
	assert.ErrorIs(t, verify("wrong_secret"), ErrBadSignature)
	assert.ErrorIs(t, verify("empty"), ErrBadToken)
	assert.ErrorIs(t, verify("too_long"), ErrBadToken)
	assert.ErrorIs(t, verify("signed_bad_zlib"), ErrBadToken)
	assert.ErrorIs(t, verify("signed_non_string_payload_number"), ErrBadToken)
}

func TestVerifyAccessTokenEmptySecretRejected(t *testing.T) {
	f := loadTokenVectors(t)
	v := f.Vectors[0]
	_, err := VerifyAccessToken(v.Token, "", time.Hour, time.Unix(v.Now, 0))
	assert.Error(t, err)
}

func independentSignature(value, secret string) string {
	k := sha1.Sum([]byte("itsdangerous" + "signer" + secret)) //nolint:gosec
	m := hmac.New(sha1.New, k[:])
	m.Write([]byte(value))
	return base64.RawURLEncoding.EncodeToString(m.Sum(nil))
}

func TestDumpAccessTokenStructureAndRoundTrip(t *testing.T) {
	f := loadTokenVectors(t)
	now := time.Unix(f.SignedAt, 0)
	tok, err := DumpAccessToken(f.Inner, f.Secret, now)
	require.NoError(t, err)

	i := strings.LastIndexByte(tok, '.')
	value, sig := tok[:i], tok[i+1:]
	assert.Len(t, sig, 27)
	assert.Equal(t, independentSignature(value, f.Secret), sig)

	j := strings.LastIndexByte(value, '.')
	payload, tsb64 := value[:j], value[j+1:]
	tsBytes, err := base64.RawURLEncoding.DecodeString(tsb64)
	require.NoError(t, err)
	require.NotEmpty(t, tsBytes)
	assert.NotEqual(t, byte(0), tsBytes[0], "timestamp must be minimal length")
	var padded [8]byte
	copy(padded[8-len(tsBytes):], tsBytes)
	assert.Equal(t, uint64(f.SignedAt), binary.BigEndian.Uint64(padded[:]))

	require.True(t, strings.HasPrefix(payload, "."), "UUID payloads are always compressed")
	raw, err := base64.RawURLEncoding.DecodeString(payload[1:])
	require.NoError(t, err)
	zr, err := zlib.NewReader(bytes.NewReader(raw))
	require.NoError(t, err)
	js, err := io.ReadAll(zr)
	require.NoError(t, err)
	assert.Equal(t, `"`+f.Inner+`"`, string(js))

	got, err := VerifyAccessToken(tok, f.Secret, 30*24*time.Hour, now.Add(time.Minute))
	require.NoError(t, err)
	assert.Equal(t, f.Inner, got)
	_, err = VerifyAccessToken(tok, f.Secret, 30*24*time.Hour, now.Add(30*24*time.Hour+time.Second))
	assert.ErrorIs(t, err, ErrExpired)
}

func TestDumpAccessTokenUncompressedWhenShorter(t *testing.T) {
	now := time.Unix(1700000000, 0)
	tok, err := DumpAccessToken("a", "test-secret-key-0123456789abcdef0123456789abcdef", now)
	require.NoError(t, err)
	assert.False(t, strings.HasPrefix(tok, "."))
	got, err := VerifyAccessToken(tok, "test-secret-key-0123456789abcdef0123456789abcdef", time.Hour, now)
	require.NoError(t, err)
	assert.Equal(t, "a", got)
}

func TestValidInner(t *testing.T) {
	cases := map[string]bool{
		strings.Repeat("0", 32):               true,
		strings.Repeat("f", 40):               true,
		strings.Repeat("0", 31):               false,
		"   ":                                 false,
		"":                                    false,
		"INVALID_" + strings.Repeat("a", 30):  false,
		"  " + strings.Repeat("a", 34) + "  ": true,
	}
	for in, want := range cases {
		assert.Equal(t, want, ValidInner(in), "%q", in)
	}
}

func TestNewAccessTokenInner(t *testing.T) {
	re := regexp.MustCompile(`^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$`)
	seen := map[string]bool{}
	for i := 0; i < 50; i++ {
		s, err := NewAccessTokenInner()
		require.NoError(t, err)
		assert.Regexp(t, re, s)
		assert.True(t, ValidInner(s))
		assert.False(t, seen[s])
		seen[s] = true
	}
}

func TestGoIssuedTokenFixture(t *testing.T) {
	path := fixturePath("go_issued_token.json")
	secret := "test-secret-key-0123456789abcdef0123456789abcdef"
	if os.Getenv("GO_ISSUED_TOKEN_WRITE") == "1" {
		inner, err := NewAccessTokenInner()
		require.NoError(t, err)
		issued := int64(1760000000)
		tok, err := DumpAccessToken(inner, secret, time.Unix(issued, 0))
		require.NoError(t, err)
		out, err := json.MarshalIndent(map[string]any{
			"generated_by": "GO_ISSUED_TOKEN_WRITE=1 go test ./internal/common -run TestGoIssuedTokenFixture (DumpAccessToken)",
			"token":        tok,
			"secret":       secret,
			"inner":        inner,
			"issued_at":    issued,
			"max_age":      2592000,
		}, "", "  ")
		require.NoError(t, err)
		require.NoError(t, os.WriteFile(path, append(out, '\n'), 0o644))
	}
	raw, err := os.ReadFile(path)
	require.NoError(t, err)
	var fx struct {
		GeneratedBy string `json:"generated_by"`
		Token       string `json:"token"`
		Secret      string `json:"secret"`
		Inner       string `json:"inner"`
		IssuedAt    int64  `json:"issued_at"`
		MaxAge      int64  `json:"max_age"`
	}
	require.NoError(t, json.Unmarshal(raw, &fx))
	assert.NotEmpty(t, fx.GeneratedBy)
	got, err := VerifyAccessToken(fx.Token, fx.Secret, time.Duration(fx.MaxAge)*time.Second, time.Unix(fx.IssuedAt+5, 0))
	require.NoError(t, err)
	assert.Equal(t, fx.Inner, got)
}
