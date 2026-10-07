//go:build integration

package service

import (
	"context"
	"errors"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/testutil"
)

var (
	apiTokenShape  = regexp.MustCompile(`^ragflow-[A-Za-z0-9_-]{43}$`)
	betaTokenShape = regexp.MustCompile(`^[0-9a-f]{32}$`)
)

// tokenEnv adds the token service and the token-aware gate to the user fixture.
type tokenEnv struct {
	*userEnv
	tok  *Token
	gate *Auth
}

func newTokenEnv(t *testing.T, limits *TokenLimits) *tokenEnv {
	t.Helper()
	u := newUserEnv(t, nil)
	l := DefaultTokenLimits()
	if limits != nil {
		l = *limits
	}
	e := &tokenEnv{
		userEnv: u,
		tok:     NewToken(u.db, NewLimiter(dao.OpenRedis(u.cfg.Redis), "test-"+testutil.UniqueName("tok")), l),
		gate:    NewAuth(u.db, u.cfg.Security.SecretKey, u.cfg.Security.TokenMaxAge).WithTokens(u.db),
	}
	t.Cleanup(func() {
		for _, id := range e.ids {
			_ = e.raw.Exec("DELETE FROM api_token WHERE tenant_id = ?", id).Error
		}
	})
	return e
}

// owner registers a user and returns the session principal and the user id.
func (e *tokenEnv) owner(t *testing.T) Principal {
	t.Helper()
	email := testutil.UniqueEmail("tok")
	e.register(t, email, testutil.FixtureCredential())
	p, err := e.gate.ResolvePrincipal(context.Background(), e.login(t, email, testutil.FixtureCredential()).Token, []string{AuthTypeJWT})
	require.NoError(t, err)
	return p
}

func (e *tokenEnv) create(t *testing.T, p Principal) APIToken {
	t.Helper()
	tok, err := e.tok.Create(context.Background(), p)
	require.NoError(t, err)
	return tok
}

func (e *tokenEnv) rows(t *testing.T, tenant string) []entity.APIToken {
	t.Helper()
	var rows []entity.APIToken
	require.NoError(t, e.raw.Where("tenant_id = ?", tenant).Find(&rows).Error)
	return rows
}

func TestCreateTokenFormatAndStorage(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	first, second := e.create(t, p), e.create(t, p)
	for _, tok := range []APIToken{first, second} {
		assert.Regexp(t, apiTokenShape, tok.Token)
		assert.Regexp(t, betaTokenShape, tok.Beta)
		assert.NotZero(t, tok.CreateTime)
	}
	assert.NotEqual(t, first.Token, second.Token)
	assert.NotEqual(t, first.Beta, second.Beta)
	rows := e.rows(t, p.TenantID)
	require.Len(t, rows, 2, "rows are stored for the caller's own tenant")
	for _, r := range rows {
		assert.Equal(t, p.TenantID, r.TenantID)
		require.NotNil(t, r.Beta)
		assert.Regexp(t, betaTokenShape, *r.Beta)
		assert.Nil(t, r.DialogID)
	}
}

func TestListIsTenantScopedAndNewestFirst(t *testing.T) {
	e := newTokenEnv(t, nil)
	a, b := e.owner(t), e.owner(t)
	base := time.Now()
	for i, p := range []Principal{a, a, b} {
		at := base.Add(time.Duration(i) * time.Second)
		e.tok.now = func() time.Time { return at }
		e.create(t, p)
	}
	got, err := e.tok.List(context.Background(), a, 1, 50)
	require.NoError(t, err)
	require.Len(t, got, 2)
	assert.Greater(t, got[0].CreateTime, got[1].CreateTime, "newest first")
	for _, g := range got {
		for _, r := range e.rows(t, b.TenantID) {
			assert.NotEqual(t, r.Token, g.Token, "another tenant's token must never be listed")
		}
	}
	other, err := e.tok.List(context.Background(), b, 1, 50)
	require.NoError(t, err)
	assert.Len(t, other, 1)
}

func TestListPaginationBounds(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	for i := 0; i < 3; i++ {
		e.create(t, p)
	}
	page1, err := e.tok.List(context.Background(), p, 1, 2)
	require.NoError(t, err)
	page2, err := e.tok.List(context.Background(), p, 2, 2)
	require.NoError(t, err)
	assert.Len(t, page1, 2)
	assert.Len(t, page2, 1)
	for _, bad := range [][2]int{{0, 10}, {-1, 10}, {1, 0}, {1, -5}, {1, MaxTokenPageSize + 1}} {
		_, err := e.tok.List(context.Background(), p, bad[0], bad[1])
		var ve *ValidationError
		assert.True(t, errors.As(err, &ve), "page %d size %d must be rejected", bad[0], bad[1])
	}
}

func TestDeleteOwnTokenStopsItWorking(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	_, err := e.gate.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT, AuthTypeAPI})
	require.NoError(t, err)
	require.NoError(t, e.tok.Delete(context.Background(), p, tok.Token))
	assert.Empty(t, e.rows(t, p.TenantID))
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated, "a deleted token authenticates nowhere")
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Beta, []string{AuthTypeBeta, AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated, "the beta value goes with the row")
	assert.ErrorIs(t, e.tok.Delete(context.Background(), p, tok.Token), ErrTokenNotFound, "a second delete is not-found")
}

func TestDeleteForeignTokenIsNotFoundAndChangesNothing(t *testing.T) {
	e := newTokenEnv(t, nil)
	a, b := e.owner(t), e.owner(t)
	mine := e.create(t, a)
	foreign := e.tok.Delete(context.Background(), b, mine.Token)
	missing := e.tok.Delete(context.Background(), b, "ragflow-"+strings.Repeat("A", 43))
	assert.ErrorIs(t, foreign, ErrTokenNotFound)
	assert.ErrorIs(t, missing, ErrTokenNotFound)
	assert.Equal(t, missing.Error(), foreign.Error(), "foreign and nonexistent are indistinguishable")
	assert.Len(t, e.rows(t, a.TenantID), 1, "the row is untouched")
	// A case-variant of a real token is a different value.
	assert.ErrorIs(t, e.tok.Delete(context.Background(), a, strings.ToUpper(mine.Token)), ErrTokenNotFound)
	assert.Len(t, e.rows(t, a.TenantID), 1)
	for _, bad := range []string{"", strings.Repeat("a", 300), "ragflow-%", "%"} {
		assert.ErrorIs(t, e.tok.Delete(context.Background(), a, bad), ErrTokenNotFound, "%q", bad)
	}
	assert.Len(t, e.rows(t, a.TenantID), 1, "no pattern delete")
}

func TestManagementNeedsSessionOwnerPrincipal(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	for name, bad := range map[string]Principal{
		"api credential":  {UserID: p.UserID, TenantID: p.TenantID, Role: "owner", AuthType: AuthTypeAPI},
		"beta credential": {UserID: p.UserID, TenantID: p.TenantID, Role: "owner", AuthType: AuthTypeBeta},
		"no workspace":    {UserID: p.UserID, AuthType: AuthTypeJWT},
		"normal member":   {UserID: p.UserID, TenantID: p.TenantID, Role: "normal", AuthType: AuthTypeJWT},
		"admin member":    {UserID: p.UserID, TenantID: p.TenantID, Role: "admin", AuthType: AuthTypeJWT},
	} {
		_, err := e.tok.Create(context.Background(), bad)
		assert.ErrorIs(t, err, ErrForbidden, "create: %s", name)
		_, err = e.tok.List(context.Background(), bad, 1, 10)
		assert.ErrorIs(t, err, ErrForbidden, "list: %s", name)
		assert.ErrorIs(t, e.tok.Delete(context.Background(), bad, tok.Token), ErrForbidden, "delete: %s", name)
	}
	assert.Len(t, e.rows(t, p.TenantID), 1)
}

func TestCreationIsCappedPerTenantAndRateLimited(t *testing.T) {
	capped := newTokenEnv(t, &TokenLimits{CreatePerWindow: 100, Window: time.Hour, MaxPerTenant: 2})
	p := capped.owner(t)
	capped.create(t, p)
	capped.create(t, p)
	_, err := capped.tok.Create(context.Background(), p)
	assert.ErrorIs(t, err, ErrTokenLimit)
	assert.Len(t, capped.rows(t, p.TenantID), 2)
	other := capped.owner(t)
	capped.create(t, other)

	limited := newTokenEnv(t, &TokenLimits{CreatePerWindow: 2, Window: time.Hour, MaxPerTenant: 50})
	q := limited.owner(t)
	limited.create(t, q)
	limited.create(t, q)
	_, err = limited.tok.Create(context.Background(), q)
	_, isLimited := IsRateLimited(err)
	assert.True(t, isLimited, "third creation inside the window is rate limited: %v", err)
	assert.Len(t, limited.rows(t, q.TenantID), 2)
}

func TestConcurrentCreationNeverExceedsTheCap(t *testing.T) {
	e := newTokenEnv(t, &TokenLimits{CreatePerWindow: 100, Window: time.Hour, MaxPerTenant: 3})
	p := e.owner(t)
	done := make(chan error, 8)
	for i := 0; i < 8; i++ {
		go func() { _, err := e.tok.Create(context.Background(), p); done <- err }()
	}
	for i := 0; i < 8; i++ {
		if err := <-done; err != nil {
			require.ErrorIs(t, err, ErrTokenLimit)
		}
	}
	assert.Len(t, e.rows(t, p.TenantID), 3)
}

func TestAPITokenResolvesToOwningTenantOnApiRoutesOnly(t *testing.T) {
	e := newTokenEnv(t, nil)
	p, other := e.owner(t), e.owner(t)
	tok := e.create(t, p)
	e.create(t, other)

	got, err := e.gate.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT, AuthTypeAPI})
	require.NoError(t, err)
	assert.Equal(t, p.TenantID, got.TenantID)
	assert.Equal(t, p.UserID, got.UserID)
	assert.Equal(t, AuthTypeAPI, got.AuthType)
	assert.False(t, got.IsSuperuser, "a token never carries superuser rights")

	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT})
	assert.ErrorIs(t, err, ErrUnauthenticated, "jwt-only routes refuse API tokens")
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Beta, []string{AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated, "the beta value is not an API token")
}

func TestAccessTokenStillPassesApiRoutes(t *testing.T) {
	e := newTokenEnv(t, nil)
	email := testutil.UniqueEmail("both")
	e.register(t, email, testutil.FixtureCredential())
	access := e.login(t, email, testutil.FixtureCredential()).Token
	got, err := e.gate.ResolvePrincipal(context.Background(), access, []string{AuthTypeJWT, AuthTypeAPI})
	require.NoError(t, err)
	assert.Equal(t, AuthTypeJWT, got.AuthType)
}

func TestBetaTokenResolvesOnlyOnBetaRoutes(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	beta := []string{AuthTypeBeta, AuthTypeJWT, AuthTypeAPI}

	got, err := e.gate.ResolvePrincipal(context.Background(), tok.Beta, beta)
	require.NoError(t, err)
	assert.Equal(t, p.TenantID, got.TenantID)
	assert.Equal(t, AuthTypeBeta, got.AuthType)
	assert.False(t, got.IsSuperuser)
	// beta routes also accept an API token, as the reference does
	viaAPI, err := e.gate.ResolvePrincipal(context.Background(), tok.Token, beta)
	require.NoError(t, err)
	assert.Equal(t, AuthTypeAPI, viaAPI.AuthType)

	for name, credential := range map[string]string{
		"wrong":        strings.Repeat("0", 32),
		"empty":        "",
		"too short":    tok.Beta[:31],
		"too long":     tok.Beta + "0",
		"with percent": "%" + tok.Beta[1:],
	} {
		_, err := e.gate.ResolvePrincipal(context.Background(), credential, beta)
		assert.ErrorIs(t, err, ErrUnauthenticated, name)
	}
	if upper := strings.ToUpper(tok.Beta); upper != tok.Beta {
		_, err = e.gate.ResolvePrincipal(context.Background(), upper, beta)
		assert.ErrorIs(t, err, ErrUnauthenticated, "MySQL collation must not make the match case-insensitive")
	}
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Beta, []string{AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated, "api routes refuse the beta value")
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Beta, []string{AuthTypeJWT})
	assert.ErrorIs(t, err, ErrUnauthenticated, "jwt routes refuse the beta value")
}

func TestTokenOfDisabledOwnerIsRefused(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	require.NoError(t, e.raw.Exec("UPDATE user SET status = '0' WHERE id = ?", p.UserID).Error)
	_, err := e.gate.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated)
	_, err = e.gate.ResolvePrincipal(context.Background(), tok.Beta, []string{AuthTypeBeta})
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestMalformedCredentialsNeverReachTheDatabase(t *testing.T) {
	e := newTokenEnv(t, nil)
	require.NoError(t, e.db.Close())
	for name, credential := range map[string]string{
		"empty":        "",
		"wrong prefix": "token-" + strings.Repeat("a", 43),
		"over long":    "ragflow-" + strings.Repeat("a", 2000),
		"api too long": "ragflow-" + strings.Repeat("a", 250),
		"short beta":   strings.Repeat("a", 31),
		"garbage":      "not a token at all",
	} {
		_, err := e.gate.ResolvePrincipal(context.Background(), credential, []string{AuthTypeBeta, AuthTypeJWT, AuthTypeAPI})
		assert.ErrorIs(t, err, ErrUnauthenticated, "%s is rejected without a database call (a closed pool would return another error)", name)
	}
}

func TestDatabaseOutageIsAnInfrastructureErrorNot401(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	require.NoError(t, e.db.Close())
	for _, credential := range []string{tok.Token, tok.Beta} {
		_, err := e.gate.ResolvePrincipal(context.Background(), credential, []string{AuthTypeBeta, AuthTypeJWT, AuthTypeAPI})
		require.Error(t, err)
		assert.NotErrorIs(t, err, ErrUnauthenticated, "R-114: a dependency failure is never a credential verdict")
	}
}

func TestGateWithoutTokenStoreRefusesApiAndBeta(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	tok := e.create(t, p)
	bare := NewAuth(e.db, e.cfg.Security.SecretKey, e.cfg.Security.TokenMaxAge)
	_, err := bare.ResolvePrincipal(context.Background(), tok.Token, []string{AuthTypeJWT, AuthTypeAPI})
	assert.ErrorIs(t, err, ErrUnauthenticated)
}
