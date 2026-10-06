---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 17
subsystem: logging
tags: [redaction, zap, python-logging, gap-closure, security]
provides:
  - Shared redaction vectors (test/fixtures/log_redaction_vectors.json) consumed by Python and Go
  - Python and Go redactors covering bearer/basic, JSON-quoted keys, x-api-key, pwd/passwd, URL userinfo
  - Container/structured-field redaction (Python lists/tuples; Go zap.Any/Reflect/Strings/ByteString)
  - json:"-" on Go MySQL and Redis passwords
key-files:
  created: [test/fixtures/log_redaction_vectors.json, internal/server/config_redaction_test.go]
  modified: [common/log_utils.py, internal/common/logger.go, internal/common/logger_test.go, internal/server/config.go, test/unit_test/test_log_redaction.py]
requirements-completed: [SEC-04, TEST-01, TEST-03]
metrics:
  tasks: 2
  completed: 2026-10-06
---

# Phase 1 Plan 17: Log redaction gaps Summary

Both engines now mask every vector in one shared JSON file, and Go structured fields and config structs can no longer leak passwords (closes WR-03, WR-04).

## Tasks

| Task | Commit |
|------|--------|
| 1. Shared vectors and failing tests | 439c38e |
| 2. Fix redactors, tag Go password fields | 444a132 |

## RED evidence (observed against pre-fix code)

- Python (7 failed, 13 passed): `x_api_key_header`, `api_key_equals`, `pwd_equals`, `passwd_colon`, `url_userinfo`, `test_nested_list_and_tuple_secrets_masked`, `test_x_api_key_header_extra_masked`.
- Go: `TestSharedRedactionVectors/{bearer_header, basic_header, json_quoted_password, json_spaced_access_token, x_api_key_header, api_key_equals, pwd_equals, passwd_colon, url_userinfo}` and `TestStructuredFieldsRedacted` failed.

After the fix: all of these pass (Python 20 passed for `log_redaction`; Go `internal/common` and `internal/server` pass with `-race`).

## Verification (as observed)

- `make ci`: 7/7 gates passed, ruff clean.
- `uv run python run_tests.py -m unit`: 268 passed, 1 skipped, 134 deselected.
- `GOTOOLCHAIN=local go test -count=1 ./cmd/... ./internal/...`: all packages ok.
- `go vet ./...`: clean.
- `-t log_redaction` selected 20 tests (collect-only confirmed implicitly by the 20-test run; no `--allow-empty`).

## Deviations from Plan

None. Notes: the Go URL-userinfo and fragment rules drop an auth scheme (`Bearer`) along with the token, matching the Python behaviour (`Authorization: ***`). Only MySQL and Redis password fields exist in `internal/server/config.go`; no MinIO/ES secrets are present there. A bare tuple like `("token", "t")` has no key, so only strings inside it are scrubbed.

## Known Stubs

None.

## Self-Check: PASSED
