package handler

import (
	"mime"
	"net/http"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
)

// WriteGuard is the browser-facing guard of every state-changing request (WR-05, R-132):
//
//   - a request with a body must be application/json. A cross-site HTML form can only send
//     urlencoded, multipart or text/plain, and a blob body can omit the type, so all of those are 415;
//   - a public route (auth none in the generated policy: register, login, reset steps) that is called with
//     an Origin header must name this host or an allowed origin, else 403. Browsers send Origin on every
//     cross-site POST, so this blocks login and reset CSRF; a non-browser client sends no Origin and is
//     unaffected. Authenticated routes keep their own rule in AuthGate (cookie requests only).
//
// It must run before the auth gate and before any handler.
func WriteGuard(allowedOrigins []string) gin.HandlerFunc {
	origins := normaliseOrigins(allowedOrigins)
	return func(c *gin.Context) {
		r := c.Request
		if safeMethod(r.Method) {
			c.Next()
			return
		}
		if common.PolicyFor(r.Method, r.URL.Path).Auth == "none" && r.Header.Get("Origin") != "" && !sameOrigin(r, origins) {
			common.Fail(c, http.StatusForbidden, common.CodeForbidden, "forbidden")
			c.Abort()
			return
		}
		if hasBody(r) && !isJSON(r.Header.Get("Content-Type")) {
			common.Fail(c, http.StatusUnsupportedMediaType, common.CodeBadRequest, "content type must be application/json")
			c.Abort()
			return
		}
		c.Next()
	}
}

// hasBody reports whether the client declared or streamed a body (a chunked body has length -1).
func hasBody(r *http.Request) bool {
	return r.ContentLength != 0 && r.Body != nil && r.Body != http.NoBody
}

func isJSON(contentType string) bool {
	media, _, err := mime.ParseMediaType(contentType)
	return err == nil && media == "application/json"
}
