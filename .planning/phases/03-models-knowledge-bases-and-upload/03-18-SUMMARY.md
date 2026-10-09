---
phase: 03-models-knowledge-bases-and-upload
plan: 18
subsystem: knowledge-bases
tags: [datasets, update, delete, embedding-lock, blob-gc, shared-index, row-locks, cross-tenant, leak-sweep, openapi]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-14 dataset service, DTO and create helpers; 03-16 upload lock name and shared blobs; 03-17 delete_documents, release_files, release_blobs; 03-08 delete_idx; 03-04 can_manage_dataset and the route registry"
provides:
  - "knowledgebase_service.update_dataset / update_view and delete_datasets"
  - "PUT /api/v1/datasets/{dataset_id} and DELETE /api/v1/datasets served on the real stack (both registry rows implemented)"
  - "reasons fields_invalid and embedding_locked"
  - "matrix builder for the update row, no-id check for the delete row, sweep_dataset_write_rows"
affects: [03-19 role and leak proofs, 03-25 dataset settings and delete dialogs, 03-28 decision record R-136]

tech-stack:
  added: []
  patterns:
    - "Update decides manage rights from the permission subject, never an inherited role, so an API token is not elevated to its owner's role (D-09, D-26)"
    - "A rename takes kb-create:{tenant_id} and compares with the case-insensitive collation excluding the dataset itself; an embedding change takes kb-upload:{dataset_id} and re-reads the counters under it"
    - "Dataset delete never holds kb-upload around delete_documents (the lock is non-reentrant); it takes the lock afterwards for the index prune and the final transaction"
    - "PUT body keys are read with model_fields_set so an absent key is not a change and an explicit null is not the same as absent"

key-files:
  created: []
  modified:
    - api/db/services/knowledgebase_service.py
    - api/db/services/document_service.py
    - api/utils/reasons.py
    - api/apps/restful_apis/dataset_api.py
    - conf/routes.yaml
    - test/integration/test_dataset_lifecycle.py
    - test/testcases/test_dataset_lifecycle_flow.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "Dataset delete removes the dataset's rows from the shared per-workspace index ragflow_{tenant_id} (filtered by dataset id) and does not drop the index itself (R-136), because every dataset of the workspace shares that index. KB-07 and D-10's 'the search index is removed' is therefore satisfied as 'the dataset's content is removed from the index'. The raw Elasticsearch client in test_dataset_lifecycle.py proves the tenant index, the other dataset's chunks and its vector field all survive, including when the last dataset of a workspace is deleted."
  - "The update handler runs in the docstore executor (45 s), not the db executor of the plan text, because an embedding change provisions the vector field in the index."
  - "delete_datasets takes an optional tenant_id keyword for the body's workspace selector; a dataset of another workspace is the one 404."
  - "Delete removes documents in batches of up to 100 through delete_documents (per-document authorisation, index prune, reference-counted blob release) and then takes kb-upload:{id} for delete_idx and one transaction that drops stragglers, related rows and the dataset; blobs are removed after the commit."

patterns-established:
  - "Matrix: a no-id check for a body-selected delete row replays foreign ids alone and mixed with the outsider's own id, with a session and an API token, and asserts that nothing of the outsider's own is deleted either"

requirements-completed: [KB-06, KB-07, KB-08, KB-09, TEN-13, TEN-16, DOC-14, DOC-15]

duration: resumed run after an interruption
completed: 2026-10-09
---

# Phase 3 Plan 18: Dataset update and delete Summary

**A dataset's creator, or a workspace owner or admin, can rename, re-share, reconfigure and permanently delete it: an embedding change is allowed only while the dataset is empty and provisions the vector field first, and a delete authorises every id before changing anything, prunes the dataset's chunks from the shared tenant index (the index itself stays, R-136), removes its rows and removes a blob only when no other document of the workspace still links it.**

Dataset delete removes the dataset's rows from the shared tenant index and does not drop the index (R-136), so KB-07 and D-10's "the search index is removed" is satisfied as "the dataset's content is removed from the index".

## Run history

The first run was interrupted after Tasks 1 and 2 were committed and Task 3 was written but not committed. This run read the uncommitted diff against the plan, found it complete and correct, re-ran every generator, rebuilt the stack once, ran all verification, and committed Task 3.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `100ee91` | failing lifecycle service tests (70) and flow tests (41) |
| 2 (GREEN) | `bac1296` | update_dataset and delete_datasets, reasons, upload lock name moved to the dataset service |
| 3 | `c07ca0f` | PUT and DELETE routes, registry flip, matrix and leak-sweep coverage, OpenAPI and types |

## Findings on the uncommitted diff (this run)

- The handlers, request models, registry rows, the matrix builder and no-id check and `sweep_dataset_write_rows` matched Task 3 and were kept as written.
- The flow-test helper `workspace()` and `test_server_owned_fields_cannot_be_assigned_by_an_update` had been corrected by the first run (a second embedding model is added through the provider instance route; the "nothing applied" assertion compares against the dataset read just before the refused request). Both were kept; they now pass.
- Generated outputs were re-created rather than trusted: `gen_routes.py` rewrote the Go/Python permission and route-policy tables, both Nginx configurations and the SPA route table with no diff against HEAD (these tables do not depend on `implemented`); `export_openapi.py` and `npm run gen:api` reproduced the working-tree OpenAPI document and types. The pinned unit tests `test_probes.py` and `test_route_policy.py` pass unchanged.

## Red and green evidence

- RED (Task 1): `test_dataset_lifecycle.py` 70 failed (`AttributeError` for `update_dataset` / `delete_datasets`); the flow file 41 failed against a stack without the routes.
- Integration: `test_dataset_lifecycle.py` + `test_knowledgebase_service.py` + `test_document_service.py`: `130 passed in 100.97s`; `test_layering.py`: `7 passed`.
- After the single stack rebuild (`make up`, `scripts/wait_stack.sh`, all containers healthy): `LIVE_BASE_URL=http://127.0.0.1:8088` e2e of `test_dataset_lifecycle_flow.py`, `test_dataset_flow.py`, `test_cross_tenant_matrix.py`, `test_response_leaks.py`, `test_route_enumeration.py`: `161 passed, 12 deselected in 101.29s`; `test_upload_flow.py`, `test_document_flow.py`, `test_provider_flow.py`: `57 passed`.
- Unit tier: `1771 passed, 1 skipped, 808 deselected`, 0 failed (the skip is not from this plan). `uv run ruff check .`: `All checks passed!`. `gen_routes.py --check` and `export_openapi.py --check`: exit 0. `uv run python scripts/ci/run_all.py`: `7/7 gates passed`.
- `grep -n sleep` over the two new test files: nothing.

## What was built

- **Update.** `update_dataset(settings, visible, user_id, changes, doc_store=None)`: allow-list of name, description, permission, avatar, language, parser_id, parser_config, embd_id; an empty or unknown-key mapping is `fields_invalid`; creator, owner and admin only (403 `forbidden`, decided by the permission subject); validation reuses the create helpers; `parser_config` merges over the stored value (which carries the defaults); a rename checks duplicates under `kb-create:{tenant_id}` excluding the dataset (own-name case change allowed); an `embd_id` equal to the current one is ignored, a different one requires `doc_num == 0` and `chunk_num == 0`, re-read under `kb-upload:{dataset_id}` (`embedding_locked`), resolves as a configured embedding model of the workspace and calls `create_idx` before the row changes; `update_time` and `update_date` advance explicitly.
- **Delete.** `delete_datasets(settings, principal, ids, tenant_id=None, storage=None, doc_store=None)`: 1 to 20 unique 32-hex ids (`ids_invalid`); any absent or invisible id is the one 404, then `can_manage_dataset` for every id (403), all before any change; per dataset in request order: documents out in batches through `delete_documents`, `delete_idx(index, dataset_id)` under `kb-upload:{dataset_id}`, then one transaction (stragglers, pipeline-log, connector and sync-log rows, the dataset row), blobs after the commit. One structured log line per dataset with tenant id, dataset id and document count.
- **Routes.** `PUT /api/v1/datasets/<dataset_id>` and `DELETE /api/v1/datasets` in `dataset_bp`; delete runs in the storage executor with a 60 s deadline.
- **Matrix and sweep.** `PUT` builder on A's team dataset; `check_datasets_delete` (outsiders by session, pending invitee, API tokens and another workspace's owner and token, each alone or mixed with their own dataset id, with and without the workspace selector, all the one 404 with nothing of A's or their own changed; A's normal member 403 for a team dataset, 404 when a private id is mixed in; admin 404 for a private dataset). `sweep_dataset_write_rows` scans 17 PUT and 13 DELETE labelled cases, success and error paths, plus the unauthenticated and wrong-method errors.

## Deviations from Plan

**1. [Decision] Update runs in the docstore executor** instead of the db executor named in the plan, since an embedding change calls `create_idx`. Timeout 45 s (a rename waits up to 10 s for the creation lock; an embedding change adds the upload lock and the index call).

**2. [Decision] Documents go out through `delete_documents` before the dataset-level steps.** The plan describes one transaction that releases the files; reusing the 03-17 path keeps per-document authorisation, index pruning and reference-counted blob release in one place. The final transaction still removes any document an upload added meanwhile. Consequence: if the index is down while the dataset holds documents, the first batch fails with `index_unavailable` before anything changes; if the index fails later in a multi-batch delete, the already removed documents stay removed (the call can be repeated) and `data.deleted` lists the finished dataset ids.

**3. [Rule 1 - Bug] Test-only fixes.** The flow helper `workspace()` saved two embedding models in one provider save, which the route does not take; it now adds the second through the instance route. The assertion that a refused update applies nothing compared a fresh read with the create response, which differs in unrelated fields; it now compares two reads.

**4. [Decision] `tenant_id` on delete** is passed to the service as a keyword and enforced there (a dataset of another workspace is the one 404), in addition to the coarse `acting_scope` check.

## Issues Encountered

None blocking. The port-ownership and `vm.max_map_count` preflight checks were bypassed with the two documented overrides for this host.

## Known Stubs

None.

## Threat Flags

None. T-03-18-01 and -02 by the matrix, the flow and integration role tests (creator, owner, admin, normal member, private dataset); T-03-18-03 by the service allow-list and `extra="forbid"` models; T-03-18-04 by `embedding_locked`; T-03-18-05 by the shared-blob integration case; T-03-18-06 by index-first ordering and `data.deleted`; T-03-18-07 by the shared lock and the post-delete upload 404 test.

## For the next plans

**Update API (03-19, 03-25)**
- `PUT /api/v1/datasets/{dataset_id}` (session or API token). Body: any non-empty subset of `name, description, permission ("me"|"team"), avatar, language, parser_id, parser_config (object, merged over the stored one), embd_id ("model@provider" composite)`. Unknown keys (including `tenant_id`, `created_by`, `doc_num`) are a validation 400 with no `data.reason`. An absent key is not a change. `description` and `avatar` may be null to clear; `null` for the others is 400 `dataset_invalid`. The workspace is taken from the dataset (no `tenant_id`).
- Success `200 {code: 0, message: "", data: <dataset DTO>}`, the same view as create and read (no `status`, `source`, storage details).
- Errors: `404 {"code":404,"message":"not found","data":null}` for a missing, malformed, foreign or someone else's `me` dataset (also for owners and admins, D-27); `403 {"message":"forbidden"}` for a visible dataset the caller may not manage (a normal member of a `team` dataset); `400 data.reason`: `fields_invalid` (empty body or a non-editable key reaching the service), `dataset_invalid` (bad value), `model_unavailable` (unknown, chat-type or unconfigured embedding model); `409 data.reason`: `duplicate_name` (another dataset of the workspace has the name, case-insensitive; changing only the case of its own name is accepted), `embedding_locked` (documents or chunks exist and `embd_id` differs); `503 busy` (a creation or upload lock held for the wait limit; retry), `503 index_unavailable` (vector field could not be provisioned; nothing changed), `504`.
- Narrowing `permission` to `me` hides the dataset from every other member at once (their list and read answer 404); their documents stay in it. Setting it back to `team` restores it.
- The settings dialog should send only changed fields and disable the embedding select when `doc_num > 0` or `chunk_num > 0`.

**Delete API (03-19, 03-25)**
- `DELETE /api/v1/datasets` with JSON `{"ids": ["<32-hex>", ...], "tenant_id"?: "<32-hex>"}` (1 to 20 unique ids; no other field). Success `200 {code: 0, message: "", data: {deleted: ["<id>", ...]}}` (the ids, in request order, not a count; this differs from the document delete, which returns a number).
- All ids are authorised before anything changes. Any id that is absent, malformed-but-hex, foreign or someone else's `me` dataset gives the one `404` (and wins over a 403 in the same list); otherwise `403` if the caller may not manage any one of them (nothing deleted; a UI should delete per dataset). `400 data.reason: "ids_invalid"` for an empty list, more than 20, or an id that is not 32 lowercase hex; a body that is not `{"ids": [strings]}` or carries another field is a 400 without a reason. Repeating a delete is `404`.
- Who may delete: the dataset's creator, or an owner or admin session. An API token is judged as its user and is not elevated.
- Failure part-way: `503 data.reason "index_unavailable"` (search index unreachable) or `"busy"` (the dataset lock was held for 30 s), with `data.deleted` listing the ids already finished; the failed dataset is intact apart from documents already removed, and the same call can be repeated. `504` on the 60 s handler deadline.
- Deletion is permanent. It removes the dataset's chunks from the shared tenant index (the index and other datasets' chunks stay), all documents, tasks and links, and a blob only when no other document of the workspace links it, so the dialog needs no shared-file warning.

## Self-Check: PASSED

Commits `100ee91`, `bac1296` and `c07ca0f` exist on `master`; every verification above ran green on the rebuilt stack.
