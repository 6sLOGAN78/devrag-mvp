package service

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"devrag/internal/common"
)

const (
	otpDigits      = 6
	otpMaxAttempts = 5
	ticketBytes    = 32
	// ticketLength is the length of a base64url (unpadded) ticket of ticketBytes random bytes.
	ticketLength = 43
	otpKeyLabel  = "devrag/otp/v1"
)

// ErrOTPInvalid is the single failure for a wrong, expired, used or destroyed code.
var ErrOTPInvalid = errors.New("That code is incorrect or has expired.")

// ErrTicketInvalid is the single failure for an unknown, expired, used or foreign reset ticket.
var ErrTicketInvalid = errors.New("This reset session is invalid or has expired. Request a new code.")

// OTPBackend is the Redis surface of the code store. dao.Redis satisfies it.
type OTPBackend interface {
	OTPIssue(ctx context.Context, key, value, owner string, ttl time.Duration) error
	OTPAttempt(ctx context.Context, key string, max int) (value, owner string, attempt int64, found bool, err error)
	OTPCompareDelete(ctx context.Context, key, value string) (bool, error)
	SetEX(ctx context.Context, key, value string, ttl time.Duration) error
	Get(ctx context.Context, key string) (string, bool, error)
	GetDel(ctx context.Context, key string) (string, bool, error)
	Delete(ctx context.Context, key string) error
}

// OTP issues and checks one-time codes and reset tickets. Codes are stored only as a salted HMAC
// keyed with a server secret; tickets only as a SHA-256 digest. Every key carries a TTL.
type OTP struct {
	be     OTPBackend
	prefix string
	ttl    time.Duration
	key    []byte
}

// NewOTP wires the store. Keys start with prefix; secret keys the code hash and never leaves memory.
func NewOTP(be OTPBackend, prefix, secret string, ttl time.Duration) *OTP {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(otpKeyLabel))
	return &OTP{be: be, prefix: prefix, ttl: ttl, key: mac.Sum(nil)}
}

func storeFailure(what string, err error) error {
	return fmt.Errorf("%w: %s: %v", ErrUnavailable, what, err)
}

// generateCode returns a uniformly random six-digit code (000000 to 999999) from crypto/rand.
func generateCode() (string, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(1_000_000))
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%0*d", otpDigits, n.Int64()), nil
}

func validCodeShape(code string) bool {
	if len(code) != otpDigits {
		return false
	}
	for i := 0; i < len(code); i++ {
		if code[i] < '0' || code[i] > '9' {
			return false
		}
	}
	return true
}

func (o *OTP) otpKey(emailDigest string) string { return o.prefix + ":otp:" + emailDigest }
func (o *OTP) ticketKey(digest string) string   { return o.prefix + ":otp_ticket:" + digest }
func (o *OTP) ticketUserKey(subject string) string {
	return o.prefix + ":otp_ticket_user:" + subject
}

// mac binds the hash to the salt and to the email it was issued for.
func (o *OTP) mac(salt, emailDigest, code string) []byte {
	m := hmac.New(sha256.New, o.key)
	m.Write([]byte(salt))
	m.Write([]byte{0})
	m.Write([]byte(emailDigest))
	m.Write([]byte{0})
	m.Write([]byte(code))
	return m.Sum(nil)
}

// Issue creates a code for subject (the account identity from accountSubject, never a typed address), owned by userID ("" for a decoy that no one can read), and
// replaces any earlier code and its attempt count atomically. It returns the plain code so the
// caller can mail it; the code is never stored.
func (o *OTP) Issue(ctx context.Context, subject, userID string) (string, error) {
	digest := emailKey(common.CanonicalEmail(subject))
	code, err := generateCode()
	if err != nil {
		return "", err
	}
	salt, err := randomHex(16)
	if err != nil {
		return "", err
	}
	value := salt + ":" + hex.EncodeToString(o.mac(salt, digest, code))
	if err := o.be.OTPIssue(ctx, o.otpKey(digest), value, userID, o.ttl); err != nil {
		return "", storeFailure("code store", err)
	}
	return code, nil
}

// Verify checks a code and consumes it. The attempt is counted before anything is compared, so
// parallel guesses cannot exceed the cap; the fifth wrong attempt destroys the code; a correct
// code can be used by exactly one caller.
func (o *OTP) Verify(ctx context.Context, subject, code string) (string, error) {
	if !validCodeShape(code) {
		return "", ErrOTPInvalid
	}
	digest := emailKey(common.CanonicalEmail(subject))
	key := o.otpKey(digest)
	value, owner, attempt, found, err := o.be.OTPAttempt(ctx, key, otpMaxAttempts)
	if err != nil {
		return "", storeFailure("code store", err)
	}
	if !found {
		return "", ErrOTPInvalid
	}
	salt, stored, ok := strings.Cut(value, ":")
	storedMAC, decErr := hex.DecodeString(stored)
	if !ok || decErr != nil {
		return "", ErrOTPInvalid
	}
	if !hmac.Equal(storedMAC, o.mac(salt, digest, code)) {
		if attempt >= otpMaxAttempts {
			if _, err := o.be.OTPCompareDelete(ctx, key, value); err != nil {
				return "", storeFailure("code store", err)
			}
		}
		return "", ErrOTPInvalid
	}
	won, err := o.be.OTPCompareDelete(ctx, key, value)
	if err != nil {
		return "", storeFailure("code store", err)
	}
	if !won {
		return "", ErrOTPInvalid
	}
	return owner, nil
}

func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

// ticketSubject identifies who a ticket belongs to for replacement: the user, or the email for a decoy.
func ticketSubject(userID, emailDigest string) string {
	if userID != "" {
		return userID
	}
	return "email:" + emailDigest
}

// IssueTicket creates the random, single-use, short-lived ticket that proves a verified code. It is
// stored under its SHA-256 digest, bound to the owner and the email, and replaces the owner's earlier ticket.
func (o *OTP) IssueTicket(ctx context.Context, subject, userID string, ttl time.Duration) (string, error) {
	digest := emailKey(common.CanonicalEmail(subject))
	raw := make([]byte, ticketBytes)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	ticket := base64.RawURLEncoding.EncodeToString(raw)
	th := sha256Hex(ticket)
	userKey := o.ticketUserKey(ticketSubject(userID, digest))
	if old, found, err := o.be.Get(ctx, userKey); err != nil {
		return "", storeFailure("ticket store", err)
	} else if found {
		if err := o.be.Delete(ctx, o.ticketKey(old)); err != nil {
			return "", storeFailure("ticket store", err)
		}
	}
	if err := o.be.SetEX(ctx, o.ticketKey(th), userID+"|"+digest, ttl); err != nil {
		return "", storeFailure("ticket store", err)
	}
	if err := o.be.SetEX(ctx, userKey, th, ttl); err != nil {
		return "", storeFailure("ticket store", err)
	}
	return ticket, nil
}

func validTicketShape(t string) bool {
	if len(t) != ticketLength {
		return false
	}
	for i := 0; i < len(t); i++ {
		c := t[i]
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '-' || c == '_') {
			return false
		}
	}
	return true
}

// ConsumeTicket uses a ticket once and returns its owner ("" for a decoy). The ticket is removed
// before it is compared with the email, so a mismatched use burns it.
func (o *OTP) ConsumeTicket(ctx context.Context, subject, ticket string) (string, error) {
	if !validTicketShape(ticket) {
		return "", ErrTicketInvalid
	}
	digest := emailKey(common.CanonicalEmail(subject))
	th := sha256Hex(ticket)
	value, found, err := o.be.GetDel(ctx, o.ticketKey(th))
	if err != nil {
		return "", storeFailure("ticket store", err)
	}
	if !found {
		return "", ErrTicketInvalid
	}
	owner, boundDigest, ok := strings.Cut(value, "|")
	if !ok {
		return "", ErrTicketInvalid
	}
	userKey := o.ticketUserKey(ticketSubject(owner, boundDigest))
	if cur, ok, err := o.be.Get(ctx, userKey); err == nil && ok && cur == th {
		_ = o.be.Delete(ctx, userKey)
	}
	if subtle.ConstantTimeCompare([]byte(boundDigest), []byte(digest)) != 1 {
		return "", ErrTicketInvalid
	}
	return owner, nil
}

// Revoke removes the code of subject and every ticket of userID.
func (o *OTP) Revoke(ctx context.Context, subject, userID string) error {
	digest := emailKey(common.CanonicalEmail(subject))
	if err := o.be.Delete(ctx, o.otpKey(digest)); err != nil {
		return storeFailure("code store", err)
	}
	userKey := o.ticketUserKey(ticketSubject(userID, digest))
	th, found, err := o.be.Get(ctx, userKey)
	if err != nil {
		return storeFailure("ticket store", err)
	}
	if found {
		if err := o.be.Delete(ctx, o.ticketKey(th)); err != nil {
			return storeFailure("ticket store", err)
		}
	}
	if err := o.be.Delete(ctx, userKey); err != nil {
		return storeFailure("ticket store", err)
	}
	return nil
}
