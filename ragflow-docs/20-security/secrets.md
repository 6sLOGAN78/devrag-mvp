# Secrets & Credentials Management

## Level 1: Conceptual Explanation

Secrets management ensures system credentials (database passwords, object store access keys, Redis passwords, encryption keys, and third-party LLM API keys) are stored securely, populated via environment variables, and never hardcoded in source repositories or emitted in log files.

---

## Level 2: Implementation Details

### Configuration Secret Management

1. **Environment Interpolation**: Production configuration values in [`conf/service_conf.yaml`](file:///home/logan78/Desktop/ragflow/conf/service_conf.yaml#L1-L191) are loaded dynamically from `.env` via `envsubst` during container initialization (`entrypoint.sh`).
2. **Secret Key Hash Generation**:
   - Implemented in [`internal/cli/crypt.go`](file:///home/logan78/Desktop/ragflow/internal/cli/crypt.go#L20-L80) using SHA256 / AES encryption for password hashing and credential storage.
3. **Third-Party Model Credentials**:
   - Model provider API keys (OpenAI, Anthropic, DashScope, TEI) are encrypted before insertion into MySQL (`tenant_llm` table) and sanitized during REST responses.

---

## References & Source Links

- [`internal/cli/crypt.go:L20-L80`](file:///home/logan78/Desktop/ragflow/internal/cli/crypt.go#L20-L80) - Password cryptographic routines.
- [`conf/service_conf.yaml:L1-L191`](file:///home/logan78/Desktop/ragflow/conf/service_conf.yaml#L1-L191) - Production service secret configurations.
- [`docker/entrypoint.sh:L1-L50`](file:///home/logan78/Desktop/ragflow/docker/entrypoint.sh#L1-L50) - Dynamic secret interpolation script.
