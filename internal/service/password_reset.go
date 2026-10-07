package service

import (
	"context"
	"time"

	"devrag/internal/entity"
	"devrag/internal/server"
)

// ResetStore is the persistence surface of password reset. dao.DB satisfies it.
type ResetStore interface {
	FindUserByEmail(ctx context.Context, email string) (*entity.User, error)
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	SetPassword(ctx context.Context, userID, newHash, token string) (bool, error)
}

// ResetInput is a reset request: the ticket from verify (or the code itself) plus the new password.
type ResetInput struct{ Email, Ticket, Code, NewPassword string }

// PasswordReset implements the forgot-password flow.
type PasswordReset struct{}

// NewPasswordReset wires the service.
func NewPasswordReset(store ResetStore, limiter *Limiter, otp *OTP, mail MailQueue, cfg server.Config) *PasswordReset {
	return &PasswordReset{}
}

// RequestReset applies the limits and sends a code to an existing account.
func (p *PasswordReset) RequestReset(ctx context.Context, email, clientIP string) error {
	return errNotImplemented
}

// VerifyCode checks a code and returns a reset ticket.
func (p *PasswordReset) VerifyCode(ctx context.Context, email, code string) (string, error) {
	return "", errNotImplemented
}

// ResetPassword sets a new password for a verified grant.
func (p *PasswordReset) ResetPassword(ctx context.Context, in ResetInput) error {
	return errNotImplemented
}

var _ = time.Second
