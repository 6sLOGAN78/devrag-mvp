# Tokens & Token Management

## Level 1: Token Architecture

RAGFlow uses three types of tokens:

1. **JWT User Access Tokens**: Signed JWT strings generated upon successful email/password or OAuth login.
2. **Programmatic API Tokens**: Managed in the `APIToken` table, enabling programmatic SDK and API integrations.
3. **SDK Beta Tokens**: Dedicated tokens (`AUTH_BETA`) used for public search bots and MCP server endpoints (`/searchbots/*`, `/mcp`).

---

## Level 2: Token Validation & Revocation Code Analysis

### Token Validation Rules ([`api/apps/__init__.py:L185`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L185) & [`api/db/services/user_service.py:L48`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L48))

```python
# Validation rules enforced during token resolution:
# 1. Token string cannot be empty, None, or whitespace-only.
# 2. Token length must be at least 32 characters (UUID-based).
# 3. Token cannot start with "INVALID_" (revoked token string).
```

### Revocation Mechanism (`INVALID_<hex>`)
When a token is revoked (via logout or explicit deletion), the backend updates the database column:
```python
user.access_token = f"INVALID_{get_uuid()}"
user.save()
```
Any subsequent request presenting the old token string will match `access_token.startswith("INVALID_")` and be rejected with `401 Unauthorized`.

### Database Schema for API Tokens (`APIToken`)

```python
# api/db/db_models.py
class APIToken(DataBaseModel):
    tenant_id = StringField(max_length=32, primary_key=True)
    token = StringField(max_length=255, index=True)
    beta = StringField(max_length=255, index=True)
    dialog_id = StringField(max_length=32, null=True)
```

### Source File References

- Python Auth Pipeline: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L98-L220)
- User Service Query Guards: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L48)
- APIToken Model: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- Go Auth Middleware: [`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go)
