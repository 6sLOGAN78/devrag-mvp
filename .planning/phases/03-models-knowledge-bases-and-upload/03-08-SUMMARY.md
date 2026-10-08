---
phase: 03-models-knowledge-bases-and-upload
plan: 08
subsystem: doc-store
tags: [elasticsearch, dense_vector, hnsw, cosine, port-adapter, tenant-isolation]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: common/doc_store and rag/utils package markers, EsSettings wiring (plan 01)
provides:
  - DocStoreConnection port, value objects, typed errors and validation helpers (common/doc_store/doc_store_base.py)
  - ESConnection adapter and get_doc_store (rag/utils/es_conn.py)
  - Index settings, dynamic templates and vector_mapping (rag/utils/es_mapping.py)
  - DocStoreContract, an engine-agnostic contract class reusable by the Infinity adapter (test/helpers/doc_store_contract.py)
affects: [03-12 dataset service, 03-14 E2E-03, Phase 4 indexing, Phase 5 retrieval]

tech-stack:
  added: []
  patterns:
    - "One shared index ragflow_{tenant_id}; every row carries kb_id; every query, update and delete is AND-ed with a kb_id terms filter"
    - "Validation before any request: index-name regex, non-empty dataset ids, non-empty condition, plain-field-name condition keys, vector length and magnitude"
    - "_guard context manager turns every engine error into DocStoreError naming only the operation (raised from None, no host or body)"
    - "Writes refresh the index before returning, so tests never wait on a timer"

key-files:
  created:
    - common/doc_store/doc_store_base.py
    - rag/utils/es_mapping.py
    - rag/utils/es_conn.py
    - test/unit_test/test_doc_store_port.py
    - test/helpers/doc_store_contract.py
    - test/integration/test_doc_store_es.py

key-decisions:
  - "Index name is ragflow_{tenant_id} (one index per tenant), resolving the docs contradiction between ragflow_{uid} and ragflow_{kb_id}; the decision row belongs in DECISIONS.md via plan 03-28"
  - "Search hits are _source dicts plus id (from _id) and _score; highlight fragments appear under _highlight. The plan's SearchResult had no score slot, and weighted-fusion ordering cannot be asserted without it"
  - "insert checks that the index exists first (one HEAD request) because the engine would otherwise auto-create it with dynamic mapping, producing a float array instead of the HNSW field"
  - "Text match uses query_string (reference behaviour, Phase 5 passes boosted expressions); lenient mode and the always-present kb_id filter bound its effect"
  - "rank_feature is implemented as rank_feature should-clauses with name validation, since the port signature already carries the parameter"

patterns-established:
  - "Contract class without a Test prefix; the concrete subclass supplies store, tenant_index, dataset_ids and an engine helper for raw read-back"

requirements-completed: [IDX-04, IDX-05, IDX-06, IDX-08, IDX-09, TEST-08]

duration: ~50min
completed: 2026-10-09
---

# Phase 3 Plan 08: Doc store port and Elasticsearch adapter Summary

**One hardened `DocStoreConnection` port and an Elasticsearch 8 adapter with a shared tenant index and an on-demand `q_{dim}_vec` field (dense_vector, cosine, HNSW 16/200), proven by a 22-case engine-agnostic contract run against the live Elasticsearch 8.11.3.**

## Accomplishments

- Task 1 (red): unit module failed at collection with `ImportError: cannot import name 'doc_store_base' from 'common.doc_store'`.
- Port: frozen expression dataclasses, `OrderByExpr`, `SearchResult`, seven typed errors, and helpers `index_name`, `validate_index_names`, `vector_field`, `require_dataset_ids`, `require_condition`, `validate_condition_keys`, `check_row_vectors`. Imports nothing from api, rag, quart or elasticsearch.
- Adapter: idempotent `create_idx` (mapping read back and compared, `DimensionConflict` on any difference, race-safe), `delete_idx` by `kb_id` keeping the shared index, `insert` (all vectors checked before the bulk call, failed ids returned), `get`, parameterised painless `update`, `delete`, and `search` with query_string, top-level kNN with the bool filter, weighted fusion as boosts, sort, paging (window capped at 10000), highlight, terms aggregations and rank features.
- Live mapping read back from ES 8.11.3 shows `q_1024_vec` and `q_1536_vec` side by side with dense_vector, cosine, hnsw m=16, ef_construction=200.

## Verification (real output)

- `uv run pytest -m integration test/integration/test_doc_store_es.py -q` -> `32 passed in 4.24s` (22 contract cases plus 10 ES-specific; five consecutive runs all green)
- `uv run pytest test/unit_test/test_doc_store_port.py test/unit_test/test_layering.py -q` -> `60 passed`
- `uv run pytest test/unit_test -m unit -q` -> `1211 passed, 1 skipped` (the skip is pre-existing)
- `uv run ruff check` on all six owned paths plus the two modules -> `All checks passed!`
- Acceptance greps: no `match_all`, no `sleep` in the adapter or tests; `"m": 16` and `ef_construction` present in `es_mapping.py`; no fixed-dimension vector templates.
- `_cat/indices/ragflow_*` after the runs listed nothing: every test index was deleted by recorded name, and teardown asserts it is gone.

## Task Commits

1. Task 1, failing port tests and contract suite: `c0f9ddd`
2. Task 2, port, mapping and index lifecycle: `b40236d`
3. Task 3, data operations and live contract run: `f74787f`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Concurrent create_idx failed with a 404**
- **Found during:** Task 3 live run (`test_concurrent_create_idx_calls_both_succeed`)
- **Issue:** the engine answers 404 `{}` to `get_field_mapping` for a field no mapping holds yet, which surfaced as DocStoreError when four callers raced.
- **Fix:** `_field_mapping` treats that 404 as "absent"; a caller that lost the index-creation race waits server-side with `cluster.health(wait_for_status=yellow)` (bounded 10 s) instead of polling.
- **Files:** rag/utils/es_conn.py. **Commit:** `f74787f`

**2. [Rule 2 - Missing critical] insert into a never-created index**
- **Issue:** a bulk write would auto-create the index with dynamic mapping, silently losing the HNSW field and the templates.
- **Fix:** `insert` raises DocStoreError when the index does not exist; covered by a contract case that also asserts nothing was created.

**3. [Rule 2 - Extra hardening] Value and field validation**
- Condition values must be scalars or lists of scalars, `new_value` may not touch `id` or `kb_id`, match fields and sort/select/aggregation fields are regex-checked, offset/limit are validated, and fusion weights are parsed strictly. All refuse before a request (T-03-08-03).

**4. [Documentation] SearchResult hits carry `_score`** (see key-decisions); the plan did not specify a score slot.

The plan text said "Do not commit (the orchestrator commits)"; per the sequential-execution instruction each task was committed individually.

## Known Stubs

None. `MatchSparseExpr` is intentionally reserved and raises `NotSupported` on Elasticsearch; the Infinity adapter (later phase) implements it. `parser_id` on `create_idx` is accepted for port compatibility and unused by Elasticsearch.

## Threat Flags

None beyond the plan's register. T-03-08-01..06 are each covered by a contract or unit case (wildcard and comma names, empty dataset ids, two-dataset isolation, empty condition, hostile keys, fixed error messages, zero and wrong-length vectors, request timeout 30 s with no retries).

## Notes for next plans

- Construct the adapter with `get_doc_store(settings)`; it is synchronous, so call it from a bounded executor (plan 03-12). Use `index_name(tenant_id)` for the name and the dataset id for `dataset_id`.
- `create_idx(index, dataset_id, dim)` must receive the dimension the provider actually returned; it raises `InvalidVectorSize` (outside 1..4096) and `DimensionConflict` (existing field differs), both subclasses of `DocStoreError`, so the handler should map them to 400 and 409/500 respectively.
- Phase 4 must keep all-zero embeddings out of `insert` (empty text); the port raises `ZeroVectorError` for the whole batch.
- `delete_idx` removes one dataset's rows only; dropping the tenant index is deliberately not exposed.
- The DECISIONS.md rows for the index naming and for the `_score` hit key are still to be written (plan 03-28 owns that file).

## Self-Check: PASSED
