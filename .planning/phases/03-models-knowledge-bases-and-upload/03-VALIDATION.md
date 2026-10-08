---
phase: 3
slug: models-knowledge-bases-and-upload
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-08
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md`, section "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode=auto`, `-p no:anyio`, `filterwarnings=error`), `go test` (tiers), vitest (plus `--project live`), Chrome CDP for browser tests |
| **Config file** | `pyproject.toml`, `run_tests.py`, the `web/` vitest config, `scripts/clean_room.sh` (gate) |
| **Quick run command** | `uv run python run_tests.py -m unit` |
| **Full suite command** | `scripts/clean_room.sh --runs 3` (phase exit). Live tiers alone: `uv run python run_tests.py -m "integration or e2e"` after `scripts/wait_stack.sh` |
| **Estimated runtime** | Not measured for this phase. The planner records it once Wave 0 lands. |

New marker to register in `pyproject.toml` (strict markers): `live_model`. It needs the provider key and runs as its own gate step that fails, not skips, when the key is absent (D-04).

---

## Sampling Rate

- **After every task commit:** Run `uv run python run_tests.py -m unit` plus the touched module's tests
- **After every plan wave:** Run unit + `-m integration` (needs the stack: `make infra-up`) and `cd web && npm run test -- --run`
- **Before `/gsd:verify-work`:** `scripts/clean_room.sh --runs 3` must be green with the key present, including the new `live-model` step, on web port 8088 with at least 4096 MB of available RAM
- **Max feedback latency:** Not measured. The planner sets it from the unit-tier runtime.

---

## Per-Task Verification Map

Task IDs, plans, waves and threat references are assigned by the planner. Rows are keyed by requirement until then.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SEC-03 | TBD | AES-GCM envelope round trip, AAD binding, tamper detection, no plaintext key in MySQL | unit + integration | `pytest test/unit_test/test_secretbox.py` ; `pytest -m integration test/integration/test_provider_key_at_rest.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SEC-02, D-17, D-23 | TBD | Key never appears in any response, log or error; leak sweep with a sentinel key | e2e | `pytest -m e2e test/testcases/test_response_leaks.py` | extend existing | ⬜ pending |
| TBD | TBD | TBD | LLM-01..05, LLM-17..20 | TBD | Drivers against fake OpenAI, Azure and Ollama servers over real loopback HTTP: error map, retry, whitelist, reasoning, sanitizer | unit | `pytest test/unit_test/test_llm_drivers.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LLM-14, LLM-15 | — | Composite id parsing, bundle credential resolution | unit | `pytest test/unit_test/test_llm_bundle.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LLM-16, LLM-24, LLM-25, LLM-27..29, TEN-12 | TBD | Provider save tests the key first; list, delete, instances, defaults; masked responses; role checks | e2e | `pytest -m e2e test/testcases/test_provider_flow.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LLM-03, LLM-21, LLM-22 (live) | — | Real chat, streamed chat, embedding batch and bad-key error on OpenRouter; `used_tokens` rises; dimension asserted from the live response | live_model | `pytest -m live_model test/testcases/test_live_models.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | KB-01..09, TEN-16 | TBD | Dataset CRUD, duplicate name (case variant), unknown embedding model, permission default `me`, update, delete | e2e | `pytest -m e2e test/testcases/test_dataset_flow.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDX-04..06, IDX-08, IDX-09, KB-03, TEST-08 | TBD | Contract suite on the real Elasticsearch: idempotent `create_idx`, mapping read back (dims, cosine, HNSW 16/200), conflicting dims error, zero-vector error, insert/get/update/delete/search with kb filter, empty `dataset_ids` refused, index-name validation | integration | `pytest -m integration test/integration/test_doc_store_es.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | E2E-03 | — | Create KB: DB row plus ES field mapping for the model's dimension | e2e | `pytest -m e2e test/testcases/test_create_kb_e2e.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STOR-01, STOR-02, STOR-06, STOR-08, STOR-10, STOR-11 | TBD | Factory, MinIO put/get/rm, bucket-on-write, presigned URL with 3600 s expiry, local traversal rejection, UUID keys | integration + unit | `pytest -m integration test/integration/test_storage.py` ; `pytest test/unit_test/test_local_storage.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-01..07, SEC-06, E2E-04 | TBD | Upload happy path (blob in MinIO, rows `run=0`, progress 0); extension, MIME, size, traversal and inaccessible-dataset rejections store nothing; same content shares a blob; auto-rename; limits; hash-collision byte compare; concurrent delete vs duplicate upload | e2e | `pytest -m e2e test/testcases/test_upload_flow.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-08, DOC-14..16 | TBD | List with paging and keywords; delete prunes chunks and garbage-collects the blob only at zero references; per-document parser override | e2e | `pytest -m e2e test/testcases/test_document_flow.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | TEN-13, D-20 | TBD | Cross-tenant matrix builders for every new tenant-scoped registry row; member roles 403/404; API token refused on key routes; second member sees a `team` dataset, not a `me` one | e2e | `pytest -m e2e test/testcases/test_cross_tenant_matrix.py` | extend existing | ⬜ pending |
| TBD | TBD | TBD | D-19 (routes, registry) | — | Registry rows, generated Nginx limits, drift gate | unit | `uv run python scripts/gen_routes.py --check` ; `pytest test/unit_test/test_gen_routes.py test/unit_test/test_nginx_limits.py` | extend existing | ⬜ pending |
| TBD | TBD | TBD | D-19 (permissions) | TBD | New permission rows regenerated in Go and Python; oracle cases | unit + Go | `pytest test/unit_test/test_permissions*.py` ; `go test ./internal/common/...` | extend existing | ⬜ pending |
| TBD | TBD | TBD | Layering | — | `rag/` and new services respect the import rules | unit | `pytest test/unit_test/test_layering.py` | extend existing | ⬜ pending |
| TBD | TBD | TBD | UI-10, UI-11, UI-12, UI-37 | — | Gallery, dialogs, workspace table, status badges, upload dialog validation, masked key form, "configured" state, missing-embedding-default message, en/zh key parity | vitest unit | `cd web && npm run test -- --run` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | UI live | TBD | Settings save with the live key; create dataset; upload through the real DOM; large upload does not hit a timeout; a bad key keeps the session | vitest live + Chrome CDP | `cd web && npm run test:live` ; `pytest -m e2e test/testcases/test_spa_browser.py` | extend existing | ⬜ pending |
| TBD | TBD | TBD | D-21 (schema) | — | Go schema verify unchanged; regenerate `conf/schema.json` and entities only if a migration is added | Go integration | `go test -tags=integration ./internal/dao/...` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Register the `live_model` marker; add the `live-model` step to `scripts/clean_room.sh` (reads the key from `docker/.env` in a subshell export, never prints it, fails when absent); add a `scripts/preflight.sh` presence check that prints only "present" or "missing"
- [ ] `test/helpers/fake_provider.py` — loopback OpenAI-compatible, Azure-shaped and Ollama-shaped server fixture that records requests
- [ ] `_matrix_fixtures.py` — builders for providers, datasets and documents (one `BUILDERS` entry per new tenant-scoped row)
- [ ] `test/fixtures/log_redaction_vectors.json` — key-shaped strings; Go logger and Nginx map parity
- [ ] `test/integration/test_doc_store_es.py` — engine-agnostic contract class so the Infinity adapter can reuse it later
- [ ] `docker/.env.example` — `LLM_KEY_ENCRYPTION_KEY`, `UPLOAD_*`, `DATASET_MAX_DOCUMENTS`, `STORAGE_IMPL`, `LLM_ALLOW_PRIVATE_BASE_URLS` and the live-test variable names (no values); `test_env_catalog.py` expectations
- [ ] `conf/service_conf.yaml.template`, `scripts/render_conf.py`, `common/settings.py` — new sections
- [ ] Package approval checkpoint (D-21), then `uv add` and the `uv.lock` commit
- [ ] `web` — i18n keys en/zh, `no-hardcoded-copy` coverage for new pages, `api-routes.generated.json` regeneration, OpenAPI types (`npm run gen:api`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Provider key placed in `docker/.env` | D-02 | Only the user holds the key; it is never pasted in chat, committed or printed | The user adds the variable to `docker/.env`; `scripts/preflight.sh` then reports "present" |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency recorded and within the planner's limit
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
