package service

import (
	"context"
	"errors"
	"time"
)

// ErrOTPInvalid is the single failure for a wrong, expired, used or destroyed code.
var ErrOTPInvalid = errors.New("code is incorrect or has expired")

// ErrTicketInvalid is the single failure for an unknown, expired, used or foreign reset ticket.
var ErrTicketInvalid = errors.New("reset session is invalid or has expired")

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

// OTP issues and checks one-time codes and reset tickets.
type OTP struct{}

// NewOTP wires the store. Keys start with prefix; secret keys the code hash.
func NewOTP(be OTPBackend, prefix, secret string, ttl time.Duration) *OTP { return &OTP{} }

// Issue creates a code for email owned by userID ("" for a decoy) and replaces any earlier one.
func (o *OTP) Issue(ctx context.Context, email, userID string) (string, error) {
	return "", errNotImplemented
}

// Verify checks and consumes a code, returning its owner.
func (o *OTP) Verify(ctx context.Context, email, code string) (string, error) {
	return "", errNotImplemented
}

// IssueTicket creates the single-use ticket proving a verified code.
func (o *OTP) IssueTicket(ctx context.Context, email, userID string, ttl time.Duration) (string, error) {
	return "", errNotImplemented
}

// ConsumeTicket uses a ticket once and returns its owner.
func (o *OTP) ConsumeTicket(ctx context.Context, email, ticket string) (string, error) {
	return "", errNotImplemented
}

// Revoke removes the code of email and every ticket of userID.
func (o *OTP) Revoke(ctx context.Context, email, userID string) error { return errNotImplemented }

func generateCode() (string, error) { return "", errNotImplemented }
