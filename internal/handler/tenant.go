package handler

import (
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
