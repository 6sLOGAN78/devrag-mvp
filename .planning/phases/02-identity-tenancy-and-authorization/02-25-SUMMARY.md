---
phase: 02-identity-tenancy-and-authorization
plan: 25
subsystem: testing
tags: [tenancy, isolation, security, leak-sweep, log-masking, nginx, live-tests]
requires: [02-14, 02-23]
provides:
  - registry-driven cross-tenant matrix, Python and Go twins, with a guard that fails a scope-tenant row that has no fixture
  - response leak sweep over every implemented registry row (success and error), by key name, hash shape and secret value
  - real-container-log proof that no credential reaches the Nginx, Go or Python logs, and that token-bearing paths are logged as templates
  - three log defects fixed (Nginx raw token path, Go raw token on unmatched spellings, Python raw path)
affects: [03, every later phase that adds a scope-tenant endpoint]
tech-stack:
  added: []
  patterns:
    - "matrix rows are read from conf/routes.yaml; BUILDERS (rows with path ids) and NO_ID_CHECKS (rows without) must cover every implemented scope-tenant row, and a stale fixture key fails too"
    - "failure messages carry counts and labels, never secret values"
    - "Nginx masks with a map on the normalised $uri and a named log_format without query string or Referer"
key-files:
  created:
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_cross_tenant_matrix.py
    - internal/e2e/matrix_fixtures_test.go
    - internal/e2e/cross_tenant_matrix_e2e_test.go
    - test/testcases/_leak_sweep.py
    - test/testcases/test_response_leaks.py
    - test/testcases/test_log_token_masking.py
    - test/unit_test/test_request_log_template.py
    - test/unit_test/test_nginx_log_format.py
  modified:
    - docker/nginx/nginx.conf
    - api/apps/middleware.py
    - internal/router/middleware.go
    - internal/router/router_test.go
    - .planning/DECISIONS.md
key-decisions:
  - "R-127: matrix generation, the two explicit caller-variant exclusions, Nginx log format change, logger masking and its residual, leak sweep rules"
requirements-completed: []
duration: single session
completed: 2026-10-08
---

# Phase 2 Plan 25: Cross-tenant matrix, leak sweep and log masking Summary

Tenant isolation is proven from the endpoint registry on both language twins, no implemented endpoint leaks a credential, a hash or an internal column, and the real container logs of Nginx, Go and Python never contain a credential; the log checks found and fixed three real defects.

## Commits

| Commit | What |
|---|---|
| a1d83d7 | Task 1: registry-driven matrix, Python and Go twins |
| 38db01b | Task 2 tests: leak sweep, log masking e2e, Python template unit test (written first, red) |
| 5740a7c | fix: Nginx access log masks token-bearing paths |
| 3ac7214 | fix: Go and Python loggers mask credential spellings, Python logs the route template |
| 6daf0cf | matrix failure messages carry counts, never values |
| 172d7e5 | R-127 and the Nginx log format unit test |

## Matrix

- Source: `conf/routes.yaml`, implemented rows with scope tenant: **8 rows** (6 with ids: `DELETE /api/v1/system/tokens/{token}`, `GET|POST /api/v1/tenants/{tenant_id}/users`, `DELETE /api/v1/tenants/{tenant_id}/users`, `PATCH /api/v1/tenants/{tenant_id}`, `PATCH /api/v1/tenants/{tenant_id}/users/{user_id}`; 2 list-isolation rows: `GET|POST /api/v1/system/tokens`). **No row is excluded.** Python collects 19 cases for `-t cross_tenant` (6 outsider, 6 other-position, 5 role-refusal, 2 list-isolation) plus 4 unit guard tests; Go runs the same 8 rows in `TestCrossTenantMatrix` (logged: "8 registry rows covered (6 with ids, 2 without)") plus 2 guard tests.
- Per row: B (stranger), the user with only a pending invitation to A, and B's API token each call A's real id and every mix of real and random ids, and the (status, code, message) triple equals the one for random nonexistent ids (32-hex, and a well-formed random token for the token row); stranger and invitee get 404, B's API token gets 401 (all tenant rows are jwt-only); A's data is snapshotted as A (members, tokens, the memberships seen by the invited and joined users) before and after and is unchanged. A's ids in query and body positions and B's own tenant in the path reach nothing of A's and reveal none of A's values. An admin and a normal member of A that lack the route's role get 403 (404 for the invitee-only route). Token list and create: B's, the pending invitee's and A's members' lists never contain A's tokens even with `tenant_id` smuggled, B's create ignores a client-chosen token value and tenant, A's list is unchanged.
- Explicit variant exclusions (R-127): the pending-invitee caller is not run against `PATCH /api/v1/tenants/{tenant_id}` (answering the invitation is that route's purpose); the role-refusal variants run only for rows with a tenant id in the path.
- Guard proof: synthetic registry copies (`tmp_path` in Python, `t.TempDir` in Go) with one row of each kind fail with a message naming the row and the dict to extend; unimplemented and non-tenant synthetic rows are ignored; a stale fixture key fails.

## Leak sweep

`test_response_leaks.py` exercises all 29 implemented registry rows (public, session, account, password reset, tenant) on success and error paths, through Nginx with real accounts and Mailpit, and scans every recorded response (bodies and headers; at least two per row). Scanner (`_leak_sweep.py`): forbidden key names anywhere in the JSON, hash-shaped values, the credential fields only in the login and token rows, `reset_ticket` only in the verify row, and the values of 20+ secrets (passwords, session tokens, API tokens and beta values, the real and a wrong OTP, the ticket, the hashes and stored access tokens read back from MySQL, and the stack's own password/secret/key settings). Result: no leak found. The scanner is proven with planted leaks (unit). A registry row the sweep does not call, or one without a success and an error response, fails the test.

## Defects found and fixed

1. **Nginx logged the raw request line, including the token in `DELETE /api/v1/system/tokens/<token>`** (default combined format; my own matrix run wrote real tokens into it). Fixed in `docker/nginx/nginx.conf` (5740a7c): `map $uri $loggable_uri` (decoded, normalised path, case-insensitive) replaces the segment after the token family and any `ragflow-` shaped segment with `***`; named `log_format` without the request line, query string and Referer. Red first: the masking test failed on the raw path.
2. **Go logged the raw token for unmatched spellings of the token path** (e.g. `DELETE /api/v1/system//tokens/<token>`, found by the extended masking test, and a mistyped endpoint). Fixed in `internal/router/middleware.go` (3ac7214): any spelling is logged as the template; token-shaped segments are masked before truncation. Red first: `TestUnmatchedTokenPathSpellingsDoNotLogTheToken` failed.
3. **Python logged the raw path for every request**, so any later Python route with an id or token in the path would have leaked it. Fixed in `api/apps/middleware.py` (3ac7214): logs `request.url_rule.rule` for matched routes, the same masking as Go for unmatched ones. Red first: 2 failures in the new unit test.

Residual (R-127): a 405 on a known path with another method has no route template in Quart or Gin, so its raw path is logged; only the token family and token-shaped values are protected there. Log files under `ragflow-logs/` written by earlier runs (before the fix) may still contain raw token paths; they are git-ignored and were not rewritten.

## Test-first record

- Matrix: fixtures and tests were written together and passed on the first live run (no production change was needed; the matrix found no isolation defect). The guard tests are the red-capable half: with an empty `BUILDERS` they fail by construction (proven by the synthetic-row tests).
- Task 2: `test_log_token_masking.py` failed (`the Nginx access log must record the masked path`), `test_request_log_template.py` failed (2 of 3), the doubled-slash case failed against the fixed Nginx (`appears 1 time(s) in the go log`), `TestUnmatchedTokenPathSpellings...` failed (token in the log). All pass after the fixes.

## Live results (stack devrag-stack, port 8088, MemAvailable 7400 MiB before start, app image rebuilt with `docker compose ... up -d --build app` after each logger change)

- `uv run python run_tests.py -m e2e -t cross_tenant`: 19 passed (`-- --collect-only -q` selects 19).
- `-t "token_masking or response_leaks or cross_tenant"`: 25 passed after the first rebuild; `-t token_masking`: 3 passed after the last rebuild and again after the full regression (whole container log: 0 token-shaped values, 24 masked Nginx lines, 25 Go template lines).
- `GOTOOLCHAIN=local go test -count=1 -tags=e2e ./internal/e2e/ -run CrossTenant -v`: pass, 8 rows.
- `uv run python run_tests.py -m "integration or e2e"`: 280 passed.
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...` (SERVICE_CONF, `E2E_BASE_URL=http://127.0.0.1:8088`, `MAILPIT_URL`, root password from `docker/.env`, not printed): all packages ok.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 8 files, 36 tests passed.
- Cleanup: the 17 accounts the web live run created (created after 08:44 UTC) were deleted by SQL with their tenant, user_tenant, api_token and tenant_llm rows; Python and Go tests removed their own. Older `http-` and `status-` rows (3 per web live run, from earlier plans, last at 07:36 and 08:15) were not touched; the web live helper `registerLiveAccount` does not clean them up (not fixed here).
- Stack stopped with compose `stop` (profiles cpu, elasticsearch, mail); `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal, foreign `compose` project untouched. `make up` was not re-run for rebuilds because its preflight (correctly) refuses ports held by the stack itself; the app service was rebuilt with the same compose files and profiles.

## Final checks (as observed, after the last code change)

- `make ci`: 7/7 gates passed, ruff clean
- `uv run python run_tests.py -m unit`: 789 passed, 1 skipped, 280 deselected (763 before)
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean (also with `-tags=integration,e2e`); `scripts/gen_routes.py --check`: exit 0

## Deviations from Plan

1. [Rule 3] Added helper modules `_leak_sweep.py` (scanner) and two unit test files (`test_request_log_template.py`, `test_nginx_log_format.py`) beyond the plan's file list, to keep files small and to test the loggers without a live stack. `test/testcases/test_request_log.py` and the plan's Go logger code needed no change for the template (Go already logged `c.FullPath()` since 02-20); `internal/router/middleware.go` changed for unmatched spellings.
2. The Nginx mask matches `$uri` (decoded and normalised) instead of `$request_uri`, and the new log format omits the query string and Referer (R-127 item 4).
3. The doubled-slash and mistyped-endpoint spellings were added to the masking test after the first pass revealed them; they are part of the plan's intent (no token in any log).
4. Matrix and masking tests carry marker `e2e` per test (guard tests carry `unit`), so `-m unit` also runs the guards.

## Known Stubs

None.

## Threat Flags

None new. T-02-117, T-02-118 (matrix incl. mutating rows with read-back), T-02-119 (real container logs), T-02-120 (leak sweep) and T-02-121 (missing-fixture guard) are mitigated and tested.

## Self-Check: PASSED

Commits a1d83d7, 38db01b, 5740a7c, 3ac7214, 6daf0cf and 172d7e5 exist; `test/testcases/_matrix_fixtures.py`, `test/testcases/test_cross_tenant_matrix.py`, `internal/e2e/cross_tenant_matrix_e2e_test.go`, `internal/e2e/matrix_fixtures_test.go`, `test/testcases/test_response_leaks.py`, `test/testcases/_leak_sweep.py`, `test/testcases/test_log_token_masking.py`, `test/unit_test/test_request_log_template.py` and `test/unit_test/test_nginx_log_format.py` exist.
