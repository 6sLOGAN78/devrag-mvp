---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 07
subsystem: database
tags: [peewee, mysql, schema, migrations, schema-json]
requires:
  - phase: 01-06
    provides: pooled DB, migration runner, system_settings, init_db
provides:
  - 38 Peewee models in seven modules plus api/db/db_models.py re-export
  - migration 0002 creating the 37 tables beyond system_settings
  - scripts/export_schema.py and committed conf/schema.json (input for the Go entity generator)
affects: [01-11, 01-09, Phase 2 auth and tenancy]
tech-stack:
  added: []
  patterns: [db_default constraint for documented DEFAULTs, index_specs shared by migration and exporter, idempotent baseline migration]
key-files:
  created: [api/db/models/identity.py, api/db/models/llm.py, api/db/models/knowledge.py, api/db/models/files.py, api/db/models/chat.py, api/db/models/canvas.py, api/db/models/integrations.py, api/db/db_models.py, api/db/migrations/0002_baseline_schema.py, scripts/export_schema.py, conf/schema.json, test/unit_test/test_schema_export.py, test/integration/test_schema.py]
  modified: [api/db/models/__init__.py, api/db/models/base.py, .planning/DECISIONS.md]
key-decisions:
  - "R-76: all text columns are LONGTEXT (Peewee maps TextField to TEXT)"
  - "R-77: documented tables carry real MySQL DEFAULT clauses; schema.json exports default and app_default"
  - "R-78: reference-only details adapted (English language defaults, no pytz, callable JSON defaults)"
requirements-completed: [DATA-01, DATA-02, DATA-05, DATA-06]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 07: Baseline schema Summary

Thirty-eight tables are created from an empty database by the single Peewee migration owner (0001 plus 0002), the documented `document`, `task` and `knowledgebase` DDL is matched column by column on a live MySQL, and the schema is exported deterministically to `conf/schema.json`.

## Sourcing of tables
- From docs/08-database/schema.md (exact name, type, nullability, DB default, named indexes): `document`, `task`, `knowledgebase`.
- Supplemental from the reference (R-60), listed per column in `knowledge.py`: `knowledgebase` tenant_embd_id, permission, created_by, doc_num, token_num, chunk_num, similarity_threshold, vector_similarity_weight, pipeline_id, pagerank and the 11 task-tracking id/finish_at pairs; plus the BaseModel create_date/update_date columns on every table.
- Entities listed in docs/08-database/entities.md with columns from the reference only: the other 34 documented tables (identity 4, llm 9, pipeline_operation_log, files 4, chat 5, canvas 6, integrations 5). `system_settings` is from plan 01-06.
- Table names: all docs and reference names agreed; no difference to log. `ingestion_task`, `skill_*`, `license`, `evaluation` and billing tables were not created.

## Commits
- ffd1071: identity, llm, knowledge, files models; db_default and index_specs helpers
- caedf10: chat, canvas, integrations models, db_models re-export, migration 0002
- 5b2de24: exporter, schema.json, tests, LONGTEXT fix, R-76 to R-78

## Observed results
- Unit: test_schema_export 6 passed.
- Live integration: test_schema 14 passed (38 tables, version 0002, second run applies nothing, 7 documented index columns, documented index names, three documented tables vs schema.md, no tenant_id on document/task, user.email unique, live columns and indexes vs schema.json, extra temp migration applies once, rerun repairs a dropped table and index).
- Full `run_tests.py -m "unit or integration or serial"`: 230 passed, 1 skipped (pre-existing numpy gadget skip, B-13).
- `make ci`: 6/6 gates passed, ruff S/ASYNC/FIX pass clean.
- Live `python -m api.db.init_db` on `rag_flow`: applied 0002, exit 0; `information_schema` shows 38 tables, `schema.version` = `0002`.
- `export_schema.py --check` exits 0.

## Deviations from Plan
**1. [Rule 1 - Bug] TextField mapped to TEXT, not LONGTEXT.** The first live run showed Peewee 3.19 creates `text` (64 KB) while schema.md says `longtext`; thumbnails and progress messages would truncate. All text columns now use `LongTextField` (R-76).
**2. [Rule 2 - Missing] DB-level DEFAULT clauses.** Peewee `default=` is application-side only; the documented DDL has real DEFAULTs, so documented tables use a `db_default` constraint (R-77). Exporter records both `default` and `app_default`.
**3. DateTimeTzField without pytz** (not in the approved package set) and callable JSON defaults instead of shared mutable dicts (R-78).
**4. Task 1 commit alone does not satisfy its 24-model acceptance check**, because `__init__.py` (Task 2 file) lists all 38; the check passes after commit 2.
**5.** Added three tests beyond the plan (documented index names, user.email uniqueness, partial-baseline repair).

## Known Stubs
None.

## Self-Check: PASSED
