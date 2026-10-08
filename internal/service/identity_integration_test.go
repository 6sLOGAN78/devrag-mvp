//go:build integration

package service

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

// spellings returns spellings of one ASCII address that MySQL's utf8mb4_unicode_ci collation treats
// as equal to it: accented, combining-mark, upper-case accented and fullwidth forms (CR-01).
func spellings(email string) []string {
	rest := email[1:]
	return []string{
		"á" + rest,                          // a with acute, precomposed
		"á" + rest,                         // a plus combining acute
		"à" + rest,                          // a with grave
		"Á" + rest,                          // upper-case A with acute
		"â" + rest,                          // a with circumflex
		"ａ" + rest,                          // fullwidth a (NFKC folds it to ASCII)
		"  " + strings.ToUpper(email) + " ", // padding and case
	}
}

func TestCollationAliasesOfOneAccountExist(t *testing.T) {
	// Precondition of the CR-01 tests: the database really does resolve these spellings to the account.
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("alias")
	p := e.register(t, email, testutil.FixtureCredential())
	for _, s := range spellings(email)[:5] {
		u, err := e.db.FindUserByEmail(context.Background(), s)
		require.NoError(t, err, "%q", s)
		assert.Equal(t, p.ID, u.ID)
	}
}

func TestSpellingsOfOneAccountShareOneLoginFailureCounter(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 3 })
	email := testutil.UniqueEmail("alice")
	e.register(t, email, testutil.FixtureCredential())
	sp := spellings(email)
	for i := 0; i < 3; i++ {
		_, err := login(e, sp[i], "wrong-password-1")
		require.ErrorIs(t, err, ErrInvalidCredentials, "failure %d through spelling %q", i+1, sp[i])
	}
	var rl *RateLimitedError
	for _, s := range append([]string{email}, sp[3:]...) {
		_, err := login(e, s, "wrong-password-1")
		assert.ErrorAs(t, err, &rl, "spelling %q must hit the account's lock", s)
	}
	_, err := login(e, email, testutil.FixtureCredential())
	assert.ErrorAs(t, err, &rl, "the lock is per account, not per spelling")
}

func TestUnknownAddressesStillGetTheirOwnCounter(t *testing.T) {
	e := newAccountEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 2 })
	ghost := testutil.UniqueEmail("ghost")
	for i := 0; i < 2; i++ {
		_, err := login(e, ghost, "wrong-password-1")
		require.ErrorIs(t, err, ErrInvalidCredentials)
	}
	var rl *RateLimitedError
	_, err := login(e, " "+strings.ToUpper(ghost), "wrong-password-1")
	assert.ErrorAs(t, err, &rl, "case and padding of an unknown address share its counter")
	_, err = login(e, testutil.UniqueEmail("other"), "wrong-password-1")
	assert.ErrorIs(t, err, ErrInvalidCredentials, "a different address is unaffected")
}

func TestSpellingsCannotRegisterAsSeparateAccounts(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("alice")
	e.register(t, email, testutil.FixtureCredential())
	for i, s := range spellings(email) {
		_, err := e.svc.Register(context.Background(), RegisterInput{Email: s, Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.9"})
		if common.CanonicalEmail(s) == email {
			assert.ErrorIs(t, err, ErrEmailTaken, "spelling %d folds to the registered address", i)
			continue
		}
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, "spelling %d is not a valid new address", i)
	}
	assert.EqualValues(t, 1, e.count(t, "user", "email", email), "exactly one account exists for the address")
}

func TestNonASCIIAddressesAreRefusedForNewAccounts(t *testing.T) {
	e := newAccountEnv(t, nil)
	for _, s := range []string{"álice-" + testutil.UniqueName("n") + "@example.test", "bob@exámple.test", "bo​b@example.test"} {
		_, err := e.svc.Register(context.Background(), RegisterInput{Email: s, Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.9"})
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, "%q", s)
	}
}

func TestFullwidthSpellingRegistersAsTheCanonicalASCIIAccount(t *testing.T) {
	e := newAccountEnv(t, nil)
	email := testutil.UniqueEmail("wide")
	p, err := e.svc.Register(context.Background(), RegisterInput{Email: "ｗ" + email[1:], Password: testutil.FixtureCredential(), Nickname: "n", ClientIP: "203.0.113.9"})
	require.NoError(t, err)
	e.ids = append(e.ids, p.ID)
	assert.Equal(t, email, p.Email)
}

func TestSpellingsOfOneAccountShareOneOTPBudget(t *testing.T) {
	e := newResetEnv(t, func(c *server.Config) { c.RateLimit.OTPPerEmailPerHour = 2 })
	email := testutil.UniqueEmail("alice")
	e.register(t, email, testutil.FixtureCredential())
	sp := spellings(email)
	ctx := context.Background()

	require.NoError(t, e.reset.RequestReset(ctx, email, "203.0.113.60"))
	var rl *RateLimitedError
	for _, s := range sp {
		assert.ErrorAs(t, e.reset.RequestReset(ctx, s, "203.0.113.60"), &rl, "interval is per account: %q", s)
	}

	e.clearInterval(t, email)
	require.NoError(t, e.reset.RequestReset(ctx, sp[0], "203.0.113.60"), "second request of the hour")
	e.clearInterval(t, email)
	for _, s := range []string{email, sp[1], sp[2]} {
		assert.ErrorAs(t, e.reset.RequestReset(ctx, s, "203.0.113.60"), &rl, "hourly cap of 2 is per account: %q", s)
	}
	assert.Equal(t, 2, len(e.queue.sent()), "exactly the budgeted mails were queued")
}

func TestSpellingsOfOneAccountShareOneOTPAttemptBudget(t *testing.T) {
	e := newResetEnv(t, nil)
	email := testutil.UniqueEmail("alice")
	e.register(t, email, testutil.FixtureCredential())
	sp := spellings(email)
	ctx := context.Background()
	code := e.request(t, sp[0]) // asked through an accented spelling, mailed to the stored address
	require.NotEmpty(t, code)
	wrong := wrongCode(code)
	for i := 0; i < 5; i++ {
		_, err := e.reset.VerifyCode(ctx, sp[i%len(sp)], wrong)
		require.ErrorIs(t, err, ErrOTPInvalid)
	}
	_, err := e.reset.VerifyCode(ctx, email, code)
	assert.ErrorIs(t, err, ErrOTPInvalid, "five wrong guesses through five spellings destroyed the one code")
}

func TestCodeRequestedThroughOneSpellingResetsThroughAnother(t *testing.T) {
	e := newResetEnv(t, nil)
	email := testutil.UniqueEmail("alice")
	p := e.register(t, email, testutil.FixtureCredential())
	sp := spellings(email)
	ctx := context.Background()
	code := e.request(t, sp[1])
	ticket, err := e.reset.VerifyCode(ctx, sp[2], code)
	require.NoError(t, err)
	require.NoError(t, e.reset.ResetPassword(ctx, ResetInput{Email: sp[4], Ticket: ticket, NewPassword: resetPassword}))
	e.login(t, email, resetPassword)
	_ = p
}

func TestResetClearsTheAccountLoginLockWhateverSpellingWasUsed(t *testing.T) {
	e := newResetEnv(t, func(c *server.Config) { c.RateLimit.LoginFailuresPerEmail = 2 })
	email := testutil.UniqueEmail("alice")
	e.register(t, email, testutil.FixtureCredential())
	sp := spellings(email)
	for i := 0; i < 2; i++ {
		_, err := login(e.accountEnv, sp[i], "wrong-password-1")
		require.ErrorIs(t, err, ErrInvalidCredentials)
	}
	code := e.request(t, email)
	require.NoError(t, e.reset.ResetPassword(context.Background(), ResetInput{Email: sp[3], Code: code, NewPassword: resetPassword}))
	e.login(t, email, resetPassword)
}
