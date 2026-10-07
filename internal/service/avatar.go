package service

import "errors"

// MaxAvatarBytes is the largest decoded avatar image (D-29, R-94).
const MaxAvatarBytes = 256 * 1024

// ErrInvalidAvatar is returned for every avatar rejection. It never echoes the input.
var ErrInvalidAvatar = errors.New("avatar must be a PNG, JPEG or WebP image of at most 256 KB")

// ValidateAvatarDataURL is not implemented yet.
func ValidateAvatarDataURL(string) error { return errors.New("not implemented") }
