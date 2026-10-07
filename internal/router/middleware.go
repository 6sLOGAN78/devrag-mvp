package router

import (
	"fmt"
	"net/http"
	"slices"
	"strings"
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

// credentialPathFamily is the Go-owned family whose last path segment is a credential.
const credentialPathFamily = "/api/v1/system/tokens/"

// loggedPath is the path a log line may carry. A matched route logs its template (c.FullPath), so the
// token in DELETE /api/v1/system/tokens/:token never reaches the log. For an unmatched request (404 or
// 405) the raw path is logged, except under the token family, whose template is substituted (T-02-94).
func loggedPath(c *gin.Context) string {
	if p := c.FullPath(); p != "" {
		return p
	}
	if strings.HasPrefix(c.Request.URL.Path, credentialPathFamily) {
		return credentialPathFamily + ":token"
	}
	return common.TruncateField(c.Request.URL.Path, common.MaxLogField)
}

// requestLogger logs method, route template (no query string), status and duration.
func requestLogger(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		started := time.Now()
		c.Next()
		for _, err := range c.Errors {
			logger.Error("handler error", zap.String("path", loggedPath(c)), zap.String("error", common.TruncateField(err.Error(), common.MaxLogField)))
		}
		logger.Info("request",
			zap.String("method", c.Request.Method),
			zap.String("path", loggedPath(c)),
			zap.Int("status", c.Writer.Status()),
			zap.Float64("duration_ms", float64(time.Since(started).Microseconds())/1000.0),
		)
	}
}

// recovery turns a panic into the 500 envelope. The panic value never reaches the client.
func recovery(logger *zap.Logger) gin.HandlerFunc {
	return gin.CustomRecovery(func(c *gin.Context, recovered any) {
		logger.Error("panic recovered", zap.String("path", loggedPath(c)), zap.String("panic", fmt.Sprint(recovered)))
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
