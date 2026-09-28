# API Security & Protection

## Level 1: Conceptual Explanation

API Security protects RAGFlow HTTP endpoints from unauthorized access, rate-limiting abuse, injection attacks, CORS violations, and invalid parameter payloads.

---

## Level 2: Implementation Details

### API Security Safeguards

1. **Authentication Decorator Enforcement**: Every non-public API endpoint is protected with `@login_required` ([`api/apps/__init__.py#L235`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L235)).
2. **API Key Masking**: Sensitive keys (`api_key`, `access_token`, LLM credentials) returned in JSON responses are masked (e.g. `ragflow-xxxx...xxxx`) to prevent leakage in client logs.
3. **CORS & CSRF Controls**: Cross-Origin Resource Sharing is controlled via Quart CORS middleware, ensuring requests originate only from whitelisted domain origins.
4. **Input Validation**: Request bodies are parsed via Pydantic or schema validators prior to SQL/vector engine execution to prevent SQL injection and command injection.

---

## References & Source Links

- [`api/apps/__init__.py:L235-L280`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L235-L280) - Endpoint access restriction logic.
- [`internal/cli/http_client.go:L30-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/http_client.go#L30-L100) - Secure client TLS and headers.
