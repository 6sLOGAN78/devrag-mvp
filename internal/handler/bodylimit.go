package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
)

const (
	// DefaultBodyLimit is the request body cap of every route without its own entry (WR-04, R-130): the
	// Go-owned routes take small JSON documents, and the same figure is the Nginx limit generated for them.
	DefaultBodyLimit int64 = 16 << 10
	// MaxSettingBody is the cap of POST /v1/user/setting, which carries an avatar data URL of up to 256 KB
	// decoded (349,528 base64 characters) plus the other fields.
	MaxSettingBody int64 = maxSettingBody
)

// routeBodyLimits holds the routes that may exceed DefaultBodyLimit, keyed by gin's route template.
var routeBodyLimits = map[string]int64{
	"/v1/user/setting": MaxSettingBody,
}

// BodyLimit returns the request body cap for a gin route template ("" for an unmatched request).
func BodyLimit(route string) int64 {
	if limit, ok := routeBodyLimits[route]; ok {
		return limit
	}
	return DefaultBodyLimit
}

// BodyLimitMiddleware caps every request body so the limit holds when Go is reached without Nginx. A
// declared Content-Length over the cap is refused with 413 before the auth gate or a handler runs; an
// undeclared (chunked) body is wrapped in http.MaxBytesReader, whose error the handlers map to the same 413.
// It must run after route resolution, which gin does before any middleware, so FullPath is set.
func BodyLimitMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		limit := BodyLimit(c.FullPath())
		if c.Request.ContentLength > limit {
			common.Fail(c, http.StatusRequestEntityTooLarge, common.CodeBadRequest, "payload too large")
			c.Abort()
			return
		}
		if c.Request.Body != nil && c.Request.Body != http.NoBody {
			c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, limit)
		}
		c.Next()
	}
}
