package testutil

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"
)

// Message is the part of a Mailpit message the tests need.
type Message struct {
	ID      string `json:"ID"`
	Subject string `json:"Subject"`
	Text    string `json:"Text"`
	HTML    string `json:"HTML"`
}

var codeRE = regexp.MustCompile(`\b\d{6}\b`)

// MailBaseURL returns the Mailpit HTTP API base URL (MAILPIT_URL, default loopback 8025).
func MailBaseURL() string {
	if v := os.Getenv("MAILPIT_URL"); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "http://127.0.0.1:8025"
}

var mailClient = &http.Client{Timeout: 5 * time.Second}

func mailDo(method, path string, out any) error {
	req, err := http.NewRequest(method, MailBaseURL()+path, nil)
	if err != nil {
		return err
	}
	resp, err := mailClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		return fmt.Errorf("mailpit %s %s: status %d", method, path, resp.StatusCode)
	}
	if out != nil {
		return json.Unmarshal(body, out)
	}
	return nil
}

func firstMessageID(recipient string) string {
	var found struct {
		Messages []struct {
			ID string `json:"ID"`
		} `json:"messages"`
	}
	path := "/api/v1/search?limit=1&query=" + url.QueryEscape("to:"+recipient)
	if err := mailDo(http.MethodGet, path, &found); err != nil || len(found.Messages) == 0 {
		return ""
	}
	return found.Messages[0].ID
}

// WaitForMail waits for the newest message addressed to recipient and returns it.
func WaitForMail(t testing.TB, recipient string) Message {
	t.Helper()
	var id string
	err := WaitUntil(context.Background(), 30*time.Second, 300*time.Millisecond, func() bool {
		id = firstMessageID(recipient)
		return id != ""
	})
	if err != nil {
		t.Fatalf("no mail for %s: %v", recipient, err)
	}
	var msg Message
	if err := mailDo(http.MethodGet, "/api/v1/message/"+id, &msg); err != nil {
		t.Fatalf("read mail %s: %v", id, err)
	}
	return msg
}

// ClearMailbox deletes every captured message.
func ClearMailbox(t testing.TB) {
	t.Helper()
	if err := mailDo(http.MethodDelete, "/api/v1/messages", nil); err != nil {
		t.Fatalf("clear mailbox: %v", err)
	}
}

// ExtractCode returns the first six-digit code in the message text.
func ExtractCode(t testing.TB, msg Message) string {
	t.Helper()
	code := codeRE.FindString(msg.Text)
	if code == "" {
		t.Fatalf("no 6-digit code in message %q", msg.Subject)
	}
	return code
}

// AssertNoMailFor fails if a message for recipient appears within a bounded window.
func AssertNoMailFor(t testing.TB, recipient string) {
	t.Helper()
	err := WaitUntil(context.Background(), 3*time.Second, 300*time.Millisecond, func() bool {
		return firstMessageID(recipient) != ""
	})
	if err == nil {
		t.Fatalf("unexpected mail for %s", recipient)
	}
}

// DeleteMailFor removes the captured messages addressed to recipient (and nothing else), so a test
// cleans up exactly what it caused.
func DeleteMailFor(t testing.TB, recipient string) {
	t.Helper()
	if err := mailDo(http.MethodDelete, "/api/v1/search?query="+url.QueryEscape("to:"+recipient), nil); err != nil {
		t.Errorf("delete mail for %s: %v", recipient, err)
	}
}
