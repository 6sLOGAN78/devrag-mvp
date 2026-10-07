package handler

import (
	"context"
	"net/http"
	"net/url"
	"slices"
	"strings"

	"github.com/gin-gonic/gin"

	"devrag/internal/common"
	"devrag/internal/service"
)

const principalKey = "devrag.principal"

// PrincipalResolver turns a credential into a Principal. It returns service.ErrUnauthenticated for
// every credential failure; any other error is an infrastructure failure (R-114).
type PrincipalResolver interface {
	ResolvePrincipal(ctx context.Context, credential string, allowedTypes []string) (service.Principal, error)
}

type denyAll struct{}

func (denyAll) ResolvePrincipal(context.Context, string, []string) (service.Principal, error) {
	return service.Principal{}, service.ErrUnauthenticated
}

// DenyAll is the resolver used when none is configured: every protected route answers 401.
func DenyAll() PrincipalResolver { return denyAll{} }

// PrincipalFrom returns the authenticated caller set by AuthGate.
func PrincipalFrom(c *gin.Context) (service.Principal, bool) {
	v, ok := c.Get(principalKey)
	if !ok {
		return service.Principal{}, false
	}
	p, ok := v.(service.Principal)
	return p, ok
}

func deny(c *gin.Context) {
	common.Fail(c, http.StatusUnauthorized, common.CodeUnauthorized, "unauthorized")
	c.Abort()
}

// AuthGate is the default-deny middleware (D-30, SEC-01). It must be installed before any route.
// The policy comes from the generated table: a path with no entry is jwt. Only an explicit
// "none" entry is public. The api and beta credential types answer 401 until their resolver exists.
func AuthGate(resolver PrincipalResolver, allowedOrigins []string) gin.HandlerFunc {
	origins := make([]string, 0, len(allowedOrigins))
	for _, o := range allowedOrigins {
		origins = append(origins, strings.ToLower(strings.TrimRight(o, "/")))
	}
	return func(c *gin.Context) {
		r := c.Request
		if r.Method == http.MethodOptions {
			c.Next()
			return
		}
		policy := common.PolicyFor(r.Method, r.URL.Path)
		if policy.Auth == "none" {
			c.Next()
			return
		}
		if policy.Auth != service.AuthTypeJWT {
			deny(c)
			return
		}
		credential, ok, viaCookie := extractCredential(r)
		if !ok {
			deny(c)
			return
		}
		if viaCookie && !safeMethod(r.Method) && !sameOrigin(r, origins) {
			common.Fail(c, http.StatusForbidden, common.CodeForbidden, "forbidden")
			c.Abort()
			return
		}
		p, err := resolver.ResolvePrincipal(r.Context(), credential, []string{service.AuthTypeJWT})
		if err != nil {
			if isUnauthenticated(err) {
				deny(c)
				return
			}
			_ = c.Error(errAuthInfrastructure)
			common.Fail(c, http.StatusServiceUnavailable, common.CodeServiceUnavailable, "service unavailable")
			c.Abort()
			return
		}
		c.Set(principalKey, p)
		c.Next()
	}
}

type coarseError string

func (e coarseError) Error() string { return string(e) }

// errAuthInfrastructure is the only text logged for a gate infrastructure failure.
const errAuthInfrastructure = coarseError("auth gate: infrastructure failure")

func isUnauthenticated(err error) bool { return err == service.ErrUnauthenticated } //nolint:errorlint // sentinel returned unwrapped

// extractCredential reads the Authorization header (Bearer or raw). The cookie is consulted only
// when no Authorization header is present (D-21).
func extractCredential(r *http.Request) (credential string, ok, viaCookie bool) {
	if h := r.Header.Get("Authorization"); strings.TrimSpace(h) != "" {
		h = strings.TrimSpace(h)
		if len(h) >= 7 && strings.EqualFold(h[:7], "bearer ") {
			h = strings.TrimSpace(h[7:])
		}
		return h, true, false
	}
	if ck, err := r.Cookie(AuthCookieName); err == nil {
		return ck.Value, true, true
	}
	return "", false, false
}

func safeMethod(m string) bool {
	return m == http.MethodGet || m == http.MethodHead || m == http.MethodOptions
}

// sameOrigin implements the CSRF rule for cookie-authenticated unsafe requests: Origin, else
// Referer, must name the request's own host (X-Forwarded-Host when the peer is the loopback proxy,
// else Host) or an allowed origin. A missing or opaque origin is refused.
func sameOrigin(r *http.Request, allowed []string) bool {
	raw := r.Header.Get("Origin")
	if raw == "" {
		raw = r.Header.Get("Referer")
	}
	if raw == "" || raw == "null" {
		return false
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") {
		return false
	}
	if slices.Contains(allowed, strings.ToLower(u.Scheme+"://"+u.Host)) {
		return true
	}
	host := r.Host
	if fwd := r.Header.Get("X-Forwarded-Host"); fwd != "" && common.IsLoopbackPeer(r) {
		host = fwd
	}
	if i := strings.IndexByte(host, ','); i >= 0 {
		host = host[:i]
	}
	return strings.EqualFold(u.Host, strings.TrimSpace(host))
}

// secureRequest reports whether the auth cookie should carry Secure: the connection itself is TLS,
// or the loopback reverse proxy (Nginx in the same container) says it terminated TLS. The header
// from any other peer is ignored (R-114), the same rule as the client IP.
func secureRequest(r *http.Request) bool {
	return r.TLS != nil || (r.Header.Get("X-Forwarded-Proto") == "https" && common.IsLoopbackPeer(r))
}
