---
phase: 02-identity-tenancy-and-authorization
plan: 01
subsystem: logging-security
tags: [redaction, dos, CR-02, WR-04, WR-24, D-31]
requires: []
provides:
  - linear-time Python log redactor (KEYSEP two-stage scan)
  - shared redaction vectors (22) consumed by Python and Go
  - TruncateField / truncate_field log-site bounds in both engines
affects: [common/log_utils.py, internal/common/logger.go, api/apps/middleware.py, internal/router/middleware.go]
key-files:
  modified:
    - common/log_utils.py
    - api/apps/middleware.py
    - internal/common/logger.go
    - internal/router/middleware.go
    - test/fixtures/log_redaction_vectors.json
    - test/unit_test/test_log_redaction.py
    - internal/common/logger_test.go
    - internal/router/router_test.go
  created:
    - test/unit_test/test_request_log_truncation.py
decisions:
  - "Cookie values redact to end of line unless quoted; AWS4-HMAC-SHA256 authorization consumes to end of line."
  - "URL userinfo keeps the user and redacts the password (existing vector keeps `app`), instead of replacing the whole userinfo span."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 01: Linear-time log redaction (CR-02) Summary

Replaced the backtracking Python redactor with a linear two-stage scan (bounded `{0,4096}` quantifiers, possessive quoted-value match, 64 KiB input cap, `rfind('@')` userinfo scan), mirrored the new vectors in Go (RE2), and truncated request paths to 512 characters at the log site in both engines.

## Commits
- 66170cf test(02-01): failing vectors and timing tests (Task 1)
- 7581796 fix(02-01): Python linear redactor and path truncation (Task 2)
- bfea1fe fix(02-01): Go mirror and path truncation (Task 3)

## Pre-fix failures (against unchanged code)
- Python timing, 100 KB input, bound 0.25 s: `a_run`, `token_repeat`, `dash_run` and the 64 KiB-cap test did not finish (each killed after 15 s, 4 hung); `password_equals_repeat` 0.002 s, `password_open_quote` 0.006 s, `cookie_colon_repeat` 0.002 s, `scheme_repeat` 0.010 s passed pre-fix (kept as regression guards).
- Python vectors: 9 failed (redis_empty_user, amqp_at_in_password, auth_apikey_scheme, auth_api_dash_key_scheme, auth_negotiate_scheme, auth_aws4_scheme, cookie_to_end_of_line, set_cookie_to_end_of_line, json_escaped_quote); path_token_query already passed.
- Go vectors: the same 9 failed.

## Post-fix
- Python timings (100 KB): a_run 0.004 s, token_repeat 0.004, password_equals_repeat 0.001, password_open_quote 0.005, dash_run 0.004, cookie_colon_repeat 0.001, scheme_repeat 0.012. Bound 0.25 s (about 20x headroom over the slowest, decisive against the multi-second quadratic cases). Extra adversarial inputs (100k `@`, long open quote, long dash key) all under 0.004 s.
- Go: hostile-input test bound 2 s, measured 0.2-0.4 s per case under `-race`.
- 8 KB path request through the real Quart test client and Go httptest engine logs `path` with the `[truncated]` marker (512 chars + marker).

## Final checks (as observed)
- `make ci`: 7/7 gates passed, ruff clean, exit 0
- `uv run python run_tests.py -m unit`: 368 passed, 1 skipped (pre-existing), 142 deselected
- `GOTOOLCHAIN=local go test -count=1 ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean
- `GOTOOLCHAIN=local go test -race ./internal/common/... ./internal/router/...`: ok

## Deviations from Plan
1. [Rule 3] The 8 KB-path Python test lives in new `test/unit_test/test_request_log_truncation.py`, not `test/testcases/test_request_log.py`: that module is marked e2e and needs the Docker stack, which this plan must not start.
2. [Rule 1] A first Go cap implementation recursed forever (truncate output plus marker exceeded the cap); fixed by truncating to cap minus marker length before the recursive call. Caught by the new Go hostile-input test before commit.
3. Go test `require.GreaterOrEqual` on the fixture length raised from 11 to 22; added Go hostile-input and TruncateField tests beyond the plan.
4. Plan said `run_tests.py ... --collect-only -q`; the wrapper requires passthrough after `--` (`-- --collect-only -q`). Selected 38 tests (at least 8). The `-t log_redaction` expression also matches other tests in that file.
5. Plan text said userinfo span replaced wholesale; kept user and redacted only the password to keep the pre-existing `url_userinfo` vector valid.
6. `{0,4096}` appears once literally in `log_utils.py` (other bounds use the `_MAX_RUN` constant); noted in a comment.

## Known Stubs
None.

## Self-Check: PASSED
