---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 11
subsystem: database
tags: [gorm, go, schema, migrate, peewee, drift-gate]
requires:
  - phase: 01-07
    provides: conf/schema.json export of the Peewee models
  - phase: 01-09
    provides: Go module layout, run-mode table, DAO base
provides:
  - 38 generated GORM entities plus registry
  - verify-only `--migrate` run mode
  - dao.Transaction helper
  - drift gate chain routes, schema export, Go entities
affects: [phase-02 auth and Go DAO work]
tech-stack:
  added: []
  patterns: [generated entities from schema.json, read-only schema verification, scratch database for destructive tests]
key-files:
  created:
    - scripts/gen_go_entities.py
    - internal/entity/ (38 table files + registry.go)
    - internal/dao/verify.go
    - internal/dao/transaction.go
    - internal/testutil/scratch.go
    - cmd/migrate.go
  modified:
    - cmd/modes.go
    - cmd/modes_test.go
    - scripts/ci/check_generated.py
key-decisions:
  - "Peewee owns DDL (D-10): Go --migrate only reads information_schema and exits 1 on drift; AutoMigrate appears nowhere (grep clean)."
  - "VerifySchema takes a SchemaProvider interface (SELECT-only constants, bound parameters) so every drift class is unit-tested without a database."
  - "Type comparison is by family (string, int, float, time); tinyint(1) bool maps to the int family."
  - "Scratch database helper uses MYSQL_ROOT_PASSWORD from env only, validates identifiers by whitelist, drops the database on cleanup."
requirements-completed: [DATA-04, DATA-05, DATA-06]
completed: 2026-10-05
---

# Phase 1 Plan 11: Go entities, verify-only --migrate, transactions Summary

The Go engine now maps the shared schema through 38 generated GORM entities and verifies, but never writes, the Peewee-created database.

## Tasks

1. **Entity generator and 38 structs** - commit 61bb3e6. `scripts/gen_go_entities.py` with `--check`/`--root`/`--out-root`, deterministic gofmt-clean output, `registry.go` `All()`. Verified in this continuation (stat, generator and entity read; `--check` exit 0).
2. **Schema verifier and --migrate** - commit 08ab543. `VerifySchema` reports missing tables, missing and extra columns and type-family mismatches. `--migrate` prints `schema OK: 38 tables, schema.version=0002` and exits 0 live; it exits 1 naming `document.kb_id` after that column is dropped on a scratch copy. `--admin`, `--ingestor`, `--syncer` still exit 2.
3. **Transaction helper, contract test, gate** - commit fa82825. `dao.Transaction`; `TestTransactionRollsBack` (live, scratch DB) and a commit counterpart; `TestEntitiesMatchSchemaJSON` compares tables, ordered columns and nullability with `conf/schema.json` without a database.

The `check_generated.py` extension (routes, schema export, Go entities in order, naming the drifted generator) had already landed in 61bb3e6, so Task 3 added no change to it; its drift test `test_check_generated_fails_when_schema_json_column_edited` exists in `test_gen_go_entities.py`.

## Verification (as observed)

- `go vet ./...` and `go vet -tags=integration ./internal/...` clean
- `go test -race ./internal/... ./cmd/...` all ok
- Integration: `set -a; . docker/.env; set +a; MYSQL_HOST=127.0.0.1 REDIS_HOST=127.0.0.1 SERVICE_CONF=$PWD/conf/service_conf.yaml go test -tags=integration ./internal/...` all ok (live verify, scratch positive and negative, binary exit codes, rollback and commit)
- `make ci`: 7/7 gates passed, ruff clean; pytest `test/unit_test`: 159 passed, 1 skipped
- No `devrag_scratch_*` databases remained after the runs

## Deviations from Plan

- `VerifySchema(ctx, provider, models)` takes a `SchemaProvider` (obtained with `db.SchemaProvider()`) instead of a `*gorm.DB`, and `Transaction` takes the `*dao.DB` wrapper, because the GORM handle is unexported. Rule 3, no behavior change.
- Integration commands need an absolute `SERVICE_CONF` because the Go test working directory is the package directory.

## Known Stubs

None.

## Threat Flags

None. Scratch helper handles root credentials from environment only, never logged.
