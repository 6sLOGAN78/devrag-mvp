package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

// Tenant serves the caller's workspace info and memberships.
type Tenant struct{}

// NewTenant builds the handler.
func NewTenant(*service.Tenant) *Tenant { return &Tenant{} }

// Info is not implemented yet.
func (*Tenant) Info(c *gin.Context) {
	common.Fail(c, http.StatusNotImplemented, common.CodeServerError, "not implemented")
}

// List is not implemented yet.
func (*Tenant) List(c *gin.Context) {
	common.Fail(c, http.StatusNotImplemented, common.CodeServerError, "not implemented")
}
