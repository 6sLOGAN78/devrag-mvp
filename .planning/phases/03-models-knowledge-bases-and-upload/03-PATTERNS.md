# Phase 3: Models, Knowledge Bases and Upload - Pattern Map

**Mapped:** 2026-10-08
**Files analyzed:** 96 new or modified files (Python 41, config/ops 14, Go 3, frontend 38)
**Analogs found:** 74 with a codebase analog / 96 total. The 22 without one are listed under "No Analog Found" and take their pattern from RESEARCH.md and the read-only RAGFlow reference.

Scope notes for the planner:
- The Python side has exactly one handler module today (`api/apps/restful_apis/system_api.py`) and no multipart, ES-adapter, storage-driver or LLM-driver code. `rag/` and `common/doc_store/` do not exist. Phase 2 owns all identity routes in Go.
- Every path below is relative to `/home/logan78/desktop x/devRag_@` (the path contains a space and `@`; always quote it).
- Reference repo `/home/logan78/desktop x/ragflow` is evidence only. `docs/` and the code here win.

---

## File Classification

### Python: config, security, plumbing

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `common/settings.py` (modify: `StorageSettings`, `UploadSettings`, `LlmSettings`) | config | request-response | same file: `SecuritySettings`, `RateLimitSettings`, `_parse_ratelimit` | exact |
| `conf/service_conf.yaml.template` (modify) | config | batch | same file, `security:` and `ratelimit:` blocks | exact |
| `scripts/render_conf.py` (modify only if a new validation is added) | config | batch | same file `main()` secret-length check, lines 104-107 | exact |
| `docker/.env.example` (modify) | config | batch | same file, `SECRET_KEY` block lines 80-83 | exact |
| `docker/docker-compose.yml` (modify `x-app-env`) | config | batch | same file lines 27-45 | exact |
| `docker/docker-compose.dev.yml` (modify: `LLM_ALLOW_PRIVATE_BASE_URLS` default true) | config | batch | same file `app.environment` lines 33-38 | exact |
| `scripts/init_env.sh` (modify: generate 32-byte key) | config | batch | same file `generated()` lines 44-45 | exact |
| `pyproject.toml` (modify: deps, `live_model` marker) | config | n/a | same file `[tool.pytest.ini_options].markers` | exact |
| `common/security/secretbox.py` (new) | utility | transform | `common/security/tokens.py` (module shape, `None`/raise contract) | role-match |
| `common/net/url_guard.py` (new) | utility | transform | none (nearest: `common/security/proxy.py::is_loopback_peer`, not read in full) | none |
| `common/log_utils.py` (modify: key-shape redaction) | utility | transform | same file `redact_text`, `_redact_keys` | exact |
| `internal/common/logger.go` (modify: same shapes in Go) | utility | transform | same file `fragmentPattern`, `RedactString` | exact |
| `docker/nginx/nginx.conf` (modify `map $uri $loggable_uri`) | config | transform | same file lines 18-23 | exact |
| `test/fixtures/log_redaction_vectors.json` (modify) | test fixture | transform | same file (24 lines) | exact |

### Python: doc store, storage, drivers

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `common/doc_store/doc_store_base.py` (new port) | model/port | CRUD + search | none in repo; ref `common/doc_store/doc_store_base.py` | none |
| `rag/utils/es_conn.py` (new adapter) | service | CRUD | `common/health/probes.py::probe_doc_store` (client construction only) | partial |
| `rag/utils/storage_factory.py` (new) | utility | file-I/O | none (ref `rag/utils/*`) | none |
| `rag/utils/minio_conn.py` (new) | service | file-I/O | `common/bootstrap/ensure_bucket.py` | role-match |
| `rag/utils/local_conn.py` (new) | service | file-I/O | none | none |
| `rag/llm/__init__.py`, `chat_model.py`, `embedding_model.py`, `model_meta.py` (new) | service | request-response + streaming | none; ref `rag/llm/chat_model.py`, `embedding_model.py` | none |
| `rag/__init__.py`, `rag/llm/...`, `rag/utils/...` package markers (new) | config | n/a | `common/__init__.py`, `common/security/__init__.py` | exact |

### Python: services, handlers

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `api/db/services/tenant_scope.py` (new) | service | request-response | `api/db/services/auth_service.py` (Protocol store + frozen dataclasses + `PeeweeAuthStore`) | role-match |
| `api/db/services/tenant_llm_service.py`, `tenant_model_{provider,instance,model}_service.py` (new) | service | CRUD | `api/db/services/superuser_service.py` (transaction, uuid ids, IntegrityError recheck) | role-match |
| `api/db/services/llm_service.py` (`LLMBundle`) (new) | service | request-response | none (ref `api/db/services/llm_service.py`) | none |
| `api/db/services/knowledgebase_service.py` (new) | service | CRUD | `superuser_service.py::_seed` (DatabaseLock + transaction) | role-match |
| `api/db/services/document_service.py`, `file_service.py` (new) | service | CRUD + file-I/O | `superuser_service.py` + `ensure_bucket.py` | role-match |
| `api/apps/restful_apis/provider_api.py`, `models_api.py` (new) | controller | request-response | `api/apps/restful_apis/system_api.py` + `test/helpers/app.py::build_blueprint` (validated body) | role-match |
| `api/apps/restful_apis/dataset_api.py` (new) | controller | CRUD | `system_api.py` + `build_blueprint` | role-match |
| `api/apps/restful_apis/document_api.py` (new; multipart upload) | controller | file-I/O | `system_api.py`; no multipart analog | partial |
| `api/apps/__init__.py` (modify: register blueprints) | config | n/a | same file lines 48-52 | exact |
| `api/apps/errors.py` (modify only if a typed domain-error mapper is added) | middleware | request-response | same file `register_error_handlers` | exact |
| `conf/routes.yaml` (modify: endpoint rows, python family rows) | config | n/a | same file `endpoints:` rows 74-120 | exact |
| `conf/permissions.yaml` (modify: `view_models`, `set_default_models`) | config | n/a | same file line 22 | exact |
| `api/apps/permissions_gen.py`, `api/apps/route_policy_gen.py`, `internal/common/permissions_gen.go`, `internal/common/route_policy_gen.go`, `docker/nginx/ragflow*.conf`, `web/src/constants/api-routes.generated.json` | generated | n/a | regenerate with `uv run python scripts/gen_routes.py`; never hand-edit | n/a |

### Tests (Python and Go)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `test/unit_test/test_secretbox.py` | test | transform | `test/unit_test/test_security_tokens.py` | exact |
| `test/unit_test/test_llm_drivers.py`, `test_llm_bundle.py` | test | request-response | `test/unit_test/test_auth_gate.py` style + `test/helpers/app.py` | partial |
| `test/unit_test/test_local_storage.py` | test | file-I/O | `test/unit_test/test_security_passwords.py` style | partial |
| `test/unit_test/test_layering.py` (extend) | test | n/a | same file lines 25-44 | exact |
| `test/unit_test/test_permissions_table.py`, `test/fixtures/permission_cases.json`, `internal/common/permissions_test.go` (extend) | test | n/a | same files | exact |
| `test/unit_test/test_nginx_limits.py`, `test_gen_routes.py`, `test_route_policy.py`, `test/fixtures/route_policy_cases.json` (extend) | test | n/a | same files | exact |
| `test/unit_test/test_env_catalog.py`, `test_settings.py`, `test_render_conf.py`, `test_container_scripts.py` (extend) | test | n/a | same files | exact |
| `test/unit_test/test_log_redaction.py` + vectors, Go `internal/common/logger_test.go` | test | transform | same files | exact |
| `test/helpers/fake_provider.py` (new) | test helper | request-response | `test/helpers/app.py` (Quart app builder) | partial |
| `test/helpers/accounts.py` (modify `delete_accounts`) | test helper | CRUD | same file lines 105-120 | exact |
| `test/integration/test_doc_store_es.py` (new, engine-agnostic contract class) | test | CRUD | `test/integration/test_python_system_routes.py` (live-stack module fixtures) | role-match |
| `test/integration/test_storage.py`, `test_provider_key_at_rest.py` (new) | test | file-I/O / CRUD | `test/integration/test_db_core.py` + `test/helpers/db.py::root_connection` | role-match |
| `test/testcases/test_provider_flow.py`, `test_dataset_flow.py`, `test_upload_flow.py`, `test_document_flow.py`, `test_create_kb_e2e.py` (new) | test | request-response | `test/testcases/test_api_token_flow.py` | exact |
| `test/testcases/test_live_models.py` (new, `live_model`) | test | request-response | `test_api_token_flow.py` + `web/.../api-tokens.live.test.ts` key handling | partial |
| `test/testcases/_matrix_fixtures.py`, `test_cross_tenant_matrix.py` (extend) | test | request-response | same files | exact |
| `test/testcases/test_response_leaks.py`, `_leak_sweep.py` (extend) | test | request-response | same files | exact |
| `test/testcases/test_spa_browser.py` (extend) | test | request-response | same file | exact |
| `scripts/clean_room.sh`, `scripts/preflight.sh` (modify) | config | batch | same files | exact |

### Frontend (`web/src`)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `constants/api-paths.ts` (modify) | config | n/a | same file `resolveUnder` | exact |
| `services/{model,dataset,document}-service.ts` (new) | service | request-response | `services/api-token-service.ts`, `services/team-service.ts` | exact |
| `hooks/use-llm-request.ts`, `use-knowledge-request.ts`, `use-document-request.ts` (new) | hook | request-response | `hooks/use-api-token-request.ts`, `hooks/use-team-request.ts` | exact |
| `stores/workspace-store.ts` (new) | store | event-driven | `stores/user-store.ts` (+ `utils/authorization.ts` for storage guards) | role-match |
| `components/workspace-switch.tsx` (new) | component | request-response | `components/user-menu.tsx` | role-match |
| `layouts/standard-layout.tsx` (modify) | component | n/a | same file | exact |
| `constants/routes.ts`, `components/app-sidebar.tsx` (modify) | config/component | n/a | same files | exact |
| `pages/user-setting/model/*` (new) | component | CRUD | `pages/user-setting/api/*`, `pages/user-setting/team/*` | role-match |
| `pages/datasets/index.tsx`, `dataset-card.tsx` (new) | component | CRUD | `pages/user-setting/api/index.tsx` | role-match |
| `pages/dataset/index.tsx`, `dataset-files.tsx` (new) | component | CRUD | `pages/user-setting/team/members-table.tsx` + `api/index.tsx` | role-match |
| `components/create-dataset-dialog/*` (new) | component | request-response | `pages/user-setting/team/invite-form.tsx` | role-match |
| `components/file-upload-dialog/*` (new) | component | file-I/O | none for upload; dialog/AlertDialog from `api/delete-dialog.tsx` | partial |
| `components/llm-select/*` (new) | component | n/a | `components/ui/native-select.tsx` | role-match |
| `components/ui/{textarea,progress,pagination,search-input,choice-group}.tsx` (new), `ui/alert.tsx` (modify `info` variant) | component | n/a | `components/ui/native-select.tsx`, `ui/alert.tsx`, `ui/badge.tsx` | exact |
| `pages/user-setting/model/secret-mask.ts` | utility | transform | `pages/user-setting/api/mask.ts` | exact |
| `locales/en.json`, `locales/zh.json` (modify) | config | n/a | same files; `locales/locales.test.ts` | exact |
| `*.test.tsx`, `*.live.test.ts` for each page (new) | test | request-response | `api-tokens.test.tsx`, `api-tokens.live.test.ts`, `team.live.test.ts` | exact |
| nav-order tests: `layouts/layouts.test.tsx`, `components/shell-i18n.test.tsx`, `routes.test.tsx` (modify) | test | n/a | same files | exact |

---

## Gotchas found while mapping (read before planning)

These are existing tests or conventions that a straightforward implementation will break.

1. **Permission table size is pinned.** `test/unit_test/test_permissions_table.py:85` asserts `len(data["permissions"]) == len(ORACLE["rows"]) == 10`, and the oracle `test/fixtures/permission_cases.json` is hand-written and shared with `internal/common/permissions_test.go`. Adding `view_models` / `set_default_models` rows means: edit `conf/permissions.yaml`, add rows to the oracle, change the `10`, add areas to `DOC_AREAS` only if a new area is introduced, regenerate with `uv run python scripts/gen_routes.py`. Keep `tenant_settings` as the area so `DOC_AREAS` stays valid.
2. **Every Python Nginx location is asserted to be exactly 1024m.** `test_nginx_limits.py:62-75` (`test_python_owned_locations_keep_the_upload_allowance_explicitly`) fails as soon as the generator emits a `1m` JSON location or the `101m` upload location. The planner must change that assertion in the same task that adds `body_limit` to Python rows. The streaming test (`:78-86`) also requires every non-Go location to have `proxy_read_timeout >= 3600`.
3. **The leak sweep bans response keys.** `test/testcases/_leak_sweep.py:20-26` bans `status` and `source` everywhere except system rows (`INTERNAL_COLUMN`), plus any key matching `secret|salt|ticket|otp|password|access_token` and the exact keys `token` and `beta` outside the token rows. Dataset and document DTOs must not emit `status`, `source`, `source_type` is fine (not exact `source`), and a model/provider DTO must not contain a field literally named `token` or `secret`. Use `run`, `progress`, `configured`, `last4`, `used_tokens` (exact-key check only matches `token`/`beta`).
4. **`Principal` only knows the caller's own workspace, and a token principal inherits the owner's role** (`auth_service.py:113-129`). `allowed(principal.role, ...)` is wrong for API tokens; compute the subject from `auth_type` (RESEARCH Pattern 7, Pitfall 6).
5. **New `Settings` fields need defaults.** `test/helpers/app.py::memory_settings` builds `Settings(...)` with only the nine original sections and uses `dataclasses.replace`; any new section must use `field(default_factory=...)` like `auth`, `mail`, `models`, `ratelimit` (`settings.py:174-177`) or every unit test constructing settings breaks. The encryption key must default to empty and be validated lazily (routes fail closed with 503; the app still boots).
6. **`scripts/init_env.sh` generates `token_hex(16)` for every `# secret` key except `SECRET_KEY`** (line 45). `LLM_KEY_ENCRYPTION_KEY` needs 32 random bytes, base64. Extend `generated()`; `OPERATOR_SUPPLIED` (line 41) is the set for keys that must stay empty. `test_container_scripts.py` / `test_env_catalog.py` pin the variable lists.
7. **`render_conf.py` `_escape`** rejects quotes in unquoted YAML positions and control characters; render the key inside single quotes like `secret_key` and use URL-safe base64 (no quote characters).
8. **Layering is enforced on imports.** Handlers in `api/apps/**` may not import `api.db.models`, `api.db.database`, `peewee` or `common.health`; services may not import `quart`, `quart_schema`, `quart_cors` (`test_layering.py:34-39`). The upload service must take a small `Protocol` for the file object, not a Quart type. New `rag/` and `common/doc_store/` need their own layering tests (no `api.apps`, no `quart`).
9. **`DatabaseLock` names are capped at 64 characters** (`database.py:35,185-187`). `kb-create:{tenant_id}` and `kb-upload:{kb_id}` are 42 characters; do not append more.
10. **`document` has no `tenant_id`; `content_hash` is `VARCHAR(32)`** (`models/knowledge.py:82,99`). Dedupe must join `file2document -> file.tenant_id`. `tenant_model_instance.api_key` is `NOT NULL VARCHAR(512)`, `tenant_llm.api_key` is LONGTEXT, `tenant_llm.used_tokens` is a 32-bit INT (`models/llm.py:41,44,76`).
11. **The SPA purges the session on any 401 carrying the current token** (`services/http.ts:164-170`). A rejected provider key must be HTTP 400. `http.ts` `safeMessage` caps toast text at 160 characters (`MAX_MESSAGE_LENGTH`); provider refusals shown inline come from `ApiError.message` directly and are limited in the page's own `errors.ts` (UI-SPEC says 300).
12. **Nav tests hard-code the order.** `layouts/layouts.test.tsx:75-86,190,195`, `components/shell-i18n.test.tsx:55` and `routes.test.tsx:212-217` list the five existing entries by order. Adding Datasets (order 2) and Models (order 5) shifts every later entry; update all three in the same task as `constants/routes.ts`.
13. **`test/helpers/accounts.py::delete_accounts` deletes only user, tenant, user_tenant, api_token and tenant_llm rows** (lines 113-118). New e2e tests will leave `knowledgebase`, `document`, `file`, `file2document`, `tenant_model*` rows (and MinIO objects, ES documents) behind. Extend cleanup by recorded tenant id only (same rule: never by pattern).
14. **The dev `app` container has `mem_limit: 768m`** (`docker/docker-compose.dev.yml:35`) while `import litellm` costs roughly 200 MB. Import it lazily inside the driver (RESEARCH, Standard Stack) and keep upload streaming (no `await file.read()`).
15. **Log redaction is key-name based today** (`log_utils.py:14-15`, `logger.go:20,28`, `nginx.conf:18-23`). The Python, Go and Nginx implementations all read the same vector file (`test_log_redaction.py:67-79`, `logger_test.go:89`). Add shape-based patterns in all three, in the same task, with vectors first.

---

## Pattern Assignments

### `common/settings.py` (config, request-response)

**Analog:** same file. New sections copy `SecuritySettings` (masked repr), `RateLimitSettings` (bounded ints with defaults) and `_parse_ratelimit` (lines 94-103, 149-161, 273-280).

**Masked secret dataclass** (lines 94-103):
```python
@dataclass(frozen=True)
class SecuritySettings:
    secret_key: str = field(repr=False)
    token_max_age_seconds: int = TOKEN_MAX_AGE_SECONDS
    password_iterations: int = PASSWORD_ITERATIONS

    def __repr__(self) -> str:
        return f"SecuritySettings(secret_key={MASK!r}, token_max_age_seconds={self.token_max_age_seconds}, password_iterations={self.password_iterations})"

    __str__ = __repr__
```

**Bounded numeric parse with defaults** (lines 217-229, 273-280): `_bounded(sec, "ratelimit", name, getattr(defaults, name), hi)` returns the default when unset and raises `ConfigError("invalid value for config key: <section>.<key>")` otherwise. Use it for `UPLOAD_MAX_FILE_BYTES`, `UPLOAD_MAX_FILES_PER_REQUEST`, `DATASET_MAX_DOCUMENTS`, `UPLOAD_BODY_TIMEOUT_SECONDS`, and the LLM timeouts/retries.

**Bool parse** (lines 205-214): `_bool(sec, "llm", "allow_private_base_urls", False)` for `LLM_ALLOW_PRIVATE_BASE_URLS`.

**Optional section wiring** (lines 164-177 and 283-327): add `storage: StorageSettings = field(default_factory=StorageSettings)` etc. to `Settings`, and a `_parse_storage(data)` call in `parse_settings`. Key validation pattern (lines 201-202, 232-239): `_valid_secret_key` -> `ConfigError(... "run make init-env")`; for the encryption key do **not** raise at parse time when empty (gotcha 5), validate length/base64 when non-empty.

---

### `conf/service_conf.yaml.template`, `docker/.env.example`, `docker/docker-compose.yml`, `scripts/init_env.sh` (config, batch)

**Template** (lines 39-40, 60-69): single-quoted for strings, bare for ints.
```yaml
security:
  secret_key: '${SECRET_KEY:?SECRET_KEY is required, at least 32 characters (run make init-env)}'
...
ratelimit:
  register_per_ip: ${RATE_LIMIT_REGISTER_PER_IP:-10}
```
Add `storage:`, `upload:`, `llm:` blocks the same way (`'${LLM_KEY_ENCRYPTION_KEY:-}'` quoted; ints bare).

**`.env.example`** (lines 80-83): a `# secret` comment line directly above the empty key:
```
# Token signing key (D-09, R-96): ...
# secret
SECRET_KEY=
```
Add `LLM_KEY_ENCRYPTION_KEY` the same way, plus `UPLOAD_*`, `DATASET_MAX_DOCUMENTS`, `STORAGE_IMPL`, `LLM_ALLOW_PRIVATE_BASE_URLS`, `LIVE_CHAT_MODEL`, `LIVE_EMBED_MODEL` (names only, no values). `OPENROUTER_API_KEY` must **not** be given a value; whether it is listed in the example is a planner decision (D-02, D-29), and if listed it needs the `# secret` marker and an `OPERATOR_SUPPLIED` entry in `init_env.sh` so it is never generated.

**Compose** (`docker/docker-compose.yml` lines 27, 43): required secret uses `${VAR:?message}`; optional uses `${VAR:-default}`. The encryption key follows `SECRET_KEY` (fail-fast message "run scripts/init_env.sh --append-missing"). Do **not** pass `OPENROUTER_API_KEY` into the `app` container; the live tier reads it from the host `docker/.env`.

**`init_env.sh`** (lines 41-45):
```python
OPERATOR_SUPPLIED = {"SUPERUSER_PASSWORD", "SMTP_PASSWORD"}

def generated(key: str) -> str:
    return secrets.token_hex(32) if key == "SECRET_KEY" else secrets.token_hex(16)
```
Extend with `if key == "LLM_KEY_ENCRYPTION_KEY": return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()`.

**Tests to extend:** `test_env_catalog.py:82-99` (add a `PHASE3_VARIABLES` set and secret assertions, same shape as `test_phase2_variables_are_catalogued_and_secrets_empty`); `test_settings.py` (render the template with `SECRETS`, `load_settings`, assert `repr` hides the key, like `test_repr_masks_every_secret` lines 47-51).

---

### `common/security/secretbox.py` (utility, transform)

**Analog:** `common/security/tokens.py` (module docstring states the contract; pure functions; `None`/bool returns for invalid input; `now` injected for tests).

**Module shape** (tokens.py lines 1-12, 30-44): docstring with the wire format, constants at top, a `verify` that never raises on malformed input and an `_serializer` seam tests can monkeypatch (`test_overlong_rejected_before_hmac`).

Use the RESEARCH "AES-GCM envelope" excerpt (RESEARCH.md lines 585-606) as the body: `v1:<kid>:<b64url(nonce||ct||tag)>`, AAD = `f"{tenant_id}|{provider}|{instance}"`, `from Crypto.Cipher import AES` (pycryptodome, not `Cryptodome`). Unlike `tokens.verify`, a tamper/wrong-AAD must raise a typed error (`ValueError` from `decrypt_and_verify` wrapped), never return plaintext. Add a `mask_last4(secret) -> str` helper computed at save time (D-17).

**Test analog:** `test/unit_test/test_security_tokens.py` (vector-file style lines 12-30, monkeypatch seam lines 43-48). Put vectors in `test/fixtures/secretbox_vectors.json` and parametrize like `test_shared_vector`.

---

### `common/log_utils.py`, `internal/common/logger.go`, `docker/nginx/nginx.conf` (utility, transform)

**Python analog (same file):** `redact_text` is a two-stage linear scan (lines 107-110); `SENSITIVE_KEYS` (line 14) is the key list. Add a third, bounded, anchored stage for key shapes (`sk-or-v1-[A-Za-z0-9]{16,}`, `sk-[A-Za-z0-9_-]{20,}`) inside `redact_text`; keep every quantifier bounded (`{16,4096}` style, compare `_MAX_RUN` line 19) because `test_hostile_100kb_line_redacts_in_bounded_time` (test_log_redaction.py:94-113) runs a 0.25 s bound.

**Go analog:** `internal/common/logger.go` lines 68-76:
```go
func RedactString(s string) string {
	if len(s) > maxRedactInput { return RedactString(TruncateField(s, maxRedactInput-len(truncatedMarker))) }
	s = urlUserinfoPattern.ReplaceAllString(s, "${1}"+RedactedValue+"${2}")
	s = redactWith(cookiePattern, s)
	return redactWith(fragmentPattern, s)
}
```
Add a `keyShapePattern` replaced before `fragmentPattern`. RE2 is linear so no extra guard.

**Nginx analog:** `docker/nginx/nginx.conf` lines 18-23, the `map $uri $loggable_uri` with a case-insensitive regex entry for `ragflow-[A-Za-z0-9_-]{20,}`. Add one for `sk-...` shapes. Only `$uri` is logged (no query), so this covers path-borne keys only.

**Shared vectors** (`test/fixtures/log_redaction_vectors.json`): one JSON object per line, schema `{"id", "input", "secrets": [...], "keep": [...]}`:
```json
{"id": "url_userinfo", "input": "mysql://app:hunter2-fake@mysql:3306/db", "secrets": ["hunter2-fake"], "keep": ["mysql:3306/db", "app", "mysql://"]},
```
Test-first: add vectors (an SDK message such as `Incorrect API key provided: sk-or-v1-FAKE...`), see Python and Go tests fail, then implement. Use obviously fake key text.

---

### `common/doc_store/doc_store_base.py` and `rag/utils/es_conn.py` (port + adapter, CRUD)

**No close codebase analog for the port.** Use RESEARCH Pattern 3 (lines 342-395) for the signatures and the reference `common/doc_store/doc_store_base.py` lines 58-90 (`MatchTextExpr`, `MatchDenseExpr`) for field names. Safety changes required by RESEARCH: `dataset_ids` non-empty on every read/write, empty `condition` refused for `delete`/`update`, index names validated against `^[0-9a-f]{32}$` after the `ragflow_` prefix.

**Only in-repo ES precedent** is client construction (`common/health/probes.py` lines 63-70):
```python
def probe_doc_store(settings: Settings) -> None:
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=2, max_retries=0)
    try:
        client.info()
    finally:
        client.close()
```
Copy: settings-driven construction, explicit `request_timeout`, `max_retries=0`, `close()` in `finally`. The adapter keeps one sync client with a larger timeout from `Settings`, called from a bounded dedicated thread pool (see `auth.py` lines 34-39 for the `ThreadPoolExecutor` pattern and its comment on why not the default executor).

**Mapping call** (verified live, RESEARCH.md lines 622-629):
```python
es.indices.put_mapping(index=index_name, properties={
    f"q_{dim}_vec": {"type": "dense_vector", "dims": dim, "index": True, "similarity": "cosine",
                     "index_options": {"type": "hnsw", "m": 16, "ef_construction": 200}}})
info = es.indices.get_field_mapping(index=index_name, fields=f"q_{dim}_vec")
```
Treat "same dims and options already present" as success; a conflicting dims 400 is an error; reject `dims` outside 1..4096 before calling.

**Test analog for the contract suite:** `test/integration/test_python_system_routes.py` (lines 1-60): `pytestmark = pytest.mark.integration`, module-scope fixtures binding to the live stack (`_bound_database`), `load_settings()` for real endpoints. Write `test_doc_store_es.py` as an abstract contract class plus an ES subclass so Infinity can reuse it (VALIDATION Wave 0).

---

### `rag/utils/minio_conn.py`, `rag/utils/storage_factory.py`, `rag/utils/local_conn.py` (service, file-I/O)

**MinIO analog:** `common/bootstrap/ensure_bucket.py` lines 18-34:
```python
def ensure_bucket(settings: Settings, bucket: str = BUCKET_NAME) -> bool:
    mn = settings.minio
    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=10), retries=urllib3.Retry(total=2, backoff_factor=0.5))
    try:
        client = Minio(f"{mn.host}:{mn.port}", access_key=mn.user, secret_key=mn.password, secure=False, http_client=http)
        if client.bucket_exists(bucket):
            return False
        try:
            client.make_bucket(bucket)
        except S3Error as exc:
            if exc.code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):  # lost a creation race
                return False
            raise
        return True
    finally:
        http.clear()
```
Copy verbatim for STOR-08 (bucket-on-first-write inside `put`), including the bounded `urllib3` timeouts and the two tolerated S3 error codes. `probe_storage` (`common/health/probes.py` lines 51-60) is the same client construction with 2 s timeouts. `BUCKET_NAME` comes from `common/constants.py`; `INDEX_PREFIX = "ragflow_"` is already there.

**Factory:** no analog. `STORAGE_IMPL` selects `MINIO` (default) or `LOCAL`; read it from the new `StorageSettings`, not `os.environ` (the repo reads configuration only through `Settings`; `common/health/probes.py` is the one documented env exception).

**Local driver:** no analog; follow RESEARCH Pattern 8 (resolve + `is_relative_to`, reject absolute, `..`, NUL, backslash before resolving, `O_EXCL`, temp file + `os.replace`). `scripts/render_conf.py` lines 108-119 shows the existing atomic-write idiom (`os.open(..., O_EXCL, 0o600)`, `os.replace`, unlink on failure) to copy.

---

### `rag/llm/*` (service, request-response + streaming)

**No codebase analog.** Pattern source is RESEARCH Pattern 1 (provider table, error map, stream sanitizer) and the reference:
- `rag/llm/embedding_model.py` lines 259-280 (`OpenAIEmbed`: `encoding_format="float"`, sort by index, batch 16, ceiling 8191). Pass `max_retries=0` to the SDK (Pitfall 9).
- `rag/llm/chat_model.py` lines 247-266 (`_classify_error`) for error classification, but map by **exception type / status code**, not by substring of the message (the reference's substring approach would put key text through a classifier and into messages).
- `ALLOWED_GEN_CONF_KEYS` and `sanitize_gen_conf`: RESEARCH "Code Examples" lines 566-583.

Project rules that apply: never `str(exc)` a provider exception into a response or log (Pitfall 14); `litellm.suppress_debug_info = True`; lazy `import litellm`; import-warning clean (`filterwarnings=error` in `pyproject.toml`).

**Contract test fake:** `test/helpers/fake_provider.py` below.

---

### `api/db/services/tenant_scope.py` (service, request-response)

**Analog:** `api/db/services/auth_service.py`. Copy its structure: frozen dataclasses, a `Protocol` store with a real Peewee implementation, constants `_ACTIVE`/`_OWNER`, and a resolver that runs inside `DB.connection_context()`.

**Dataclasses + Protocol** (lines 46-83):
```python
@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    auth_type: str
    is_superuser: bool

class AuthStore(Protocol):
    def find_own_membership(self, user_id: str) -> MembershipRecord | None: ...
```

**Peewee store** (lines 160-171): selects use `.where(...)`, `.first()`, and compare `status == _ACTIVE`:
```python
def find_own_membership(self, user_id: str) -> MembershipRecord | None:
    row = UserTenant.select().where((UserTenant.user_id == user_id) & (UserTenant.role == _OWNER) & (UserTenant.status == _ACTIVE)).first()
    return MembershipRecord(tenant_id=row.tenant_id, role=row.role) if row is not None else None
```
`joined(user_id)` selects `UserTenant` rows with `status == "1"` and `role in (owner, admin, normal)`; the pending role is `invite` and must never be returned (matches `permissions_gen.allowed` denying unknown subjects).

**Token principals** (lines 122-129): `_principal_for_token` pins the tenant to `record.tenant_id` and the role to the owner's. `resolve()` must therefore fix the tenant for `auth_type in ("api", "beta")` and return the permission subject `"api_token"` / `"beta_token"` rather than `principal.role`.

**One 404 for everything not visible** (D-20): the handler returns the same `error_result(RetCode.NOT_FOUND, "not found", 404)` envelope for "no such id", "other tenant", and "private dataset" (compare the matrix `triple()` byte-for-byte check in `_matrix_fixtures.py:69-77`).

---

### `api/db/services/knowledgebase_service.py`, `document_service.py`, `file_service.py`, `tenant_llm_service.py` (service, CRUD)

**Analog:** `api/db/services/superuser_service.py`. It is the only service in the repo that writes several rows in one transaction under a named lock.

**Imports** (lines 18-30):
```python
import logging, re, uuid
import peewee
from api.db.database import DB, DatabaseLock, transaction
from api.db.models import Tenant, User, UserTenant
```

**Ids and one transaction** (lines 87-119): `uuid.uuid4().hex` ids (32 chars, fits every `CharField(max_length=32)`), then
```python
with transaction():
    User.create(id=user_id, ...)
    Tenant.create(id=user_id, ...)
    UserTenant.create(id=uuid.uuid4().hex, ...)
```
Use this for `File` + `Document` + `File2Document` + `Knowledgebase.doc_num += n` (RESEARCH Pattern 9 step 6) and for the dataset delete transaction (Pattern 6).

**Named lock + recheck on IntegrityError** (lines 135-153):
```python
def _seed(email: str, password: str) -> bool:
    lock_name = f"ensure_superuser:{DB.database}"[:64]
    with DatabaseLock(lock_name, LOCK_TIMEOUT_SECONDS):
        user = _existing(email)
        if user is not None:
            return _check_existing(user)
        try:
            _create(email, password)
        except peewee.IntegrityError:
            user = _existing(email)
            ...
```
Copy for `DatabaseLock(f"kb-create:{tenant_id}")` (duplicate-name check then insert) and `DatabaseLock(f"kb-upload:{kb_id}")` (auto-rename + dedupe + put). Always wrap service entry points in `with DB.connection_context():` (line 129-130). Name length stays under 64 (gotcha 9).

**Typed errors that never carry secrets** (lines 41-47): small `Exception` subclasses whose message names the setting, never the value. Define `ServiceError` subclasses carrying an HTTP intent (`NotFound`, `Forbidden`, `Conflict`, `Unavailable`) and let the handler map them; services must not import quart.

**Threading:** Peewee is synchronous; `common/bootstrap/ensure_superuser.py` line 36 shows the project's approach (`await asyncio.to_thread(...)`). For request paths use a dedicated bounded executor like `auth.py` lines 34-39 instead of the default executor (R-133).

**No analog for:** xxh64 dedupe lookup, byte-compare on hit, auto-rename, blob GC after commit. Follow RESEARCH Patterns 9-10 and the "Stream-hash" excerpt (RESEARCH.md lines 608-620).

---

### `api/apps/restful_apis/{provider,models,dataset,document}_api.py` (controller, request-response / file-I/O)

**Analog:** `api/apps/restful_apis/system_api.py` for the blueprint shape, and `test/helpers/app.py::build_blueprint` for a validated JSON body.

**Imports and blueprint** (system_api.py lines 1-13):
```python
from __future__ import annotations
from pydantic import BaseModel
from quart import Blueprint, Response, current_app
from quart_schema import document_response
from api.db.services import system_service
from api.utils.api_utils import error_result, json_result
from common.constants import RetCode
system_bp = Blueprint("system", __name__)
```

**Response models + handler + registration** (lines 38-71): an envelope `BaseModel` with `code`, `message`, `data`; `@document_response(Model, 200)`; handler returns `json_result(data)` or `error_result(RetCode.X, "msg", http_status)`; routes registered with `bp.add_url_rule(path, endpoint=..., view_func=..., methods=[...])`. Keep the path constants identical to `conf/routes.yaml` (the comment on line 15 says the module "mirrors" the registry).

**Validated request body** (`test/helpers/app.py` lines 68-70, 95-100):
```python
class NameBody(BaseModel):
    name: SafeIdentifier

@bp.post("/test/named")
@validate_request(NameBody)
async def named(data: NameBody) -> Any:
    return json_result({"name": data.name})
```
`SafeIdentifier` and `SafeText` live in `api/utils/validation.py` (lines 12-16); `RequestSchemaValidationError` is already mapped to `400 {"code":101,"message":"invalid request"}` without echoing input (`errors.py` lines 56-59). Use pydantic models with explicit allowed fields only (mass-assignment rule from RESEARCH Security Domain); never accept `tenant_id`, `created_by`, `doc_num` from the body.

**Principal access:** the gate stores it on `g.principal` (`api/apps/auth.py` line 124); handlers read `g.principal` and pass plain values (user id, tenant id, auth type) to services. Handlers must not import models or peewee (gotcha 8).

**Registration** (`api/apps/__init__.py` lines 48-52):
```python
from api.apps.restful_apis.system_api import system_bp
app.register_blueprint(system_bp)
for blueprint in extra_blueprints:
    app.register_blueprint(blueprint)
```
Add the four blueprints next to `system_bp` (local import inside `create_app`, as written).

**Envelope and status helpers** (`api/utils/api_utils.py` lines 11-42): `http_status_for(code)`; `error_result(code, message, http_status=None, data=None)`. Use `RetCode.ARGUMENT_ERROR` (101 -> 400) for a rejected provider key (Pitfall 7: never 401), `RetCode.NOT_FOUND`, `RetCode.FORBIDDEN`, `RetCode.CONFLICT`, `RetCode.SERVICE_UNAVAILABLE`.

**Upload handler (no analog):** `await request.files` / `await request.form`, per-request `request.max_content_length`, `BODY_TIMEOUT` raised for the route only, zero files is a 400 (Quart's parser is `silent=True`). Follow RESEARCH Pattern 9 and Pitfall 5. The app-wide `MAX_CONTENT_LENGTH` is 1 GiB (`api/apps/__init__.py` line 32); tighten per route.

**Test analog for handlers without a database:** `test/helpers/app.py::make_test_app(resolver=..., **sections)` builds the real factory with a stub principal; `extra_blueprints` injects a blueprint; use `Principal(...)` variants to exercise roles (`STUB_PRINCIPAL` lines 32-34).

---

### `conf/routes.yaml` and `conf/permissions.yaml` (config)

**Endpoint row format** (`conf/routes.yaml` lines 74-116). A Python tenant-scoped row:
```yaml
- {method: GET, path: "/api/v1/tenants/{tenant_id}/users", owner: go, auth: jwt, roles: [owner, admin, normal], scope: tenant,
   implemented: true, note: any active member lists; ...}
```
New rows: `owner: python`, `scope: tenant`, `roles` per D-07/D-09, `auth: jwt` for the key-writing rows (`PUT/DELETE /api/v1/providers...`, `PATCH /api/v1/models/default`) and `auth: api` otherwise, `implemented: false` until the handler lands, then flipped in the same plan. The registry row wins over the family entry for `(method, path)` (header comment lines 8-10), so per-method auth differences within `/api/` need rows, not new families.

**Family entries** (lines 52-68): add `{owner: python, match: exact, path: /api/v1/documents/upload, auth: api, body_limit: 101m, streaming: true}`; a `body_limit: 1m` entry for JSON prefixes `/api/v1/datasets`, `/api/v1/providers`, `/api/v1/models`. The catch-all `/api/` stays `1024m`. Remember gotcha 2.

**Permission rows** (`conf/permissions.yaml` lines 15, 22):
```yaml
- {area: tenant_settings, action: update_llm_keys, description: Update LLM Provider Keys, allow: [owner, admin], enforced_in: phase-3}
```
Add `{area: tenant_settings, action: view_models, ..., allow: [owner, admin, normal, api_token], enforced_in: phase-3}` and `{area: tenant_settings, action: set_default_models, ..., allow: [owner, admin], enforced_in: phase-3}`. The generator rejects `invite` as a subject, unknown fields, duplicate rows and rows missing `enforced_in` (`test_invalid_table_is_rejected`, lines 135-153). `datasets.manage_dataset` / `manage_document` already exist and include `normal` and `api_token`; D-09's "own documents only" is an object rule in the service, not a matrix row.

**Generated outputs** to regenerate and commit: `api/apps/permissions_gen.py`, `api/apps/route_policy_gen.py`, `internal/common/permissions_gen.go`, `internal/common/route_policy_gen.go`, `docker/nginx/ragflow.conf`, `docker/nginx/ragflow.https.conf`, `web/src/constants/api-routes.generated.json`. Drift gate: `uv run python scripts/gen_routes.py --check` (also run by `scripts/ci/check_generated.py`). Add cases to `test/fixtures/route_policy_cases.json` (schema: `{"method","path","auth","owner","scope","preflight"}`) so Go and Python resolvers are proven identical.

---

### `test/testcases/test_{provider,dataset,upload,document}_flow.py`, `test_create_kb_e2e.py` (test, request-response)

**Analog:** `test/testcases/test_api_token_flow.py`.

**Header and fixtures** (lines 1-52):
```python
pytestmark = pytest.mark.e2e
...
@pytest.fixture
def accounts() -> Iterator[tuple[Account, Account]]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.two_accounts()
    finally:
        registry.cleanup()

def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```
Tests take the session-scoped `ingress: httpx.Client` from `test/testcases/conftest.py` (lines 41-48), call the real endpoints through Nginx, assert `resp.json()["code"] == 0` and `resp.headers["x-api-source"] == "python"` (line 65 shows the header assertion for Go). Envelope equality for errors: `assert bad.json() == UNAUTHORIZED` (line 72).

**Real-state assertions** (no mocks): read MySQL via `test/helpers/db.py::root_connection()` (used in `accounts.py` lines 109-119), list MinIO by prefix with the `minio` client built from `stack_env()`, and read ES mapping via the Python client against `ES_PORT`. Cleanup by recorded ids (gotcha 13).

**Live-model tests (`live_model`)**: register the marker in `pyproject.toml` `markers` (lines 31-37 pattern: `"live_model: needs the provider key; fails, not skips, when absent (D-04)"`). Read the key from `stack_env()["OPENROUTER_API_KEY"]` (`test/conftest.py::stack_env`), pass it only in the PUT body, never print or assert on it, and fail with a fixed message when missing (D-04).

---

### `test/helpers/fake_provider.py` (test helper, request-response)

**Analog:** `test/helpers/app.py` (builds a real Quart app and a `Blueprint`) and `test/helpers/wait.py::wait_until` for readiness polling (used in `conftest.py` line 45).

Pattern: a Quart app (`Blueprint` routes for `/v1/chat/completions`, `/v1/embeddings`, `/openai/deployments/<d>/...`, `/api/embed`) served by Hypercorn on an ephemeral loopback port inside a fixture, recording method, path, query, headers and body for assertions. It stands in for a third party, not for an own service. No existing fixture binds a real port; use `hypercorn.asyncio.serve` (already a dependency) as `api/ragflow_server.py::_serve` does (lines 110-119: `Config().bind`, `shutdown_trigger=stop.wait`). No fixed sleeps: wait with `wait_until`.

---

### `test/testcases/_matrix_fixtures.py`, `test_cross_tenant_matrix.py` (test, request-response)

**Analog:** same files. Rows are read from the registry (`load_tenant_rows`, lines 52-59); a row with path parameters needs a `BUILDERS` entry, one without needs a `NO_ID_CHECKS` entry, otherwise `coverage_problems` fails (lines 299-313).

**Builder shape** (lines 193-215, 241-248):
```python
@dataclass
class Target:
    real: dict[str, str]                 # placeholder -> id of A's real resource
    send: Callable[..., httpx.Response]  # (client, token, ids, *, query=None, extra_body=None)
    snapshot: Callable[[], Any]          # reads the resource back as A

def _delete_token(w: World) -> Target:
    return Target({"token": str(w.a_tokens[0]["token"])}, _sender("DELETE", TOKENS + "/{token}"), w.snapshot_tokens)

BUILDERS: dict[str, Builder] = {"DELETE /api/v1/system/tokens/{token}": _delete_token, ...}
```
Phase 3: extend `World` (lines 110-123) with A's provider (use the fake-provider URL, the matrix is about isolation, Pitfall 15), a `team` dataset, a `me` dataset created by `normal`, and a document; add `BUILDERS` entries for `GET/PUT/DELETE /api/v1/datasets/{dataset_id}`, `GET/DELETE /api/v1/datasets/{dataset_id}/documents`, `DELETE /api/v1/providers/{provider}` etc.; add `NO_ID_CHECKS` for `GET/POST /api/v1/datasets`, `GET /api/v1/providers`, `GET /api/v1/models`, `PATCH /api/v1/models/default`, `POST /api/v1/documents/upload`, modelled on `check_tokens_list` (lines 259-272): call as B, with smuggled `tenant_id`/`user_id` query and body, `_assert_no_a_data`, then `assert w.snapshot... == before`. Add the API-token-refused check for key routes (line 271 is the pattern: `assert call(..., w.b_api_token, ...).status_code == 401`; for `auth: jwt` rows an API token gets 401).

---

### `test/testcases/test_response_leaks.py`, `_leak_sweep.py` (test, request-response)

**Analog:** same files. `Sweep` (lines 44-74) records every response with a row label and scans it; `s.secret(label, value, allowed_rows)` registers a value that must never appear. `sweep_tenant_rows(s, w)` (line 167) is where per-row exercisers live; `test_every_implemented_row_is_exercised_on_a_success_and_an_error_path` (line 278) fails for an unexercised registry row.

Phase 3 additions: a `sweep_model_rows` and `sweep_dataset_rows` exerciser; register a sentinel provider key (`s.secret("provider key", SENTINEL, frozenset())`, allowed in no row, including the request echo); register the ciphertext envelope read back from MySQL (`collect_database_secrets`, line 225, is the pattern for DB-read secrets). Add `v1:` envelope prefix handling if needed. Mind gotcha 3 for DTO key names.

---

### `test/helpers/accounts.py` (test helper, CRUD)

**Analog:** same file, lines 105-120 (`delete_accounts`): per-account `DELETE FROM ... WHERE tenant_id = %s` statements with a single `USE` and recorded ids only. Add `DELETE FROM` for `document` (via `kb_id IN (SELECT id FROM knowledgebase WHERE tenant_id=%s)`), `file2document`, `file`, `knowledgebase`, `tenant_model`, `tenant_model_instance`, `tenant_model_provider` for the tenant. Do not delete by pattern (comment at line 106).

---

### `test/unit_test/test_layering.py` (test, n/a)

**Analog:** same file lines 25-44. Add:
```python
def test_rag_and_doc_store_do_not_import_the_web_layer():
    assert _violations("rag", ("api.apps", "quart", "quart_schema", "quart_cors")) == []
    assert _violations("common/doc_store", ("api.apps", "quart", "api.db")) == []
```
`_violations` already accepts any directory relative to `ROOT`.

---

### `scripts/clean_room.sh`, `scripts/preflight.sh` (config, batch)

**clean_room.sh** step list (lines 86-97): each step is `step NAME CMD...`, a failing step exits 1. Insert after `e2e-serial`:
```bash
step live-model uv run python run_tests.py -m live_model
```
The key is read from `docker/.env` inside the test process (via `stack_env()`), so the script never needs to export or print it. The script already shows the safe-read idiom for other secrets (lines 52-55): `grep -E '^MYSQL_ROOT_PASSWORD=' docker/.env | tail -n1 | cut -d= -f2-` then `export`. Do not copy that for the OpenRouter key; reading it in Python keeps it out of the shell environment and process list.

**preflight.sh** (lines 11-17, 36-40): `env_value KEY DEFAULT` reads `.env`; `fail CHECK MEASURED ACTION` prints `FAIL`/`ACTION`. Add a key-presence check that tests `[ -n "$(env_value OPENROUTER_API_KEY '')" ]` and prints only `OK openrouter key: present` or `fail "openrouter key" "missing" "add OPENROUTER_API_KEY to docker/.env"`; never echo the value. Note the script is `set -uo pipefail` without `-e`, so a failed `grep` inside `$(...)` is already tolerated (`|| true`).

**run_tests.py** (72 lines, not read in full): confirm `-m live_model` is passed through to pytest and that the default `-m "e2e and not serial"` selection does not pick up `live_model` tests (mark them `live_model` only, not `e2e`).

---

### Frontend: `services/*-service.ts`, `constants/api-paths.ts` (service, request-response)

**Analog:** `web/src/services/api-token-service.ts` (lines 1-36) and `team-service.ts` (lines 1-103).

**Pattern** (api-token-service.ts):
```ts
import { apiTokenPath, apiTokensPath } from "@/constants/api-paths";
import { expectRecord, request } from "./http";

interface ApiTokenDto { token: string; beta?: string; create_time: number; }
function toApiToken(dto: ApiTokenDto): ApiToken { return { token: dto.token, createTime: dto.create_time }; }

export async function listApiTokens(): Promise<ApiToken[]> {
  const rows = await request<ApiTokenDto[]>({ url: apiTokensPath, method: "GET" }, { silent: true });
  return Array.isArray(rows) ? rows.map(toApiToken) : [];
}
export async function createApiToken(): Promise<ApiToken> {
  const dto = await request<unknown>({ url: apiTokensPath, method: "POST" }, { silent: true });
  return toApiToken(expectRecord<ApiTokenDto>(dto, "token creation", ["token"]));
}
```
Rules to copy: snake_case DTO interface separate from the camelCase domain type; a `toX` mapper; `text()` coercion helper from `team-service.ts` line 53 for untrusted strings; `expectRecord` with the identifying key; every call `{ silent: true }` (pages render their own states). Drop fields the screen never shows (the provider DTO must never map any key-bearing field).

**Per-request timeouts** (UI-SPEC "HTTP client rules"): `request({ url, method, data, timeout: 45_000 }, { silent: true })`; `http.request({ ...config })` passes any axios option through (`http.ts` `requestWithMeta`). Upload: `timeout: 0`, `signal: controller.signal`, `onUploadProgress`, `data: FormData`. Do not set a `Content-Type` header manually for `FormData`.

**Paths** (`constants/api-paths.ts` lines 6-24, 38-57): paths are resolved from the generated route table; `resolveUnder("python", "/api/", "v1/datasets")` works because the Python catch-all `/api/` prefix exists in `conf/routes.yaml` (line 67). Add constants and small functions (`datasetPath(id)`) using `encodeURIComponent`, as `apiTokenPath` does (lines 41-44). A miss is a build-time throw, so regenerate `api-routes.generated.json` first (`scripts/gen_routes.py`).

---

### Frontend: `hooks/use-llm-request.ts`, `use-knowledge-request.ts`, `use-document-request.ts` (hook, request-response)

**Analog:** `hooks/use-api-token-request.ts` (lines 1-36) and `hooks/use-team-request.ts` (lines 1-86).

**Query key + hook** (use-team-request.ts lines 12-27):
```ts
export const MEMBERSHIPS_QUERY_KEY = ["team", "memberships"] as const;
export const membersQueryKey = (tenantId: string) => ["team", "members", tenantId] as const;
export function useMembershipsRequest(enabled = true) {
  return useQuery({ queryKey: MEMBERSHIPS_QUERY_KEY, queryFn: listMemberships, retry: false, enabled });
}
```
Phase 3 keys start with `["ws", tenantId, ...]` (UI-SPEC "Data and state"); read `tenantId` from the workspace store. `retry: false` because a 4xx is an answer.

**Mutation** (use-api-token-request.ts lines 17-27, 29-35): `gcTime: 0`, `onSuccess` updates cache with `setQueryData`, `onSettled: () => queryClient.invalidateQueries({ queryKey })`. Provider save mutations must call `reset()` after settle and use `gcTime: 0` so the typed key never lingers in the mutation cache (UI-SPEC "Key field").

**Cache clearing on sign out:** `http.ts` `dropSessionState` calls `queryClient?.clear()`; keys carrying provider/dataset data are cleared with the rest. Comments at the top of these hooks state which keys hold sensitive values; copy that habit.

---

### Frontend: `pages/user-setting/model/*` (component, CRUD)

**Analog:** `pages/user-setting/api/*` (page, errors, mask, delete dialog) and `pages/user-setting/team/*` (cards, forms).

**Page skeleton** (`pages/user-setting/api/index.tsx` lines 62-140): `useTranslation`, hook-driven state ladder (`isPending` -> skeleton, `forbidden` (`error instanceof ApiError && error.status === 403`) -> `ErrorState` with custom heading, `isError` -> `ErrorState noun=... onAction={() => void x.refetch()}`, empty -> `EmptyState as="h2"`), `useEffect` setting `document.title`, wrapper `data-testid="tokens-page"`, `PageHeader` + `Card`/`CardContent p-0`. Copy the structure for `models-page`, one card per section, each failing independently.

**Dialog trigger/focus handling** (`api/delete-dialog.tsx` lines 24-87): `AlertDialog` with the row's own button as `AlertDialogTrigger asChild`, cancel gets initial focus, `onClick` of the action calls `event.preventDefault()` then an async `confirm()`, `onCloseAutoFocus` prevented when the item was removed, `aria-disabled` while pending. Use for "Delete provider credentials" and the dataset/document delete dialogs.

**Form dialogs** (`team/invite-form.tsx` lines 1-105): `useForm` + `zodResolver`, `mode: "onSubmit"`, `reValidateMode: "onChange"`, `noValidate`, `inFlight` ref guard + `busy` state, inline `<Alert data-testid="alert-form-error">`, button with `aria-busy`/`aria-disabled` and `Loader2 className="animate-spin motion-reduce:animate-none"`, `Form/FormField/FormItem/FormLabel/FormControl/FormDescription/FormMessage`. Provider dialogs, create-dataset and dataset-settings reuse it; the key field uses the existing `components/password-input.tsx`.

**Server-error mapping** (`team/errors.ts` lines 7-49): one `errors.ts` per page, `statusOf(error)` from `ApiError`, fixed translated messages, and the single place server text is shown is bounded:
```ts
if (status === 400 || status === 404 || status === 409) {
  const message = error instanceof ApiError ? error.message.trim() : "";
  if (message !== "" && message.length <= MAX_SERVER_MESSAGE) return message;
}
return t("team.invite.error.fallback");
```
Phase 3 sets the bound to 300 for provider refusals (UI-SPEC "HTTP client rules"). Never route provider failures through `notifyError` with server text unbounded.

**Masked value** (`api/mask.ts` lines 14-32): all masking in one module with tests (`api/mask.test.ts`). `secret-mask.ts` is the Phase 3 twin: `maskSecret(last4)` returns 8 bullets + the 4 characters the server supplied; no reveal, no copy; a missing/short `last4` yields all bullets of the same width.

**Role-gated UI:** controls the caller may not use are **absent**, not disabled (UI-SPEC). The role in the active workspace comes from the workspace store + `GET /v1/tenant/list` (`team-service.ts::listMemberships`), not from `useUserStore` alone.

---

### Frontend: `stores/workspace-store.ts`, `components/workspace-switch.tsx`, `layouts/standard-layout.tsx` (store/component)

**Store analog:** `stores/user-store.ts` (lines 1-21), a Zustand `create<State>()((set) => ({...}))` with `reset`. The `dropSessionState` function in `http.ts` (lines 120-123) resets only `useUserStore`; add the workspace store reset there so a sign-out clears `activeTenantId` (and keep the `localStorage` key `devrag.workspace` as `{ userId, tenantId }`, ignoring another user's value, as the UI-SPEC requires).

**Storage guard analog:** `utils/authorization.ts` lines 1-40 wraps every `localStorage` access in try/catch and falls back to memory; copy that for `devrag.workspace` (blocked storage must not crash the tree).

**Menu analog:** `components/user-menu.tsx` (lines 1-77): `DropdownMenu` + `DropdownMenuTrigger asChild` + `Button variant="ghost"`, `DropdownMenuContent align=... className="min-w-56"`, `DropdownMenuLabel`, `DropdownMenuSeparator`, `DropdownMenuItem asChild` with `Link`, `data-testid` per item, user-supplied text rendered as text only. WorkspaceSwitch needs `menuitemradio`/`aria-checked` items; `components/ui/dropdown-menu.tsx` is installed (check whether `DropdownMenuRadioItem` is exported; if not, add it by hand in the same shadcn style).

**Layout edit** (`layouts/standard-layout.tsx` lines 29-50): the header's left cluster is `<div className="flex items-center gap-2">` containing the Sheet trigger and `<span className="text-xl font-semibold leading-tight">{t("app.wordmark")}</span>`. Add `hidden sm:inline` to the wordmark span, then a `Separator` and `<WorkspaceSwitch />`. `layouts/layouts.test.tsx` renders this layout; update it.

---

### Frontend: `constants/routes.ts`, `components/app-sidebar.tsx` (config/component)

**Route entry shape** (`constants/routes.ts` lines 92-98):
```ts
{
  path: "/user-setting/api",
  layout: "standard",
  auth: "required",
  component: () => import("@/pages/user-setting/api"),
  nav: { labelKey: "nav.apiTokens", icon: KeyRound, order: 4, group: "account" },
},
```
Add `/datasets` (Database, order 2, platform), `/dataset/files` (no `nav`), `/user-setting/model` (Cpu, order 5, account), and shift existing orders per UI-SPEC "Layout Shell changes". Import the new icons from `lucide-react` at line 1. Lazy `import()` per page (the build has a chunk-size check: `web/scripts/check-chunks.mjs`).

**Active match for `/dataset/files`** (`app-sidebar.tsx` lines 37-46): `NavLink`'s `isActive` is path-based with `end={entry.path === "/"}`. Add a small helper so `Datasets` is active on `/dataset` prefix too, keeping `aria-current` semantics (tested at `layouts.test.tsx:93-94`).

---

### Frontend: `components/file-upload-dialog/*` (component, file-I/O)

**No analog for drag-and-drop or per-file progress.** Use the UI-SPEC upload section as the contract. Reuse:
- `Dialog`/`DialogContent` (`components/ui/dialog.tsx`, accepts `className` so `max-w-xl` overrides `max-w-md`).
- `AlertDialog` for "Stop uploading?" (as in `api/delete-dialog.tsx`).
- The `ApiError` status switch from `team/errors.ts` for the per-file answer table.
- `AbortController` + `http.request({ signal })`: `axios.isCancel(failure)` is already passed through un-toasted by the response interceptor (`http.ts` line 142).

Native events only (no `react-dropzone`; D-21). `progress` is a hand-written two-div component with `role="progressbar"` and the aria attributes from the UI-SPEC.

---

### Frontend: new `components/ui/*` (textarea, progress, pagination, search-input, choice-group; `alert` info variant)

**Analogs:** `components/ui/native-select.tsx` (forwardRef + `cn` + displayName, lines 1-28), `components/ui/alert.tsx` (lines 1-19) and `components/ui/badge.tsx` (lines 1-27; `cva` variants).

**Extend Alert with a variant** (alert.tsx today has no variants and hard-codes `role="alert"` and the destructive stripe). Follow `badge.tsx`'s `cva` + `VariantProps` pattern to add `variant="info"` with `role="status"`, muted stripe and an `Info` icon; keep the default identical so existing tests (`data-testid="alert-form-error"` in invite-form) are unaffected.

---

### Frontend: locales, copy gate (config, n/a)

**Analog:** `locales/locales.test.ts` (flatten + `diffLocales`: same keys in `en.json` and `zh.json`, no empty values, same `{{placeholders}}`) and `constants/no-hardcoded-copy.test.ts` (scans `/src/(pages|components|layouts)/` for JSX text and for attributes `title|description|aria-label|placeholder|alt|label|heading|body|actionLabel` set to a literal containing a letter, and for any locale value of 5+ characters used as a string literal).

Consequences for new files: all copy through `t(...)`; model ids, provider names and example URLs shown as literals must live in constants that do not sit in an `aria-label=`/`placeholder=` literal; JSX text such as `OpenAI` between tags is flagged, so render provider names from a typed constant (`{provider.name}`). `data-testid` strings equal to a short locale word are tolerated only when not followed by a word character.

---

### Frontend: tests (`*.test.tsx`, `*.live.test.ts`)

**Unit analog:** `pages/user-setting/api/api-tokens.test.tsx` lines 1-100. Pattern: stub `http.defaults.adapter` (`const originalAdapter = http.defaults.adapter`), a swappable `handler(config)` returning `ok(config, data)` or `failure(config, status, code, message)`, a `calls` array to assert requests, `QueryClient` with `retry: false`, `registerQueryClient(client)`, `MemoryRouter`, `<Toaster />`, `setAuthorization("tok-session")`, `useUserStore.getState().reset()`. Obviously fake secrets with distinctive middles. For upload tests, assert `config.timeout === 0` and that `config.data instanceof FormData`.

**Live analog:** `pages/user-setting/api/api-tokens.live.test.ts` lines 1-80 and `web/src/test/live/account.ts`: `fetch(new URL(path, window.location.origin))`, register accounts through the real endpoints, record emails to `LIVE_ACCOUNTS_FILE` for removal, probe via the real ingress, `waitUntil` instead of sleeps (`web/src/test/wait-until.ts`). The live provider key must not enter the browser tier: use a loopback fake provider URL for the SPA live suite, and keep the real OpenRouter call in the Python `live_model` tier (the UI-SPEC "bad key keeps the session" live test only needs a rejecting provider, which the fake can supply).

**Config:** `web/vitest.config.ts` (projects `unit` and `live`, 60 s timeouts); scripts in `package.json` lines 9-17 (`test`, `test:live`, `gen:api`).

---

## Shared Patterns

### Envelope and status mapping (all Python handlers)
**Source:** `api/utils/api_utils.py` lines 11-42; `api/apps/errors.py` lines 55-76.
**Apply to:** every new handler.
```python
def json_result(data: Any = None, message: str = "", code: int = RetCode.SUCCESS, http_status: int | None = None) -> Response: ...
def error_result(code: int, message: str, http_status: int | None = None, data: Any = None) -> Response: ...
```
Unhandled exceptions become `500 {"code":500,"message":"internal error"}` and are logged with `exc_info` (errors.py 73-76): services must not embed secrets in exception messages because `logger.error("unhandled exception", exc_info=exc)` runs through `RedactingFilter` only for key-name shapes.

### Default-deny gate and principal
**Source:** `api/apps/auth.py` lines 96-125.
**Apply to:** all routes. The gate resolves policy by `(method, path)` from `route_policy_gen.policy_for`, answers 401/403/503 itself, and sets `g.principal`. A route not in the registry falls to the `/api/` catch-all (`auth: api`), so a missing registry row is a silent downgrade for key-writing routes. Add the `jwt` rows first, test-first.

### Tenant isolation and role checks
**Source:** `api/apps/permissions_gen.py` lines 24-27 (`allowed(subject, area, action)`), `conf/permissions.yaml`, `auth_service.py` lines 113-129.
**Apply to:** provider, model, dataset, document services. Matrix first (`allowed(subject, "tenant_settings", "update_llm_keys")`), then the object rule (creator / owner / admin), then visibility (404 vs 403, D-20, D-27).

### Transactions and locks
**Source:** `api/db/database.py` lines 175-179 (`transaction()` = `DB.atomic()`), 182-243 (`DatabaseLock`); `superuser_service.py` lines 87-153.
**Apply to:** dataset create/delete, upload, document delete, provider save (credential row + structure rows in one transaction, RESEARCH Pattern 4).

### Structured logging without secrets
**Source:** `common/log_utils.py` (`init_root_logger`, `RedactingFilter`); `api/apps/middleware.py` lines 31-43 (`logged_path`: route template only, never a value that filled it).
**Apply to:** all new logging. Use `logger.info("event", extra={...})` with ids and counts; never log request bodies, key material, provider response bodies or `str(exc)` of provider/SDK errors. Token-usage log line fields per RESEARCH Pattern 5 contain no content.

### Settings access
**Source:** `common/settings.py` (`get_settings()`); handlers get settings through `current_app.extensions["ragflow_settings"]` (`system_api.py` line 57).
**Apply to:** every new component. No `os.environ` reads in feature code.

### Bounded blocking calls
**Source:** `api/apps/auth.py` lines 34-39 (dedicated `ThreadPoolExecutor`, why), 82-93 (`asyncio.wait_for` around `run_in_executor`); `common/health/probes.py` lines 78-83 (`asyncio.timeout(cap)` + `asyncio.to_thread`).
**Apply to:** ES, MinIO, MySQL and provider calls from request paths. Use one dedicated bounded executor per concern and an explicit timeout on every call.

### Test discipline
**Source:** `test/testcases/test_api_token_flow.py`, `test/integration/test_python_system_routes.py`, `scripts/ci/check_no_sleep.py`.
**Apply to:** all tests. `pytestmark = pytest.mark.<tier>`; live fixtures wait with `wait_until`, never `sleep`; fake credentials are obviously fake (`"fake-test-secret-key-0123456789abcdef-ZZ"`, `"ragflow-test-only-0001"`); `scripts/ci/check_secrets.py` scans for real-looking secrets, so sentinel provider keys must be built so they do not trip it (build from parts, as `api-tokens.live.test.ts` line 25 does: `["live","token","pass","0001"].join("-")`).

---

## No Analog Found

Planner should use RESEARCH.md patterns (and the read-only reference where noted):

| File | Role | Data Flow | Reason / pattern source |
|---|---|---|---|
| `common/net/url_guard.py` | utility | transform | No outbound-URL validation exists. RESEARCH Pitfall 13 (scheme allow-list, no userinfo, deny link-local/metadata/own service hostnames, private ranges only when `LLM_ALLOW_PRIVATE_BASE_URLS`, re-validate at call time) |
| `common/doc_store/doc_store_base.py` | port | CRUD/search | RESEARCH Pattern 3; ref `common/doc_store/doc_store_base.py` |
| `rag/utils/es_conn.py` (search/insert/delete bodies) | adapter | CRUD/search | Only client construction exists (probes.py). RESEARCH Pattern 3; ref `rag/utils/es_conn.py`, `common/doc_store/es_conn_base.py`, `conf/mapping.json` (drop the four hard-coded `*_vec` templates) |
| `rag/utils/storage_factory.py`, `local_conn.py` | utility/service | file-I/O | RESEARCH Pattern 8 |
| `rag/llm/chat_model.py`, `embedding_model.py`, `model_meta.py`, `__init__.py` | service | request-response + streaming | RESEARCH Pattern 1, Code Examples; ref `rag/llm/` |
| `api/db/services/llm_service.py` (`LLMBundle`, composite ids, usage) | service | request-response | RESEARCH Patterns 2 and 5; ref `api/db/services/llm_service.py` |
| upload multipart handler + validation (`document_api.py`, `document_service.py`) | controller/service | file-I/O | RESEARCH Pattern 9, Pitfalls 1-3, 5; docs `docs/06-document-processing/upload.md`, `docs/20-security/file-security.md` |
| xxh64 dedupe with byte-compare, auto-rename, blob GC | service | file-I/O | RESEARCH Patterns 9-10 |
| `test/helpers/fake_provider.py` (real loopback server) | test helper | request-response | Hypercorn `serve` on an ephemeral port; see Pattern in `api/ragflow_server.py::_serve` |
| `test/integration/test_storage.py` | test | file-I/O | MinIO client construction from `ensure_bucket.py`; presigned URL fetch with `httpx` |
| `web/.../file-upload-dialog/*` dropzone and per-file progress | component | file-I/O | UI-SPEC upload section; native drag events |
| `web/.../progress.tsx`, `pagination.tsx`, `search-input.tsx`, `choice-group.tsx`, `textarea.tsx` | component | n/a | UI-SPEC component inventory; styled like `native-select.tsx` |
| `web/.../DocumentStatusBadge`, `DatasetActionsMenu` | component | n/a | `badge.tsx` + `dropdown-menu.tsx` composition per UI-SPEC |
| `internal/common/*` key-shape patterns | utility | transform | Extend `fragmentPattern` family in `logger.go` |

---

## Metadata

**Analog search scope:** `api/`, `common/`, `conf/`, `scripts/`, `docker/`, `test/`, `internal/common`, `internal/dao`, `internal/e2e`, `web/src`; reference repo `rag/llm/`, `common/doc_store/` (read-only, outline and four excerpts only).
**Files scanned:** about 110 tracked files listed; 62 read in full or in relevant ranges.
**Not read (planner to confirm when touching):** `run_tests.py`, `scripts/gen_routes.py` internals beyond its function list and constants, `api/apps/route_policy_gen.py`, `common/security/proxy.py`, `components/ui/dropdown-menu.tsx` (radio item export), `test/unit_test/test_container_scripts.py`, `test/unit_test/test_render_conf.py`, `internal/handler/*`, `internal/service/*`.
**Pattern extraction date:** 2026-10-08
