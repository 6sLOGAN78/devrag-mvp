package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// PasswordReset serves the three public forgot-password endpoints.
type PasswordReset struct {
	svc *service.PasswordReset
}

// NewPasswordReset builds the handler.
func NewPasswordReset(svc *service.PasswordReset) *PasswordReset { return &PasswordReset{svc: svc} }

func notBuilt(c *gin.Context) {
	common.Fail(c, http.StatusNotImplemented, common.CodeServerError, "not implemented")
}

// RequestOTP answers POST /api/v1/auth/password/forgot/otp.
func (h *PasswordReset) RequestOTP(c *gin.Context) { notBuilt(c) }

// VerifyOTP answers POST /api/v1/auth/password/forgot/otp/verify.
func (h *PasswordReset) VerifyOTP(c *gin.Context) { notBuilt(c) }

// Reset answers POST /api/v1/auth/password/reset.
func (h *PasswordReset) Reset(c *gin.Context) { notBuilt(c) }
