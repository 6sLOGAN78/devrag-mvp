---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 16
subsystem: database
tags: [peewee, mysql, pooling, retry, gap-closure]
requires:
  - phase: 01-06
    provides: RetryingPooledMySQLDatabase (defective pool wrapping)
provides:
  - Pool-preserving MySQL subclass (_PyMySQLDatabase below PooledDatabase)
  - Bounded reconnect budget; read-only-only standalone statement retry; pre-send ping on checkout
  - Fake-driver unit suite and extended live integration tests
affects: [01-24]
key-files:
  created: [test/unit_test/test_db_pool.py]
  modified: [api/db/database.py, test/integration/test_db_core.py, .planning/DECISIONS.md]
key-decisions:
  - "R-83: pool structure and retry safety (amends R-74); writes never replayed, read-only statements retried"
requirements-completed: [DATA-03]
metrics:
  tasks: 3
  completed: 2026-10-06
---

# Phase 1 Plan 16: DB pool and retry fix Summary

PooledDatabase checkout restored (CR-01), failed reconnects consume the retry budget (WR-01), standalone writes are never re-executed (WR-02), all proven by fake-driver unit tests and live MySQL tests.

## Tasks

| Task | Commit |
|------|--------|
| 1. Failing fake-driver tests | 0dea8ab |
| 2. Restore pool, bounded reconnect, read-only-only retry, R-83 | 5b926c4 |
| 3. Live integration tests (pool reuse, cap, write after kill, no replay) | 1500500 |

## RED evidence (re-derived)

Task 1 tests were re-run against the pre-fix code (`git archive 0dea8ab api common` into a scratch directory, outside the repo, with the Task 1 test file). Result: 11 failed, 6 passed. Failing: pool reuse (connect/close cycles), max_connections cap, close_all, reconnect budget (succeed and exhaust), and the standalone-write non-replay cases (UPDATE, INSERT, DELETE, CREATE TABLE, SET, CALL). This confirms the tests detect CR-01, WR-01 and WR-02.

## Live results (MySQL from `make infra-up`, project devrag-stack)

- `uv run python run_tests.py -m integration -t test_db_core`: 16 passed.
- `uv run python run_tests.py -m unit`: 254 passed, 1 skipped. `make ci`: 7/7 gates passed, ruff clean.
- `uv run python run_tests.py -m serial`: 1 failed (`test_tls.py::test_tls_variant_routes_identically_and_restores`), 11 passed, 2 errors (`test_dependency_outage.py`, two tests). These need the full app stack; `app` was not running (exited 143 during `make infra-up`, which reported a wait_stack timeout at 300s although mysql, redis, es01, minio were healthy). They do not touch the DB pool code and were not investigated; left for plan 01-24.

## Deviations from Plan

**[Rule 1 - Bug] Test defect in my predecessor's uncommitted edit.** `test_pool_reuses_one_physical_connection` measured `Threads_connected` after `DB.close()` with autoconnect off, raising InterfaceError. Fixed by measuring before closing. No product code change was needed.

`make infra-up` exited 1 on the wait_stack timeout (app container, see above); infra services were healthy, so the live tests ran.

## Known Stubs

None.

## Self-Check: PASSED
