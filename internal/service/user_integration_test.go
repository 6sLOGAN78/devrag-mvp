//go:build integration

package service

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

// userEnv adds the profile and password services to the account fixture.
type userEnv struct {
	*accountEnv
	user *User
	auth *Auth
}

func newUserEnv(t *testing.T, mutate func(*server.Config)) *userEnv {
	t.Helper()
	e := newAccountEnv(t, mutate)
	return &userEnv{
		accountEnv: e,
		user:       NewUser(e.db, e.svc.limiter, e.cfg),
		auth:       NewAuth(e.db, e.cfg.Security.SecretKey, e.cfg.Security.TokenMaxAge),
	}
}

func (e *userEnv) login(t *testing.T, email, password string) LoginResult {
	t.Helper()
	res, err := e.svc.Login(context.Background(), LoginInput{Email: email, Password: password, ClientIP: "203.0.113.2"})
	require.NoError(t, err)
	return res
}

func (e *userEnv) row(t *testing.T, id string) entity.User {
	t.Helper()
	var u entity.User
	require.NoError(t, e.raw.First(&u, "id = ?", id).Error)
	return u
}

func str(s string) *string { return &s }

func TestUpdateSettingPersistsAndInfoShowsIt(t *testing.T) {
	e := newUserEnv(t, nil)
	email := testutil.UniqueEmail("set")
	p := e.register(t, email, testutil.FixtureCredential())
	tok := e.login(t, email, testutil.FixtureCredential()).Token

	got, err := e.user.UpdateSetting(context.Background(), p.ID, SettingInput{Nickname: str("  Ada Lovelace  "), Language: str("zh"), ColorSchema: str("Dark")})
	require.NoError(t, err)
	assert.Equal(t, "Ada Lovelace", got.Nickname)

	pr, err := e.auth.ResolvePrincipal(context.Background(), tok, []string{AuthTypeJWT})
	require.NoError(t, err)
	info, err := e.auth.UserInfo(context.Background(), pr)
	require.NoError(t, err)
	assert.Equal(t, "Ada Lovelace", info.Nickname)
	assert.Equal(t, "zh", info.Language)
	assert.Equal(t, "Dark", info.ColorSchema)
	assert.Equal(t, strings.ToLower(email), info.Email, "email is not a profile field")
}

func TestUpdateSettingLeavesUnsentFieldsAlone(t *testing.T) {
	e := newUserEnv(t, nil)
	p := e.register(t, testutil.UniqueEmail("part"), testutil.FixtureCredential())
	before := e.row(t, p.ID)
	_, err := e.user.UpdateSetting(context.Background(), p.ID, SettingInput{ColorSchema: str("Dark")})
	require.NoError(t, err)
	after := e.row(t, p.ID)
	assert.Equal(t, before.Nickname, after.Nickname)
	assert.Equal(t, before.Language, after.Language)
	assert.Equal(t, before.Email, after.Email)
	assert.Equal(t, before.Password, after.Password)
	assert.Equal(t, "Dark", *after.ColorSchema)
}

func TestLegacyLanguageLabelsReadBackAsCodes(t *testing.T) {
	e := newUserEnv(t, nil)
	email := testutil.UniqueEmail("lang")
	p := e.register(t, email, testutil.FixtureCredential())
	tok := e.login(t, email, testutil.FixtureCredential()).Token
	pr, err := e.auth.ResolvePrincipal(context.Background(), tok, []string{AuthTypeJWT})
	require.NoError(t, err)
	for stored, want := range map[string]string{"English": "en", "Chinese": "zh", "en": "en", "zh": "zh", "Klingon": "en", "": "en"} {
		require.NoError(t, e.raw.Exec("UPDATE user SET language = ? WHERE id = ?", stored, p.ID).Error)
		info, err := e.auth.UserInfo(context.Background(), pr)
		require.NoError(t, err)
		assert.Equal(t, want, info.Language, "stored %q", stored)
	}
}

func TestUpdateSettingRejectsInvalidInput(t *testing.T) {
	e := newUserEnv(t, nil)
	p := e.register(t, testutil.UniqueEmail("bad"), testutil.FixtureCredential())
	before := e.row(t, p.ID)
	cases := map[string]SettingInput{
		"language fr":       {Language: str("fr")},
		"language script":   {Language: str("<script>")},
		"language empty":    {Language: str("")},
		"colour unknown":    {ColorSchema: str("Neon")},
		"nickname empty":    {Nickname: str("   ")},
		"nickname 65 runes": {Nickname: str(strings.Repeat("n", 65))},
		"nickname control":  {Nickname: str("a\x00b")},
		"nickname newline":  {Nickname: str("a\nb")},
		"nickname bidi":     {Nickname: str("a‮b")},
		"nickname tag":      {Nickname: str("<img src=x onerror=alert(1)>")},
		"nothing sent":      {},
		"avatar svg":        {Avatar: str(dataURL("image/svg+xml", []byte("<svg/>")))},
		"avatar html":       {Avatar: str(dataURL("image/png", []byte("<html></html>")))},
		"avatar oversize":   {Avatar: str(dataURL("image/png", pngBytes(MaxAvatarBytes+1)))},
	}
	for name, in := range cases {
		_, err := e.user.UpdateSetting(context.Background(), p.ID, in)
		var ve *ValidationError
		if assert.ErrorAs(t, err, &ve, name) {
			assert.NotContains(t, ve.Msg, "script", name)
		}
	}
	after := e.row(t, p.ID)
	assert.Equal(t, before.Nickname, after.Nickname, "nothing was written")
	assert.Equal(t, before.Language, after.Language)
	assert.Equal(t, before.ColorSchema, after.ColorSchema)
	assert.Equal(t, before.Avatar, after.Avatar)
}

func TestAvatarIsStoredAndCanBeRemoved(t *testing.T) {
	e := newUserEnv(t, nil)
	p := e.register(t, testutil.UniqueEmail("av"), testutil.FixtureCredential())
	url := dataURL("image/webp", webpBytes(2048))
	_, err := e.user.UpdateSetting(context.Background(), p.ID, SettingInput{Avatar: &url})
	require.NoError(t, err)
	require.NotNil(t, e.row(t, p.ID).Avatar)
	assert.Equal(t, url, *e.row(t, p.ID).Avatar)
	_, err = e.user.UpdateSetting(context.Background(), p.ID, SettingInput{Avatar: str("")})
	require.NoError(t, err)
	assert.Empty(t, e.row(t, p.ID).Avatar, "an empty avatar removes the image")
}

func TestChangePasswordWrongCurrentKeepsTokenAndHash(t *testing.T) {
	e := newUserEnv(t, nil)
	email := testutil.UniqueEmail("pw")
	p := e.register(t, email, testutil.FixtureCredential())
	tok := e.login(t, email, testutil.FixtureCredential()).Token
	before := e.row(t, p.ID)

	err := e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: "wrong-current-pass", New: "brand-new-pass-0002"})
	assert.ErrorIs(t, err, ErrCurrentPasswordIncorrect)
	after := e.row(t, p.ID)
	assert.Equal(t, before.Password, after.Password)
	assert.Equal(t, before.AccessToken, after.AccessToken)
	_, err = e.auth.ResolvePrincipal(context.Background(), tok, []string{AuthTypeJWT})
	assert.NoError(t, err, "a failed change keeps the session")
}

func TestChangePasswordLengthRules(t *testing.T) {
	e := newUserEnv(t, nil)
	p := e.register(t, testutil.UniqueEmail("len"), testutil.FixtureCredential())
	before := e.row(t, p.ID)
	for name, pw := range map[string]string{"7 characters": "abcdefg", "129 characters": strings.Repeat("a", 129), "empty": ""} {
		err := e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: pw})
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, name)
	}
	assert.Equal(t, before.Password, e.row(t, p.ID).Password)
	// the boundaries 8 and 128 are accepted
	require.NoError(t, e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: "abcdefgh"}))
	require.NoError(t, e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: "abcdefgh", New: strings.Repeat("a", 128)}))
}

func TestChangePasswordSignsEveryDeviceOut(t *testing.T) {
	e := newUserEnv(t, nil)
	email := testutil.UniqueEmail("out")
	p := e.register(t, email, testutil.FixtureCredential())
	tok := e.login(t, email, testutil.FixtureCredential()).Token
	newPw := "brand-new-pass-0002"

	require.NoError(t, e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: newPw}))

	row := e.row(t, p.ID)
	require.NotNil(t, row.AccessToken)
	assert.True(t, strings.HasPrefix(*row.AccessToken, "INVALID_"), "token rewritten in the same write as the hash")
	require.NotNil(t, row.Password)
	assert.True(t, strings.HasPrefix(*row.Password, "pbkdf2:sha256:600000$"))
	assert.True(t, common.VerifyPassword(newPw, *row.Password))
	assert.False(t, common.VerifyPassword(testutil.FixtureCredential(), *row.Password))

	_, err := e.auth.ResolvePrincipal(context.Background(), tok, []string{AuthTypeJWT})
	assert.ErrorIs(t, err, ErrUnauthenticated, "the old token is dead")
	_, err = e.svc.Login(context.Background(), LoginInput{Email: email, Password: testutil.FixtureCredential(), ClientIP: "203.0.113.3"})
	assert.ErrorIs(t, err, ErrInvalidCredentials, "the old password no longer works")
	fresh := e.login(t, email, newPw)
	assert.NotEqual(t, tok, fresh.Token)
	_, err = e.auth.ResolvePrincipal(context.Background(), fresh.Token, []string{AuthTypeJWT})
	assert.NoError(t, err)
}

func TestChangePasswordIsRateLimitedPerUser(t *testing.T) {
	e := newUserEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 3 })
	p := e.register(t, testutil.UniqueEmail("rl"), testutil.FixtureCredential())
	other := e.register(t, testutil.UniqueEmail("rl2"), testutil.FixtureCredential())
	for i := 0; i < 3; i++ {
		err := e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: "wrong-current-pass", New: "brand-new-pass-0002"})
		require.ErrorIs(t, err, ErrCurrentPasswordIncorrect)
	}
	err := e.user.ChangePassword(context.Background(), p.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: "brand-new-pass-0002"})
	rl, ok := IsRateLimited(err)
	require.True(t, ok, "the fourth attempt is locked even with the right password: %v", err)
	assert.Positive(t, rl.RetryAfter)
	assert.True(t, common.VerifyPassword(testutil.FixtureCredential(), *e.row(t, p.ID).Password), "the locked attempt changed nothing")
	// another user is unaffected
	require.NoError(t, e.user.ChangePassword(context.Background(), other.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: "brand-new-pass-0002"}))
}

func TestChangePasswordFailsClosedWithoutRedis(t *testing.T) {
	e := newUserEnv(t, nil)
	p := e.register(t, testutil.UniqueEmail("rd"), testutil.FixtureCredential())
	bad := e.cfg.Redis
	bad.Port = 1 // nothing listens here
	rd := dao.OpenRedis(bad)
	defer func() { _ = rd.Close() }()
	down := NewUser(e.db, NewLimiter(rd, "test-down"), e.cfg)
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	err := down.ChangePassword(ctx, p.ID, ChangePasswordInput{Current: testutil.FixtureCredential(), New: "brand-new-pass-0002"})
	assert.ErrorIs(t, err, ErrUnavailable)
	assert.True(t, common.VerifyPassword(testutil.FixtureCredential(), *e.row(t, p.ID).Password), "nothing was changed")
}
