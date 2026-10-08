package handler

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// IN-09: the small JSON caps must hold the largest legal bodies, including multi-byte nicknames and passwords
// (a 4-byte rune is 4 bytes raw and up to 12 bytes as an escaped surrogate pair).
func TestSmallBodyCapsHoldTheLargestLegalBodies(t *testing.T) {
	long := func(n int) string { return strings.Repeat("\U0001F600", n) } // 4-byte rune
	email := strings.Repeat("a", 243) + "@example.test"                   // 255 characters
	cases := map[string]struct {
		body any
		cap  int64
	}{
		"register": {registerRequest{Email: email, Password: long(128), Nickname: long(64)}, maxAccountBody},
		"login":    {loginRequest{Email: email, Password: long(128)}, maxAccountBody},
		"reset":    {map[string]string{"email": email, "otp": "123456", "reset_ticket": strings.Repeat("t", 43), "new_password": long(128)}, maxResetBody},
		"password": {map[string]string{"old_password": long(128), "new_password": long(128)}, maxPasswordBody},
	}
	for name, tc := range cases {
		raw, err := json.Marshal(tc.body)
		require.NoError(t, err)
		assert.LessOrEqual(t, int64(len(raw)), tc.cap, "%s: worst-case raw UTF-8 body is %d bytes", name, len(raw))
		assert.LessOrEqual(t, int64(len(raw)), DefaultBodyLimit, name)
	}
}
