package handler

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// maxResetBody caps the bodies of the public reset endpoints (T-02-75).
const maxResetBody = 1 << 10

// PasswordReset serves the three public forgot-password endpoints. They never read or set the
// auth cookie and answer with the same envelope for every account state (D-07).
type PasswordReset struct {
	svc *service.PasswordReset
}

// NewPasswordReset builds the handler.
func NewPasswordReset(svc *service.PasswordReset) *PasswordReset { return &PasswordReset{svc: svc} }

type otpRequest struct {
	Email string `json:"email"`
}

type verifyRequest struct {
	Email string `json:"email"`
	OTP   string `json:"otp"`
}

type resetRequest struct {
	Email       string `json:"email"`
	OTP         string `json:"otp"`
	ResetTicket string `json:"reset_ticket"`
	NewPassword string `json:"new_password"`
}

// ResetTicketDTO is the verify result.
type ResetTicketDTO struct {
	ResetTicket string `json:"reset_ticket"`
}

// resetFail maps the reset-specific failures to one generic 400; everything else goes through fail.
func resetFail(c *gin.Context, err error) {
	if errors.Is(err, service.ErrOTPInvalid) || errors.Is(err, service.ErrTicketInvalid) {
		common.Fail(c, http.StatusBadRequest, common.CodeArgumentError, err.Error())
		return
	}
	fail(c, err)
}

// RequestOTP answers POST /api/v1/auth/password/forgot/otp with the same body for every well-formed email.
func (h *PasswordReset) RequestOTP(c *gin.Context) {
	var req otpRequest
	if !bindLimit(c, &req, maxResetBody) {
		return
	}
	if err := h.svc.RequestReset(c.Request.Context(), req.Email, common.ClientIP(c.Request)); err != nil {
		resetFail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}

// VerifyOTP answers POST /api/v1/auth/password/forgot/otp/verify with a single-use reset ticket.
func (h *PasswordReset) VerifyOTP(c *gin.Context) {
	var req verifyRequest
	if !bindLimit(c, &req, maxResetBody) {
		return
	}
	ticket, err := h.svc.VerifyCode(c.Request.Context(), req.Email, req.OTP)
	if err != nil {
		resetFail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, ResetTicketDTO{ResetTicket: ticket})
}

// Reset answers POST /api/v1/auth/password/reset. It creates no session and sets no cookie.
func (h *PasswordReset) Reset(c *gin.Context) {
	var req resetRequest
	if !bindLimit(c, &req, maxResetBody) {
		return
	}
	err := h.svc.ResetPassword(c.Request.Context(), service.ResetInput{Email: req.Email, Ticket: req.ResetTicket, Code: req.OTP, NewPassword: req.NewPassword})
	if err != nil {
		resetFail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	common.OK(c, nil)
}
