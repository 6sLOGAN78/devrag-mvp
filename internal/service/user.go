package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"strings"
	"unicode"
	"unicode/utf8"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

// ErrCurrentPasswordIncorrect means the current password did not verify. The caller is signed in,
// so this is a 400 and never a 401 (a 401 would sign the browser out).
var ErrCurrentPasswordIncorrect = errors.New("current password is incorrect")

// Language codes shipped in the SPA (R-98) and the colour schemes of the stored vocabulary.
const (
	languageEnglish = "en"
	languageChinese = "zh"
	colourBright    = "Bright"
	colourDark      = "Dark"
)

// UserStore is the persistence surface of profile and password changes. dao.DB satisfies it.
type UserStore interface {
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	UpdateProfile(ctx context.Context, userID string, u dao.ProfileUpdate) error
	ReplacePassword(ctx context.Context, userID, oldHash, newHash, token string) (bool, error)
}

// SettingInput carries the optional profile fields; nil means unchanged and an empty Avatar removes it.
type SettingInput struct {
	Nickname, Language, ColorSchema, Avatar *string
}

// ChangePasswordInput is a password change request.
type ChangePasswordInput struct{ Current, New string }

// User implements profile settings and password change.
type User struct {
	store   UserStore
	limiter *Limiter
	cfg     server.Config
}

// NewUser wires the service.
func NewUser(store UserStore, limiter *Limiter, cfg server.Config) *User {
	return &User{store: store, limiter: limiter, cfg: cfg}
}

// NormaliseLanguage maps a stored language to a shipped locale code. Legacy labels (English,
// Chinese) read as codes; anything unknown or empty reads as en.
func NormaliseLanguage(v string) string {
	lower := strings.ToLower(strings.TrimSpace(v))
	if lower == "chinese" || lower == languageChinese || strings.HasPrefix(lower, languageChinese+"-") {
		return languageChinese
	}
	return languageEnglish
}

// parseLanguage is the strict write-side rule: only a shipped locale (or its legacy label).
func parseLanguage(v string) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "en", "english":
		return languageEnglish, true
	case "zh", "chinese":
		return languageChinese, true
	}
	return "", false
}

func parseColourSchema(v string) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "bright":
		return colourBright, true
	case "dark":
		return colourDark, true
	}
	return "", false
}

// validNickname trims and checks a nickname: 1 to 64 characters, valid UTF-8, no control, format
// (for example bidirectional override) or angle-bracket characters.
func validNickname(raw string) (string, error) {
	n := strings.TrimSpace(raw)
	count := utf8.RuneCountInString(n)
	if !utf8.ValidString(n) || count < 1 || count > maxNicknameLength {
		return "", &ValidationError{Msg: "nickname must be 1 to 64 characters"}
	}
	for _, r := range n {
		if unicode.IsControl(r) || unicode.Is(unicode.Cf, r) || r == '<' || r == '>' {
			return "", &ValidationError{Msg: "nickname contains characters that are not allowed"}
		}
	}
	return n, nil
}

// UpdateSetting validates every supplied field, then writes them in one statement. The user id is
// the authenticated caller's: nothing in the input can name another account.
func (u *User) UpdateSetting(ctx context.Context, userID string, in SettingInput) (Profile, error) {
	var upd dao.ProfileUpdate
	if in.Nickname != nil {
		n, err := validNickname(*in.Nickname)
		if err != nil {
			return Profile{}, err
		}
		upd.Nickname = &n
	}
	if in.Language != nil {
		l, ok := parseLanguage(*in.Language)
		if !ok {
			return Profile{}, &ValidationError{Msg: "language must be en or zh"}
		}
		upd.Language = &l
	}
	if in.ColorSchema != nil {
		c, ok := parseColourSchema(*in.ColorSchema)
		if !ok {
			return Profile{}, &ValidationError{Msg: "color_schema must be Bright or Dark"}
		}
		upd.ColorSchema = &c
	}
	if in.Avatar != nil {
		if *in.Avatar != "" {
			if err := ValidateAvatarDataURL(*in.Avatar); err != nil {
				return Profile{}, &ValidationError{Msg: err.Error()}
			}
		}
		a := *in.Avatar
		upd.Avatar = &a
	}
	if upd == (dao.ProfileUpdate{}) {
		return Profile{}, &ValidationError{Msg: "no profile field was supplied"}
	}
	if err := u.store.UpdateProfile(ctx, userID, upd); err != nil {
		return Profile{}, err
	}
	row, err := u.store.FindUserByID(ctx, userID)
	if errors.Is(err, dao.ErrNotFound) {
		return Profile{}, ErrUnauthenticated
	}
	if err != nil {
		return Profile{}, err
	}
	return Profile{ID: row.ID, Email: row.Email, Nickname: row.Nickname, Language: NormaliseLanguage(deref(row.Language)), ColorSchema: deref(row.ColorSchema)}, nil
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// ChangePassword verifies the current password, stores a new hash and rewrites the shared access
// token to INVALID_<hex> in the same transaction, so every device is signed out (D-08). Failed
// verifications count against a per-user limit that uses the login-failure numbers of the RateLimit
// configuration; the limiter fails closed. Hash work goes through the shared PBKDF2 semaphore.
func (u *User) ChangePassword(ctx context.Context, userID string, in ChangePasswordInput) error {
	if err := common.ValidatePasswordLength(in.New); err != nil {
		return &ValidationError{Msg: "new " + err.Error()}
	}
	rl := u.cfg.RateLimit
	key := "pwchange:user:" + userID
	// The attempt is counted atomically before the password is checked, so parallel guesses cannot
	// exceed the cap (WR-01); a success clears the counter below.
	if err := u.limiter.Hit(ctx, key, rl.LoginFailuresPerEmail, window(rl.LoginWindowSeconds)); err != nil {
		return err
	}
	user, err := u.store.FindUserByID(ctx, userID)
	if errors.Is(err, dao.ErrNotFound) {
		return ErrUnauthenticated
	}
	if err != nil {
		return err
	}
	if user.Password == nil || in.Current == "" || !common.VerifyPassword(in.Current, *user.Password) {
		return ErrCurrentPasswordIncorrect
	}
	hash, err := common.HashPassword(in.New)
	if err != nil {
		return err
	}
	token, err := newInvalidToken()
	if err != nil {
		return err
	}
	swapped, err := u.store.ReplacePassword(ctx, userID, *user.Password, hash, token)
	if err != nil {
		return err
	}
	if !swapped {
		// A concurrent change replaced the password between the read and the write.
		return ErrCurrentPasswordIncorrect
	}
	return u.limiter.Reset(ctx, key)
}

// newInvalidToken returns a value that can never verify as an access token: INVALID_<random hex>.
func newInvalidToken() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return "INVALID_" + hex.EncodeToString(b[:]), nil
}
