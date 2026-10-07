package service

import (
	"context"
	"errors"

	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

// ErrCurrentPasswordIncorrect means the current password did not verify.
var ErrCurrentPasswordIncorrect = errors.New("current password is incorrect")

var errNotImplemented = errors.New("not implemented")

// UserStore is the persistence surface of profile and password changes. dao.DB satisfies it.
type UserStore interface {
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	UpdateProfile(ctx context.Context, userID string, u dao.ProfileUpdate) error
	ReplacePassword(ctx context.Context, userID, oldHash, newHash, token string) (bool, error)
}

// SettingInput carries the optional profile fields; nil means unchanged.
type SettingInput struct {
	Nickname, Language, ColorSchema, Avatar *string
}

// ChangePasswordInput is a password change request.
type ChangePasswordInput struct{ Current, New string }

// User implements profile settings and password change.
type User struct{}

// NewUser wires the service.
func NewUser(UserStore, *Limiter, server.Config) *User { return &User{} }

// UpdateSetting is not implemented yet.
func (*User) UpdateSetting(context.Context, string, SettingInput) (Profile, error) {
	return Profile{}, errNotImplemented
}

// ChangePassword is not implemented yet.
func (*User) ChangePassword(context.Context, string, ChangePasswordInput) error {
	return errNotImplemented
}
