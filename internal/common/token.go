package common

import (
	"bytes"
	"compress/zlib"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha1" //nolint:gosec // itsdangerous wire format mandates HMAC-SHA1 with a SHA-1 derived key
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"time"
)

// Access-token contract shared with Python (common/security/tokens.py):
// itsdangerous URLSafeTimedSerializer layout, verified against
// test/fixtures/access_token_vectors.json.
const (
	// AccessTokenMaxAge is the 30-day lifetime (D-11).
	AccessTokenMaxAge = 30 * 24 * time.Hour

	maxTokenLength   = 1024
	maxInflatedBytes = 4096
	minInnerLength   = 32
	invalidPrefix    = "INVALID_"
)

var (
	// ErrBadToken marks a malformed token or payload.
	ErrBadToken = errors.New("bad token")
	// ErrBadSignature marks a signature mismatch.
	ErrBadSignature = errors.New("bad token signature")
	// ErrExpired marks a token older than the max age or dated in the future.
	ErrExpired = errors.New("token expired")
)

func tokenSignature(value, secret string) string {
	key := sha1.Sum([]byte("itsdangerous" + "signer" + secret)) //nolint:gosec
	mac := hmac.New(sha1.New, key[:])
	mac.Write([]byte(value))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

// DumpAccessToken signs inner with the given secret at the injected time.
func DumpAccessToken(inner, secret string, now time.Time) (string, error) {
	if secret == "" {
		return "", ErrBadToken
	}
	js, err := json.Marshal(inner)
	if err != nil {
		return "", err
	}
	var buf bytes.Buffer
	zw := zlib.NewWriter(&buf)
	if _, err := zw.Write(js); err != nil {
		return "", err
	}
	if err := zw.Close(); err != nil {
		return "", err
	}
	payload := base64.RawURLEncoding.EncodeToString(js)
	if buf.Len() < len(js)-1 {
		payload = "." + base64.RawURLEncoding.EncodeToString(buf.Bytes())
	}
	var ts [8]byte
	binary.BigEndian.PutUint64(ts[:], uint64(now.Unix()))
	i := 0
	for i < len(ts)-1 && ts[i] == 0 {
		i++
	}
	value := payload + "." + base64.RawURLEncoding.EncodeToString(ts[i:])
	return value + "." + tokenSignature(value, secret), nil
}

// VerifyAccessToken returns the inner string of a valid, unexpired token.
// Length is bounded before any HMAC; the signature is compared in constant time.
func VerifyAccessToken(token, secret string, maxAge time.Duration, now time.Time) (string, error) {
	if token == "" || len(token) > maxTokenLength || secret == "" {
		return "", ErrBadToken
	}
	i := strings.LastIndexByte(token, '.')
	if i < 0 {
		return "", ErrBadToken
	}
	value, sig := token[:i], token[i+1:]
	if !hmac.Equal([]byte(sig), []byte(tokenSignature(value, secret))) {
		return "", ErrBadSignature
	}
	j := strings.LastIndexByte(value, '.')
	if j < 0 {
		return "", ErrBadToken
	}
	payload, tsb64 := value[:j], value[j+1:]
	tsBytes, err := base64.RawURLEncoding.DecodeString(tsb64)
	if err != nil || len(tsBytes) == 0 || len(tsBytes) > 8 {
		return "", ErrBadToken
	}
	var padded [8]byte
	copy(padded[8-len(tsBytes):], tsBytes)
	ts := binary.BigEndian.Uint64(padded[:])
	if ts > uint64(1)<<62 {
		return "", ErrBadToken
	}
	age := now.Unix() - int64(ts)
	if age < 0 || time.Duration(age)*time.Second > maxAge {
		return "", ErrExpired
	}
	compressed := strings.HasPrefix(payload, ".")
	if compressed {
		payload = payload[1:]
	}
	raw, err := base64.RawURLEncoding.DecodeString(payload)
	if err != nil {
		return "", ErrBadToken
	}
	if compressed {
		zr, err := zlib.NewReader(bytes.NewReader(raw))
		if err != nil {
			return "", ErrBadToken
		}
		defer zr.Close()
		raw, err = io.ReadAll(io.LimitReader(zr, maxInflatedBytes+1))
		if err != nil || len(raw) > maxInflatedBytes {
			return "", ErrBadToken
		}
	}
	var inner string
	if err := json.Unmarshal(raw, &inner); err != nil {
		return "", ErrBadToken
	}
	return inner, nil
}

// ValidInner applies AUTH-08: trimmed non-empty, length >= 32, not INVALID_-prefixed.
func ValidInner(value string) bool {
	if strings.TrimSpace(value) == "" || len(value) < minInnerLength {
		return false
	}
	return !strings.HasPrefix(value, invalidPrefix)
}

// NewAccessTokenInner returns 32 lowercase hex characters shaped as a UUID4 without hyphens.
func NewAccessTokenInner() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return hex.EncodeToString(b[:]), nil
}
