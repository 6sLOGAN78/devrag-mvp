package service

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"devrag/internal/dao"
	"devrag/internal/entity"
)

const (
	// APITokenPrefix starts every API token (docs/apikey llm.md).
	APITokenPrefix = "ragflow-"
	// MaxAPITokenLength is the longest credential looked up as an API token (the column is varchar(255)).
	MaxAPITokenLength = 255
	// BetaTokenLength is the length of a beta token: a hyphen-stripped UUID, 32 hex characters.
	BetaTokenLength = 32
	// MaxTokenPageSize bounds one page of the token list.
	MaxTokenPageSize = 100

	apiTokenRandomBytes  = 32
	betaTokenRandomBytes = 16
	ownerRole            = "owner"
)

var (
	// ErrTokenNotFound is returned for a token that does not exist and for one that belongs to another
	// tenant; the two cases are deliberately indistinguishable (T-02-93).
	ErrTokenNotFound = errors.New("token not found")
	// ErrForbidden means the caller may not manage API tokens: only a session (jwt) principal that owns
	// its workspace may, never an API or beta credential (R-90, T-02-92).
	ErrForbidden = errors.New("forbidden")
	// ErrTokenLimit means the tenant already holds the maximum number of API tokens.
	ErrTokenLimit = errors.New("api token limit reached")
)

// TokenStore is the persistence surface of token management. dao.DB satisfies it.
type TokenStore interface {
	CreateAPIToken(ctx context.Context, row entity.APIToken, maxPerTenant int) error
	ListAPITokens(ctx context.Context, tenantID string, limit, offset int) ([]entity.APIToken, error)
	DeleteAPIToken(ctx context.Context, tenantID, token string) (bool, error)
}

// TokenLimits holds the creation rate limit and the per-tenant cap (R-121).
type TokenLimits struct {
	CreatePerWindow int
	Window          time.Duration
	MaxPerTenant    int
}

// DefaultTokenLimits returns 20 creations per hour per tenant and at most 50 tokens per tenant.
func DefaultTokenLimits() TokenLimits {
	return TokenLimits{CreatePerWindow: 20, Window: time.Hour, MaxPerTenant: 50}
}

// APIToken is a token as shown to its owner. dialog_id and source are not exposed.
type APIToken struct {
	Token      string
	Beta       string
	CreateTime int64
}

// Token creates, lists and deletes the API tokens of the caller's own tenant.
type Token struct {
	store   TokenStore
	limiter *Limiter
	limits  TokenLimits
	now     func() time.Time
}

// NewToken wires the service.
func NewToken(store TokenStore, limiter *Limiter, limits TokenLimits) *Token {
	return &Token{store: store, limiter: limiter, limits: limits, now: time.Now}
}

// tenantOf authorises the caller and returns the tenant to act on. The tenant always comes from the
// principal, never from the request.
func tenantOf(p Principal) (string, error) {
	if p.AuthType != AuthTypeJWT || p.TenantID == "" || p.Role != ownerRole {
		return "", ErrForbidden
	}
	return p.TenantID, nil
}

func randomBytes(n int) ([]byte, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return nil, err
	}
	return b, nil
}

// newAPIToken is "ragflow-" plus 32 random bytes, URL-safe base64 without padding (43 characters).
func newAPIToken() (string, error) {
	b, err := randomBytes(apiTokenRandomBytes)
	if err != nil {
		return "", err
	}
	return APITokenPrefix + base64.RawURLEncoding.EncodeToString(b), nil
}

// newBetaToken is 16 random bytes in hex: the shape of a UUID without its hyphens (32 characters).
func newBetaToken() (string, error) {
	b, err := randomBytes(betaTokenRandomBytes)
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

// Create mints a token pair for the caller's tenant. Creation is rate limited per tenant and capped;
// the limiter fails closed, so a Redis outage is ErrUnavailable.
func (s *Token) Create(ctx context.Context, p Principal) (APIToken, error) {
	tenant, err := tenantOf(p)
	if err != nil {
		return APIToken{}, err
	}
	if err := s.limiter.Hit(ctx, "token-create:"+tenant, s.limits.CreatePerWindow, s.limits.Window); err != nil {
		return APIToken{}, err
	}
	token, err := newAPIToken()
	if err != nil {
		return APIToken{}, fmt.Errorf("generate api token: %w", err)
	}
	beta, err := newBetaToken()
	if err != nil {
		return APIToken{}, fmt.Errorf("generate beta token: %w", err)
	}
	at := s.now()
	ms := at.UnixMilli()
	row := entity.APIToken{TenantID: tenant, Token: token, Beta: &beta, CreateTime: &ms, CreateDate: &at, UpdateTime: &ms, UpdateDate: &at}
	if err := s.store.CreateAPIToken(ctx, row, s.limits.MaxPerTenant); err != nil {
		if errors.Is(err, dao.ErrTokenLimit) {
			return APIToken{}, ErrTokenLimit
		}
		return APIToken{}, err
	}
	return APIToken{Token: token, Beta: beta, CreateTime: ms}, nil
}

// List returns one page (page is 1-based) of the caller's tenant's tokens, newest first.
func (s *Token) List(ctx context.Context, p Principal, page, pageSize int) ([]APIToken, error) {
	tenant, err := tenantOf(p)
	if err != nil {
		return nil, err
	}
	if page < 1 || pageSize < 1 || pageSize > MaxTokenPageSize {
		return nil, &ValidationError{Msg: "invalid page or page_size"}
	}
	rows, err := s.store.ListAPITokens(ctx, tenant, pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, err
	}
	out := make([]APIToken, 0, len(rows))
	for _, r := range rows {
		t := APIToken{Token: r.Token, Beta: deref(r.Beta)}
		if r.CreateTime != nil {
			t.CreateTime = *r.CreateTime
		}
		out = append(out, t)
	}
	return out, nil
}

// Delete removes the caller's tenant's token. A token of another tenant, a missing token and a value
// that cannot be a token all give ErrTokenNotFound, and nothing is changed.
func (s *Token) Delete(ctx context.Context, p Principal, token string) error {
	tenant, err := tenantOf(p)
	if err != nil {
		return err
	}
	if token == "" || len(token) > MaxAPITokenLength {
		return ErrTokenNotFound
	}
	removed, err := s.store.DeleteAPIToken(ctx, tenant, token)
	if err != nil {
		return err
	}
	if !removed {
		return ErrTokenNotFound
	}
	return nil
}
