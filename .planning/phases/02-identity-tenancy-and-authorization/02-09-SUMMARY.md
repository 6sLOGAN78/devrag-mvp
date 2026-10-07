---
phase: 02-identity-tenancy-and-authorization
plan: 09
subsystem: auth
tags: [go, gin, gorm, registration, login, rate-limit, valkey, pbkdf2, itsdangerous]
requires:
  - phase: 02-04
    provides: typed config (Auth, Models, RateLimit, Security)
  - phase: 02-06
    provides: token and password packages
  - phase: 02-07
    provides: account fixtures, schema verification
  - phase: 02-08
    provides: endpoint registry
provides:
  - POST /api/v1/users (atomic user + tenant + owner membership)
  - POST /api/v1/auth/login (shared token, HttpOnly ragflow_auth cookie, generic failure, 429 with Retry-After)
  - Redis fixed-window limiter that fails closed
  - common.ClientIP (R-114)
  - register_enabled in /api/v1/system/config
affects: [02-10, 02-11, 02-12, 02-14, 02-17, 02-20]
key-files:
  created:
    - internal/common/clientip.go
    - internal/dao/user.go
    - internal/dao/tenant.go
    - internal/dao/user_tenant.go
    - internal/dao/tenant_llm.go
    - internal/service/account.go
    - internal/service/ratelimit.go
    - internal/handler/account.go
  modified:
    - internal/dao/db.go
    - internal/dao/redis.go
    - internal/service/system.go
    - internal/router/router.go
    - internal/router/middleware.go
    - cmd/ragflow_server.go
    - conf/routes.yaml
    - Dockerfile
decisions:
  - "Token swap is a compare-and-swap on the value the login read (`access_token <=> old`) followed by a re-read, instead of the plan's LIKE-based conditional UPDATE. It also repairs whitespace-only tokens that the SQL predicate would treat as valid."
  - "Login failure is HTTP 401 / envelope 401; validation 400 / 101; duplicate email 409; disabled switch 403; 429 maps to envelope 400 (R-63)."
  - "Email failures are recorded for unknown emails too, so lockout behaviour does not reveal existence; the lock holds for the right password (R-94)."
  - "gorm TranslateError is enabled so a duplicate email is detected by error type, not by driver error number."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 09: Go registration and login Summary

Registration and login work end to end through Nginx (port 8088) against the real MySQL and Valkey: one-transaction signup, a Python-verifiable shared access token, generic login failures, configurable fail-closed rate limits and a loopback-only X-Real-IP rule.

## Commits

| Task | Commit |
|------|--------|
| 1 Failing tests | e4231dd |
| 2 DAOs, services, limiter, client IP | a8457d5 |
| 3 Handlers, routes, Dockerfile fix | bc22233 |
| Follow-ups (stale tests) | route ownership test, registry unit test (see deviations) |

## Test-first record

Before implementation `go vet -tags=integration,e2e ./internal/...` failed: `undefined: ClientIP` (common), `undefined: Account` (service), `WithRegisterEnabled undefined` (router). The Python `registration` e2e tests were collected (6 tests) but not run against the old image (no stack up then); the new tests are live-run after the change only. After implementation: all Go and Python tests below pass.

## What was observed live (stack `devrag-stack`, web port 8088, rebuilt app image)

- `uv run python run_tests.py -m e2e -t registration`: 6 passed (register, rows in MySQL, token verified with Python itsdangerous, shared token on second login, generic failure, 5-then-429 lockout with Retry-After, config switch).
- `uv run python run_tests.py -m e2e`: 76 passed after fixing one stale test (below).
- `go test -count=1 -tags=integration,e2e ./...`: all packages ok, including the e2e register and login through Nginx.
- `go test -race -tags=integration ./internal/service/... ./internal/router/...`: ok (rollback, limiter, fail-closed, parallel logins, spoof test, log check).
- After the runs, `user` rows with `@example.test` emails: 0; `tenant` rows: 0.

## Deviations from Plan

1. [Rule 3 - Blocking] `Dockerfile` go-build stage did not copy `conf/embed.go` and `conf/schema.json`, so `go build ./cmd` failed in the image (since 02-07). Added the COPY line.
2. [Rule 1 - Bug] `test_route_ownership.py::test_python_documented_paths_under_go_looking_prefixes[/api/v1/system/tokens]` failed live: 02-08 moved that path to Go (R-92). Removed it from the Python collision list; Go ownership stays covered by `test_declared_owner_answers`. Not weakened.
3. [Rule 1] `test_route_policy.py::test_registry_has_phase2_endpoints_unimplemented` asserted the two rows were unimplemented; split so the two rows are asserted implemented.
4. `router_test.go` config expectation updated for the new `register_enabled` field.
5. Token write is a compare-and-swap rather than the plan's LIKE SQL (decision above).
6. In-process HTTP tests live in `internal/router/account_integration_test.go` (not in the plan's file list) because handler tests need the router and an external service test package would block the id-injection rollback test.
7. `requestLogger` now logs `c.Errors` (type-safe text, no bodies) so 500/503 causes are visible to operators.

## Notes and limits

- Through Nginx, every request reaches Go from the Nginx container address (Nginx sets X-Real-IP to `$remote_addr`, and the Go peer is not loopback), so the per-IP counters are shared by all clients. This is what the plan expected; the per-IP limits in the dev overlay are raised for tests. In production a per-IP limit is effectively global until the proxy is made a trusted peer. Needs a decision in the exit-gate review.
- Per-email lock holds for the right password too (R-94 "15-minute lock"); an attacker can lock out a victim for the window.
- Timing test compares medians of five attempts (unknown email must cost at least half a known-email failure); it guards against a missing dummy hash, not microsecond differences.
- REQUIREMENTS.md not touched.

## Known Stubs

None. Tenant default model ids are empty unless configured (D-22).

## Threat Flags

None beyond the plan's threat model (T-02-31..38 mitigated and tested).

## Final checks (as observed)

- `make ci`: 7/7 gates passed
- `uv run python run_tests.py -m unit`: 606 passed, 1 skipped
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean
- Stack stopped with `docker compose -p devrag-stack ... stop` (0 devrag-stack containers running).

## Self-Check: PASSED
