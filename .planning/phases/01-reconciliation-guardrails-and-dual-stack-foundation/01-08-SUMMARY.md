---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 08
subsystem: api
tags: [quart, quart-schema, hypercorn, health, openapi, envelope]
requires:
  - phase: 01-06
    provides: settings, logger, pooled DB, migration runner
  - phase: 01-07
    provides: migrated schema with schema.version
provides:
  - create_app factory with {code,message,data} envelope for every outcome, X-API-Source, access log, CORS allow-list
  - concurrent 2 s dependency probes and healthz/status on four URLs
  - boot sequence (logger, database verify, hooks, serve) and Hypercorn entry
  - OpenAPI export (web/openapi/openapi.json) and constrained request types
affects: [01-09, 01-11, Phase 2 auth, all later Python routes]
tech-stack:
  added: []
  patterns: [envelope via json.dumps, handlers call services only, test-only routes live in test/helpers]
key-files:
  created: [api/utils/api_utils.py, api/utils/validation.py, api/apps/__init__.py, api/apps/errors.py, api/apps/middleware.py, api/apps/restful_apis/system_api.py, api/db/services/system_service.py, api/ragflow_server.py, common/health/probes.py, common/bootstrap/ensure_bucket.py, scripts/export_openapi.py, web/openapi/openapi.json, test/helpers/app.py]
  modified: [.planning/DECISIONS.md, .planning/BLOCKERS.md]
key-decisions:
  - "R-79: quart-schema 0.25 argument names, document_response, ordered envelope serialization"
  - "R-80: probe semantics (missing bucket is down, status and elapsed_ms only)"
requirements-completed: [API-03, API-06, API-07, API-08, API-09, API-10, API-11, API-13, SYS-06, SYS-07, SEC-10]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 08: Python server skeleton Summary

Quart factory with one envelope for every outcome, bounded non-leaking MySQL/Valkey/MinIO/Elasticsearch probes served on `/api/v1/system/{healthz,status}` and the literal aliases, OpenAPI export, and a boot order proven on a live stack.

## Commits
- f9e38ea: envelope, errors, middleware, factory (Task 1)
- a89edf1: probes, system service and blueprint, ensure_bucket, OpenAPI export (Task 2)
- 0be1492: boot, validation types, layering and boot tests, R-79/R-80 (Task 3)

## Observed results
- test_envelope 11 passed; test_probes 9; test_layering 4; test_validation 12 (included in 25 passed with envelope); live test_python_system_routes 5 passed (four URLs 200 with four ok checks; Redis stopped gives 503 with `redis` down and no host text, then recovers); test_boot 2 passed (empty scratch database raises BootError with zero tables created; migrated database logs `logger, database, hooks, serve`).
- Full `run_tests.py -m "unit or integration or serial"`: 271 passed, 1 skipped (pre-existing numpy gadget, B-13).
- `make ci`: 6/6 gates passed, ruff S/ASYNC/FIX clean.
- Manual smoke: `python -m api.ragflow_server` on 127.0.0.1:9391 returned 200 healthz with `x-api-source: python`, 404 envelope for unknown path, four `boot.step` records in order; stopped with SIGTERM, port closed, no process left.
- `export_openapi.py --check` exits 0.

## Deviations from Plan
**1. [Rule 3 - Blocking] quart-schema 0.25 argument names.** `docs_path`/`redoc_path` do not exist; used `swagger_ui_path`, `redoc_ui_path`, `scalar_ui_path` = None. `document_response` used instead of `validate_response` (R-79).
**2. [Rule 1 - Bug] Quart's JSON provider sorts keys.** Envelope serialized with `json.dumps` to keep code, message, data order.
**3. [Rule 1 - Bug] Logging extra key `created` collides with LogRecord.** Renamed to `bucket_created`.
**4. [Rule 3 - Blocking] ruff ASYNC109 on a `timeout` parameter.** Renamed to `cap`, used `asyncio.timeout`.
**5.** Stack containers had been removed by the previous plan; recreated with `make infra-up` (volumes intact).
**6.** The system blueprint registration in `create_app` was added in Task 2, not Task 1, so Task 1 is committable on its own.

## Known Stubs
None. Superuser init, plugin load and update_progress daemon are not stubbed (B-08).

## Self-Check: PASSED
