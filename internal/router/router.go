// Package router builds the Gin engine: envelope-safe defaults and the Go-owned routes.
package router

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"

	"devrag/internal/common"
	"devrag/internal/handler"
	"devrag/internal/server"
)

// Option customises NewEngine. Production code passes none; tests use WithExtraRoutes.
type Option func(*gin.Engine)

// WithExtraRoutes registers additional routes after the Go-owned ones (used by tests).
func WithExtraRoutes(register func(*gin.Engine)) Option {
	return func(e *gin.Engine) { register(e) }
}

// NewEngine builds the engine. Only exact routes owned by Go in conf/routes.yaml are registered here;
// Go never proxies to Python (D-05, D-06).
func NewEngine(cfg server.Config, logger *zap.Logger, sys *handler.System, opts ...Option) *gin.Engine {
	e := gin.New()
	e.HandleMethodNotAllowed = true
	e.RedirectTrailingSlash = false
	e.RedirectFixedPath = false
	_ = e.SetTrustedProxies(nil)

	e.Use(sourceHeader(), requestLogger(logger), recovery(logger), cors(cfg.AllowedOrigins))
	e.NoRoute(func(c *gin.Context) {
		common.Fail(c, http.StatusNotFound, common.CodeNotFound, "not found")
	})
	e.NoMethod(func(c *gin.Context) {
		common.Fail(c, http.StatusMethodNotAllowed, common.CodeMethodNotAllowed, "method not allowed")
	})

	e.GET("/health", sys.Health)
	e.GET("/api/v1/system/ping", sys.Ping)
	e.GET("/api/v1/system/config", sys.Config)
	e.GET("/api/v1/system/version", sys.Version)
	e.GET("/api/v1/language", sys.Language)

	for _, opt := range opts {
		opt(e)
	}
	return e
}
