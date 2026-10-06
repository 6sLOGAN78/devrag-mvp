# Backend Middleware Infrastructure

## Level 1: Middleware Chain Mechanics

Middleware functions execute before and after HTTP route handlers, performing cross-cutting concerns:

1. **Request CORS Handling**: Configures permissive Access-Control-Allow-Origin headers (`allow_origin="*"`) for cross-domain client requests.
2. **Request Logging & Header Injection**: Logs HTTP method, URL path, response status, and duration. Injects `X-API-Source: go` on Go responses ([`internal/router/router.go:L146`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L146)).
3. **Authentication & Identity Resolution**: Decodes JWT tokens, validates session cookies, or queries API Key tokens (`APIToken`), populating execution context objects (`g.user` in Python, `c.Set("user", ...)` in Go).
4. **Global Exception & Error Recovery**: Intercepts unhandled runtime exceptions, formats error tracebacks, and returns standardized `{ retcode: 500, retmsg: "..." }` responses.

---

## Level 2: Python vs Go Middleware Implementation

### 1. Python Quart Middleware Decorators ([`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L144))

#### `_load_user(auth_types)` Function Logic
```python
# api/apps/__init__.py:L144
def _load_user(auth_types=None):
    # 1. Check if g.user already populated in current request context
    # 2. Extract Authorization header (Bearer token or raw token)
    # 3. If AUTH_BETA: query APIToken by beta token string
    # 4. If AUTH_JWT: decode token using URLSafeTimedSerializer(secret_key)
    #    Validate access_token against UserService.query(access_token=...)
    # 5. If AUTH_API: query APIToken table by token string
    # 6. If no Authorization header: fallback to session cookie (_user_id)
```

#### `@login_required` Decorator Usage
```python
# api/apps/__init__.py:L221
def login_required(func=None, auth_types=None):
    # Wraps async endpoint function. Calls _load_user(auth_types).
    # If user is None, returns 401 Unauthorized JSON response.
```

---

### 2. Go Gin Middleware Chain ([`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go))

#### `AuthMiddleware()` Implementation
- Extracts `Authorization` header from Gin context (`c.GetHeader("Authorization")`).
- Validates Bearer token or session token against Redis / MySQL DAO.
- Sets user context in Gin request state (`c.Set("user", user)`).

#### `BetaAuthMiddleware()` Implementation
- Used for public search bots and MCP server routes (`/searchbots/*`, `/mcp`).
- Resolves tenant and user identity from beta tokens.

### Key Source Links

- Python App & Auth Decorator: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
- Go Auth Middleware: [`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go)
- Go Router Middleware Pipeline: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
