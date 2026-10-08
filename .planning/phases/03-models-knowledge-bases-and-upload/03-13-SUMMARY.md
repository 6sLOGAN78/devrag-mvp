---
phase: 03-models-knowledge-bases-and-upload
plan: 13
subsystem: api
tags: [models, defaults, handlers, cross-tenant, leak-sweep, openapi]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-04 registry rows and tenant_scope; 03-09 tenant_model_service (list_models, get_defaults, set_defaults, composite id bound); 03-12 handler pattern, executors, matrix builders and sweep"
provides:
  - api/db/services/model_defaults_service.py (model_dto, list_model_dtos, defaults_dto, update_defaults)
  - api/apps/restful_apis/models_api.py (models_bp: GET /api/v1/models, GET and PATCH /api/v1/models/default)
affects: [03-14 dataset create (reads defaults), Models page in the SPA, 03-19]

tech-stack:
  added: []
  patterns:
    - "Absent vs null in a PATCH body: model_fields_set picks the slots to change; absent keys never touch a value, null clears"
    - "An invalid or over-long composite id is a typed 400 model_unavailable from the service (InvalidModelRef), never a database error"

key-files:
  created:
    - api/db/services/model_defaults_service.py
    - api/apps/restful_apis/models_api.py
    - test/testcases/test_models_flow.py
    - test/unit_test/test_model_defaults_service.py
  modified:
    - api/apps/__init__.py
    - conf/routes.yaml
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - test/unit_test/test_probes.py
    - test/unit_test/test_route_policy.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "The PATCH body model puts no length bound on the model ids: a bound would turn an over-long id into a generic validation error, while the plan requires the typed model_unavailable; the 1 MB body limit at Nginx already caps the size, and parse_model_ref checks the length first"
  - "A change set naming a slot that does not exist, or no slot at all, is 400 models_invalid; a refused slot in a two-slot body writes nothing (set_defaults verifies both before its single UPDATE)"
  - "model_dto adds provider to the keys of provider_service.model_dto and is a separate explicit key list, so the models route cannot pick up a credential field added elsewhere"

patterns-established:
  - "Route plans flip registry rows together with a NO_ID_CHECKS entry and a sweep exerciser; World.snapshot() carries every resource the checks assert unchanged (models and defaults added here)"

requirements-completed: [LLM-28, TEN-12, TEN-13, LLM-29]

duration: ~50m
completed: 2026-10-09
---

# Phase 3 Plan 13: Model list and default-model routes Summary

**Members read the workspace's configured models and defaults as composite ids; owners and admins (session token only) set or clear the default chat and embedding model explicitly, nothing is ever auto-picked, a foreign workspace is the single 404 and a bad or over-long model id is a typed 400. Proven through Nginx on the rebuilt stack, in the cross-tenant matrix and in the leak sweep.**

## Accomplishments

- `model_defaults_service`: explicit DTO keys (`id`, `name`, `provider`, `instance`, `type`, `dimension`, `max_tokens`, `used_tokens`), `type` filter (`chat` or `embedding`, else `models_invalid`), `defaults_dto` (empty string means not set), `update_defaults` (absent slot keeps, `None` clears, string parsed with `parse_model_ref`, delegating to `tenant_model_service.set_defaults` which verifies existence and type).
- `models_bp`: three thin handlers in the 03-12 order `acting_scope` (404), `forbid_unless` (403, `view_models` or `set_default_models`), `run_blocking(DB_EXECUTOR, ..., timeout=10)`, `service_error_response`; `DefaultsBody` with `extra="forbid"`, a 32-hex `tenant_id` pattern and `model_fields_set`. Registered in `create_app`.
- Registry: the three model rows are `implemented: true` (the PATCH row was already `auth: jwt`); `gen_routes --check` and `export_openapi --check` clean; OpenAPI JSON and TypeScript types regenerated.
- Matrix: `World.snapshot()` holds A's `models` and `defaults`; A chooses its embedding default when the world is built. `NO_ID_CHECKS` for `GET /models`, `GET /models/default` and `PATCH /models/default`.
- Sweep: `sweep_model_rows` calls all three rows on success and error paths (type filter, invalid type, unknown model, 129-character id, empty body, unknown field, member, outsider, API token).

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing end-to-end flow | `b9cfc6a` | red on the old stack |
| 2 Defaults service and models blueprint (+ unit tests) | `4e7cb86` | layering, route-auth markers, ruff green |
| 3 Registry flip, matrix checks, sweep exerciser, pinned tests, OpenAPI | `1bebcf1` | e2e green on the rebuilt stack |

## Verification (real output)

Red run (before implementation, old stack):

- `LIVE_BASE_URL=http://127.0.0.1:8088 uv run pytest -m e2e test/testcases/test_models_flow.py -q` -> `4 failed in 2.57s`, each `AssertionError: {"code": 404, "message": "not found", "data": null}` on the first model route (not a fixture error).

Green runs:

- `uv run pytest test/unit_test/test_model_defaults_service.py test/unit_test/test_layering.py test/unit_test/test_route_auth_markers.py -q` -> `27 passed`.
- Stack rebuilt once: `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 PREFLIGHT_PORTS= make up` then `scripts/wait_stack.sh` -> `stack ready` (app, es01, minio, mysql, mailpit, redis healthy; init exited). The port holders were confirmed as `devrag-stack-*` containers beforehand.
- `uv run python scripts/gen_routes.py --check` -> exit 0.
- `uv run pytest -m e2e test/testcases/test_models_flow.py test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py test/testcases/test_route_enumeration.py -q` -> `95 passed, 12 deselected in 20.18s` (flow: 4 passed; matrix cases for the three model rows passed).
- `uv run pytest test/unit_test scripts/ci/tests -m unit -q` -> `1725 passed, 1 skipped`.
- `uv run python scripts/ci/run_all.py` -> `7/7 gates passed`; `uv run ruff check .` -> `All checks passed!`.
- Wider live run, `test/testcases` and `test/integration`, `(e2e or integration) and not serial`, log-masking file deselected: `499 passed, 32 deselected in 159.53s`; the log-masking file alone: `3 passed`.

Not run: a mutation check against the stack (it would need a second image build). The negative cases (token PATCH 401, member PATCH 403, foreign id 400, 129-character id 400, stranger 404) are asserted in the flow, the matrix and the sweep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pinned unit tests updated**
- **Found during:** Task 3 (unit tier after the registry flip).
- **Issue:** `test_probes.py::test_blueprint_urls_match_python_exact_routes` expected the system blueprint to serve every implemented exact Python path except the providers one, and `test_route_policy.py::test_phase3_key_writing_rows_are_session_only` pinned `PATCH /api/v1/models/default` as not implemented. Both pins were written for this exact change (same situation as 03-12).
- **Fix:** the probe test now excludes the models paths (served by `models_bp`) and asserts they are in the registry; the policy test expects `implemented: True`.
- **Files modified:** `test/unit_test/test_probes.py`, `test/unit_test/test_route_policy.py` (not in the plan's file list). **Commit:** `1bebcf1`.

**2. [Rule 2 - Missing critical] Unit tests for the pre-database input policy**
- Not in the plan: `test/unit_test/test_model_defaults_service.py` covers empty change set, unknown slot, malformed and over-long ids (no echo of the input), the 129-character composite, the type filter and the exact DTO key list. One assertion in the first draft was wrong (an empty string is trivially contained in any message) and was corrected before the commit.

**3. [Rule 3 - Blocking] OpenAPI export and TypeScript types regenerated**
- `export_openapi.py --check` reports the committed document stale once new routes exist (the same gate caught it in 03-12); regenerated both `web/openapi/openapi.json` and `web/src/interfaces/openapi.d.ts` (`npm run gen:api`).

**4. `make up` overrides** `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 PREFLIGHT_PORTS=` were used as instructed; no file changed.

The plan text "Do not commit (the orchestrator commits)" was overridden by the sequential-executor instruction; each task was committed.

## Deferred Issues

None new. The earlier deferred items (`deferred-items.md`) no longer fail: `run_all.py` is 7/7 and the log-masking tests pass.

## Notes for the next plans

- **Dataset create (03-14):** read the workspace default embedding through `model_defaults_service.defaults_dto(tenant_id)["embedding"]` (or `tenant_model_service.get_defaults`); an empty string means no default was chosen and nothing should be filled in silently. Composite ids are at most 128 characters by construction.
- **World fixture:** A now has an embedding default set (`a_embed_id()` in `_matrix_fixtures.py`); `World.snapshot()` also holds `models` and `defaults`, so any new route that can change them is checked for unchanged state in the matrix automatically.
- **Provider-test budget:** this plan added no provider saves to the matrix or sweep worlds (the new sweep rows reuse `leak-chat` from the provider sweep, so `sweep_model_rows` must stay after `sweep_provider_rows`). The flow test uses a fresh owner per test.
- **SPA Models page:** `GET /api/v1/models` rows carry `id` (use as the select value), `provider`, `instance`, `type`, `dimension`, `max_tokens`, `used_tokens`; `PATCH /api/v1/models/default` takes `{chat?, embedding?, tenant_id?}`, `null` clears, answers the new defaults; error `data.reason` is `model_unavailable` or `models_invalid`.
- Stack state at the end: rebuilt once with this plan's code, healthy on web port 8088; free disk 19 GB.

## Known Stubs

None.

## Threat Flags

None. T-03-13-01 to -05 are covered: token PATCH 401 and normal-member PATCH 403 (flow, matrix, sweep); a foreign model id is `model_unavailable` in another workspace (flow, matrix); one 404 body for a non-member (flow, matrix byte comparison); the flow scans every model response for `api_key`, `last4`, `base_url`, `api_version`, the fake key and address; `model_fields_set` keeps absent keys from changing a slot (flow).

## Self-Check: PASSED

- Files present: api/db/services/model_defaults_service.py, api/apps/restful_apis/models_api.py, test/testcases/test_models_flow.py, test/unit_test/test_model_defaults_service.py.
- Commits present: b9cfc6a, 4e7cb86, 1bebcf1.
