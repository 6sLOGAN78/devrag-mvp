package service

import (
	"context"
	"crypto/tls"
	"errors"
	"time"

	"go.uber.org/zap"

	"devrag/internal/server"
)

var errNotImplemented = errors.New("not implemented")

// Mail is one outgoing plain-text message.
type Mail struct{ To, Subject, Body string }

// Mailer delivers a message.
type Mailer interface {
	Send(ctx context.Context, m Mail) error
}

// MailQueue accepts messages for asynchronous delivery.
type MailQueue interface {
	Enqueue(m Mail) bool
}

// SMTPMailer sends over SMTP.
type SMTPMailer struct {
	dialTimeout, totalTimeout time.Duration
	tlsConfig                 *tls.Config
}

// NewSMTPMailer validates cfg and builds the sender.
func NewSMTPMailer(cfg server.MailConfig) (*SMTPMailer, error) { return nil, errNotImplemented }

// Send delivers m.
func (s *SMTPMailer) Send(ctx context.Context, m Mail) error { return errNotImplemented }

// MailPool is a bounded asynchronous sender.
type MailPool struct{}

// NewMailPool starts workers.
func NewMailPool(m Mailer, workers, queue int, log *zap.Logger) *MailPool { return &MailPool{} }

// Enqueue never blocks.
func (p *MailPool) Enqueue(m Mail) bool { return false }

// Close drains the queue and stops the workers.
func (p *MailPool) Close() {}

// ResetCodeMail builds the reset-code message for a stored account address.
func ResetCodeMail(to, code string, ttl time.Duration) Mail { return Mail{} }

func buildMessage(from, to, subject, body string, now time.Time, messageID string) ([]byte, error) {
	return nil, errNotImplemented
}
