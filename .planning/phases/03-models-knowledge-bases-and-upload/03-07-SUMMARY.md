---
phase: 03-models-knowledge-bases-and-upload
plan: 07
subsystem: storage
tags: [minio, local-storage, path-traversal, presigned-url, object-keys]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: StorageSettings (impl, local_base_dir) and the rag/utils package marker (plan 01)
provides:
  - Storage ABC with StorageError, StorageNotFound, StorageNotSupported, new_object_key, validate_key, validate_bucket
  - LocalStorage with sanitize_path (resolve plus is_relative_to, 0700 dirs, atomic writes)
  - MinioStorage (bucket on first write, race codes tolerated, streaming reads, presigned GET 3600 s)
  - get_storage(settings) factory cached per impl and endpoint, reset_storage_cache()
affects: [03-08, 03-16 upload pipeline, document delete, parser workers]

tech-stack:
  added: []
  patterns:
    - "Drivers are synchronous; callers run them in a bounded executor"
    - "Storage errors name operation and bucket only (no key, path, credential)"
    - "Keys are server-generated {tenant_id}/{uuid4 hex}; client names never reach a key or path"

key-files:
  created:
    - rag/utils/storage_base.py
    - rag/utils/local_conn.py
    - rag/utils/minio_conn.py
    - rag/utils/storage_factory.py
    - test/unit_test/test_local_storage.py
    - test/unit_test/test_storage_factory.py
    - test/integration/test_storage.py
  modified: []

key-decisions:
  - "Added StorageNotFound (subclass of StorageError) so callers can tell a missing object from a failure; not in the plan's list"
  - "Unknown storage.impl raises common.settings.ConfigError('invalid value for config key: storage.impl'), the same error the settings loader raises, instead of a bare ValueError"
  - "validate_bucket lives in storage_base and is shared by both drivers (3 to 63 chars, lowercase, digits, dot, hyphen, no ..)"
  - "Presigned URLs are implemented and tested but exposed by no route in Phase 3 (they embed the internal MinIO endpoint)"

patterns-established:
  - "iter_chunks validates eagerly and returns a generator, so a bad key raises at call time"
  - "MinIO _guard context manager maps S3Error/urllib3 errors to StorageError and absent codes to StorageNotFound"

requirements-completed: [STOR-01, STOR-02, STOR-06, STOR-08, STOR-10, STOR-11]

duration: ~25min
completed: 2026-10-09
---

# Phase 3 Plan 07: Storage layer Summary

**One storage interface with MinIO and local drivers behind a settings-driven factory, server-generated tenant/uuid keys, traversal-proof local paths, and presigned GET URLs proven against the live MinIO.**

## Accomplishments

- RED: the unit files failed at collection with `ModuleNotFoundError: No module named 'rag.utils.local_conn'` (the first import, alphabetical) before any implementation existed.
- Local driver rejects `../x`, `a/../../x`, `a/./b`, `/abs`, `a\b`, NUL, newline, empty, `a//b`, trailing slash and 300-character keys before any filesystem call (test asserts the base directory is never created). Symlinked directory, file and bucket pointing outside the base are rejected on get, put and rm. Directories are 0700, files 0600. `os.replace` failure leaves no target and no temp file and keeps the previous content.
- MinIO driver: first write to a nonexistent `rf-test-xxxxxxxx` bucket creates it; two threads racing on a missing bucket both succeed; a forced lost race (bucket exists, check says no) is absorbed through `BucketAlreadyOwnedByYou`; presigned URL downloads the bytes with httpx and carries `X-Amz-Expires=3600` (60 when asked); a wrong-password driver raises an error that contains neither the password, the real password nor the key.
- The temp_bucket fixture removes only the objects it recorded and the bucket it named and asserts the bucket is gone; a post-run listing showed only `ragflow`.

## Verification (real output)

- `uv run pytest test/unit_test/test_local_storage.py test/unit_test/test_storage_factory.py test/unit_test/test_layering.py -q` -> `60 passed in 0.29s`
- `uv run pytest -m integration test/integration/test_storage.py -q` (after `scripts/wait_stack.sh --infra-only`: minio, mysql, redis healthy) -> `9 passed in 0.46s`
- `uv run pytest test/unit_test -m unit -q` -> `1158 passed, 1 skipped`
- `uv run ruff check rag/utils` -> `All checks passed!`
- `uv run python scripts/ci/check_secrets.py` -> `secrets OK`
- `grep os.environ` over the four new modules -> nothing; `is_relative_to` present in `local_conn.py`.

## Task Commits

1. Task 1 (failing tests): `3966a77`
2. Task 2 (base, local driver, factory): `71d6848`
3. Task 3 (MinIO driver, shared validate_bucket): `4d9f874`

## Deviations from Plan

### Auto-fixed / additions

**1. [Rule 2 - Missing functionality] StorageNotFound**
- Callers (download, delete, parse) need to distinguish an absent object from a backend failure; added as a StorageError subclass. Mapped from `NoSuchKey`, `NoSuchObject`, `NoSuchBucket`, `NotFound` on MinIO and `FileNotFoundError` locally.

**2. [Rule 1 - consistency] ConfigError instead of ValueError for an unknown impl**
- The plan text said both "ConfigError-style" and `ValueError(...)`. Used `ConfigError` with the exact message so it matches the settings loader.

**3. [Rule 3] validate_bucket moved to storage_base**
- Task 2 had the bucket regex in the local driver; the MinIO driver needs the same check, so it was hoisted in the Task 3 commit.

## Known Stubs

None.

## Threat Flags

None. T-03-07-01, -02, -04 and -05 mitigations are covered by tests; -03 is accepted per plan (no route exposes presigned URLs).

## Notes for next plans

- Call `get_storage(settings)` once per request path; it is cached and thread-safe. All methods block, so wrap them in the bounded executor (plan 03-16).
- Use `new_object_key(tenant_id)` for every upload; the default bucket constant is `common.constants.BUCKET_NAME` ("ragflow").
- `iter_chunks` on MinIO holds a pooled connection until the generator is exhausted or closed; consumers should close it.
- Cache key excludes the MinIO password: a credential change at the same endpoint needs `reset_storage_cache()` or a restart.
- Neither driver is async and neither exposes presigned URLs through a route; record that in DECISIONS (plan 03-28).

## Self-Check: PASSED
