package service

import (
	"context"
	"crypto/subtle"
	"errors"
	"slices"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
)

// AuthTypeJWT is the signed access-token credential type.
const AuthTypeJWT = "jwt"

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

// Auth resolves credentials to principals and signs users out.
type Auth struct {
	store  AuthStore
	secret string
	maxAge time.Duration
	now    func() time.Time
}

// NewAuth wires the service. maxAge is the access-token lifetime (30 days, D-11).
func NewAuth(store AuthStore, secret string, maxAge time.Duration) *Auth {
	return &Auth{store: store, secret: secret, maxAge: maxAge, now: time.Now}
}

// ResolvePrincipal accepts a jwt credential only when allowed lists "jwt". The signature, the
// 30-day age and AUTH-08 are checked before any database call; the user row is then re-read on
// every request and its stored token must equal the inner value exactly (D-11, AUTH-12).
func (a *Auth) ResolvePrincipal(ctx context.Context, credential string, allowed []string) (Principal, error) {
	if !slices.Contains(allowed, AuthTypeJWT) {
		return Principal{}, ErrUnauthenticated
	}
	inner, err := common.VerifyAccessToken(credential, a.secret, a.maxAge, a.now())
	if err != nil || !common.ValidInner(inner) {
		return Principal{}, ErrUnauthenticated
	}
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
	if user.Status == nil || *user.Status != "1" {
		return Principal{}, ErrUnauthenticated
	}
	p := Principal{UserID: user.ID, AuthType: AuthTypeJWT, IsSuperuser: user.IsSuperuser != nil && *user.IsSuperuser}
	m, err := a.store.FindOwnMembership(ctx, user.ID)
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
	return a.store.SetAccessToken(ctx, userID, token)
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
		return UserInfo{}, err
	}
	info := UserInfo{
		ID: u.ID, Nickname: u.Nickname, Email: u.Email, Avatar: deref(u.Avatar), Language: NormaliseLanguage(deref(u.Language)),
		ColorSchema: deref(u.ColorSchema), TenantID: p.TenantID, Role: p.Role, IsSuperuser: p.IsSuperuser,
	}
	if p.TenantID != "" {
		t, err := a.store.FindTenant(ctx, p.TenantID)
		if err != nil && !errors.Is(err, dao.ErrNotFound) {
			return UserInfo{}, err
		}
		if err == nil {
			info.TenantName = deref(t.Name)
		}
	}
	return info, nil
}
