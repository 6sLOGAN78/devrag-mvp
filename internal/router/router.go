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

// engineOptions collects what options contribute before the engine is assembled, so the auth gate is
// installed ahead of every route (gin applies middleware only to routes registered after Use).
type engineOptions struct {
	resolver handler.PrincipalResolver
	routes   []func(*gin.Engine)
}

// Option customises NewEngine. Production code passes WithAuth plus route options; tests use WithExtraRoutes.
type Option func(*engineOptions)

// WithExtraRoutes registers additional routes after the Go-owned ones (used by tests).
func WithExtraRoutes(register func(*gin.Engine)) Option {
	return func(s *engineOptions) { s.routes = append(s.routes, register) }
}

// WithAuth sets the credential resolver used by the default-deny gate. Without it every protected
// route answers 401.
func WithAuth(r handler.PrincipalResolver) Option {
	return func(s *engineOptions) { s.resolver = r }
}

// WithAccount registers the register and login routes.
func WithAccount(h *handler.Account) Option {
	return WithExtraRoutes(func(e *gin.Engine) {
		e.POST("/api/v1/users", h.Register)
		e.POST("/api/v1/auth/login", h.Login)
	})
}

// WithSession registers logout and the signed-in user lookup.
func WithSession(h *handler.User) Option {
	return WithExtraRoutes(func(e *gin.Engine) {
		e.POST("/api/v1/auth/logout", h.Logout)
		e.GET("/v1/user/info", h.Info)
	})
}

// NewEngine builds the engine. Only exact routes owned by Go in conf/routes.yaml are registered here;
// Go never proxies to Python (D-05, D-06). The auth gate runs after CORS (so preflight is answered
// first) and before routing, including NoRoute: an unknown path is 401 unauthenticated, 404 authenticated.
func NewEngine(cfg server.Config, logger *zap.Logger, sys *handler.System, opts ...Option) *gin.Engine {
	st := &engineOptions{resolver: handler.DenyAll()}
	for _, opt := range opts {
		opt(st)
	}
	e := gin.New()
	e.HandleMethodNotAllowed = true
	e.RedirectTrailingSlash = false
	e.RedirectFixedPath = false
	_ = e.SetTrustedProxies(nil)

	e.Use(sourceHeader(), requestLogger(logger), recovery(logger), cors(cfg.AllowedOrigins), handler.AuthGate(st.resolver, cfg.AllowedOrigins))
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

	for _, register := range st.routes {
		register(e)
	}
	return e
}
