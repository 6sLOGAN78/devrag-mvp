package service

import (
	"bytes"
	"encoding/base64"
	"errors"
	"strings"
)

// MaxAvatarBytes is the largest decoded avatar image (D-29, R-94).
const MaxAvatarBytes = 256 * 1024

// ErrInvalidAvatar is returned for every avatar rejection. It never echoes the input.
var ErrInvalidAvatar = errors.New("avatar must be a PNG, JPEG or WebP image of at most 256 KB")

var (
	pngSignature  = []byte{0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}
	jpegSignature = []byte{0xff, 0xd8, 0xff}
)

// avatarTypes maps each accepted declared MIME type to the check its decoded bytes must pass. A
// declared type that disagrees with the bytes is rejected: the client's claim is never trusted.
var avatarTypes = map[string]func([]byte) bool{
	"image/png":  func(b []byte) bool { return bytes.HasPrefix(b, pngSignature) },
	"image/jpeg": func(b []byte) bool { return bytes.HasPrefix(b, jpegSignature) },
	"image/webp": func(b []byte) bool { return len(b) >= 12 && string(b[:4]) == "RIFF" && string(b[8:12]) == "WEBP" },
}

// ValidateAvatarDataURL accepts only data:image/{png,jpeg,webp};base64,<canonical base64> whose
// decoded bytes carry the matching magic number and are at most MaxAvatarBytes. SVG, GIF, HTML
// and anything else scriptable fail the magic check. The avatar is stored and served as plain
// data and must only ever be rendered inside an img element (T-02-65).
func ValidateAvatarDataURL(s string) error {
	rest, ok := strings.CutPrefix(s, "data:")
	if !ok {
		return ErrInvalidAvatar
	}
	mime, payload, ok := strings.Cut(rest, ";base64,")
	if !ok {
		return ErrInvalidAvatar
	}
	matches, known := avatarTypes[mime]
	if !known || len(payload) == 0 || len(payload) > base64.StdEncoding.EncodedLen(MaxAvatarBytes) {
		return ErrInvalidAvatar
	}
	raw, err := base64.StdEncoding.DecodeString(payload)
	// Re-encoding rejects what the decoder tolerates: embedded line breaks and non-zero trailing bits.
	if err != nil || len(raw) > MaxAvatarBytes || base64.StdEncoding.EncodeToString(raw) != payload || !matches(raw) {
		return ErrInvalidAvatar
	}
	return nil
}
