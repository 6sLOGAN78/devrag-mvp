package service

import (
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"net"
	"net/mail"
	"net/smtp"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	"devrag/internal/common"
	"devrag/internal/server"
)

const (
	smtpDialTimeout  = 5 * time.Second
	smtpTotalTimeout = 10 * time.Second
	poolSendTimeout  = 15 * time.Second
	maxAddressLength = 254
	resetMailSubject = "Your devRag password reset code"
)

// Mail is one outgoing plain-text message.
type Mail struct{ To, Subject, Body string }

// Mailer delivers a message.
type Mailer interface {
	Send(ctx context.Context, m Mail) error
}

// MailQueue accepts messages for asynchronous delivery. Enqueue never blocks and reports whether
// the message was accepted.
type MailQueue interface {
	Enqueue(m Mail) bool
}

// DiscardMail is the queue used when no SMTP host is configured: nothing is delivered.
type DiscardMail struct{}

// Enqueue drops the message.
func (DiscardMail) Enqueue(Mail) bool { return false }

// cleanAddress reports whether s is exactly one bare mailbox: no display name, comment, quote,
// whitespace or control character (so no CR or LF), at most 254 bytes.
func cleanAddress(s string) bool {
	if s == "" || len(s) > maxAddressLength || strings.Count(s, "@") != 1 {
		return false
	}
	for _, r := range s {
		if r <= ' ' || r == 0x7f || r > 0x7e || strings.ContainsRune(`<>()[]\",;:`, r) {
			return false
		}
	}
	addr, err := mail.ParseAddress(s)
	return err == nil && addr.Address == s && addr.Name == ""
}

// headerText reports whether s is safe as a header value: printable ASCII only, so no CR, LF or encoded word.
func headerText(s string) bool {
	if s == "" || len(s) > 200 {
		return false
	}
	for _, r := range s {
		if r < ' ' || r > 0x7e {
			return false
		}
	}
	return true
}

// buildMessage renders an RFC 5322 plain-text message. Every address and the subject are validated
// first, so no input can add a header (T-02-78).
func buildMessage(from, to, subject, body string, now time.Time, messageID string) ([]byte, error) {
	if !cleanAddress(from) {
		return nil, errors.New("mail: invalid sender address")
	}
	if !cleanAddress(to) {
		return nil, errors.New("mail: invalid recipient address")
	}
	if !headerText(subject) {
		return nil, errors.New("mail: invalid subject")
	}
	if strings.ContainsRune(body, 0) {
		return nil, errors.New("mail: invalid body")
	}
	if messageID == "" || strings.ContainsAny(messageID, "<>@\r\n ") {
		return nil, errors.New("mail: invalid message id")
	}
	domain := from[strings.IndexByte(from, '@')+1:]
	body = strings.ReplaceAll(strings.ReplaceAll(body, "\r\n", "\n"), "\r", "\n")
	body = strings.ReplaceAll(body, "\n", "\r\n")
	if !strings.HasSuffix(body, "\r\n") {
		body += "\r\n"
	}
	var b strings.Builder
	for _, h := range [][2]string{
		{"Date", now.UTC().Format(time.RFC1123Z)},
		{"Message-ID", "<" + messageID + "@" + domain + ">"},
		{"From", from},
		{"To", to},
		{"Subject", subject},
		{"MIME-Version", "1.0"},
		{"Content-Type", "text/plain; charset=UTF-8"},
		{"Content-Transfer-Encoding", "8bit"},
	} {
		b.WriteString(h[0] + ": " + h[1] + "\r\n")
	}
	b.WriteString("\r\n")
	b.WriteString(body)
	return []byte(b.String()), nil
}

// SMTPMailer sends over SMTP with the standard library. Dial and total timeouts bound every send,
// certificates are verified for starttls and tls, and credentials are never offered on a plaintext
// connection.
type SMTPMailer struct {
	host, from, username, password string
	port                           int
	security                       string
	dialTimeout, totalTimeout      time.Duration
	tlsConfig                      *tls.Config // nil: verify against the system roots
}

// NewSMTPMailer validates cfg and builds the sender. It refuses credentials with security none.
func NewSMTPMailer(cfg server.MailConfig) (*SMTPMailer, error) {
	if cfg.Host == "" || strings.ContainsAny(cfg.Host, " \t\r\n/@") || len(cfg.Host) > 253 {
		return nil, errors.New("mail: host is missing or invalid")
	}
	if cfg.Port < 1 || cfg.Port > 65535 {
		return nil, errors.New("mail: port is invalid")
	}
	switch cfg.Security {
	case "none", "starttls", "tls":
	default:
		return nil, errors.New("mail: security must be none, starttls or tls")
	}
	if !cleanAddress(cfg.From) {
		return nil, errors.New("mail: from address is invalid")
	}
	if strings.ContainsAny(cfg.Username, "\r\n\x00") {
		return nil, errors.New("mail: username is invalid")
	}
	if cfg.Username != "" && cfg.Security == "none" {
		return nil, errors.New("mail: credentials require security starttls or tls")
	}
	return &SMTPMailer{
		host: cfg.Host, port: cfg.Port, security: cfg.Security, from: cfg.From, username: cfg.Username, password: cfg.Password,
		dialTimeout: smtpDialTimeout, totalTimeout: smtpTotalTimeout,
	}, nil
}

func (s *SMTPMailer) tlsCfg() *tls.Config {
	if s.tlsConfig != nil {
		c := s.tlsConfig.Clone()
		if c.ServerName == "" {
			c.ServerName = s.host
		}
		return c
	}
	return &tls.Config{ServerName: s.host, MinVersion: tls.VersionTLS12}
}

func randomHex(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

// Send delivers m. The message is validated before any network use.
func (s *SMTPMailer) Send(ctx context.Context, m Mail) error {
	id, err := randomHex(16)
	if err != nil {
		return err
	}
	msg, err := buildMessage(s.from, m.To, m.Subject, m.Body, time.Now(), id)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, s.totalTimeout)
	defer cancel()
	addr := net.JoinHostPort(s.host, strconv.Itoa(s.port))
	dialer := &net.Dialer{Timeout: s.dialTimeout}
	var conn net.Conn
	if s.security == "tls" {
		conn, err = (&tls.Dialer{NetDialer: dialer, Config: s.tlsCfg()}).DialContext(ctx, "tcp", addr)
	} else {
		conn, err = dialer.DialContext(ctx, "tcp", addr)
	}
	if err != nil {
		return fmt.Errorf("smtp connect: %w", err)
	}
	if dl, ok := ctx.Deadline(); ok {
		_ = conn.SetDeadline(dl)
	}
	stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
	defer stop()
	c, err := smtp.NewClient(conn, s.host)
	if err != nil {
		_ = conn.Close()
		return fmt.Errorf("smtp greeting: %w", err)
	}
	defer func() { _ = c.Close() }()
	if s.security == "starttls" {
		if ok, _ := c.Extension("STARTTLS"); !ok {
			return errors.New("smtp starttls: not offered by the server")
		}
		if err := c.StartTLS(s.tlsCfg()); err != nil {
			return fmt.Errorf("smtp starttls: %w", err)
		}
	}
	if s.username != "" {
		if err := c.Auth(smtp.PlainAuth("", s.username, s.password, s.host)); err != nil {
			return fmt.Errorf("smtp auth: %w", err)
		}
	}
	if err := c.Mail(s.from); err != nil {
		return fmt.Errorf("smtp sender: %w", err)
	}
	if err := c.Rcpt(m.To); err != nil {
		return fmt.Errorf("smtp recipient: %w", err)
	}
	w, err := c.Data()
	if err != nil {
		return fmt.Errorf("smtp data: %w", err)
	}
	if _, err := w.Write(msg); err != nil {
		return fmt.Errorf("smtp data: %w", err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("smtp data: %w", err)
	}
	_ = c.Quit()
	return nil
}

// ResetCodeMail builds the reset-code message for a stored account address. The only variable text
// is the code and the lifetime; no request-supplied string reaches the subject or body.
func ResetCodeMail(to, code string, ttl time.Duration) Mail {
	minutes := int((ttl + time.Minute - 1) / time.Minute)
	if minutes < 1 {
		minutes = 1
	}
	unit := "minutes"
	if minutes == 1 {
		unit = "minute"
	}
	body := "Your devRag password reset code is " + code + ".\n\n" +
		"It expires in " + strconv.Itoa(minutes) + " " + unit + " and works once. If you did not ask for it, you can ignore this message.\n"
	return Mail{To: to, Subject: resetMailSubject, Body: body}
}

// MailPool sends queued messages from a fixed set of workers, so a request never waits for SMTP.
// A full queue drops the message and logs it; callers see no difference.
type MailPool struct {
	mailer Mailer
	queue  chan Mail
	log    *zap.Logger
	wg     sync.WaitGroup
	mu     sync.RWMutex
	closed bool
}

// NewMailPool starts workers goroutines draining a queue of the given size.
func NewMailPool(m Mailer, workers, queue int, log *zap.Logger) *MailPool {
	if workers < 1 {
		workers = 1
	}
	if queue < 1 {
		queue = 1
	}
	if log == nil {
		log = zap.NewNop()
	}
	p := &MailPool{mailer: m, queue: make(chan Mail, queue), log: log}
	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.work()
	}
	return p
}

var addressInText = regexp.MustCompile(`[^\s<>"',;()]+@[^\s<>"',;()]+`)

// scrubError masks credentials and mail addresses in an error text before it is logged.
func scrubError(err error) string {
	s := common.TruncateField(err.Error(), common.MaxLogField)
	return addressInText.ReplaceAllString(common.RedactString(s), "[address]")
}

func (p *MailPool) work() {
	defer p.wg.Done()
	for m := range p.queue {
		ctx, cancel := context.WithTimeout(context.Background(), poolSendTimeout)
		err := p.mailer.Send(ctx, m)
		cancel()
		if err != nil {
			p.log.Error("mail send failed", zap.String("error", scrubError(err)))
		}
	}
}

// Enqueue never blocks. It returns false when the pool is closed or the queue is full.
func (p *MailPool) Enqueue(m Mail) bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	if p.closed {
		return false
	}
	select {
	case p.queue <- m:
		return true
	default:
		p.log.Warn("mail queue full, message dropped")
		return false
	}
}

// Close stops accepting messages, sends what was accepted and waits for the workers.
func (p *MailPool) Close() {
	p.mu.Lock()
	if !p.closed {
		p.closed = true
		close(p.queue)
	}
	p.mu.Unlock()
	p.wg.Wait()
}
