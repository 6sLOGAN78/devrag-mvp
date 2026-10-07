package common

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func reqFrom(remote string, hdr map[string]string) *http.Request {
	r := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", nil)
	r.RemoteAddr = remote
	for k, v := range hdr {
		r.Header.Set(k, v)
	}
	return r
}

func TestClientIP(t *testing.T) {
	cases := []struct {
		name   string
		remote string
		hdr    map[string]string
		want   string
	}{
		{"loopback peer honours X-Real-IP", "127.0.0.1:5555", map[string]string{"X-Real-IP": "203.0.113.9"}, "203.0.113.9"},
		{"IPv6 loopback peer honours X-Real-IP", "[::1]:5555", map[string]string{"X-Real-IP": "203.0.113.9"}, "203.0.113.9"},
		{"non-loopback peer ignores spoofed X-Real-IP", "198.51.100.7:4444", map[string]string{"X-Real-IP": "203.0.113.9"}, "198.51.100.7"},
		{"X-Forwarded-For ignored for loopback peer", "127.0.0.1:5555", map[string]string{"X-Forwarded-For": "192.0.2.1, 10.0.0.1"}, "127.0.0.1"},
		{"X-Forwarded-For ignored for public peer", "198.51.100.7:4444", map[string]string{"X-Forwarded-For": "192.0.2.1"}, "198.51.100.7"},
		{"X-Real-IP wins over a spoofed X-Forwarded-For from loopback", "127.0.0.1:5555", map[string]string{"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "192.0.2.1"}, "203.0.113.9"},
		{"malformed X-Real-IP falls back to the peer", "127.0.0.1:5555", map[string]string{"X-Real-IP": "not-an-ip"}, "127.0.0.1"},
		{"empty X-Real-IP falls back to the peer", "127.0.0.1:5555", map[string]string{"X-Real-IP": ""}, "127.0.0.1"},
		{"IPv6 X-Real-IP is normalised", "127.0.0.1:5555", map[string]string{"X-Real-IP": "2001:DB8::1"}, "2001:db8::1"},
		{"peer without a port", "198.51.100.7", nil, "198.51.100.7"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			assert.Equal(t, c.want, ClientIP(reqFrom(c.remote, c.hdr)))
		})
	}
}

func TestIsLoopbackPeer(t *testing.T) {
	cases := []struct {
		remote string
		want   bool
	}{
		{"127.0.0.1:5555", true},
		{"[::1]:5555", true},
		{"[::ffff:127.0.0.1]:5555", true},
		{"198.51.100.7:4444", false},
		{"172.18.0.5:4444", false},
		{"", false},
		{"not-an-address", false},
	}
	for _, c := range cases {
		t.Run(c.remote, func(t *testing.T) {
			assert.Equal(t, c.want, IsLoopbackPeer(reqFrom(c.remote, nil)))
		})
	}
}
