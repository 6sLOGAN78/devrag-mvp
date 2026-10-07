package common

import (
	"crypto/pbkdf2"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"runtime"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Password hashing contract shared with Python (common/security/passwords.py):
// werkzeug format pbkdf2:sha256:<iterations>$<salt>$<hex>, salt used as UTF-8 bytes.
const (
	passwordIterations = 600_000
	minIterations      = 100_000
	maxIterations      = 10_000_000
	saltLength         = 16
	keyLength          = 32
	// MinPasswordLength and MaxPasswordLength bound user passwords (D-02, D-29).
	MinPasswordLength = 8
	MaxPasswordLength = 128
	saltAlphabet      = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

// hashSlots bounds concurrent PBKDF2 work so logins cannot exhaust the CPU.
var hashSlots = make(chan struct{}, max(1, runtime.NumCPU()))

// ValidatePasswordLength enforces 8 to 128 characters.
func ValidatePasswordLength(password string) error {
	n := utf8.RuneCountInString(password)
	if n < MinPasswordLength || n > MaxPasswordLength {
		return fmt.Errorf("password must be %d to %d characters", MinPasswordLength, MaxPasswordLength)
	}
	return nil
}

func derive(password, salt string, iterations int) (string, error) {
	hashSlots <- struct{}{}
	defer func() { <-hashSlots }()
	k, err := pbkdf2.Key(sha256.New, password, []byte(salt), iterations, keyLength)
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(k), nil
}

// HashPassword returns a pbkdf2:sha256:600000 hash with a random 16-character salt.
func HashPassword(password string) (string, error) {
	if utf8.RuneCountInString(password) > MaxPasswordLength {
		return "", errors.New("password too long")
	}
	salt := make([]byte, saltLength)
	limit := big.NewInt(int64(len(saltAlphabet)))
	for i := range salt {
		n, err := rand.Int(rand.Reader, limit)
		if err != nil {
			return "", err
		}
		salt[i] = saltAlphabet[n.Int64()]
	}
	digest, err := derive(password, string(salt), passwordIterations)
	if err != nil {
		return "", err
	}
	return "pbkdf2:sha256:" + strconv.Itoa(passwordIterations) + "$" + string(salt) + "$" + digest, nil
}

func isASCIIAlnum(s string) bool {
	if s == "" || len(s) > 64 {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z') {
			return false
		}
	}
	return true
}

// VerifyPassword fails closed for any scheme other than pbkdf2:sha256 within the iteration bounds.
func VerifyPassword(password, stored string) bool {
	if password == "" || utf8.RuneCountInString(password) > MaxPasswordLength*4 {
		return false
	}
	parts := strings.Split(stored, "$")
	if len(parts) != 3 {
		return false
	}
	method := strings.Split(parts[0], ":")
	if len(method) != 3 || method[0] != "pbkdf2" || method[1] != "sha256" {
		return false
	}
	iterations, err := strconv.Atoi(method[2])
	if err != nil || iterations < minIterations || iterations > maxIterations {
		return false
	}
	if !isASCIIAlnum(parts[1]) || len(parts[2]) != keyLength*2 {
		return false
	}
	digest, err := derive(password, parts[1], iterations)
	if err != nil {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(digest), []byte(parts[2])) == 1
}
