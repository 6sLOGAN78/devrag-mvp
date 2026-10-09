---
phase: 03-models-knowledge-bases-and-upload
plan: 16
subsystem: upload
tags: [upload, multipart, minio, dedupe, xxh64, transactions, request-limits, cross-tenant, leak-sweep, openapi]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-07 storage drivers and key scheme; 03-12 handler pattern, executors, matrix builders and sweep; 03-14 load_visible_dataset and tenant artifact cleanup; 03-15 upload_rules"
provides:
  - api/db/services/file_service.py (Candidate, find_candidates, IterReader, reuse_or_store, release_blobs)
  - api/db/services/document_service.py (UploadItem, authorize_upload, upload_documents, upload_lock_name, document_dto)
  - api/apps/restful_apis/document_api.py (document_bp, apply_upload_limits, read_upload_files, close_upload_streams)
  - api/apps/request_body.py (CappedBody, CappedRequest)
  - POST /api/v1/documents/upload served on the real stack (registry row implemented)
  - test helper test/helpers/uploads.py (tenant_object_keys, tenant_row_counts, snapshot, pdf_bytes, text_bytes)
affects: [03-17 document list and delete, 03-24 upload dialog, Phase 4 parsing]

tech-stack:
  added: []
  patterns:
    - "Authorise first, read the body second: the dataset is resolved and the permission checked before a byte of the multipart body is parsed"
    - "Validate and hash everything before the first write; one DB transaction; compensation removes only the keys this request created"
    - "A hash and size match is a hint: the stored blob is compared byte for byte (FOR UPDATE on the file row, closed read stream) before it is reused"
    - "Per-request limits without touching other routes: request.max_content_length, request.body_timeout and a counting body (CappedRequest)"

key-files:
  created:
    - api/db/services/file_service.py
    - api/db/services/document_service.py
    - api/apps/restful_apis/document_api.py
    - api/apps/request_body.py
    - test/helpers/uploads.py
    - test/unit_test/test_upload_request_limits.py
    - test/integration/test_upload_service.py
    - test/testcases/test_upload_flow.py
  modified:
    - api/apps/__init__.py
    - api/utils/reasons.py
    - conf/routes.yaml
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - test/unit_test/test_probes.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "Quart's per-request max_content_length only reaches the multipart parser's memory guard (read in the installed quart/formparser.py and wrappers/request.py); the total streamed size is never checked while a parser consumes the body. CappedRequest/CappedBody count the bytes handed over and refuse past the cap; a declared Content-Length over the cap is refused before any read. body_timeout is a plain per-request attribute in the installed Quart, so no application setting was changed and other routes keep 60 s."
  - "The parser override is query-only (parser_id, parser_config as a JSON string) and parser_config is merged over the dataset's configuration, so a partial override keeps pages and layout settings."
  - "Reasons added to api/utils/reasons.py: parser_invalid (400), storage_unavailable (503), forbidden (403, the reason inside ServiceError; the HTTP body stays the standard forbidden envelope)."
  - "A candidate blob is size-checked with storage.size before the byte comparison, and the comparison reader opens its stream lazily, so seek(0) never holds a MinIO connection."
  - "The parser's temporary files (a part over 500 KB spools to disk, and a part cut short never completes) are tracked by CappedRequest and closed by the handler, instead of waiting for the garbage collector."

patterns-established:
  - "Services take plain readable, seekable streams (SeekableReader); the handler owns Quart objects and closes the request's temporary files"
  - "Matrix: a no-id row proves isolation with the exact MinIO prefix listing of tenant A in World.snapshot() ('objects') plus its dataset counters"

requirements-completed: [DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06, DOC-07, DOC-16, STOR-01, STOR-02, STOR-11, SEC-06, TEN-13, E2E-04]

duration: ~1h45m
completed: 2026-10-09
---

# Phase 3 Plan 16: Document upload route and services Summary

**A member uploads files into a dataset through Nginx and Python on the real stack: the dataset is authorised before the body is read, every file is validated and hashed before the first write, blobs live under generated `{tenant}/{uuid}` keys, identical content shares one blob only after a byte comparison, names are auto-renamed, and a failure removes exactly the blobs the request created.**

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | `fb79904` | failing request-limit, service and flow tests, plus `test/helpers/uploads.py` |
| 2 (GREEN) | `8cb504a` | file and document services for upload |
| 3 | `7abb215` | upload blueprint, request limits, registry flip, OpenAPI, matrix and leak-sweep coverage |

## Accomplishments

- `authorize_upload` (visibility 404 first, then `datasets.manage_document` 403 by permission subject) runs alone through `run_blocking(DB_EXECUTOR)` before `request.files` is awaited. A foreign, private, unknown, malformed or missing dataset id is the one 404 body; any member may upload into a `team` dataset (D-09).
- `upload_documents`: `check_batch`, `validate_file` per file (measured size, first 8192 bytes), `check_capacity`, `hash_and_measure`, parser override check, all before any write. Under `DatabaseLock("kb-upload:{dataset_id}")` (42 characters, 30 s, `busy` 503 on timeout) it reloads `doc_num` and the dataset's names, renames with `auto_rename_batch`, and in one transaction stores or reuses each blob and writes `file`, `document`, `file2document` and `knowledgebase.doc_num += n`. Documents start at `run='0'`, `progress=0.0`, with `parser_id` and `parser_config` copied from the dataset or the override.
- Dedupe: `find_candidates` joins `document -> file2document -> file` and filters `file.tenant_id` (so another workspace never matches); `reuse_or_store` locks the candidate `file` row `FOR UPDATE`, compares sizes, then `streams_equal` against an `IterReader` over `iter_chunks`; the stream is always closed. A forged hash and size match with different bytes stores a new blob (integration test inserts the victim's row with the attacker's hash and size).
- Compensation: a `StorageError` becomes 503 `storage_unavailable`; any exception releases only `created_keys` (reused blobs are never touched) and the transaction rolls back.
- Route limits: `max_content_length = max_file_bytes + 1 MiB`, `body_timeout = upload.body_timeout_seconds`, counted by `CappedBody`; over the cap is 413 `file_too_large`; a multipart body with no `file` part (malformed, truncated, no boundary, JSON) is 400 `no_files`.
- Registry row flipped, `gen_routes.py --check` and `export_openapi.py --check` clean, `openapi.d.ts` regenerated with `npm run gen:api`.
- Matrix: `NO_ID_CHECKS["POST /api/v1/documents/upload"]`; `World.snapshot()` gains `objects` (MinIO keys under A's prefix) next to A's dataset counters, so every matrix row now also proves nothing appeared in A's storage. The check also registers an extra workspace, uploads with its session and its API token, and shows each token is pinned to its own workspace. Leak sweep: `sweep_upload_rows` with 14 success and error cases plus the standard error trio.

## Verification (real output)

- Red: `ModuleNotFoundError: No module named 'api.apps.restful_apis.document_api'` (unit) and `ImportError: cannot import name 'document_service' from 'api.db.services'` (integration).
- `uv run pytest test/unit_test/test_upload_request_limits.py test/unit_test/test_layering.py -q` -> `21 passed`.
- `uv run pytest -m integration test/integration/test_upload_service.py -q` -> `41 passed in 18.94s`.
- Stack rebuilt once (`make up`, `scripts/wait_stack.sh` -> `stack ready`), `LIVE_BASE_URL=http://127.0.0.1:8088`:
  - `pytest -m e2e test/testcases/test_upload_flow.py -q` -> `23 passed in 23.52s` (includes 100 MiB + 1 byte -> 413 `file_too_large` from Python, exactly 100 MiB accepted and 104857600 bytes in MinIO, 102 MiB -> Nginx 413 with no `x-api-source`).
  - upload flow + cross-tenant matrix + leak sweep + route enumeration + request limits -> `131 passed in 41.96s`.
- `uv run python scripts/ci/run_all.py` -> `7/7 gates passed`; `uv run python run_tests.py -m unit` -> `1771 passed, 1 skipped, 632 deselected`; `uv run ruff check .` -> `All checks passed!`.
- Acceptance greps: `for_update` and `streams_equal` present in `file_service.py`; no `.read()` of a whole file and no `quart` in the two services; no `api.db.models` or `peewee` in `document_api.py`; no `sleep` in the new tests; `check_secrets.py` -> `secrets OK`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `CappedRequest` / `CappedBody` added (`api/apps/request_body.py`)**
- **Found during:** Task 3, reading the installed Quart source.
- **Issue:** the plan assumed `request.max_content_length` per request enforces the cap. In the installed Quart it is passed to the multipart parser as a memory guard only; the streamed total is checked only when a handler awaits the whole body, which the multipart parser never does. A chunked body over the cap would have been read to the end.
- **Fix:** a small `Request` subclass whose body counts bytes against the route's cap and records `RequestEntityTooLarge` for the reader; also tracks the parser's temporary files so they can be closed. Other routes never call `cap`, so their behaviour is unchanged. No new service, library or layer.
- **Commit:** `7abb215`

**2. `apply_upload_limits(req, upload)` takes `UploadSettings`, not `Settings`** (narrower dependency; the handler passes `settings.upload`). A `read_upload_files(upload)` helper holds the body half of the handler so the in-process unit test exercises the real code without a database.

**3. [Rule 2] Reasons `parser_invalid`, `storage_unavailable`, `forbidden` added** to `api/utils/reasons.py` so those failures are typed (503 or 400) rather than a 500 or an unnamed 400. Commit `8cb504a`.

**4. Parser configuration override is merged over the dataset's** configuration instead of replacing it (plan said "or the override").

**5. Post-write failure test uses the real storage driver, not a database error.** The planned database failure could not be provoked from valid input (an over-long `created_by` was accepted by this MySQL, no error was raised), so `FaultyStorage(crash_after_put=1)` raises a non-storage error right after a successful `put`, which exercises the generic compensation path. The storage-error path is covered by `fail_on_put=2`.

**6. Extras:** `lock_timeout` keyword and `upload_lock_name` on the service (lets a test prove `busy` in 1 s without a sleep); `test/helpers/uploads.py`; `World.registry` field in the matrix fixtures; `test_probes.py` lists the upload path among the non-system blueprint paths.

## Issues Encountered

None blocking. Host disk went from 19 GB to 16 GB free over the plan (one image rebuild, 100 MiB MinIO objects created and removed by the tests).

## Known Stubs

None.

## For the next plans

**03-17 (document list, delete, blob GC):**
- Tables written per upload: `file` (`id`, `parent_id` = dataset id of the request that stored the blob, `tenant_id`, `location` = key, `name` = name of the first document that stored it, `type`, `size`, `source_type='knowledgebase'`), `document` (`kb_id`, `location` = same key, `name` = final renamed name, `content_hash` = 16-hex xxh64, `size`, `run`, `progress`, `created_by`, `parser_id`, `parser_config`, `source_type='local'`), `file2document` (one link per document). A deduplicated upload adds only `document` and `file2document`, so one `file`/blob can have many links, also across datasets of one workspace. Do not rely on `file.name` or `file.parent_id` for a document.
- Delete must lock the `file` row `FOR UPDATE`, count remaining `file2document` links, delete the `file` row and queue the key only when zero remain, `rm` the blob after commit (`BUCKET_NAME` bucket), and decrement `knowledgebase.doc_num` by the number of documents removed. Use `document_service.upload_lock_name(dataset_id)` (`kb-upload:{dataset_id}`, 42 characters) for deletes so they serialise with uploads; the upload's dedupe path already takes the `FOR UPDATE` lock on the candidate file row and skips a candidate whose row is gone.
- Use `document_service.document_dto` for list rows (keys: `id, name, size, type, suffix, run, progress, dataset_id, created_by, parser_id, chunk_num, token_num, create_time, update_time`; no `location`, `status`, `thumbnail`). `can_remove_document` in `tenant_scope` needs `created_by`.
- Existing document names of a dataset are the rename set (`document.name`, compared case-insensitively).
- `test/helpers/uploads.py` has `tenant_object_keys`, `tenant_row_counts` and `snapshot` for before/after proofs; `FaultyStorage` in `test/integration/test_upload_service.py` records storage calls and open read streams.

**03-24 (upload dialog), API contract:**
- `POST /api/v1/documents/upload?dataset_id=<32-hex>[&parser_id=<one of the dataset parser ids>][&parser_config=<JSON object as text, at most 4096 characters>]`, `Authorization: Bearer <session or API token>`, body `multipart/form-data` with one or more parts named exactly `file` (any other part name is ignored). Send one file per request (per-file progress; the server caps a request at `max_file_bytes + 1 MiB` and `max_files_per_request` files). Use axios `timeout: 0` (or minutes) for this call; the server body timeout is `upload.body_timeout_seconds` (600 s).
- Success `200`: `{code: 0, message: "", data: [document, ...]}` in request order; each element has `id, name` (the final name, possibly `report(1).pdf`), `size, type` (`pdf|doc|visual|aural|other`), `suffix, run` (`"0"`), `progress` (`0.0`), `dataset_id, created_by, parser_id, chunk_num, token_num, create_time, update_time`. Refresh the dataset's `doc_num` from `GET /api/v1/datasets/{id}` (also gives `upload_limits`).
- Errors (envelope `{code, message, data}`; the machine reason is `data.reason`; one bad file rejects the whole request and stores nothing):
  - `404` `{"code":404,"message":"not found","data":null}`: missing, malformed, unknown, foreign or private-to-others `dataset_id`.
  - `403` forbidden: caller lacks the document permission.
  - `400` with `reason`: `no_files`, `too_many_files`, `unsupported_type` (extension, declared type or content), `invalid_filename`, `empty_file`, `dataset_limit`, `parser_invalid`.
  - `413`: `reason: "file_too_large"` (`data.http_status: 413`) when the file is over `max_file_bytes` or the body over the request cap; a body over 101 MiB is refused by Nginx first as `{"code":400,"message":"payload too large","data":null}` with HTTP 413 and no `reason`.
  - `503` with `reason` `busy` (another upload to the dataset holds the lock for 30 s, retry) or `storage_unavailable`; `504` `operation_timeout` if the handler deadline passes; `408` if the body is not received within the body timeout. Only a bad or expired credential is `401`; never treat these as session loss.
- Generated types: `web/src/interfaces/openapi.d.ts` (response model `DocumentView`; the multipart request body and query parameters are not described in the schema).

## Self-Check: PASSED

Commits `fb79904`, `8cb504a`, `7abb215` exist on `master`; all created files exist; every verification above ran green on the rebuilt stack.
