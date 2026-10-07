package handler

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// Tenant serves the caller's workspace info and memberships.
type Tenant struct {
	svc *service.Tenant
}

// NewTenant builds the handler.
func NewTenant(svc *service.Tenant) *Tenant { return &Tenant{svc: svc} }

// TenantInfoDTO is GET /v1/user/tenant_info. Model ids are empty strings until configured.
type TenantInfoDTO struct {
	TenantID  string `json:"tenant_id"`
	Name      string `json:"name"`
	Role      string `json:"role"`
	ParserIDs string `json:"parser_ids"`
	LLMID     string `json:"llm_id"`
	EmbdID    string `json:"embd_id"`
	RerankID  string `json:"rerank_id"`
	ASRID     string `json:"asr_id"`
	Img2TxtID string `json:"img2txt_id"`
	TTSID     string `json:"tts_id"`
	OcrID     string `json:"ocr_id"`
}

// MembershipDTO is one entry of GET /v1/tenant/list. Role "invite" marks a pending invitation.
type MembershipDTO struct {
	TenantID      string `json:"tenant_id"`
	TenantName    string `json:"tenant_name"`
	OwnerNickname string `json:"owner_nickname"`
	OwnerAvatar   string `json:"owner_avatar"`
	Role          string `json:"role"`
	JoinedTime    string `json:"joined_time"`
}

// Info answers GET /v1/user/tenant_info.
func (h *Tenant) Info(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	t, err := h.svc.Info(c.Request.Context(), p)
	if err != nil {
		fail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, TenantInfoDTO{
		TenantID: t.TenantID, Name: t.Name, Role: t.Role, ParserIDs: t.ParserIDs, LLMID: t.LLMID, EmbdID: t.EmbdID,
		RerankID: t.RerankID, ASRID: t.ASRID, Img2TxtID: t.Img2TxtID, TTSID: t.TTSID, OcrID: t.OcrID,
	})
}

// List answers GET /v1/tenant/list with the caller's memberships and pending invitations.
func (h *Tenant) List(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	ms, err := h.svc.ListMemberships(c.Request.Context(), p)
	if err != nil {
		fail(c, err)
		return
	}
	out := make([]MembershipDTO, 0, len(ms))
	for _, m := range ms {
		joined := ""
		if !m.JoinedAt.IsZero() {
			joined = m.JoinedAt.Format(time.RFC3339)
		}
		out = append(out, MembershipDTO{
			TenantID: m.TenantID, TenantName: m.TenantName, OwnerNickname: m.OwnerNickname, OwnerAvatar: m.OwnerAvatar,
			Role: m.Role, JoinedTime: joined,
		})
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, out)
}

const (
	// maxTeamBody caps the JSON bodies of the invite and accept/decline routes.
	maxTeamBody = 1 << 10
	// defaultMemberPageSize is the page size when the client sends none.
	defaultMemberPageSize = service.MaxMemberPageSize
	notFoundText          = "not found"
)

// MemberDTO is one entry of GET /api/v1/tenants/:tenant_id/users: public profile fields only. Role
// "invite" marks a pending invitation and is shown to the owner only.
type MemberDTO struct {
	ID         string `json:"id"`
	Nickname   string `json:"nickname"`
	Email      string `json:"email"`
	Avatar     string `json:"avatar"`
	Role       string `json:"role"`
	JoinedTime string `json:"joined_time"`
}

func toMemberDTO(m service.Member) MemberDTO {
	joined := ""
	if !m.JoinedAt.IsZero() {
		joined = m.JoinedAt.Format(time.RFC3339)
	}
	return MemberDTO{ID: m.UserID, Nickname: m.Nickname, Email: m.Email, Avatar: m.Avatar, Role: m.Role, JoinedTime: joined}
}

// notFound is the one response for every tenant the caller cannot see: nonexistent, not a member, or
// only invited. Status, code and message never vary (R-93).
func notFound(c *gin.Context) {
	common.Fail(c, http.StatusNotFound, common.CodeNotFound, notFoundText)
}

func failTeam(c *gin.Context, err error) {
	switch {
	case errors.Is(err, service.ErrNotFound):
		notFound(c)
	case errors.Is(err, service.ErrForbidden):
		common.Fail(c, http.StatusForbidden, common.CodeForbidden, forbiddenText)
	case errors.Is(err, service.ErrInviteSelf), errors.Is(err, service.ErrAlreadyMember), errors.Is(err, service.ErrAlreadyInvited):
		common.Fail(c, http.StatusConflict, common.CodeConflict, err.Error())
	case errors.Is(err, service.ErrUserNotFound):
		common.Fail(c, http.StatusNotFound, common.CodeNotFound, err.Error())
	default:
		fail(c, err)
	}
}

// readBody reads at most maxTeamBody bytes. It answers 413 or 400 itself and reports false on failure.
func readBody(c *gin.Context) ([]byte, bool) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxTeamBody)
	raw, err := io.ReadAll(c.Request.Body)
	if err != nil {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			common.Fail(c, http.StatusRequestEntityTooLarge, common.CodeBadRequest, "payload too large")
			return nil, false
		}
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid request")
		return nil, false
	}
	return raw, true
}

// Members answers GET /api/v1/tenants/:tenant_id/users.
func (h *Tenant) Members(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	page, okPage := intQuery(c, "page", 1)
	size, okSize := intQuery(c, "page_size", defaultMemberPageSize)
	if !okPage || !okSize {
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid page or page_size")
		return
	}
	members, err := h.svc.ListMembers(c.Request.Context(), p, c.Param("tenant_id"), page, size)
	if err != nil {
		failTeam(c, err)
		return
	}
	out := make([]MemberDTO, 0, len(members))
	for _, m := range members {
		out = append(out, toMemberDTO(m))
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, out)
}

// Invite answers POST /api/v1/tenants/:tenant_id/users. The only input is the email; every other body
// field is ignored.
func (h *Tenant) Invite(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	raw, ok := readBody(c)
	if !ok {
		return
	}
	var in struct {
		Email string `json:"email"`
	}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &in); err != nil {
			common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid request")
			return
		}
	}
	m, err := h.svc.Invite(c.Request.Context(), p, c.Param("tenant_id"), in.Email)
	if err != nil {
		failTeam(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, toMemberDTO(m))
}

// Respond answers PATCH /api/v1/tenants/:tenant_id: accept (the default, also with no body) or decline
// the caller's own pending invitation.
func (h *Tenant) Respond(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	raw, ok := readBody(c)
	if !ok {
		return
	}
	action := service.InviteAccept
	if len(strings.TrimSpace(string(raw))) > 0 {
		var in struct {
			Action *string `json:"action"`
		}
		if err := json.Unmarshal(raw, &in); err != nil {
			common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid request")
			return
		}
		if in.Action != nil {
			action = *in.Action
		}
	}
	if err := h.svc.Respond(c.Request.Context(), p, c.Param("tenant_id"), action); err != nil {
		failTeam(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}
