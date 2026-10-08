---
phase: 3
slug: models-knowledge-bases-and-upload
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-10-08
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md`, section "Validation Architecture". Task ids are `{plan}-T{n}` and refer to the tasks of `03-NN-PLAN.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode=auto`, `-p no:anyio`, `filterwarnings=error`), `go test` (tiers), vitest (plus `--project live`), Chrome CDP for browser tests |
| **Config file** | `pyproject.toml`, `run_tests.py`, the `web/` vitest config, `scripts/clean_room.sh` (gate) |
| **Quick run command** | `uv run python run_tests.py -m unit` |
| **Full suite command** | `scripts/clean_room.sh --runs 3` (phase exit). Live tiers alone: `uv run python run_tests.py -m "integration or e2e"` after `make up`; provider tier alone: `uv run python run_tests.py -m live_model` |
| **Estimated runtime** | Unit tier measured before Phase 3 work: 835 tests in 18 s (2026-10-08). Expected after Phase 3: 40 to 90 s. Integration and e2e tiers: a few minutes each on the dev stack. The full gate (three runs) is measured and recorded by plan 03-29 |

`live_model` is registered in `pyproject.toml` (strict markers) by plan 03-27. It needs the provider key and runs as its own gate step that fails, not skips, when the key is absent (D-04).

---

## Sampling Rate

- **After every task commit:** Run `uv run python run_tests.py -m unit` plus the touched module's tests (the task's own `<automated>` command)
- **After every plan wave:** Run unit + `-m integration` (needs the stack: `make infra-up`) and `cd web && npm run test -- --run`; API plans also run their e2e files after `make up`
- **Wave rule (shared working tree, `use_worktrees=false`):** waves 1 to 4 hold sibling plans, so their task and plan checks name their own files only (never `scripts/ci/run_all.py`, a whole-directory unit run or a stack rebuild) and the full suite runs at wave end; every plan from wave 5 on runs alone in its wave, because the image build (`make up`) copies the whole working tree (web, Python, Go, conf) and would compile a sibling's unfinished files, so no two plans that rebuild or drive the shared `devrag-stack:8088` stack ever share a wave and whole-suite checks inside those plans are valid. A rebuild is shown (`(set -o pipefail; make up 2>&1 | tail -n 25)`), never hidden, and happens once per plan
- **Unit marker:** every new Python unit test file starts with `pytestmark = pytest.mark.unit` (the gate selects `-m unit`, an unmarked file is silently skipped); each such plan checks it with `grep -c` and `pytest -m unit --collect-only`
- **Before `/gsd:verify-work`:** `scripts/clean_room.sh --runs 3` must be green with the key present, including the `live-model` step, on web port 8088 with at least 4096 MB of available RAM (plan 03-29)
- **Max feedback latency:** 120 seconds for the unit tier; 60 seconds for a task-level targeted command except the e2e, live and browser commands, which are bounded by the stack and are run once per plan (the large-upload cases of plans 03-16 and 03-26 take about 30 seconds each)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1..T3 | 03-01 | 1 | SEC-03, DOC-03, STOR-01, LLM-16 | T-03-01-01..05 | AES-GCM envelope round trip, AAD binding, tamper detection; limits bounded at the Nginx cap; secrets empty in the example env | unit | `uv run pytest test/unit_test/test_secretbox.py test/unit_test/test_settings.py test/unit_test/test_env_catalog.py test/unit_test/test_container_scripts.py test/unit_test/test_layering.py -q` | ❌ W0 | ⬜ pending |
| 03-02-T1..T3 | 03-02 | 1 | SEC-02, LLM-16 | T-03-02-01..04 | Key shapes masked in Python, Go and Nginx logs; SSRF guard denies link-local, internal names, odd spellings | unit + Go | `uv run pytest test/unit_test/test_log_redaction.py test/unit_test/test_nginx_log_format.py test/unit_test/test_url_guard.py -q` ; `GOTOOLCHAIN=local go test ./internal/common/ -count=1` | ❌ W0 | ⬜ pending |
| 03-03-T1..T3 | 03-03 | 1 | TEN-13 | T-03-03-01..03 | Workspace store ignores another user's value; only joined workspaces listed; live switch with two real accounts | vitest unit + live | `cd web && npm run test -- --run src/stores src/components src/layouts` ; `npm run test:live -- src/test/live/workspace.live.test.ts` | ❌ W0 | ⬜ pending |
| 03-04-T1..T3 | 03-04 | 1 | TEN-12, TEN-13, TEN-16, LLM-23, LLM-28 | T-03-04-01..05 | Registry rows, generated Nginx limits, permission rows in Go and Python, acting-tenant resolution against real MySQL | unit + Go + integration | `uv run python scripts/gen_routes.py --check` ; `uv run pytest test/unit_test/test_permissions_table.py test/unit_test/test_nginx_limits.py test/unit_test/test_route_policy.py test/unit_test/test_tenant_scope.py -q` ; `uv run pytest -m integration test/integration/test_tenant_scope.py -q` ; `GOTOOLCHAIN=local go test ./internal/common/... -count=1` | extend existing | ⬜ pending |
| 03-05-T1..T3 | 03-05 | 2 | LLM-01, 02, 04, 05, 17..20, 22 | T-03-05-01..05 | Drivers against fake OpenAI, Azure and Ollama servers over real loopback HTTP: error map, single bounded retry (own `retry.py`), whitelist, reasoning, sanitizer (own `stream.py`), no redirect, no SSRF, lazy litellm import | unit | `uv run pytest test/unit_test/test_llm_registry.py test/unit_test/test_llm_shared.py test/unit_test/test_llm_drivers.py -q` | ❌ W0 | ⬜ pending |
| 03-06-T1..T2 | 03-06 | 3 | LLM-03, 04, 05, 19, 21 | T-03-06-01..05 | Embedding drivers: order, batching, dimension from the response, offline tokenizer, error map | unit | `uv run pytest test/unit_test/test_llm_embeddings.py -q` | ❌ W0 | ⬜ pending |
| 03-07-T1..T3 | 03-07 | 2 | STOR-01, 02, 06, 08, 10, 11, SEC-06 | T-03-07-01..05 | Factory, MinIO put/get/rm, bucket on first write, presigned URL with 3600 s expiry, local traversal rejection, generated keys | unit + integration | `uv run pytest test/unit_test/test_local_storage.py test/unit_test/test_storage_factory.py -q` ; `uv run pytest -m integration test/integration/test_storage.py -q` | ❌ W0 | ⬜ pending |
| 03-08-T1..T3 | 03-08 | 2 | IDX-04, 05, 06, 08, 09, TEST-08 | T-03-08-01..06 | Port hardening (required dataset ids, no empty condition, validated index names) and contract suite on the real Elasticsearch: mapping read back with dims, cosine, HNSW 16/200, conflict and zero-vector errors, kb isolation, hybrid search | unit + integration | `uv run pytest test/unit_test/test_doc_store_port.py -q` ; `uv run pytest -m integration test/integration/test_doc_store_es.py -q` | ❌ W0 | ⬜ pending |
| 03-09-T1..T3 | 03-09 | 3 | SEC-03, LLM-16, LLM-29, TEN-12 | T-03-09-01..06 | No plaintext key in any MySQL column, AAD-bound envelope, atomic provider rows, upsert with key rotation re-sealing every row of the instance, explicit defaults, exact capped usage counter | unit + integration | `uv run pytest test/unit_test/test_model_ref.py -q` ; `uv run pytest -m integration test/integration/test_provider_key_at_rest.py test/integration/test_tenant_model_service.py -q` | ❌ W0 | ⬜ pending |
| 03-10-T1..T3 | 03-10 | 4 | LLM-16, 19, 24, 25, 27, SEC-02, SEC-03 | T-03-10-01..08 | Save tests every model first; dimension from the live answer; SSRF refusals send zero requests; key never sent to a new address; rotation and keyless address change succeed; fail-closed limiter | unit + integration | `uv run pytest test/unit_test/test_provider_policy.py -q` ; `uv run pytest -m integration test/integration/test_provider_service.py test/integration/test_ratelimit.py -q` | ❌ W0 | ⬜ pending |
| 03-11-T1..T2 | 03-11 | 4 | LLM-14, 15, 21, 03 | T-03-11-01..06 | Composite id resolution, own-tenant credentials only, dimension check, exact usage once, no key in repr or logs | unit + integration | `uv run pytest test/unit_test/test_llm_bundle.py -q` ; `uv run pytest -m integration test/integration/test_llm_bundle_flow.py -q` | ❌ W0 | ⬜ pending |
| 03-12-T1..T3 | 03-12 | 5 | LLM-23..27, SEC-02, TEN-13 | T-03-12-01..08 | Provider routes: roles, masking (no address or last4 for members or API tokens), 400 never 401 for a refused key, rotation and address change, joined-workspace access, token refusal, byte-identical 404, matrix and sweep rows | unit + e2e | `uv run pytest test/unit_test/test_service_errors.py -q` ; `make up && uv run pytest -m e2e test/testcases/test_provider_flow.py test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py -q` | ❌ W0 | ⬜ pending |
| 03-13-T1..T3 | 03-13 | 6 | LLM-28, TEN-12, TEN-13 | T-03-13-01..05 | Models and defaults routes: nothing auto-picked, owner/admin only writes, API token refused | e2e | `make up && uv run pytest -m e2e test/testcases/test_models_flow.py test/testcases/test_cross_tenant_matrix.py -q` | ❌ W0 | ⬜ pending |
| 03-14-T1..T3 | 03-14 | 7 | KB-01..05, 08, 09, TEN-16, IDX-04, 05, E2E-03 | T-03-14-01..07 | Dataset create with duplicate rule and lock, embedding validation, real index field, `me` private from owners and admins, closed-index failure leaves no row | integration + e2e | `uv run pytest -m integration test/integration/test_knowledgebase_service.py -q` ; `make up && uv run pytest -m e2e test/testcases/test_dataset_flow.py test/testcases/test_create_kb_e2e.py -q` | ❌ W0 | ⬜ pending |
| 03-15-T1..T2 | 03-15 | 4 | DOC-02, 03, 04, SEC-06 | T-03-15-01..06 | Filename, extension, MIME, magic, size, batch and capacity rules; rename; streaming hash and byte comparison | unit | `uv run pytest test/unit_test/test_upload_rules.py -q` | ❌ W0 | ⬜ pending |
| 03-16-T1..T3 | 03-16 | 8 | DOC-01..07, 16, STOR-11, SEC-06, E2E-04 | T-03-16-01..08 | Upload happy path (blob in MinIO under a generated key, rows `run=0`, progress 0); every rejection stores nothing; forged-hash collision never links a foreign blob; compensation; per-request limits | unit + integration + e2e | `uv run pytest test/unit_test/test_upload_request_limits.py -q` ; `uv run pytest -m integration test/integration/test_upload_service.py -q` ; `make up && uv run pytest -m e2e test/testcases/test_upload_flow.py -q` | ❌ W0 | ⬜ pending |
| 03-17-T1..T3 | 03-17 | 9 | DOC-08, 14, 15, 16 | T-03-17-01..07 | List with paging and keywords; all-or-nothing authorised delete; chunks pruned; blob removed only at zero references; delete versus upload race | integration + e2e | `uv run pytest -m integration test/integration/test_document_service.py -q` ; `make up && uv run pytest -m e2e test/testcases/test_document_flow.py -q` | ❌ W0 | ⬜ pending |
| 03-18-T1..T3 | 03-18 | 10 | KB-06, 07, 08, 09, TEN-16, DOC-14, 15 | T-03-18-01..07 | Update rules (duplicate, embedding lock, visibility narrowing); permanent delete with shared blobs preserved, the dataset's index rows removed and the shared tenant index kept (R-136); index failure aborts | integration + e2e | `uv run pytest -m integration test/integration/test_dataset_lifecycle.py -q` ; `make up && uv run pytest -m e2e test/testcases/test_dataset_lifecycle_flow.py -q` | ❌ W0 | ⬜ pending |
| 03-19-T1..T2 | 03-19 | 11 | TEN-13, SEC-02, SEC-03, SEC-06 | T-03-19-01..06 | Registry-driven role, stranger, token and visibility table; key-shape scanner; sentinel key absent from responses, DB plaintext and container logs | e2e | `make up && uv run pytest -m e2e test/testcases/test_phase3_isolation.py test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py test/testcases/test_log_token_masking.py -q` | extend existing | ⬜ pending |
| 03-20-T1..T3 | 03-20 | 13 | UI-37, LLM-23, LLM-28 | T-03-20-01..05 | Models page view: five providers, role-aware credential line, per-card states, nav order | vitest unit | `cd web && npm run test -- --run src/services src/pages/user-setting/model src/layouts src/components src/routes.test.tsx` | ❌ W0 | ⬜ pending |
| 03-21-T1..T3 | 03-21 | 14 | UI-37, LLM-24, 25, 27 | T-03-21-01..06 | Provider dialogs: key only in form state, refusal inline without session purge, address-change rule, accessible names | vitest unit | `cd web && npm run test -- --run src/pages/user-setting/model src/services` | ❌ W0 | ⬜ pending |
| 03-22-T1..T3 | 03-22 | 15 | UI-37, TEN-12, TEN-13 | T-03-22-01..05 | Defaults card (nothing preselected); live: save through the dialog, mask, defaults persist, bad key keeps the session, member read-only | vitest unit + live | `cd web && npm run test -- --run src/pages/user-setting/model` ; `make up && npm run test:live -- src/pages/user-setting/model/models.live.test.ts` | ❌ W0 | ⬜ pending |
| 03-23-T1..T3 | 03-23 | 16 | UI-10, KB-01, 02, 04, TEN-13 | T-03-23-01..04 | Hand-written list and form parts, dataset service with clamped inputs, workspace-scoped query keys and invalidation | vitest unit | `cd web && npm run test -- --run src/components/ui src/services/dataset-service.test.ts src/hooks/use-knowledge-request.test.tsx` | ❌ W0 | ⬜ pending |
| 03-24-T1..T3 | 03-24 | 17 | UI-12, DOC-01..03, SEC-06 | T-03-24-01..06 | Upload rules and queue (extension, size, batch, rename, abort), `timeout: 0`, stop confirmation, announcements | vitest unit | `cd web && npm run test -- --run src/components/file-upload-dialog src/services` | ❌ W0 | ⬜ pending |
| 03-25-T1..T3 | 03-25 | 19 | KB-06, 07, DOC-14, TEN-13, TEN-16 | T-03-25-01..04 | Settings dialog, delete dataset with a fresh count, delete document, permission-driven gallery menu, 403 handling | vitest unit | `cd web && npm run test -- --run src/pages/dataset/delete-dialogs.test.tsx src/pages/dataset/settings-dialog.test.tsx src/services/dataset-service.test.ts src/pages/datasets` | ❌ W0 | ⬜ pending |
| 03-26-T1..T2 | 03-26 | 21 | UI-10..12, E2E-03, E2E-04, DOC-15, KB-07 | T-03-26-01..04 | Owner and member journeys on the real stack; real Chrome upload through the real input; throttled large upload beyond the default client timeout | vitest live + CDP | `make up && cd web && npm run test:live -- src/pages/dataset/dataset.live.test.ts` ; `uv run pytest -m e2e test/testcases/test_spa_browser.py -q` | extend existing | ⬜ pending |
| 03-27-T1..T2 | 03-27 | 12 | LLM-03, 19, 21, KB-02, 03, SEC-02 | T-03-27-01..05 | Real chat, streamed chat and embedding batch on OpenRouter; `used_tokens` rises; dimension asserted live; bad key refused; key absent from responses and logs | live_model | `uv run python run_tests.py -m live_model` | ❌ W0 | ⬜ pending |
| 03-28-T1..T2 | 03-28 | 22 | records for D-21, D-24 and the discretionary choices | T-03-28-01..03 | Decision rows R-136..R-147, pin consistent across CLAUDE.md, pyproject.toml and uv.lock, B-09 closed | unit | `uv run pytest test/unit_test/test_phase3_records.py test/unit_test/test_check_decisions.py -q` ; `uv run python scripts/ci/check_decisions.py` | ❌ W0 | ⬜ pending |
| 03-29-T1..T2 | 03-29 | 23 | all phase requirements (TEST-08, E2E-03, E2E-04) | T-03-29-01..04 | Traceability of requirements, decisions and registry rows; three clean-room runs with the key present | unit + gate | `PHASE3_GATE=1 uv run pytest test/unit_test/test_phase3_traceability.py -q` ; `scripts/clean_room.sh --runs 3` | ❌ W0 | ⬜ pending |
| 03-30-T1..T3 | 03-30 | 18 | UI-10, KB-01, 02, 04, TEN-13, TEN-16 | T-03-30-01..05 | Gallery states, paging, search, create dialog with blocked form and error mapping, nav order pins | vitest unit | `cd web && npm run test -- --run src/components/create-dataset-dialog src/pages/datasets src/layouts src/routes.test.tsx` | ❌ W0 | ⬜ pending |
| 03-31-T1..T3 | 03-31 | 20 | UI-11, UI-12, KB-05, DOC-08, DOC-14, TEN-13, TEN-16 | T-03-31-01..05 | Workspace page, document table, permission-driven controls, drop overlay, deep link into a joined workspace without an effect loop, sidebar match | vitest unit | `cd web && npm run test -- --run src/pages/dataset src/layouts` | ❌ W0 | ⬜ pending |
| cross-cutting | 03-04, 03-12 to 03-19 | 1, 5 to 11 | D-19 (routes, registry, permissions) | T-03-04-04 | Registry rows, generated Nginx limits, drift gate, oracle cases in Go and Python | unit + Go | `uv run python scripts/gen_routes.py --check` ; `uv run pytest test/unit_test/test_gen_routes.py test/unit_test/test_nginx_limits.py test/unit_test/test_permissions_table.py -q` ; `GOTOOLCHAIN=local go test ./internal/common/... -count=1` | ✅ | ⬜ pending |
| cross-cutting | 03-01, 03-05..03-09 | 1 to 3 | Layering | — | `rag/`, `common/doc_store`, `common/net` and new services respect the import rules | unit | `uv run pytest test/unit_test/test_layering.py -q` | extend existing | ⬜ pending |
| cross-cutting | 03-01 | 1 | D-21 (schema) | — | Go schema verify unchanged: no migration is added in this phase | Go integration | `go test -tags=integration ./internal/dao/...` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Each item names the plan that creates it.

- [ ] Register the `live_model` marker; add the `live-model` step to `scripts/clean_room.sh` and a key-presence check in `scripts/preflight.sh` that prints only "present" or "missing" (plan 03-27)
- [ ] `test/helpers/fake_provider.py` — loopback OpenAI-compatible, Azure-shaped and Ollama-shaped server fixture that records requests (plan 03-05); stack mode for the app container (plan 03-12); Node twin for the browser tier (plan 03-22)
- [ ] `_matrix_fixtures.py` — builders for providers, datasets and documents (plans 03-12, 03-13, 03-14, 03-16, 03-17, 03-18), role and visibility table (plan 03-19)
- [ ] `test/fixtures/log_redaction_vectors.json` — key-shaped strings; Go logger and Nginx map parity (plan 03-02)
- [ ] `test/helpers/doc_store_contract.py` and `test/integration/test_doc_store_es.py` — engine-agnostic contract class so the Infinity adapter can reuse it later (plan 03-08)
- [ ] `docker/.env.example` — `LLM_KEY_ENCRYPTION_KEY`, `UPLOAD_*`, `DATASET_MAX_DOCUMENTS`, `STORAGE_IMPL`, `LLM_ALLOW_PRIVATE_BASE_URLS` and the live-test variable names (no values); `test_env_catalog.py` expectations (plan 03-01)
- [ ] `conf/service_conf.yaml.template`, `scripts/render_conf.py`, `common/settings.py` — new sections (plan 03-01)
- [ ] Package install: approval is given by D-24, so `uv add` and the `uv.lock` change happen in plan 03-01 without a checkpoint
- [ ] `web` — i18n keys en/zh, `no-hardcoded-copy` coverage for new pages, `api-routes.generated.json` regeneration (plans 03-04, 03-20 to 03-25, 03-30 and 03-31)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Provider key placed in `docker/.env` | D-02 | Only the user holds the key; it is never pasted in chat, committed or printed | Already done on 2026-10-08 (D-25); `scripts/preflight.sh` reports "present" and the gate fails with a fixed message if it is ever removed |
| Chinese strings of the new screens | UI-42 context | Drafted by the implementer; review is the open B-18 item | Native-speaker review before release |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency recorded and within the planner's limit
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-10-08; execution results (all rows green, measured gate runtime) are recorded by plan 03-29, which also sets `wave_0_complete: true`.
