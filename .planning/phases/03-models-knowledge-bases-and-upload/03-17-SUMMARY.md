---
phase: 03-models-knowledge-bases-and-upload
plan: 17
subsystem: documents
tags: [documents, list, delete, blob-gc, reference-counting, row-locks, doc-store, cross-tenant, leak-sweep, openapi]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-16 upload rows, shared blobs, upload lock name, document_dto, matrix and sweep; 03-14 load_visible_dataset and counters; 03-08 doc store delete by condition; 03-07 storage rm; 03-04 can_remove_document"
provides:
  - "document_service.list_documents, list_view, authorize_removal, delete_documents"
  - "file_service.release_files (reference-counted blob release) and release_blobs(operation=...)"
  - "GET and DELETE /api/v1/datasets/{dataset_id}/documents served on the real stack (registry rows implemented)"
  - "reasons ids_invalid and query_invalid"
affects: [03-18 dataset update and delete, 03-24 upload dialog, 03-31 document table UI, Phase 4 parsing]

tech-stack:
  added: []
  patterns:
    - "Delete serialises with upload twice: the dataset lock kb-upload:{dataset_id} and the file row FOR UPDATE; files are locked in sorted id order before any link is deleted"
    - "Remaining links are counted with a locking read, because a plain read in REPEATABLE READ would use the transaction's older snapshot and free a blob an upload just reused"
    - "Documents are re-locked by primary key inside the lock and transaction, so a concurrent delete of the same ids loses with the one 404 and counters drop once"
    - "Blob removal runs after the commit, best effort: a failure leaves an orphan blob, never a document without its blob"

key-files:
  created:
    - test/integration/test_document_service.py
    - test/testcases/test_document_flow.py
  modified:
    - api/db/services/document_service.py
    - api/db/services/file_service.py
    - api/utils/reasons.py
    - api/apps/restful_apis/document_api.py
    - conf/routes.yaml
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "Files are locked before their links are deleted (plan text deleted first). Locking first removes a lock-order cycle between a delete (holding gap locks on file2document) and an upload (holding the file row, inserting a link). Upload and delete now both take the file row first; across several files a deadlock victim is retried up to 3 times."
  - "can_remove_document is called with the permission subject, not the role: an API token is not given its owner's role to remove other members' documents (D-26, Pitfall 6). A token removes what its user uploaded or what its user's dataset holds; owner or admin sessions are elevated."
  - "The ids shape (1 to 100, 32 lowercase hex) is checked in the service as 400 ids_invalid instead of by the request model, so every shape error carries one reason; the model only forbids unknown fields and requires a list of strings (anything else is the generic 400 without a reason)."
  - "Query errors on the list are 400 query_invalid (new reason); the service clamps page and page_size and refuses keywords over 128 characters."
  - "The index is pruned before the transaction, as the plan orders. If the transaction then fails, the chunks are gone but the document row remains and can be deleted again; the reverse (a row gone with chunks left) cannot happen."

patterns-established:
  - "Matrix: a dataset-scoped row replays with A's real dataset id and (for DELETE) A's real document id in the body; World.snapshot() has a documents entry"

requirements-completed: [DOC-08, DOC-14, DOC-15, DOC-16, TEN-13]

duration: ~1h30m
completed: 2026-10-09
---

# Phase 3 Plan 17: Document list and delete Summary

**A member lists a dataset's documents and deletes them all-or-nothing: chunks are pruned from the index first, the rows and counters go in one transaction under the upload lock, and a blob is removed only when the last link to it in the workspace is gone, with a 15-round delete-versus-upload race proving no surviving document loses its blob.**

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `5cb7572` | failing service, flow and race tests |
| 2 (GREEN) | `cdfe0ac` | list and delete services, reference-counted blob release |
| 3 | `147f4bb` | routes, registry flip, OpenAPI, matrix and leak-sweep coverage |

## Red evidence (Task 1)

- `uv run pytest -m integration test/integration/test_document_service.py -q`: `31 failed` (`AttributeError: module 'api.db.services.document_service' has no attribute 'list_documents'` / `authorize_removal`).
- `uv run pytest -m e2e test/testcases/test_document_flow.py -q` against the stack before the routes existed: `22 failed, 1 passed` (the one pass is the unauthenticated check).

## Green evidence

- Integration (3 consecutive runs, to prove the race tests are stable): `72 passed` each for `test_document_service.py` + `test_upload_service.py`.
- After the single stack rebuild: `test_document_flow.py` + `test_upload_flow.py`: `46 passed`; matrix + leak sweep + route enumeration: `106 passed, 12 deselected`; `test_layering.py`: `7 passed`.
- Unit tier: `1771 passed, 1 skipped, 692 deselected`, 0 failed (the skip is not from this plan).
- `uv run python scripts/ci/run_all.py`: `7/7 gates passed`.

## What was built

- **List.** `list_documents(visible, page, page_size, keywords)` returns `(rows, total)`, newest `create_time` first then id, escaped `LIKE` on the name (`%` and `_` literal, case-insensitive through the table collation), selecting only the DTO columns (never the thumbnail or progress message). `list_view(principal, dataset_id, ...)` adds the visibility check and returns `{"items", "total"}`.
- **Delete.** `delete_documents(settings, visible, user_id, ids, storage=None, doc_store=None)`: validate ids; load the dataset's documents and compare counts (one 404); `can_remove_document` for every document (403) before anything changes; `DocStoreConnection.delete({"doc_id": ids}, index_name(tenant), dataset_id)` (`DocStoreError` becomes 503 `index_unavailable`, nothing else changed); then `DatabaseLock(kb-upload:{dataset_id})` and one transaction: lock the documents by primary key, `file_service.release_files`, `GREATEST(x - n, 0)` on `doc_num`, `chunk_num`, `token_num`; blobs freed are removed after the commit.
- **`release_files`.** Locks the affected `file` rows sorted by id, deletes tasks, `file2document` rows and documents, then per file counts remaining links with a locking read across the whole workspace and deletes the `file` row at zero, returning its key.
- **Routes.** `GET` and `DELETE /api/v1/datasets/{dataset_id}/documents` in `document_bp`; delete runs in the storage executor with a 60 s deadline; settings and principal are read on the event loop.
- **Matrix and sweep.** A's world now holds two team documents and one private document uploaded through the real route; builders for both rows; `World.snapshot()["documents"]`; `sweep_document_rows` covers 14 GET and 16 DELETE labelled cases (including the no-credential, made-up-bearer and wrong-method errors).

## Deviations from Plan

**1. [Rule 1 - Bug avoided] Lock order in `release_files`.** The plan listed "delete task/file2document/document rows, then lock the file rows". Deleting links first holds index and gap locks on `file2document` that a concurrent upload's insert for the same file would wait on while the delete waits for the file row it holds: a deadlock cycle. Files are locked first. Documented in the module note.

**2. [Rule 1 - Bug avoided] Locking count.** A plain `COUNT` after waiting for the file lock would read the transaction's older snapshot and miss a link an upload committed meanwhile, deleting a blob that was just reused. The count is a locking read.

**3. [Rule 2 - Missing critical functionality] Re-lock the documents inside the lock.** The plan's pre-check runs before the lock; two concurrent deletes of the same ids would both pass it and subtract the counters twice. The documents are locked again by primary key inside the transaction and a mismatch is the one 404 (tested with two racing deletes).

**4. [Rule 2] Deadlock retry.** A delete retries its transaction up to 3 times when MySQL names it a deadlock victim (error 1213), for the case of several shared files locked in different orders by an upload and a delete.

**5. [Decision] API tokens are not elevated.** `can_remove_document` receives `scope.subject`, not `scope.role` (see key decisions). Pinned by `test_tokens_follow_the_matrix_and_an_api_token_is_not_elevated_to_its_owners_role`.

**6. [Decision] `ids_invalid` for every shape error.** The plan put the 1 to 100 bound on the request model (which would give an unlabelled generic 400); the service enforces it so the client gets one reason. Type errors (not a list of strings, unknown field, missing `ids`) are the generic validation 400.

**7. [Test-only] `test_upload_service` fixtures reused by assignment** (`settings = base.settings`, ...) rather than copied, so the 03-16 helpers (`FaultyStorage`, `upload`, `doc_rows`) stay the single source. `RmFailingStorage` subclasses `FaultyStorage` in the new file.

## Issues Encountered

None blocking. One test of mine asserted that the owner's tenant id is absent from a list row; an owner's user id equals the tenant id, so it was replaced by a storage-key-shape check (fixed before the first green run).

## Known Stubs

None.

## Threat Flags

None. Every threat in the plan register is covered: T-03-17-01 by the mixed-list test, T-03-17-02 by the matrix builders, T-03-17-03 and -04 by the shared-blob tests and the 30 delete-versus-upload rounds (15 same dataset, 15 other dataset), T-03-17-05 by the chunk-pruning and outage tests, T-03-17-06 by `ids_invalid`, T-03-17-07 by the DTO and the sweep.

## For the next plans

**Document list API (03-24, 03-31)**
- `GET /api/v1/datasets/{dataset_id}/documents?page=<1..1e9, default 1>&page_size=<1..100, default 12>&keywords=<=128 chars>`; any member who can see the dataset (creator, or any member for `team`); session or API token. Success `200`: `{code: 0, message: "", data: {items: [document], total: n}}`, newest first. A document has `id, name, size, type, suffix, run, progress, dataset_id, created_by, parser_id, chunk_num, token_num, create_time, update_time` (the same `DocumentView` as the upload response). No storage key, bucket or location. `keywords` is a case-insensitive substring of the name; `%` and `_` are literal.
- Errors: `404 {"code":404,"message":"not found","data":null}` for a missing, malformed, foreign or private-to-others dataset; `400` with `data.reason: "query_invalid"` for a bad `page`, `page_size` (0, over 100, not a whole number) or over-long `keywords`; `401` only for a bad or missing credential.

**Document delete API**
- `DELETE /api/v1/datasets/{dataset_id}/documents` with JSON `{"ids": ["<32-hex>", ...]}` (1 to 100 unique ids; no other field). All or nothing. Success `200`: `{code: 0, message: "", data: {deleted: n}}` (n is the number of distinct ids). The dataset's `doc_num`, `chunk_num`, `token_num` drop by the amounts removed (refetch `GET /api/v1/datasets/{id}`).
- Who may delete: the document's uploader, the dataset's creator, or a workspace owner or admin session. An API token deletes only what its user uploaded or created.
- Errors: `404` (the same body) for a bad dataset, or any id that is not a document of that dataset, including a repeated delete; `403 {"code":403,"message":"forbidden","data":null}` if the caller may not remove at least one of the documents (nothing is deleted, not even the allowed ones, so a UI should delete per row or filter first); `400` `data.reason: "ids_invalid"` for an empty list, more than 100 ids or an id that is not 32 lowercase hex characters; `400` without a reason for a body that is not `{"ids": [strings]}` or carries another field; `503` `data.reason: "index_unavailable"` (the search index could not be pruned; nothing changed, retry) or `"busy"` (the dataset lock was held for 30 s, retry); `504` `operation_timeout`.
- A blob is removed from storage only when no other document in any dataset of the workspace still links it, so a UI never needs to warn about shared files.

**Dataset delete (03-18)**
- Reuse `document_service.delete_documents` in batches of up to 100 per call (it checks the caller per document, prunes the index and releases blobs) rather than dropping rows by `kb_id`; the shared tenant index is never dropped, only per-document or `delete_idx(index, dataset_id)` rows. Take care that `delete_documents` needs a `VisibleDataset` and the dataset lock `kb-upload:{dataset_id}` is taken inside it per call, so the dataset-delete flow must not hold that lock around the calls (it is a non-reentrant named lock).
- `release_blobs(storage, keys, "delete")` and `release_files(ids)` are available for a bulk path; `release_files` must run inside a transaction.

## Self-Check: PASSED

Commits `5cb7572`, `cdfe0ac`, `147f4bb` exist on `master`; the two new test files exist; every verification above ran green on the rebuilt stack.
