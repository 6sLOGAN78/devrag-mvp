package handler

import (
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// User serves the session endpoints of the signed-in user.
type User struct {
	svc *service.Auth
}

// NewUser builds the handler.
func NewUser(svc *service.Auth) *User { return &User{svc: svc} }

// UserInfoDTO is GET /v1/user/info. It never carries the password hash or the stored token.
type UserInfoDTO struct {
	ID          string `json:"id"`
	Nickname    string `json:"nickname"`
	Email       string `json:"email"`
	Avatar      string `json:"avatar"`
	Language    string `json:"language"`
	ColorSchema string `json:"color_schema"`
	TenantID    string `json:"tenant_id"`
	TenantName  string `json:"tenant_name"`
	Role        string `json:"role"`
	IsSuperuser bool   `json:"is_superuser"`
}

// Info answers GET /v1/user/info.
func (h *User) Info(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	info, err := h.svc.UserInfo(c.Request.Context(), p)
	if err != nil {
		if errors.Is(err, service.ErrUnauthenticated) {
			deny(c)
			return
		}
		_ = c.Error(err)
		common.Fail(c, http.StatusInternalServerError, common.CodeServerError, "internal error")
		return
	}
	common.OK(c, UserInfoDTO{
		ID: info.ID, Nickname: info.Nickname, Email: info.Email, Avatar: info.Avatar, Language: info.Language,
		ColorSchema: info.ColorSchema, TenantID: info.TenantID, TenantName: info.TenantName, Role: info.Role, IsSuperuser: info.IsSuperuser,
	})
}

// Logout answers POST /api/v1/auth/logout: it invalidates the shared token and expires the cookie.
func (h *User) Logout(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	if err := h.svc.Logout(c.Request.Context(), p.UserID); err != nil {
		_ = c.Error(err)
		common.Fail(c, http.StatusInternalServerError, common.CodeServerError, "internal error")
		return
	}
	http.SetCookie(c.Writer, &http.Cookie{
		Name: AuthCookieName, Value: "", Path: "/", MaxAge: -1,
		HttpOnly: true, SameSite: http.SameSiteLaxMode, Secure: secureRequest(c.Request),
	})
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}

// Settings serves profile settings and password change.
type Settings struct{}

// NewSettings builds the handler.
func NewSettings(*service.User, time.Duration) *Settings { return &Settings{} }

// Update is not implemented yet.
func (*Settings) Update(c *gin.Context) {
	common.Fail(c, http.StatusNotImplemented, common.CodeServerError, "not implemented")
}

// ChangePassword is not implemented yet.
func (*Settings) ChangePassword(c *gin.Context) {
	common.Fail(c, http.StatusNotImplemented, common.CodeServerError, "not implemented")
}
