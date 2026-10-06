# Session & Cookie Management

## Level 1: Session Lifecycle Architecture

RAGFlow manages user sessions across Redis cache storage and browser HTTP cookies:

1. **Redis Session Cache**: Sessions are stored in Redis (`SESSION_TYPE = "redis"` in [`api/apps/__init__.py:L79`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L79)).
2. **Session Cookie Fallback (`_load_user_from_session`)**: OAuth/OIDC callbacks call `login_user(user)` which writes `_user_id` into the server-side session. When an incoming request lacks an `Authorization` header, the server resolves `_user_id` from the session cookie ([`api/apps/__init__.py:L110`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L110)).
3. **Session Invalidation**: When a user logs out, the access token is overwritten with `INVALID_<hex>`, rendering any cached session invalid.

---

## Level 2: Session Loading Implementation in Code

```python
# api/apps/__init__.py (Lines 110-141)
def _load_user_from_session():
    """Resolve the current user from the session cookie set by login_user()."""
    user_id = session.get("_user_id")
    if not user_id:
        return None
    try:
        users = UserService.query(id=user_id, status=StatusEnum.VALID.value)
    except Exception:
        return None
    if not users:
        return None
    user = users[0]
    access_token = str(user.access_token or "").strip()
    if not access_token or len(access_token) < 32 or access_token.startswith("INVALID_"):
        return None
    g.auth_type = AUTH_JWT
    g.user = user
    return user
```

### Source References

- Session Configuration & Fallback: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L79-L141)
- User Service Query Method: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L48)
- Frontend Auth Cookie Handler: [`web/src/utils/authorization-util.ts`](file:///home/logan78/Desktop/ragflow/web/src/utils/authorization-util.ts)
