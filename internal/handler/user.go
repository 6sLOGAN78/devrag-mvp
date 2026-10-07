package handler

import (
	"errors"
	"net/http"

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

const (
	// maxSettingBody leaves room for a 256 KB avatar as a base64 data URL (T-02-70).
	maxSettingBody = 400 << 10
	// maxPasswordBody caps a password-change body (T-02-70).
	maxPasswordBody = 2 << 10
)

// Settings serves profile settings and password change.
type Settings struct {
	svc *service.User
}

// NewSettings builds the handler.
func NewSettings(svc *service.User) *Settings { return &Settings{svc: svc} }

// settingRequest lists the only fields a client may set. Unknown JSON fields (id, tenant_id,
// email, is_superuser, status, password, access_token, ...) are never read.
type settingRequest struct {
	Nickname    *string `json:"nickname"`
	Avatar      *string `json:"avatar"`
	Language    *string `json:"language"`
	ColorSchema *string `json:"color_schema"`
}

// SettingDTO is the POST /v1/user/setting result: the profile fields that can change, without the avatar bytes.
type SettingDTO struct {
	ID          string `json:"id"`
	Nickname    string `json:"nickname"`
	Language    string `json:"language"`
	ColorSchema string `json:"color_schema"`
}

type passwordRequest struct {
	OldPassword string `json:"old_password"`
	NewPassword string `json:"new_password"`
}

// Update answers POST /v1/user/setting for the authenticated caller only.
func (h *Settings) Update(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	var req settingRequest
	if !bindLimit(c, &req, maxSettingBody) {
		return
	}
	prof, err := h.svc.UpdateSetting(c.Request.Context(), p.UserID, service.SettingInput{
		Nickname: req.Nickname, Avatar: req.Avatar, Language: req.Language, ColorSchema: req.ColorSchema,
	})
	if err != nil {
		fail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, SettingDTO{ID: prof.ID, Nickname: prof.Nickname, Language: prof.Language, ColorSchema: prof.ColorSchema})
}

// ChangePassword answers POST /v1/user/setting/password. Success signs every device out, so the
// auth cookie is expired in the same response (D-08).
func (h *Settings) ChangePassword(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	var req passwordRequest
	if !bindLimit(c, &req, maxPasswordBody) {
		return
	}
	if err := h.svc.ChangePassword(c.Request.Context(), p.UserID, service.ChangePasswordInput{Current: req.OldPassword, New: req.NewPassword}); err != nil {
		fail(c, err)
		return
	}
	http.SetCookie(c.Writer, &http.Cookie{
		Name: AuthCookieName, Value: "", Path: "/", MaxAge: -1,
		HttpOnly: true, SameSite: http.SameSiteLaxMode, Secure: secureRequest(c.Request),
	})
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}
