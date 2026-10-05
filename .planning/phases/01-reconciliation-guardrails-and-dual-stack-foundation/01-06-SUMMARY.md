---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 06
subsystem: database
tags: [peewee, mysql, config, logging, migrations, advisory-lock]
requires:
  - phase: 01-04
    provides: live MySQL under compose project devrag-stack
  - phase: 01-02
    provides: uv environment, run_tests.py, wait_until
provides:
  - RetCode and documented-identifier constants (common/constants.py)
  - service_conf.yaml.template, scripts/render_conf.py, typed settings loader
  - redacting JSON logger
  - RetryingPooledMySQLDatabase, DB proxy, transaction(), DatabaseLock
  - versioned migration runner, SystemSettings model, python -m api.db.init_db writing schema.version
affects: [01-07, 01-09, later phases that add models or migrations]
tech-stack:
  added: []
  patterns: [dedicated-connection advisory lock, per-migration transaction with version write, template-rendered config]
key-files:
  created: [common/constants.py, common/settings.py, common/log_utils.py, conf/service_conf.yaml.template, scripts/render_conf.py, api/db/database.py, api/db/models/base.py, api/db/models/system.py, api/db/migrations/runner.py, api/db/migrations/0001_system_settings.py, api/db/init_db.py, test/helpers/db.py, test/integration/test_db_core.py, test/integration/test_migration_runner.py]
  modified: [.planning/DECISIONS.md]
key-decisions:
  - "R-74: DatabaseLock uses its own PyMySQL connection outside the pool; no retry of statements inside an open transaction"
  - "R-75: migration DDL must be idempotent because MySQL commits DDL implicitly"
requirements-completed: [DATA-03, DATA-04, DATA-05, DATA-08, SEC-04]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 06: Python data core Summary

Env-rendered typed config, secret-redacting JSON logging, a retrying MySQL pool with transactions and a session-scoped GET_LOCK, and a lock-guarded versioned migration runner whose `init_db` wrote `schema.version=0001` to the live `rag_flow` database.

## Commits
- 9367227: constants, config template and renderer, settings, redacting logger (Task 1)
- 20b9339: pooled retrying database, transaction helper, DatabaseLock (Task 2)
- 765838e: migration runner, SystemSettings, init_db (Task 3)

## Observed results
- Unit: 99 passed, 1 skipped (pre-existing numpy gadget, B-13) after Task 1.
- Live integration: test_db_core 12 passed; test_migration_runner 9 passed; all integration+serial 43 passed.
- Full `run_tests.py -m "unit or integration or serial"`: 210 passed, 1 skipped.
- `make ci`: 6/6 gates passed and the ruff S/ASYNC/FIX pass clean.
- Live `init_db` on `rag_flow`: first run applied `0001`, second run applied nothing, exit 0 both times; MySQL shows `schema.version = 0001`, 1 row in `system_settings` before and after the rerun.
- Missing `MYSQL_PASSWORD` makes `render_conf.py` exit 1 naming the variable.

## Deviations from Plan
**1. [Rule 1 - Bug] DatabaseLock holds a dedicated PyMySQL connection, not a pooled one.** The plan said `DB.connect(reuse_if_open=True)`. A pooled connection can be returned to the pool by `DB.close()` while the session still owns the lock, which is the Pitfall 6 failure. A dedicated connection satisfies the must-have ("one dedicated connection") robustly; a test proves the lock survives `DB.close()`. Recorded as R-74.

**2. [Rule 1 - Bug] No retry inside an open transaction.** Retrying `execute_sql` after a reconnect would drop earlier statements and run later ones outside the transaction, violating DATA-04. Verified by `test_no_retry_inside_transaction`. Recorded as R-74.

**3. [Rule 3 - Blocking] `_connect` overridden and `commit` argument dropped.** Peewee 3.19 passes the deprecated `db=` keyword to PyMySQL 1.2 and deprecates `execute_sql(commit=)`; with `filterwarnings = error` both fail. The subclass connects with `database=` and the signature is `execute_sql(sql, params)`.

**4. Retry only when the connection was open.** `InterfaceError` on a never-opened connection is a programming error and is not retried (avoids five backoff cycles masking it).

**5. Template comment fix.** The renderer also processes comments, so the template header avoids literal substitution syntax.

**6. Added R-74 and R-75 to DECISIONS.md** (not covered by docs).

Notes: the runner bootstraps `system_settings` itself (needed for temp-directory migration sets in tests) and migration 0001 reuses that function. Container-internal Redis port: `.env` sets `REDIS_PORT=6380` (host mapping); plan 01-13 must override it to 6379 for in-network services.

## Known Stubs
None.

## Self-Check: PASSED
