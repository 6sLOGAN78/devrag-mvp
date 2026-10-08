package service

import (
	"context"
	"crypto/subtle"
	"errors"
	"slices"
	"strings"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
)

const (
	// AuthTypeJWT is the signed access-token credential type.
	AuthTypeJWT = "jwt"
	// AuthTypeAPI is an api_token.token credential (AUTH-22).
	AuthTypeAPI = "api"
	// AuthTypeBeta is an api_token.beta credential, accepted only on beta routes (AUTH-23).
	AuthTypeBeta = "beta"

	// maxCredentialLength bounds any credential before any work is done on it.
	maxCredentialLength = 1024
	activeStatus        = "1"
)

// ErrUnauthenticated is returned for every credential failure. Any other error from
// ResolvePrincipal is an infrastructure failure and must not be reported as 401 (R-114).
var ErrUnauthenticated = errors.New("unauthenticated")

// Principal is the authenticated caller.
type Principal struct {
	UserID      string
	TenantID    string
	Role        string
	AuthType    string
	IsSuperuser bool
}

// AuthStore is the persistence surface of credential resolution. dao.DB satisfies it.
type AuthStore interface {
	FindUserByAccessToken(ctx context.Context, token string) (*entity.User, error)
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	FindOwnMembership(ctx context.Context, userID string) (*entity.UserTenant, error)
	FindTenant(ctx context.Context, id string) (*entity.Tenant, error)
	SetAccessToken(ctx context.Context, userID, token string) error
}

// TokenLookup is the API-token side of credential resolution. dao.DB satisfies it. Both methods match
// the exact value only, and return dao.ErrNotFound when there is no such row.
type TokenLookup interface {
	FindAPIToken(ctx context.Context, token string) (*entity.APIToken, error)
	FindAPITokenByBeta(ctx context.Context, beta string) (*entity.APIToken, error)
}

// Auth resolves credentials to principals and signs users out.
type Auth struct {
	store  AuthStore
	tokens TokenLookup
	secret string
	maxAge time.Duration
	now    func() time.Time
}

// WithTokens enables the api and beta credential types. Without it only jwt credentials resolve.
func (a *Auth) WithTokens(t TokenLookup) *Auth {
	a.tokens = t
	return a
}

// NewAuth wires the service. maxAge is the access-token lifetime (30 days, D-11).
func NewAuth(store AuthStore, secret string, maxAge time.Duration) *Auth {
	return &Auth{store: store, secret: secret, maxAge: maxAge, now: time.Now}
}

// ResolvePrincipal resolves a credential for a route that accepts the listed types. It tries, in the
// documented order, a beta value (only when "beta" is allowed), an access token ("jwt") and an API token
// ("api"). Cheap checks (length, signature, 30-day age, AUTH-08, value shape) run before any database
// call. Every credential failure is ErrUnauthenticated; any other error is an infrastructure failure and
// must not be reported as 401 (R-114).
func (a *Auth) ResolvePrincipal(ctx context.Context, credential string, allowed []string) (Principal, error) {
	if credential == "" || len(credential) > maxCredentialLength {
		return Principal{}, ErrUnauthenticated
	}
	if a.tokens != nil && slices.Contains(allowed, AuthTypeBeta) && looksLikeBetaToken(credential) {
		row, err := a.tokens.FindAPITokenByBeta(ctx, credential)
		switch {
		case err == nil:
			if row.Beta != nil && subtle.ConstantTimeCompare([]byte(*row.Beta), []byte(credential)) == 1 {
				return a.tokenPrincipal(ctx, row, AuthTypeBeta)
			}
		case !errors.Is(err, dao.ErrNotFound):
			return Principal{}, err
		}
	}
	if slices.Contains(allowed, AuthTypeJWT) {
		if inner, err := common.VerifyAccessToken(credential, a.secret, a.maxAge, a.now()); err == nil && common.ValidInner(inner) {
			return a.sessionPrincipal(ctx, inner)
		}
	}
	if a.tokens != nil && slices.Contains(allowed, AuthTypeAPI) && looksLikeAPIToken(credential) {
		row, err := a.tokens.FindAPIToken(ctx, credential)
		switch {
		case err == nil:
			if subtle.ConstantTimeCompare([]byte(row.Token), []byte(credential)) == 1 {
				return a.tokenPrincipal(ctx, row, AuthTypeAPI)
			}
		case !errors.Is(err, dao.ErrNotFound):
			return Principal{}, err
		}
	}
	return Principal{}, ErrUnauthenticated
}

// looksLikeAPIToken is the pre-database shape check of an API token (same rule as the Python gate).
func looksLikeAPIToken(c string) bool {
	return strings.HasPrefix(c, APITokenPrefix) && len(c) <= MaxAPITokenLength
}

// looksLikeBetaToken is the pre-database shape check of a beta value: exactly 32 ASCII letters or digits.
func looksLikeBetaToken(c string) bool {
	if len(c) != BetaTokenLength {
		return false
	}
	for i := 0; i < len(c); i++ {
		ch := c[i]
		if (ch < '0' || ch > '9') && (ch < 'a' || ch > 'z') && (ch < 'A' || ch > 'Z') {
			return false
		}
	}
	return true
}

// sessionPrincipal re-reads the user row on every request; its stored token must equal the inner value
// exactly (D-11, AUTH-12).
func (a *Auth) sessionPrincipal(ctx context.Context, inner string) (Principal, error) {
	user, err := a.store.FindUserByAccessToken(ctx, inner)
	if errors.Is(err, dao.ErrNotFound) {
		return Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Principal{}, err
	}
	if user.AccessToken == nil || subtle.ConstantTimeCompare([]byte(*user.AccessToken), []byte(inner)) != 1 {
		return Principal{}, ErrUnauthenticated
	}
	if user.Status == nil || *user.Status != activeStatus {
		return Principal{}, ErrUnauthenticated
	}
	p := Principal{UserID: user.ID, AuthType: AuthTypeJWT, IsSuperuser: user.IsSuperuser != nil && *user.IsSuperuser}
	return a.withMembership(ctx, p)
}

// tokenPrincipal makes an API or beta token act as the user whose id equals the token's tenant id, in
// that tenant, and nothing wider: it never carries superuser rights. A disabled owner voids the token.
func (a *Auth) tokenPrincipal(ctx context.Context, row *entity.APIToken, authType string) (Principal, error) {
	owner, err := a.store.FindUserByID(ctx, row.TenantID)
	if errors.Is(err, dao.ErrNotFound) {
		return Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Principal{}, err
	}
	if owner.Status == nil || *owner.Status != activeStatus {
		return Principal{}, ErrUnauthenticated
	}
	p, err := a.withMembership(ctx, Principal{UserID: owner.ID, AuthType: authType})
	if err != nil {
		return Principal{}, err
	}
	p.TenantID = row.TenantID
	return p, nil
}

// withMembership fills the tenant and role from the user's own-workspace membership.
func (a *Auth) withMembership(ctx context.Context, p Principal) (Principal, error) {
	m, err := a.store.FindOwnMembership(ctx, p.UserID)
	switch {
	case err == nil:
		p.TenantID, p.Role = m.TenantID, m.Role
	case errors.Is(err, dao.ErrNotFound):
		// no own workspace: the principal carries no tenant
	default:
		return Principal{}, err
	}
	return p, nil
}

// Logout rewrites the stored token to INVALID_<random hex>, which signs the user out of every
// device because all devices share one token (D-10).
func (a *Auth) Logout(ctx context.Context, userID string) error {
	token, err := newInvalidToken()
	if err != nil {
		return err
	}
	if err := a.store.SetAccessToken(ctx, userID, token); err != nil {
		return dbFailure("sign out", err)
	}
	return nil
}

// UserInfo is the session payload of GET /v1/user/info.
type UserInfo struct {
	ID, Nickname, Email, Avatar, Language, ColorSchema, TenantID, TenantName, Role string
	IsSuperuser                                                                    bool
}

// UserInfo reads the caller's profile and own workspace.
func (a *Auth) UserInfo(ctx context.Context, p Principal) (UserInfo, error) {
	u, err := a.store.FindUserByID(ctx, p.UserID)
	if errors.Is(err, dao.ErrNotFound) {
		return UserInfo{}, ErrUnauthenticated
	}
	if err != nil {
		return UserInfo{}, dbFailure("profile lookup", err)
	}
	info := UserInfo{
		ID: u.ID, Nickname: u.Nickname, Email: u.Email, Avatar: deref(u.Avatar), Language: NormaliseLanguage(deref(u.Language)),
		ColorSchema: deref(u.ColorSchema), TenantID: p.TenantID, Role: p.Role, IsSuperuser: p.IsSuperuser,
	}
	if p.TenantID != "" {
		t, err := a.store.FindTenant(ctx, p.TenantID)
		if err != nil && !errors.Is(err, dao.ErrNotFound) {
			return UserInfo{}, dbFailure("tenant lookup", err)
		}
		if err == nil {
			info.TenantName = deref(t.Name)
		}
	}
	return info, nil
}
