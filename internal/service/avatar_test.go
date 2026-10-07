package service

import (
	"bytes"
	"encoding/base64"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

func pngBytes(n int) []byte {
	b := []byte{0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}
	return append(b, bytes.Repeat([]byte{0x01}, n-len(b))...)
}

func jpegBytes(n int) []byte {
	b := []byte{0xff, 0xd8, 0xff, 0xe0}
	return append(b, bytes.Repeat([]byte{0x02}, n-len(b))...)
}

func webpBytes(n int) []byte {
	b := append([]byte("RIFF"), 0x10, 0x00, 0x00, 0x00)
	b = append(b, []byte("WEBP")...)
	return append(b, bytes.Repeat([]byte{0x03}, n-len(b))...)
}

func dataURL(mime string, raw []byte) string {
	return "data:" + mime + ";base64," + base64.StdEncoding.EncodeToString(raw)
}

func TestValidateAvatarDataURL(t *testing.T) {
	cases := []struct {
		name string
		in   string
		ok   bool
	}{
		{"png", dataURL("image/png", pngBytes(64)), true},
		{"jpeg", dataURL("image/jpeg", jpegBytes(64)), true},
		{"webp", dataURL("image/webp", webpBytes(64)), true},
		{"png at exactly the cap", dataURL("image/png", pngBytes(MaxAvatarBytes)), true},
		{"png one byte over the cap", dataURL("image/png", pngBytes(MaxAvatarBytes+1)), false},
		{"declared png but html bytes", dataURL("image/png", []byte("<html><script>alert(1)</script></html>")), false},
		{"declared png but svg bytes", dataURL("image/png", []byte(`<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>`)), false},
		{"declared svg", dataURL("image/svg+xml", []byte(`<svg xmlns="http://www.w3.org/2000/svg"/>`)), false},
		{"gif bytes declared as gif", dataURL("image/gif", append([]byte("GIF89a"), make([]byte, 20)...)), false},
		{"gif bytes declared as png", dataURL("image/png", append([]byte("GIF89a"), make([]byte, 20)...)), false},
		{"jpeg bytes declared as png", dataURL("image/png", jpegBytes(64)), false},
		{"png bytes declared as jpeg", dataURL("image/jpeg", pngBytes(64)), false},
		{"riff but not webp", dataURL("image/webp", append([]byte("RIFF\x10\x00\x00\x00WAVE"), make([]byte, 20)...)), false},
		{"invalid base64", "data:image/png;base64,@@@not base64@@@", false},
		{"unpadded base64", "data:image/png;base64," + strings.TrimRight(base64.StdEncoding.EncodeToString(pngBytes(65)), "="), false},
		{"url-safe alphabet", "data:image/png;base64," + base64.URLEncoding.EncodeToString(append(pngBytes(16), 0xfb, 0xff)), false},
		{"http url", "http://example.test/a.png", false},
		{"javascript url", "javascript:alert(1)", false},
		{"data url without base64", "data:image/png,%89PNG", false},
		{"extra mime parameter", "data:image/png;charset=utf-8;base64," + base64.StdEncoding.EncodeToString(pngBytes(64)), false},
		{"upper case mime", dataURL("IMAGE/PNG", pngBytes(64)), false},
		{"empty payload", "data:image/png;base64,", false},
		{"empty string", "", false},
		{"huge encoded input is refused before decoding", "data:image/png;base64," + strings.Repeat("A", 4*MaxAvatarBytes), false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := ValidateAvatarDataURL(c.in)
			if c.ok {
				assert.NoError(t, err)
				return
			}
			assert.ErrorIs(t, err, ErrInvalidAvatar)
			assert.NotContains(t, err.Error(), "script", "the error never echoes the input")
		})
	}
}
