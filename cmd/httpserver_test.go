package main

import (
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

// IN-05: every server timeout is set, so a client that trickles bytes cannot pin a goroutine when Go is reached
// without Nginx (another container on the compose network).
func TestHTTPServerHasEveryTimeout(t *testing.T) {
	srv := newHTTPServer(":0", http.NewServeMux())
	assert.Equal(t, ":0", srv.Addr)
	assert.Positive(t, srv.ReadHeaderTimeout)
	assert.Positive(t, srv.ReadTimeout)
	assert.Positive(t, srv.WriteTimeout)
	assert.Positive(t, srv.IdleTimeout)
	assert.GreaterOrEqual(t, srv.ReadTimeout, srv.ReadHeaderTimeout)
	assert.LessOrEqual(t, srv.ReadTimeout, 2*time.Minute)
	assert.Positive(t, srv.MaxHeaderBytes)
}
