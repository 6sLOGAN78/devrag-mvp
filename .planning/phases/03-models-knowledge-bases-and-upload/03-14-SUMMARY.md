---
phase: 03-models-knowledge-bases-and-upload
plan: 14
subsystem: api
tags: [datasets, knowledge-base, elasticsearch, index-provisioning, visibility, cross-tenant, leak-sweep, openapi]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-04 registry rows and tenant_scope; 03-08 DocStoreConnection and index_name; 03-09 tenant_model_service (find_model, defaults, composite id bound); 03-12 and 03-13 handler pattern, executors, matrix builders and sweep"
provides:
  - api/db/services/knowledgebase_service.py (PARSER_IDS, DEFAULT_PARSER_CONFIG, CreateRequest, DatasetRecord, VisibleDataset, create_dataset, list_datasets, load_visible_dataset, dataset_dto, create_view, list_view, detail_view)
  - api/apps/restful_apis/dataset_api.py (dataset_bp: POST and GET /api/v1/datasets, GET /api/v1/datasets/{dataset_id})
  - test helpers: delete_tenant_artifacts (rows, ragflow_{tenant} index, MinIO keys under {tenant}/)
affects: [03-16 upload, 03-18 dataset update, 03-23 and 03-30 gallery UI, Phase 4 parsing]

tech-stack:
  added: []
  patterns:
    - "Index first, row second: the Elasticsearch index is provisioned before the knowledgebase row is inserted, so an outage leaves no half-created dataset"
    - "Named lock kb-create:{tenant_id} serialises the duplicate-name check and the insert"
    - "One NOT_FOUND answer for foreign, invisible and unknown datasets; no admin override for permission=me (D-08, D-20, D-27)"

key-files:
  created:
    - api/db/services/knowledgebase_service.py
    - api/apps/restful_apis/dataset_api.py
    - test/integration/test_knowledgebase_service.py
    - test/testcases/test_dataset_flow.py
    - test/testcases/test_create_kb_e2e.py
    - test/unit_test/test_knowledgebase_validation.py
  modified:
    - api/apps/__init__.py
    - api/utils/reasons.py
    - conf/routes.yaml
    - test/helpers/accounts.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - test/unit_test/test_probes.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "Create runs on the DOCSTORE executor (not the DB executor) with a 45 s handler timeout, so the service's 10 s lock wait and 30 s engine timeout produce typed errors rather than a handler timeout, and a stalled engine cannot park the database pool threads"
  - "Validation failures of the body values are the typed 400 reason dataset_invalid (new in api/utils/reasons.py); the request model bounds nothing itself, except the 32-hex tenant_id pattern, so an over-long embd_id stays model_unavailable"
  - "Tenant index (ragflow_{tenant_id}) is used, as decided by plan 03-28"

patterns-established:
  - "Service view functions (create_view, list_view, detail_view) return plain dicts so handlers import no models"

requirements-completed: [KB-01, KB-02, KB-03, KB-04, KB-05, KB-08, KB-09, TEN-13, TEN-16, IDX-04, IDX-05, E2E-03]

duration: closed out in ~20m (original run interrupted)
completed: 2026-10-09
---

# Phase 3 Plan 14: Dataset create, list and detail Summary

**A member creates a dataset with an explicit or default embedding model, gets a real Elasticsearch index with a `q_{dim}_vec` cosine HNSW (m=16, ef_construction=200) field before the row exists, lists and opens only the datasets visible to them, and a foreign, private or unknown id is always the same 404.**

## Note on how this plan finished

The original executor was interrupted after the three task commits and before this SUMMARY. This run did not re-implement anything: it checked the commits against the plan's acceptance criteria, confirmed the generators were current, rebuilt the stack once (the app container predated commit `122fbdc` by about two minutes) and re-ran every verification. No fix commits were needed.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `2f187c9` | failing dataset service, flow and E2E-03 tests and tenant artifact cleanup |
| 2 (GREEN) | `218af7f` | knowledge-base service with index provisioning and visibility rules |
| 3 | `122fbdc` | dataset create, list and detail routes with matrix and leak-sweep coverage |

## Accomplishments

- Service: name trimmed, 1..128, unique per workspace case-insensitively under `DatabaseLock("kb-create:{tenant}")` (42 characters); embedding model resolved through `find_model` (type embedding, recorded dimension) or the workspace default; no auto-pick; over-long composite ids are `model_unavailable` before any lock, index call or write; `create_idx` before the insert; `DocStoreError` becomes `index_unavailable` with no row.
- List: visibility predicate `tenant_id = scope AND (created_by = user OR permission = 'team')`, `keywords` as escaped LIKE, `update_time` descending, page size capped at 100.
- Detail: `load_visible_dataset` with one NOT_FOUND for foreign, invisible and unknown ids, `embedding_dimension` from the model, `upload_limits` from settings, `parser_config` merged over `DEFAULT_PARSER_CONFIG`.
- Blueprint: `CreateDatasetBody` with `extra="forbid"` accepts only name, embd_id, parser_id, permission, description, language, avatar, parser_config and `tenant_id`; responses carry no `status`, `source`, `location` or credential.
- Registry rows flipped; `gen_routes --check` and `export_openapi --check` clean (OpenAPI JSON and TS types are current); matrix builder, `NO_ID_CHECKS` and sweep exerciser added; E2E-03 asserts the DB row and the raw `get_field_mapping` of `q_1024_vec`; cleanup removes only recorded tenants' rows, `ragflow_{tenant_id}` index and `{tenant_id}/` MinIO keys.

## Verification run (this closing session, stack rebuilt, `LIVE_BASE_URL=http://127.0.0.1:8088`)

- `gen_routes.py --check` rc=0; `export_openapi.py --check` rc=0
- `pytest -m integration test/integration/test_knowledgebase_service.py`: 29 passed
- `pytest -m e2e` dataset flow, create-KB E2E-03, cross-tenant matrix, leak sweep, route enumeration: 109 passed
- `test_layering.py` and `test_account_helpers.py`: 10 passed
- `scripts/ci/run_all.py`: 7/7 gates passed
- `ruff check .`: All checks passed
- `run_tests.py -m unit`: 1757 passed, 1 skipped, 0 failed
- Acceptance greps: no `quart` or `"status"/"source"/"location"` in the service, no `api.db.models`/`peewee` in the blueprint, `extra="forbid"` present, no pattern-based delete in `test/helpers/accounts.py`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] `dataset_invalid` reason and service view functions**
- Handlers may not import models, so `create_view`, `list_view`, `detail_view` and `view_of` were added to the service, and `DATASET_INVALID` to `api/utils/reasons.py` for typed 400s on bad body values and bad `page`/`page_size`/`keywords`.
- Commits: `218af7f`, `122fbdc`

**2. [Rule 3 - Blocking] Probe-test expectation and extra unit test**
- `test/unit_test/test_probes.py` now lists `DATASETS` among the non-system blueprint paths; `test/unit_test/test_knowledgebase_validation.py` added for pure validation cases.
- Commit: `122fbdc`

**3. Create uses the DOCSTORE executor with a 45 s timeout** (plan text said the DB executor with 30 s). See key-decisions; the service also uses `DB.connection_context()` internally.

None of these change the documented behaviour or the architecture.

## Issues Encountered

None in this session. Docker needed `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 PREFLIGHT_PORTS=` for `make up` on this host (low `vm.max_map_count`, no sudo; preflight objects to ports held by this stack's own containers).

## Known Stubs

None.

## For the next plans

**03-16 (upload):**
- Resolve the dataset with `knowledgebase_service.load_visible_dataset(principal, dataset_id)` (returns `VisibleDataset(dataset, scope)`; one NOT_FOUND `dataset_not_found` for foreign, private and unknown ids). Do not write a second visibility rule.
- The index `ragflow_{tenant_id}` and the `q_{dim}_vec` field already exist after create; `embedding_dimension` is in the detail response and `tenant_embd_id` is on `DatasetRecord`.
- `upload_limits` in the detail: `max_file_bytes`, `max_files_per_request`, `max_documents`, `allowed_extensions`.
- `doc_num`, `chunk_num`, `token_num` start at 0 and are server-owned; the upload plan must update them transactionally.
- `delete_tenant_artifacts` in `test/helpers/accounts.py` already cleans `file2document`, `document`, `file`, `knowledgebase`, the tenant index and MinIO keys under `{tenant_id}/`.

**03-23 and 03-30 (gallery UI), API contract:**
- `POST /api/v1/datasets`: body `{name (required), embd_id?, parser_id? (default naive), permission? (me default | team), description?, language? (English default), avatar?, parser_config?, tenant_id?}`; unknown keys are 400. `embd_id` is the composite model id as returned by `GET /api/v1/models`. Returns the dataset DTO.
- `GET /api/v1/datasets?page=1&page_size=12&keywords=&tenant_id=` returns `data: {items: [DTO], total}`; `page_size` 1..100, `keywords` at most 128 characters.
- `GET /api/v1/datasets/{dataset_id}` returns the DTO plus `upload_limits`.
- DTO fields: `id, name, description, avatar, language, permission, embd_id, embedding_dimension, parser_id, parser_config, doc_num, chunk_num, token_num, tenant_id, created_by, create_time, update_time` (`upload_limits` on detail only). No `status`.
- `data.reason` values: `duplicate_name` (409), `dataset_invalid` (400), `model_unavailable` (400), `dimension_unsupported` (400), `no_default_embedding` (400, tell the user to pick a model or set a default), `index_unavailable` (503), `busy` (503, creation lock timeout), `dataset_not_found` (404, same for foreign/private/unknown). Forbidden role is 403 via `forbid_unless`.
- Generated types: `web/src/interfaces/openapi.d.ts`.

## Self-Check: PASSED

Commits `2f187c9`, `218af7f`, `122fbdc` exist on `master`; the service, blueprint and three test files exist; all verification above ran green on the rebuilt stack.
