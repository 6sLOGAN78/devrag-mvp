package handler

import (
	"errors"
	"io"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

const (
	// maxTokenBody caps the optional POST body of token creation.
	maxTokenBody = 1 << 10
	// defaultTokenPageSize is the page size when the client sends none.
	defaultTokenPageSize = service.MaxTokenPageSize
)

// Token serves API token management. Every route is jwt-only in the registry (R-90); the tenant is
// always the principal's, never read from the request.
type Token struct {
	svc *service.Token
}

// NewToken builds the handler.
func NewToken(svc *service.Token) *Token { return &Token{svc: svc} }

// TokenDTO is one API token as shown to its owner. It carries no dialog_id and no tenant id.
type TokenDTO struct {
	Token      string `json:"token"`
	Beta       string `json:"beta"`
	CreateTime int64  `json:"create_time"`
}

func toTokenDTO(t service.APIToken) TokenDTO {
	return TokenDTO{Token: t.Token, Beta: t.Beta, CreateTime: t.CreateTime}
}

// forbiddenText is the one message of a refused management call.
const forbiddenText = "forbidden"

func failToken(c *gin.Context, err error) {
	switch {
	case errors.Is(err, service.ErrTokenNotFound):
		common.Fail(c, http.StatusNotFound, common.CodeNotFound, "token not found")
	case errors.Is(err, service.ErrForbidden):
		common.Fail(c, http.StatusForbidden, common.CodeForbidden, forbiddenText)
	case errors.Is(err, service.ErrTokenLimit):
		common.Fail(c, http.StatusConflict, common.CodeConflict, "api token limit reached")
	default:
		fail(c, err)
	}
}

// drainBody reads and discards an optional request body of at most maxTokenBody bytes. Creation takes
// no input: any fields a client sends (tenant_id, token, ...) are ignored.
func drainBody(c *gin.Context) bool {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxTokenBody)
	if _, err := io.Copy(io.Discard, c.Request.Body); err != nil {
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

// Create answers POST /api/v1/system/tokens.
func (h *Token) Create(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	if !drainBody(c) {
		return
	}
	t, err := h.svc.Create(c.Request.Context(), p)
	if err != nil {
		failToken(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, toTokenDTO(t))
}

func intQuery(c *gin.Context, key string, def int) (int, bool) {
	raw, present := c.GetQuery(key)
	if !present {
		return def, true
	}
	n, err := strconv.Atoi(raw)
	return n, err == nil
}

// List answers GET /api/v1/system/tokens with the caller's tenant's tokens, newest first.
func (h *Token) List(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	page, okPage := intQuery(c, "page", 1)
	size, okSize := intQuery(c, "page_size", defaultTokenPageSize)
	if !okPage || !okSize {
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, "invalid page or page_size")
		return
	}
	tokens, err := h.svc.List(c.Request.Context(), p, page, size)
	if err != nil {
		failToken(c, err)
		return
	}
	out := make([]TokenDTO, 0, len(tokens))
	for _, t := range tokens {
		out = append(out, toTokenDTO(t))
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, out)
}

// Delete answers DELETE /api/v1/system/tokens/:token. A token of another tenant is 404, exactly like a
// missing one.
func (h *Token) Delete(c *gin.Context) {
	p, ok := PrincipalFrom(c)
	if !ok {
		deny(c)
		return
	}
	if err := h.svc.Delete(c.Request.Context(), p, c.Param("token")); err != nil {
		failToken(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}
