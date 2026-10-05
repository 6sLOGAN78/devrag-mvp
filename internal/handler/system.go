// Package handler holds thin Gin handlers. They call the service layer and write envelopes.
package handler

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// System serves the system endpoints.
type System struct {
	svc *service.System
}

// NewSystem builds the handler set.
func NewSystem(svc *service.System) *System { return &System{svc: svc} }

// Health answers /health with 200 when every probe is ok and 503 otherwise.
func (h *System) Health(c *gin.Context) {
	data, healthy := h.svc.Health(c.Request.Context())
	if healthy {
		common.OK(c, data)
		return
	}
	common.FailWithData(c, http.StatusServiceUnavailable, common.CodeServiceUnavailable, "service unavailable", data)
}

// Ping answers /api/v1/system/ping.
func (h *System) Ping(c *gin.Context) { common.OK(c, "pong") }

// Config answers /api/v1/system/config.
func (h *System) Config(c *gin.Context) { common.OK(c, h.svc.Config()) }

// Version answers /api/v1/system/version, reading the schema version from the database.
func (h *System) Version(c *gin.Context) {
	data, err := h.svc.Version(c.Request.Context())
	if err != nil {
		if errors.Is(err, service.ErrUnavailable) {
			common.Fail(c, http.StatusServiceUnavailable, common.CodeServiceUnavailable, "service unavailable")
			return
		}
		common.Fail(c, http.StatusInternalServerError, common.CodeServerError, "internal error")
		return
	}
	common.OK(c, data)
}

// Language answers /api/v1/language.
func (h *System) Language(c *gin.Context) { common.OK(c, h.svc.Language()) }
