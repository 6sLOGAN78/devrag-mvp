package handler

import (
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

const (
	// maxAccountBody caps register and login bodies (T-02-35).
	maxAccountBody = 1 << 10
	// AuthCookieName carries the signed access token for requests without an Authorization header (D-21).
	AuthCookieName = "ragflow_auth"
)

// Account serves registration and login.
type Account struct {
	svc          *service.Account
	cookieMaxAge int
}

// NewAccount builds the handler; tokenMaxAge is the cookie lifetime (the token lifetime).
func NewAccount(svc *service.Account, tokenMaxAge time.Duration) *Account {
	return &Account{svc: svc, cookieMaxAge: int(tokenMaxAge.Seconds())}
}

type registerRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Nickname string `json:"nickname"`
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// UserDTO is the public user shape. It never carries the password hash or the stored token.
type UserDTO struct {
	ID          string `json:"id"`
	Email       string `json:"email"`
	Nickname    string `json:"nickname"`
	Avatar      string `json:"avatar"`
	Language    string `json:"language"`
	ColorSchema string `json:"color_schema"`
	TenantID    string `json:"tenant_id"`
}

// LoginDTO is the login payload.
type LoginDTO struct {
	Token    string  `json:"token"`
	User     UserDTO `json:"user"`
	TenantID string  `json:"tenant_id"`
	Role     string  `json:"role"`
	LLMID    string  `json:"llm_id"`
	EmbdID   string  `json:"embd_id"`
	RerankID string  `json:"rerank_id"`
}

func toUserDTO(p service.Profile) UserDTO {
	return UserDTO{ID: p.ID, Email: p.Email, Nickname: p.Nickname, Avatar: p.Avatar, Language: p.Language, ColorSchema: p.ColorSchema, TenantID: p.TenantID}
}

// bind reads a size-capped JSON body into dst. It writes the error envelope and returns false on failure.
func bind(c *gin.Context, dst any) bool {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxAccountBody)
	if err := json.NewDecoder(c.Request.Body).Decode(dst); err != nil {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			common.Fail(c, http.StatusRequestEntityTooLarge, common.CodeBadRequest, "payload too large")
			return false
		}
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid request")
		return false
	}
	return true
}

// Register answers POST /api/v1/users.
func (h *Account) Register(c *gin.Context) {
	var req registerRequest
	if !bind(c, &req) {
		return
	}
	p, err := h.svc.Register(c.Request.Context(), service.RegisterInput{Email: req.Email, Password: req.Password, Nickname: req.Nickname, ClientIP: common.ClientIP(c.Request)})
	if err != nil {
		fail(c, err)
		return
	}
	common.OK(c, toUserDTO(p))
}

// Login answers POST /api/v1/auth/login and sets the HttpOnly auth cookie.
func (h *Account) Login(c *gin.Context) {
	var req loginRequest
	if !bind(c, &req) {
		return
	}
	res, err := h.svc.Login(c.Request.Context(), service.LoginInput{Email: req.Email, Password: req.Password, ClientIP: common.ClientIP(c.Request)})
	if err != nil {
		fail(c, err)
		return
	}
	http.SetCookie(c.Writer, &http.Cookie{
		Name: AuthCookieName, Value: res.Token, Path: "/", MaxAge: h.cookieMaxAge,
		HttpOnly: true, SameSite: http.SameSiteLaxMode, Secure: secureRequest(c.Request),
	})
	c.Header("Cache-Control", "no-store")
	common.OK(c, LoginDTO{Token: res.Token, User: toUserDTO(res.Profile), TenantID: res.Profile.TenantID, Role: res.Role, LLMID: res.LLMID, EmbdID: res.EmbdID, RerankID: res.RerankID})
}

// fail maps a service error to the envelope. Internal details never reach the client.
func fail(c *gin.Context, err error) {
	var ve *service.ValidationError
	if errors.As(err, &ve) {
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, ve.Msg)
		return
	}
	if rl, ok := service.IsRateLimited(err); ok {
		c.Header("Retry-After", strconv.Itoa(int(math.Ceil(rl.RetryAfter.Seconds()))))
		common.Fail(c, http.StatusTooManyRequests, common.CodeBadRequest, "too many requests")
		return
	}
	switch {
	case errors.Is(err, service.ErrRegistrationDisabled):
		common.Fail(c, http.StatusForbidden, common.CodeForbidden, "registration is disabled")
	case errors.Is(err, service.ErrEmailTaken):
		common.Fail(c, http.StatusConflict, common.CodeConflict, "email already registered")
	case errors.Is(err, service.ErrInvalidCredentials):
		common.Fail(c, http.StatusUnauthorized, common.CodeUnauthorized, service.ErrInvalidCredentials.Error())
	case errors.Is(err, service.ErrUnavailable):
		_ = c.Error(err)
		common.Fail(c, http.StatusServiceUnavailable, common.CodeServiceUnavailable, "service unavailable")
	default:
		_ = c.Error(err)
		common.Fail(c, http.StatusInternalServerError, common.CodeServerError, "internal error")
	}
}
