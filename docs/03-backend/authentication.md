# Backend Authentication Mechanisms

## Level 1: Multi-Modal Authentication Architecture

The backend supports five distinct authentication channels across Python and Go:

1. **Email & Password Authentication**: Validates user credentials, verifies hashed password strings using PBKDF2 / Bcrypt, and returns a signed access token.
2. **JWT Access Token Authentication**: Standard Bearer token authentication validated via `Serializer(secret_key)` in Python ([`api/apps/__init__.py:L185`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L185)) and Go JWT middleware ([`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go)).
3. **API Key Token Authentication**: Programmatic SDK authentication (`APIToken` table), allowing external applications to invoke REST endpoints using dedicated tokens.
4. **SDK Beta Token Authentication**: Used for public search bots and MCP server endpoints (`AUTH_BETA`).
5. **Session Cookie Fallback**: If no Authorization header is present, the server loads `_user_id` from Redis session cookies ([`api/apps/__init__.py:L110`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L110)).

---

## Level 2: Python Authentication Pipeline Code Analysis

```python
# api/apps/__init__.py (Lines 185-206)
# Try JWT decoding
if AUTH_JWT in auth_types:
    try:
        jwt = Serializer(secret_key=settings.get_secret_key())
        access_token = str(jwt.loads(auth_token))

        if not access_token or not access_token.strip():
            return None

        if len(access_token.strip()) < 32:
            return None

        user = UserService.query(access_token=access_token, status=StatusEnum.VALID.value)
        if user:
            g.auth_type = AUTH_JWT
            g.user = user[0]
            return user[0]
    except Exception:
        pass
```

### Password Verification Logic ([`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33))

```python
# User password hashing & verification
check_password_hash(user.password, raw_password)
```

### Invalidation & Revocation (`INVALID_<hex>`)
When a user logs out or invalidates an access token, the system rewrites the `access_token` column in the `user` table to `INVALID_<hex>`. Token query methods explicitly reject any token starting with `INVALID_` ([`api/db/services/user_service.py:L62`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L62)).

### Key Source Links

- Python Auth Pipeline: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L98-L220)
- User Service Auth Methods: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33)
- Go Auth Middleware: [`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go)
- API Token Database Schema: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
