---
phase: 03-models-knowledge-bases-and-upload
plan: 15
subsystem: upload
tags: [upload-rules, filename-validation, magic-bytes, auto-rename, xxh64, dedupe]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-01 UploadSettings limits; 03-09 ServiceError and api/utils/reasons.py"
provides:
  - api/db/services/upload_rules.py (ValidatedFile, validate_file, normalize_filename, split_name, check_magic, check_batch, check_capacity, auto_rename, auto_rename_batch, hash_and_measure, streams_equal, file_type_for, ALLOWED_MIME_BY_EXT)
affects: [03-16 upload route and dedupe path, document service]

tech-stack:
  added: []
  patterns:
    - "Pure rules module: no quart, peewee or storage import; plain SeekableReader Protocol"
    - "Fixed ServiceError messages that never echo name, extension, MIME type, size or limit"

key-files:
  created:
    - api/db/services/upload_rules.py
    - test/unit_test/test_upload_rules.py
  modified: []

key-decisions:
  - "PDF magic is strict: `%PDF-` must be at offset 0 (no 1024-byte leniency). A PDF with leading junk is refused with unsupported_type."
  - "An extension must be on the configured allow-list AND have an ALLOWED_MIME_BY_EXT entry; a configured extension with no table entry is unsupported_type (no parser or MIME rule exists for it). file_type_for returns 'other' for unknown extensions."
  - "Content that fails the magic/NUL check is unsupported_type (message: content does not match its type); only an empty head or zero size is empty_file."
  - "auto_rename_batch added beyond the plan list so the route renames names of one request against each other in one call."
  - "file_too_large carries data={'http_status': 413}, kind PAYLOAD_TOO_LARGE; every other rejection is Kind.INVALID (400)."

patterns-established:
  - "Route (03-16): normalize, validate_file on the spooled file using hash_and_measure's size and head, check_batch before the loop, check_capacity under the kb upload lock, auto_rename_batch under the lock, streams_equal mandatory on a dedupe hit"

requirements-completed: [DOC-02, DOC-03, DOC-04, SEC-06]

duration: ~15min
completed: 2026-10-09
---

# Phase 3 Plan 15: Upload Rules Summary

**Pure upload validation, case-insensitive auto-rename and streaming xxh64 hashing with a byte-for-byte stream comparison, pinned by 134 unit tests.**

## Accomplishments

- `validate_file(raw_name, declared_mime, head, size, limits)` applies, in order: name, extension allow-list (last extension decides, so `a.pdf.exe` is `exe`), declared MIME (parameters stripped, per-extension set plus octet-stream and empty), zero size, size limit (413), magic bytes or NUL check.
- Names are rejected, not sanitised: empty, over 255 characters, `.`/`..`, `/`, `\`, any control character (Unicode category Cc, which includes NUL and DEL), Windows drive prefix, trailing dot, no stem.
- `check_batch` (`no_files`, `too_many_files`), `check_capacity` (`dataset_limit`).
- `auto_rename` / `auto_rename_batch`: `stem(n).ext`, casefold comparison, last extension only, stem trimmed to keep 255 characters.
- `hash_and_measure` (1 MiB chunks, `xxhash.xxh64` hex, byte count, first 8192 bytes, stream rewound) and `streams_equal` (lock-step, tolerant of short reads, rewinds both streams even on mismatch).

## Verification (real output)

- Red run: `ImportError: cannot import name 'upload_rules' from 'api.db.services'` (commit `9d1911d`).
- `uv run pytest test/unit_test/test_upload_rules.py test/unit_test/test_layering.py -q` -> `134 passed in 0.36s`.
- `uv run ruff check` on both files -> `All checks passed!`; `ruff format --check` -> `2 files already formatted`.
- `grep -n "quart\|peewee\|open(" api/db/services/upload_rules.py` -> no output.

## Deviations from Plan

None - plan executed as written. The plan's "Do not commit" note was a planning-time note; each task was committed per the execution instructions.

## Issues Encountered

None.

## Next Phase Readiness

Plan 03-16 (upload route) consumes this module. Dedupe must call `streams_equal` on a hash hit before reusing a blob (T-03-15-05). The module does not check `max_files_per_request` per file; call `check_batch` once with the file count before validating files.

## Self-Check: PASSED

- FOUND: api/db/services/upload_rules.py, test/unit_test/test_upload_rules.py
- FOUND commits: 9d1911d, 36aa611
