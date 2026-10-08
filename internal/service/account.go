package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/mail"
	"strings"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

const (
	maxEmailLength    = 255
	maxNicknameLength = 64
	loginFailureText  = "Email or password is incorrect"
	// defaultParserIDs is the RAGFlow default document-parser list of a new tenant.
	defaultParserIDs = "naive:General,qa:Q&A,resume:Resume,manual:Manual,table:Table,paper:Paper,book:Book,laws:Laws,presentation:Presentation,picture:Picture,one:One,audio:Audio,email:Email,tag:Tag"
	// dummyHash is verified for unknown or disabled accounts so the work done does not reveal
	// whether the email exists (D-04). It is not a credential: the digest matches no password.
	dummyHash = "pbkdf2:sha256:600000$dummysaltdummy00$0000000000000000000000000000000000000000000000000000000000000000"
)

var (
	// ErrRegistrationDisabled means the registration switch is off (D-01).
	ErrRegistrationDisabled = errors.New("registration is disabled")
	// ErrEmailTaken means the email is already registered.
	ErrEmailTaken = errors.New("email already registered")
	// ErrInvalidCredentials is the one failure message for every login rejection (D-04).
	ErrInvalidCredentials = errors.New(loginFailureText)
)

// ValidationError describes a rejected input; the message never echoes the input value.
type ValidationError struct{ Msg string }

func (e *ValidationError) Error() string { return e.Msg }

// AccountStore is the persistence surface of registration and login. dao.DB satisfies it.
type AccountStore interface {
	CreateAccount(ctx context.Context, a dao.NewAccount) error
	FindUserByEmail(ctx context.Context, email string) (*entity.User, error)
	FindUserByID(ctx context.Context, id string) (*entity.User, error)
	SwapAccessToken(ctx context.Context, userID string, old *string, next string) (bool, error)
	TouchLastLogin(ctx context.Context, userID string, at time.Time) error
	FindOwnMembership(ctx context.Context, userID string) (*entity.UserTenant, error)
	FindTenant(ctx context.Context, id string) (*entity.Tenant, error)
}

// RegisterInput is a registration request.
type RegisterInput struct {
	Email, Password, Nickname, ClientIP string
}

// LoginInput is a login request.
type LoginInput struct {
	Email, Password, ClientIP string
}

// Profile is the public part of a user.
type Profile struct {
	ID, Email, Nickname, Avatar, Language, ColorSchema, TenantID string
}

// LoginResult is the outcome of a successful login.
type LoginResult struct {
	Token                   string
	Profile                 Profile
	Role                    string
	LLMID, EmbdID, RerankID string
}

// Account implements registration and login.
type Account struct {
	store   AccountStore
	limiter *Limiter
	cfg     server.Config
	now     func() time.Time
	newID   func() string
}

// NewAccount wires the service.
func NewAccount(store AccountStore, limiter *Limiter, cfg server.Config) *Account {
	return &Account{store: store, limiter: limiter, cfg: cfg, now: time.Now, newID: randomID}
}

func randomID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic("crypto/rand unavailable: " + err.Error())
	}
	return hex.EncodeToString(b[:])
}

// validEmail checks the syntax of a canonical address. It is the check for finding an existing
// account (reset, invitations): rows created before R-129 may hold characters new accounts cannot.
func validEmail(email string) bool {
	if email == "" || len(email) > maxEmailLength || strings.Count(email, "@") != 1 {
		return false
	}
	addr, err := mail.ParseAddress(email)
	if err != nil || addr.Address != email {
		return false
	}
	return strings.Contains(email[strings.IndexByte(email, '@')+1:], ".")
}

// validNewEmail is validEmail plus the character restriction for addresses that become a new
// account (R-129): printable ASCII only, so no two different strings can name one collation-equal address.
func validNewEmail(email string) bool {
	return common.NewAccountEmailChars(email) && validEmail(email)
}

func ipKey(ip string) string {
	if ip == "" {
		return "unknown"
	}
	return ip
}

func window(seconds int) time.Duration { return time.Duration(seconds) * time.Second }

// Register creates the user, their tenant and the owner membership in one transaction.
func (a *Account) Register(ctx context.Context, in RegisterInput) (Profile, error) {
	if !a.cfg.Auth.RegisterEnabled {
		return Profile{}, ErrRegistrationDisabled
	}
	rl := a.cfg.RateLimit
	if err := a.limiter.Hit(ctx, "register:ip:"+ipKey(in.ClientIP), rl.RegisterPerIP, window(rl.RegisterWindowSeconds)); err != nil {
		return Profile{}, err
	}
	email := common.CanonicalEmail(in.Email)
	if !validNewEmail(email) {
		return Profile{}, &ValidationError{Msg: "email is not valid"}
	}
	nickname, err := validNickname(in.Nickname)
	if err != nil {
		return Profile{}, err
	}
	if err := common.ValidatePasswordLength(in.Password); err != nil {
		return Profile{}, &ValidationError{Msg: err.Error()}
	}
	hash, err := common.HashPassword(in.Password)
	if err != nil {
		return Profile{}, err
	}
	acct, profile := a.buildAccount(email, nickname, hash)
	if err := a.store.CreateAccount(ctx, acct); err != nil {
		if errors.Is(err, dao.ErrEmailTaken) {
			return Profile{}, ErrEmailTaken
		}
		return Profile{}, err
	}
	return profile, nil
}

func (a *Account) buildAccount(email, nickname, hash string) (dao.NewAccount, Profile) {
	now := a.now().UTC()
	ms := now.UnixMilli()
	id, membershipID := a.newID(), a.newID()
	str := func(s string) *string { return &s }
	notSuper := false
	m := a.cfg.Models
	ids := map[string]string{"chat": m.DefaultChatModel, "embedding": m.DefaultEmbeddingModel, "rerank": m.DefaultRerankModel}
	tenant := entity.Tenant{
		ID: id, Name: str(nickname + "'s Kingdom"), ParserIds: defaultParserIDs, Credit: 512, Status: str("1"),
		CreateTime: &ms, CreateDate: &now, UpdateTime: &ms, UpdateDate: &now,
		LLMID: qualified(ids["chat"], m.DefaultFactory), EmbdID: qualified(ids["embedding"], m.DefaultFactory), RerankID: qualified(ids["rerank"], m.DefaultFactory),
	}
	var rows []entity.TenantLLM
	if m.DefaultFactory != "" {
		rows = dao.TenantModelRows(id, m.DefaultFactory, m.DefaultBaseURL, ids, ms)
	}
	return dao.NewAccount{
		User: entity.User{
			ID: id, Email: email, Nickname: nickname, Password: &hash, Language: str("English"), ColorSchema: str("Bright"),
			Timezone: str("UTC+8\tAsia/Shanghai"), IsAuthenticated: "1", IsActive: "1", IsAnonymous: "0", LoginChannel: str("password"),
			Status: str("1"), IsSuperuser: &notSuper, CreateTime: &ms, CreateDate: &now, UpdateTime: &ms, UpdateDate: &now,
		},
		Tenant: tenant,
		Membership: entity.UserTenant{
			ID: membershipID, UserID: id, TenantID: id, InvitedBy: id, Role: "owner", Status: str("1"),
			CreateTime: &ms, CreateDate: &now, UpdateTime: &ms, UpdateDate: &now,
		},
		Models: rows,
	}, Profile{ID: id, Email: email, Nickname: nickname, Language: "English", ColorSchema: "Bright", TenantID: id}
}

func qualified(model, factory string) string {
	if model == "" || factory == "" {
		return model
	}
	return model + "@" + factory
}

// Login verifies the credentials and returns the shared access token (D-10).
//
// The failure counter is keyed on the resolved account (accountSubject), not on the typed spelling,
// and each attempt is counted atomically BEFORE the password is checked, so neither collation-equal
// spellings nor parallel guesses can exceed the cap (CR-01, WR-01). A success clears the counter.
func (a *Account) Login(ctx context.Context, in LoginInput) (LoginResult, error) {
	email := common.CanonicalEmail(in.Email)
	if email == "" || in.Password == "" {
		return LoginResult{}, &ValidationError{Msg: "email and password are required"}
	}
	rl := a.cfg.RateLimit
	win := window(rl.LoginWindowSeconds)
	if err := a.limiter.Hit(ctx, "login:ip:"+ipKey(in.ClientIP), rl.LoginPerIP, win); err != nil {
		return LoginResult{}, err
	}
	user, err := a.store.FindUserByEmail(ctx, email)
	if err != nil && !errors.Is(err, dao.ErrNotFound) {
		return LoginResult{}, dbFailure("user lookup", err)
	}
	if err != nil {
		user = nil
	}
	ek := "login:email:" + emailKey(accountSubject(user, email))
	if err := a.limiter.Hit(ctx, ek, rl.LoginFailuresPerEmail, win); err != nil {
		return LoginResult{}, err
	}
	if err := a.authenticate(user, in.Password); err != nil {
		return LoginResult{}, err
	}
	if err := a.limiter.Reset(ctx, ek); err != nil {
		return LoginResult{}, err
	}
	return a.complete(ctx, user)
}

// authenticate accepts only a valid account with the right password. Every other outcome performs
// one hash verification and returns ErrInvalidCredentials.
func (a *Account) authenticate(user *entity.User, password string) error {
	if user == nil || user.Password == nil || user.Status == nil || *user.Status != "1" {
		common.VerifyPassword(password, dummyHash)
		return ErrInvalidCredentials
	}
	if !common.VerifyPassword(password, *user.Password) {
		return ErrInvalidCredentials
	}
	return nil
}

func (a *Account) complete(ctx context.Context, user *entity.User) (LoginResult, error) {
	inner, err := a.sharedInner(ctx, user)
	if err != nil {
		return LoginResult{}, dbFailure("access token", err)
	}
	token, err := common.DumpAccessToken(inner, a.cfg.Security.SecretKey, a.now())
	if err != nil {
		return LoginResult{}, err
	}
	m, err := a.store.FindOwnMembership(ctx, user.ID)
	if errors.Is(err, dao.ErrNotFound) {
		return LoginResult{}, ErrNoTenant
	}
	if err != nil {
		return LoginResult{}, dbFailure("membership lookup", err)
	}
	t, err := a.store.FindTenant(ctx, m.TenantID)
	if errors.Is(err, dao.ErrNotFound) {
		return LoginResult{}, ErrNoTenant
	}
	if err != nil {
		return LoginResult{}, dbFailure("tenant lookup", err)
	}
	if err := a.store.TouchLastLogin(ctx, user.ID, a.now().UTC()); err != nil {
		return LoginResult{}, dbFailure("last login", err)
	}
	return LoginResult{
		Token: token, Role: m.Role, LLMID: t.LLMID, EmbdID: t.EmbdID, RerankID: t.RerankID,
		Profile: Profile{ID: user.ID, Email: user.Email, Nickname: user.Nickname, Avatar: deref(user.Avatar), Language: NormaliseLanguage(deref(user.Language)), ColorSchema: deref(user.ColorSchema), TenantID: t.ID},
	}, nil
}

// sharedInner returns the stored valid access token or installs a new one. The write is a
// compare-and-swap on the value this call read, then a re-read, so parallel first logins converge
// on a single stored token (D-10).
func (a *Account) sharedInner(ctx context.Context, user *entity.User) (string, error) {
	if user.AccessToken != nil && common.ValidInner(*user.AccessToken) {
		return *user.AccessToken, nil
	}
	candidate, err := common.NewAccessTokenInner()
	if err != nil {
		return "", err
	}
	if _, err := a.store.SwapAccessToken(ctx, user.ID, user.AccessToken, candidate); err != nil {
		return "", err
	}
	fresh, err := a.store.FindUserByID(ctx, user.ID)
	if err != nil {
		return "", err
	}
	if fresh.AccessToken == nil || !common.ValidInner(*fresh.AccessToken) {
		return "", errors.New("access token could not be stored")
	}
	return *fresh.AccessToken, nil
}
