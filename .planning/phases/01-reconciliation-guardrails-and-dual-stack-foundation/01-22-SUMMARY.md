---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 22
subsystem: api
tags: [quart, error-envelope, migrations, peewee, startup-hooks]
requires: []
provides:
  - 4xx-class envelope codes for unmapped client HTTP statuses
  - db-bound migration version I/O and uniqueness-aware index helper
  - install_startup_hooks(app) running hooks on the serving loop
affects: [phase-4-daemon, migrations]
key-files:
  modified:
    - api/apps/errors.py
    - api/db/migrations/runner.py
    - api/ragflow_server.py
    - test/integration/test_migration_runner.py
    - test/integration/test_boot.py
  created:
    - test/unit_test/test_error_status_mapping.py
    - test/unit_test/test_startup_hooks.py
key-decisions:
  - "413/429 map to RetCode.BAD_REQUEST (no new member, so no Go parity change)"
  - "Uniqueness mismatch in add_index_if_missing raises MigrationError in both directions"
requirements-completed: [API-03, API-09, API-13, DATA-05]
duration: ~40min
completed: 2026-10-06
---

# Phase 1 Plan 22: 4xx fallback, migration runner, startup hooks Summary

Closes WR-08, WR-09, WR-07: unmapped 4xx never yield envelope code 500, the migration runner reads and writes `schema.version` on the db it is given, and startup hooks run in `before_serving` on the serving loop.

## Tasks and commits

| Task | Commit |
|------|--------|
| 1 WR-08 4xx fallback (BAD_REQUEST below 500; 413 "payload too large", 429 "too many requests") | 740edec |
| 2 WR-09 `current_version(db)`/`upsert_setting(key, value, db)` via `bind_ctx`; `add_index_if_missing` raises on uniqueness mismatch | c0b4562 |
| 3 WR-07 `install_startup_hooks(app)`; `boot()` emits `logger`,`database`; `hooks`,`serve` emitted from `before_serving` | 1e6ad48 |
| follow-up: replace fixed sleeps in the hook test (no_sleep CI gate) | 2e809a8 |

## Tests written first (RED observed against pre-fix code)

- Task 1: 6 of 7 failed pre-fix (408/413/415/429 returned code 500; message checks; 4xx property loop failed at 406); all 7 pass after.
- Task 2 (live MySQL): both new tests failed pre-fix (index test "DID NOT RAISE MigrationError"; two-db test failed); all 11 in test_migration_runner pass after. One test-side assertion bug (tuple vs list) was fixed in my own test, not weakened.
- Task 3: 4 of 4 new unit tests failed pre-fix (`install_startup_hooks` absent); pass after. The raising-hook test expects Quart's `LifespanError` wrapper (startup still aborts).

## Verification (as observed)

- `make ci`: 7/7 gates passed (after fixing the no_sleep finding).
- `uv run python run_tests.py -m unit`: 320 passed, 1 skipped.
- Live: `free -m` showed ~5.9 GB available; `make infra-up` (PREFLIGHT_ALLOW_LOW_MAP_COUNT=1) timed out in `wait_stack` on the stopped `app` container as predicted, with mysql/redis/minio/es01 healthy, so infra was treated as usable. Ran test_migration_runner, test_boot, test_schema integration files: all passed (13 + 14). Scratch databases only; `rag_flow` untouched.
- Final stack state: the four infra containers stopped with `docker stop`; `app`/`init` untouched; no `down`.

## Deviations

None to plan scope. Note: `bind_ctx` rebinding of `SystemSettings` is class-level, so concurrent runners against different dbs in one process are not safe; runs on one db (the real use) are.

## Self-Check: PASSED
