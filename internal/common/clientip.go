package common

import (
	"net"
	"net/http"
	"net/netip"
	"strings"
)

// ClientIP returns the address the request should be attributed to (R-114).
//
// X-Real-IP is honoured only when the socket peer is a loopback address, i.e. a proxy on the same
// host that overwrites the header. For any other peer the socket peer address is returned, because
// the header is then attacker-controlled. X-Forwarded-For is never read: the proxy appends to it,
// so its leftmost entry is whatever the client sent.
func ClientIP(r *http.Request) string {
	peer := peerAddr(r.RemoteAddr)
	if !peer.IsValid() {
		return ""
	}
	if peer.IsLoopback() {
		if real, err := netip.ParseAddr(strings.TrimSpace(r.Header.Get("X-Real-IP"))); err == nil {
			return real.Unmap().String()
		}
	}
	return peer.String()
}

// IsLoopbackPeer reports whether the socket peer is a loopback address. Inside the app container
// Nginx connects to Go and Python over 127.0.0.1, so a loopback peer is the trusted reverse proxy
// that overwrites the X-Forwarded-* headers; any other peer controls them itself (R-114).
func IsLoopbackPeer(r *http.Request) bool {
	peer := peerAddr(r.RemoteAddr)
	return peer.IsValid() && peer.IsLoopback()
}

func peerAddr(remote string) netip.Addr {
	host := remote
	if h, _, err := net.SplitHostPort(remote); err == nil {
		host = h
	}
	addr, err := netip.ParseAddr(strings.Trim(host, "[]"))
	if err != nil {
		return netip.Addr{}
	}
	return addr.Unmap()
}
