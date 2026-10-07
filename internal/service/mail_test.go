package service

import (
	"bufio"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"errors"
	"fmt"
	"math/big"
	"net"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"

	"devrag/internal/common"
	"devrag/internal/server"
)

var fixedNow = time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)

// fakeSMTP is a small in-process SMTP server for the wire-format tests. The reset flow against a real
// catcher (Mailpit) is covered by the e2e tier.
type fakeSMTP struct {
	ln          net.Listener
	tlsCfg      *tls.Config
	implicitTLS bool
	startTLS    bool
	silent      bool // accept and never speak

	mu        sync.Mutex
	conns     int32
	mailFrom  string
	rcpts     []string
	data      string
	authLine  string
	delivered int
}

func newFakeSMTP(t *testing.T, opts func(*fakeSMTP)) *fakeSMTP {
	t.Helper()
	f := &fakeSMTP{}
	if opts != nil {
		opts(f)
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	if f.implicitTLS {
		ln = tls.NewListener(ln, f.tlsCfg)
	}
	f.ln = ln
	t.Cleanup(func() { _ = ln.Close() })
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			atomic.AddInt32(&f.conns, 1)
			go f.serve(c)
		}
	}()
	return f
}

func (f *fakeSMTP) port() int { return f.ln.Addr().(*net.TCPAddr).Port }

func (f *fakeSMTP) serve(conn net.Conn) {
	defer func() { _ = conn.Close() }()
	if f.silent {
		_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
		_, _ = bufio.NewReader(conn).ReadByte()
		return
	}
	r := bufio.NewReader(conn)
	w := func(s string) { _, _ = conn.Write([]byte(s + "\r\n")) }
	w("220 fake ESMTP")
	secure := f.implicitTLS
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			return
		}
		line = strings.TrimRight(line, "\r\n")
		verb := strings.ToUpper(line)
		switch {
		case strings.HasPrefix(verb, "EHLO"):
			w("250-fake")
			if f.startTLS && !secure {
				w("250-STARTTLS")
			}
			w("250 AUTH PLAIN")
		case verb == "STARTTLS":
			w("220 go ahead")
			tc := tls.Server(conn, f.tlsCfg)
			if tc.Handshake() != nil {
				return
			}
			conn, r, secure = tc, bufio.NewReader(tc), true
			w = func(s string) { _, _ = tc.Write([]byte(s + "\r\n")) }
		case strings.HasPrefix(verb, "AUTH PLAIN"):
			f.mu.Lock()
			f.authLine = line
			f.mu.Unlock()
			w("235 ok")
		case strings.HasPrefix(verb, "MAIL FROM:"):
			f.mu.Lock()
			f.mailFrom = line[len("MAIL FROM:"):]
			f.mu.Unlock()
			w("250 ok")
		case strings.HasPrefix(verb, "RCPT TO:"):
			f.mu.Lock()
			f.rcpts = append(f.rcpts, line[len("RCPT TO:"):])
			f.mu.Unlock()
			w("250 ok")
		case verb == "DATA":
			w("354 go")
			var sb strings.Builder
			for {
				l, err := r.ReadString('\n')
				if err != nil {
					return
				}
				if l == ".\r\n" {
					break
				}
				sb.WriteString(l)
			}
			f.mu.Lock()
			f.data = sb.String()
			f.delivered++
			f.mu.Unlock()
			w("250 queued")
		case verb == "QUIT":
			w("221 bye")
			return
		default:
			w("250 ok")
		}
	}
}

func (f *fakeSMTP) snapshot() (mailFrom string, rcpts []string, data, auth string, delivered int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.mailFrom, append([]string(nil), f.rcpts...), f.data, f.authLine, f.delivered
}

// selfSigned returns a server certificate for 127.0.0.1 and a pool that trusts it.
func selfSigned(t *testing.T) (*tls.Config, *x509.CertPool) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)
	tpl := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "fake"}, NotBefore: fixedNow.Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		IPAddresses: []net.IP{net.ParseIP("127.0.0.1")}, IsCA: true, BasicConstraintsValid: true,
	}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	require.NoError(t, err)
	leaf, err := x509.ParseCertificate(der)
	require.NoError(t, err)
	pool := x509.NewCertPool()
	pool.AddCert(leaf)
	return &tls.Config{Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: key}}, MinVersion: tls.VersionTLS12}, pool
}

func testMailCfg(f *fakeSMTP, security string) server.MailConfig {
	return server.MailConfig{Host: "127.0.0.1", Port: f.port(), Security: security, From: "no-reply@devrag.local"}
}

func goodMail() Mail {
	return Mail{To: "alice@example.test", Subject: "Your devRag password reset code", Body: "Your code is 123456.\r\n"}
}

func TestBuildMessageSetsRequiredHeaders(t *testing.T) {
	raw, err := buildMessage("no-reply@devrag.local", "alice@example.test", "Hello", "line one\nline two", fixedNow, "id123")
	require.NoError(t, err)
	msg := string(raw)
	head, body, ok := strings.Cut(msg, "\r\n\r\n")
	require.True(t, ok, "headers end with a blank CRLF line")
	for _, want := range []string{
		"Date: Wed, 07 Oct 2026 12:00:00 +0000", "Message-ID: <id123@devrag.local>", "From: no-reply@devrag.local", "To: alice@example.test",
		"Subject: Hello", "MIME-Version: 1.0", "Content-Type: text/plain; charset=UTF-8",
	} {
		assert.Contains(t, head, want)
	}
	assert.Equal(t, "line one\r\nline two\r\n", body, "body uses CRLF line endings")
	assert.NotContains(t, strings.ReplaceAll(msg, "\r\n", ""), "\n", "no bare LF anywhere")
}

func TestBuildMessageRejectsHeaderInjection(t *testing.T) {
	ok := func(to string) error {
		_, err := buildMessage("no-reply@devrag.local", to, "Subject", "body", fixedNow, "id")
		return err
	}
	require.NoError(t, ok("alice@example.test"))
	for name, to := range map[string]string{
		"crlf":            "alice@example.test\r\nBcc: evil@example.test",
		"lf":              "alice@example.test\nBcc: evil@example.test",
		"cr":              "alice@example.test\rBcc: evil@example.test",
		"display name":    "Alice <alice@example.test>",
		"two recipients":  "alice@example.test, bob@example.test",
		"quoted":          `"alice"@example.test`,
		"space":           "alice @example.test",
		"empty":           "",
		"no domain":       "alice",
		"nul":             "alice\x00@example.test",
		"long":            strings.Repeat("a", 300) + "@example.test",
		"angle":           "<alice@example.test>",
		"comment":         "alice@example.test (hi)",
		"percent routing": "alice%evil.test@example.test\r\n",
	} {
		assert.Error(t, ok(to), name)
	}
	_, err := buildMessage("no-reply@devrag.local", "alice@example.test", "Hi\r\nBcc: evil@example.test", "body", fixedNow, "id")
	assert.Error(t, err, "subject with CRLF")
	_, err = buildMessage("no-reply@devrag.local\r\nBcc: x@example.test", "alice@example.test", "Hi", "body", fixedNow, "id")
	assert.Error(t, err, "from with CRLF")
}

func TestNewSMTPMailerRefusesBadConfiguration(t *testing.T) {
	_, err := NewSMTPMailer(server.MailConfig{Host: "mail.example.test", Port: 25, Security: "none", Username: "u", Password: "fake-smtp-secret-9", From: "no-reply@devrag.local"})
	require.Error(t, err, "credentials over an unencrypted connection are refused")
	assert.NotContains(t, err.Error(), "fake-smtp-secret-9")
	for name, cfg := range map[string]server.MailConfig{
		"no host":        {Port: 25, Security: "none", From: "no-reply@devrag.local"},
		"bad port":       {Host: "mail.example.test", Port: 0, Security: "none", From: "no-reply@devrag.local"},
		"bad security":   {Host: "mail.example.test", Port: 25, Security: "plain", From: "no-reply@devrag.local"},
		"bad from":       {Host: "mail.example.test", Port: 25, Security: "none", From: "not an address"},
		"from with crlf": {Host: "mail.example.test", Port: 25, Security: "none", From: "a@example.test\r\nBcc: b@example.test"},
		"host with crlf": {Host: "mail.example.test\r\nx", Port: 25, Security: "none", From: "no-reply@devrag.local"},
	} {
		_, err := NewSMTPMailer(cfg)
		assert.Error(t, err, name)
	}
	for _, sec := range []string{"starttls", "tls"} {
		_, err := NewSMTPMailer(server.MailConfig{Host: "mail.example.test", Port: 587, Security: sec, Username: "u", Password: "fake-smtp-secret-9", From: "no-reply@devrag.local"})
		assert.NoError(t, err, "credentials are allowed over %s", sec)
	}
}

func TestSMTPMailerDeliversMessage(t *testing.T) {
	f := newFakeSMTP(t, nil)
	m, err := NewSMTPMailer(testMailCfg(f, "none"))
	require.NoError(t, err)
	require.NoError(t, m.Send(context.Background(), goodMail()))
	from, rcpts, data, auth, n := f.snapshot()
	assert.Equal(t, 1, n)
	assert.Contains(t, from, "<no-reply@devrag.local>")
	assert.Equal(t, []string{"<alice@example.test>"}, rcpts)
	assert.Contains(t, data, "To: alice@example.test\r\n")
	assert.Contains(t, data, "Subject: Your devRag password reset code\r\n")
	assert.Contains(t, data, "Your code is 123456.")
	assert.Empty(t, auth, "no credentials are configured, none are sent")
}

func TestSMTPMailerRejectsBadRecipientWithoutConnecting(t *testing.T) {
	f := newFakeSMTP(t, nil)
	m, err := NewSMTPMailer(testMailCfg(f, "none"))
	require.NoError(t, err)
	for _, to := range []string{"a@example.test\r\nBcc: b@example.test", "a@example.test\nRCPT TO:<b@example.test>", "Alice <a@example.test>"} {
		bad := goodMail()
		bad.To = to
		assert.Error(t, m.Send(context.Background(), bad), "%q", to)
	}
	bad := goodMail()
	bad.Subject = "x\r\nBcc: b@example.test"
	assert.Error(t, m.Send(context.Background(), bad))
	assert.EqualValues(t, 0, atomic.LoadInt32(&f.conns), "an invalid message never reaches the network")
}

func TestSMTPMailerStartTLSVerifiesCertificate(t *testing.T) {
	cfgTLS, pool := selfSigned(t)
	f := newFakeSMTP(t, func(f *fakeSMTP) { f.tlsCfg, f.startTLS = cfgTLS, true })
	cfg := testMailCfg(f, "starttls")
	cfg.Username, cfg.Password = "mailer", "fake-smtp-secret-9"
	m, err := NewSMTPMailer(cfg)
	require.NoError(t, err)

	err = m.Send(context.Background(), goodMail())
	require.Error(t, err, "an untrusted certificate is refused")
	_, _, _, auth, n := f.snapshot()
	assert.Zero(t, n)
	assert.Empty(t, auth, "credentials are never sent before the certificate is trusted")
	assert.NotContains(t, err.Error(), "fake-smtp-secret-9")

	m.tlsConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	require.NoError(t, m.Send(context.Background(), goodMail()))
	_, _, _, auth, n = f.snapshot()
	assert.Equal(t, 1, n)
	assert.NotEmpty(t, auth, "credentials are sent once the channel is encrypted")
}

func TestSMTPMailerImplicitTLSVerifiesCertificate(t *testing.T) {
	cfgTLS, pool := selfSigned(t)
	f := newFakeSMTP(t, func(f *fakeSMTP) { f.tlsCfg, f.implicitTLS = cfgTLS, true })
	m, err := NewSMTPMailer(testMailCfg(f, "tls"))
	require.NoError(t, err)
	require.Error(t, m.Send(context.Background(), goodMail()), "an untrusted certificate is refused")
	m.tlsConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	require.NoError(t, m.Send(context.Background(), goodMail()))
	_, _, _, _, n := f.snapshot()
	assert.Equal(t, 1, n)
}

func TestSMTPMailerStartTLSRefusesDowngrade(t *testing.T) {
	f := newFakeSMTP(t, nil) // the server does not offer STARTTLS
	m, err := NewSMTPMailer(testMailCfg(f, "starttls"))
	require.NoError(t, err)
	require.Error(t, m.Send(context.Background(), goodMail()), "starttls mode must not fall back to plaintext")
	_, _, _, _, n := f.snapshot()
	assert.Zero(t, n)
}

func TestSMTPMailerDialTimeoutIsBounded(t *testing.T) {
	m, err := NewSMTPMailer(server.MailConfig{Host: "192.0.2.1", Port: 25, Security: "none", From: "no-reply@devrag.local"})
	require.NoError(t, err)
	m.dialTimeout = 300 * time.Millisecond
	started := time.Now()
	require.Error(t, m.Send(context.Background(), goodMail()))
	assert.Less(t, time.Since(started), 5*time.Second)
}

func TestSMTPMailerTotalDeadlineIsBounded(t *testing.T) {
	f := newFakeSMTP(t, func(f *fakeSMTP) { f.silent = true })
	m, err := NewSMTPMailer(testMailCfg(f, "none"))
	require.NoError(t, err)
	m.totalTimeout = 400 * time.Millisecond
	started := time.Now()
	require.Error(t, m.Send(context.Background(), goodMail()))
	assert.Less(t, time.Since(started), 5*time.Second, "a server that never answers cannot hold the sender")
}

func TestDefaultMailTimeouts(t *testing.T) {
	m, err := NewSMTPMailer(server.MailConfig{Host: "mail.example.test", Port: 25, Security: "none", From: "no-reply@devrag.local"})
	require.NoError(t, err)
	assert.Equal(t, 5*time.Second, m.dialTimeout)
	assert.Equal(t, 10*time.Second, m.totalTimeout)
}

var sixDigits = regexp.MustCompile(`\d{6}`)

func TestResetCodeMailCarriesOnlyTheCode(t *testing.T) {
	m := ResetCodeMail("alice@example.test", "042517", 10*time.Minute)
	assert.Equal(t, "alice@example.test", m.To)
	assert.Equal(t, "Your devRag password reset code", m.Subject)
	assert.Contains(t, m.Body, "042517")
	assert.Contains(t, m.Body, "10 minutes")
	assert.Equal(t, []string{"042517"}, sixDigits.FindAllString(m.Body, -1))
	assert.NotContains(t, m.Body+m.Subject, "<", "plain text, no markup")
	assert.False(t, strings.ContainsAny(m.Subject, "\r\n"))
}

type gateMailer struct {
	release chan struct{}
	started chan struct{}
	sent    atomic.Int32
	err     error
}

func (g *gateMailer) Send(ctx context.Context, m Mail) error {
	g.started <- struct{}{}
	select {
	case <-g.release:
	case <-ctx.Done():
	}
	g.sent.Add(1)
	return g.err
}

func TestMailPoolIsBoundedAndNeverBlocks(t *testing.T) {
	g := &gateMailer{release: make(chan struct{}), started: make(chan struct{}, 8)}
	core, logs := observer.New(zapcore.DebugLevel)
	pool := NewMailPool(g, 1, 1, zap.New(core))
	require.True(t, pool.Enqueue(goodMail()), "the worker takes the first message")
	<-g.started
	require.True(t, pool.Enqueue(goodMail()), "one message waits in the queue")
	began := time.Now()
	assert.False(t, pool.Enqueue(goodMail()), "a full queue drops instead of blocking")
	assert.Less(t, time.Since(began), time.Second)
	assert.GreaterOrEqual(t, logs.FilterMessage("mail queue full, message dropped").Len(), 1)
	close(g.release)
	pool.Close()
	assert.EqualValues(t, 2, g.sent.Load(), "Close drains what was accepted")
	assert.False(t, pool.Enqueue(goodMail()), "a closed pool accepts nothing")
}

func TestMailPoolLogsFailuresWithoutSecrets(t *testing.T) {
	g := &gateMailer{release: make(chan struct{}), started: make(chan struct{}, 8), err: fmt.Errorf("535 authentication failed password=%s for alice@example.test", "fake-smtp-secret-9")}
	close(g.release)
	core, logs := observer.New(zapcore.DebugLevel)
	pool := NewMailPool(g, 1, 4, zap.New(common.WrapRedacting(core)))
	require.True(t, pool.Enqueue(goodMail()))
	<-g.started
	pool.Close()
	entries := logs.FilterMessage("mail send failed").All()
	require.Len(t, entries, 1)
	rendered := fmt.Sprint(entries[0].ContextMap())
	assert.NotContains(t, rendered, "fake-smtp-secret-9")
	assert.NotContains(t, rendered, "alice@example.test", "the recipient address is not logged")
}

func TestMailPoolSurvivesAMailerError(t *testing.T) {
	var calls atomic.Int32
	pool := NewMailPool(mailerFunc(func(context.Context, Mail) error {
		calls.Add(1)
		return errors.New("boom")
	}), 2, 8, zap.NewNop())
	for i := 0; i < 5; i++ {
		require.True(t, pool.Enqueue(goodMail()))
	}
	pool.Close()
	assert.EqualValues(t, 5, calls.Load())
}

type mailerFunc func(context.Context, Mail) error

func (f mailerFunc) Send(ctx context.Context, m Mail) error { return f(ctx, m) }

func TestPasswordIsOnlyAuthPlainBase64(t *testing.T) {
	// The credential reaches the wire only inside AUTH PLAIN, over the encrypted channel.
	cfgTLS, pool := selfSigned(t)
	f := newFakeSMTP(t, func(f *fakeSMTP) { f.tlsCfg, f.startTLS = cfgTLS, true })
	cfg := testMailCfg(f, "starttls")
	cfg.Username, cfg.Password = "mailer", "fake-smtp-secret-9"
	m, err := NewSMTPMailer(cfg)
	require.NoError(t, err)
	m.tlsConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	require.NoError(t, m.Send(context.Background(), goodMail()))
	_, _, data, auth, _ := f.snapshot()
	fields := strings.Fields(auth)
	require.Len(t, fields, 3)
	dec, err := base64.StdEncoding.DecodeString(fields[2])
	require.NoError(t, err)
	assert.Equal(t, "\x00mailer\x00fake-smtp-secret-9", string(dec))
	assert.NotContains(t, data, "fake-smtp-secret-9", "the message never carries the credential")
}
