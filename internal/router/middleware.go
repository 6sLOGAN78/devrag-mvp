package router

import (
	"fmt"
	"net/http"
	"slices"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"

	"devrag/internal/common"
)

// sourceHeader marks every response, including 404, 405, 500 and preflight, with the engine.
func sourceHeader() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header(common.APISourceHeader, common.APISourceGo)
		c.Next()
	}
}

// requestLogger logs method, path (no query string), status and duration.
func requestLogger(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		started := time.Now()
		c.Next()
		logger.Info("request",
			zap.String("method", c.Request.Method),
			zap.String("path", c.Request.URL.Path),
			zap.Int("status", c.Writer.Status()),
			zap.Float64("duration_ms", float64(time.Since(started).Microseconds())/1000.0),
		)
	}
}

// recovery turns a panic into the 500 envelope. The panic value never reaches the client.
func recovery(logger *zap.Logger) gin.HandlerFunc {
	return gin.CustomRecovery(func(c *gin.Context, recovered any) {
		logger.Error("panic recovered", zap.String("path", c.Request.URL.Path), zap.String("panic", fmt.Sprint(recovered)))
		common.Fail(c, http.StatusInternalServerError, common.CodeServerError, "internal error")
		c.Abort()
	})
}

const (
	allowedMethods  = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
	allowedHeaders  = "Authorization, Content-Type"
	preflightMaxAge = "600"
)

// cors implements an explicit allow-list. An empty list adds no CORS headers (same-origin only);
// "*" is rejected at configuration time and is never emitted.
func cors(origins []string) gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if origin == "" || len(origins) == 0 || !slices.Contains(origins, origin) {
			c.Next()
			return
		}
		c.Header("Access-Control-Allow-Origin", origin)
		c.Header("Vary", "Origin")
		if c.Request.Method == http.MethodOptions && c.GetHeader("Access-Control-Request-Method") != "" {
			c.Header("Access-Control-Allow-Methods", allowedMethods)
			c.Header("Access-Control-Allow-Headers", allowedHeaders)
			c.Header("Access-Control-Max-Age", preflightMaxAge)
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}
