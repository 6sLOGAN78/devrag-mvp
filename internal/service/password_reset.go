package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

// resetTicketTTL is how long a verified code can be exchanged for a new password.
const resetTicketTTL = 5 * time.Minute

// ResetStore is the persistence surface of password reset. dao.DB satisfies it.
type ResetStore interface {
	FindUserByEmail(ctx context.Context, email string) (*entity.User, error)
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	SetPassword(ctx context.Context, userID, newHash, token string) (bool, error)
}

// ResetInput is a reset request: the ticket from verify (or the code itself, as in the endpoint
// catalogue) plus the new password.
type ResetInput struct{ Email, Ticket, Code, NewPassword string }

// PasswordReset implements the forgot-password flow (D-05 to D-08).
type PasswordReset struct {
	store     ResetStore
	limiter   *Limiter
	otp       *OTP
	mail      MailQueue
	cfg       server.Config
	ticketTTL time.Duration
}

// NewPasswordReset wires the service.
func NewPasswordReset(store ResetStore, limiter *Limiter, otp *OTP, mail MailQueue, cfg server.Config) *PasswordReset {
	return &PasswordReset{store: store, limiter: limiter, otp: otp, mail: mail, cfg: cfg, ticketTTL: resetTicketTTL}
}

func dbFailure(what string, err error) error {
	return fmt.Errorf("%w: %s: %T", ErrUnavailable, what, err)
}

// RequestReset applies the per-IP and per-email limits, then issues a code. For an existing active
// account the code is mailed (asynchronously, to the stored address only). For an unknown or
// inactive account the same limits are consumed and a decoy record is stored, so the work, the
// Redis state and the return value do not depend on whether the account exists (D-07).
func (p *PasswordReset) RequestReset(ctx context.Context, email, clientIP string) error {
	rl := p.cfg.RateLimit
	win := window(rl.OTPWindowSeconds)
	if err := p.limiter.Hit(ctx, "otp:ip:"+ipKey(clientIP), rl.OTPPerIPPerHour, win); err != nil {
		return err
	}
	email = normaliseEmail(email)
	if !validEmail(email) {
		return &ValidationError{Msg: "email is not valid"}
	}
	ek := emailKey(email)
	if err := p.limiter.Hit(ctx, "otp:email:interval:"+ek, 1, window(rl.OTPEmailIntervalSeconds)); err != nil {
		return err
	}
	if err := p.limiter.Hit(ctx, "otp:email:hour:"+ek, rl.OTPPerEmailPerHour, win); err != nil {
		return err
	}
	user, err := p.store.FindUserByEmail(ctx, email)
	if err != nil && !errors.Is(err, dao.ErrNotFound) {
		return dbFailure("user lookup", err)
	}
	active := err == nil && user.Status != nil && *user.Status == "1"
	owner := ""
	if active {
		owner = user.ID
	}
	code, err := p.otp.Issue(ctx, email, owner)
	if err != nil {
		return err
	}
	if active {
		p.mail.Enqueue(ResetCodeMail(user.Email, code, p.cfg.Auth.OTPTTL))
	}
	return nil
}

// VerifyCode checks and consumes a code and returns the reset ticket for it. A wrong, expired,
// used or destroyed code, and a code of an unknown email, all fail the same way.
func (p *PasswordReset) VerifyCode(ctx context.Context, email, code string) (string, error) {
	email = normaliseEmail(email)
	owner, err := p.otp.Verify(ctx, email, code)
	if err != nil {
		return "", err
	}
	return p.otp.IssueTicket(ctx, email, owner, p.ticketTTL)
}

// ResetPassword sets a new password for a verified grant: a ticket from VerifyCode, or the code
// itself. The grant is bound to the email it was issued for and to the user that owned it. The
// new hash and the INVALID_<hex> access token are written in one transaction (D-08), then every
// outstanding code and ticket of the user is removed. A decoy grant gets the same success and
// changes nothing.
func (p *PasswordReset) ResetPassword(ctx context.Context, in ResetInput) error {
	if err := common.ValidatePasswordLength(in.NewPassword); err != nil {
		return &ValidationError{Msg: "new " + err.Error()}
	}
	email := normaliseEmail(in.Email)
	var owner string
	var err error
	switch {
	case in.Ticket != "":
		owner, err = p.otp.ConsumeTicket(ctx, email, in.Ticket)
	case in.Code != "":
		owner, err = p.otp.Verify(ctx, email, in.Code)
	default:
		return ErrTicketInvalid
	}
	if err != nil {
		return err
	}
	hash, err := common.HashPassword(in.NewPassword)
	if err != nil {
		return err
	}
	if owner == "" {
		return nil
	}
	user, err := p.store.FindUserByID(ctx, owner)
	if errors.Is(err, dao.ErrNotFound) {
		return ErrTicketInvalid
	}
	if err != nil {
		return dbFailure("user lookup", err)
	}
	if user.Status == nil || *user.Status != "1" || normaliseEmail(user.Email) != email {
		return ErrTicketInvalid
	}
	token, err := newInvalidToken()
	if err != nil {
		return err
	}
	changed, err := p.store.SetPassword(ctx, owner, hash, token)
	if err != nil {
		return dbFailure("password update", err)
	}
	if !changed {
		return ErrTicketInvalid
	}
	// The password is already replaced; cleanup failures must not turn the success into an error.
	_ = p.otp.Revoke(ctx, email, owner)
	_ = p.limiter.Reset(ctx, "login:email:"+emailKey(email))
	return nil
}
