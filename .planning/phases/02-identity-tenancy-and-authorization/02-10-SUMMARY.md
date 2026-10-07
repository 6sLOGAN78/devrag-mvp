---
phase: 02-identity-tenancy-and-authorization
plan: 10
subsystem: auth
tags: [go, gin, auth-gate, default-deny, csrf, cookie, logout, itsdangerous]
requires:
  - phase: 02-06
    provides: access-token package (verify, 30-day max age, AUTH-08 rules)
  - phase: 02-08
    provides: endpoint registry and generated PolicyFor table
  - phase: 02-09
    provides: accounts, login, cookie, ClientIP
provides:
  - handler.AuthGate default-deny middleware (jwt resolution, cookie fallback, CSRF)
  - service.Auth (ResolvePrincipal, Logout, UserInfo) with ErrUnauthenticated vs infrastructure errors
  - POST /api/v1/auth/logout, GET /v1/user/info
  - /api/v1/system/version authenticated (D-19)
affects: [02-11, 02-12, 02-14, 02-20]
key-files:
  created:
    - internal/handler/auth.go
    - internal/handler/user.go
    - internal/service/auth.go
    - internal/handler/auth_test.go
    - internal/router/auth_integration_test.go
    - internal/e2e/auth_gate_e2e_test.go
  modified:
    - internal/dao/user.go
    - internal/router/router.go
    - internal/handler/account.go
    - cmd/ragflow_server.go
    - conf/routes.yaml
    - docker/nginx/proxy.conf
    - web/src/constants/api-routes.generated.json
    - test/unit_test/test_route_auth_markers.py
    - test/unit_test/test_route_policy.py
    - test/testcases/{conftest,test_envelope,test_routing,test_request_log}.py
decisions:
  - "NewEngine options became a collected struct so the gate is installed by Use before any route (gin binds middleware at registration). Without WithAuth every protected route answers 401 (handler.DenyAll)."
  - "Nginx now sends X-Forwarded-Host $http_host: `Host $host` drops the port, so Origin http://host:8088 could never match. The CSRF check compares Origin or Referer to X-Forwarded-Host, else Host, else the configured allowed origins."
  - "Secure on the cookie follows `TLS or X-Forwarded-Proto: https` from any peer (shared helper for login and logout), not loopback only: behind the Nginx container the peer is never loopback, and a forged header can only add Secure, never remove it. Needs reviewer sign-off against the plan's wording."
  - "MySQL equality is collation-based, so the service re-compares the stored token with a constant-time exact compare after the lookup."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 10: Go default-deny auth gate Summary

The Go server now rejects every request that has no valid credential unless a registry entry says `none`. Logout, session lookup and an authenticated version route work through Nginx on port 8088.

## Commits

| Task | Commit |
|------|--------|
| 1 Failing tests | 5ef310c |
| 2 and 3 Gate, service, handlers, routes, Phase 1 test updates | bfc362e |
| Follow-up (log probe cookie header) | see git log for 02-10 |

## Test-first record

Before implementation `go vet -tags=integration,e2e ./internal/...` failed with `undefined: service.NewAuth` (handler tests) and `undefined: service.Principal` (router tests). `run_tests.py -m unit -t route_auth_markers` failed `test_marker_rules_hold_for_routes_yaml` (version marker still present). After implementation all pass.

## Route enumeration

`TestEveryEngineRouteIsDeclaredAndGated` iterates the real engine's `Routes()`: 9 routes, 0 undeclared. Each is an implemented Go registry row, and each non-`none` route answers the exact 401 envelope unauthenticated. The reverse check (every implemented Go row exists in the engine) passes. `TestUndeclaredHandlerWouldBeCaught` shows a handler without a row is denied and flagged. `TestEveryGoFamilyIsDeniedUnlessPublic` probes every non-public Go family (prefixes with a `prefixprobe-` suffix).

## Live results (stack devrag-stack, port 8088, rebuilt image, container healthy)

- `go test -count=1 -tags=integration,e2e ./...`: all packages ok (SERVICE_CONF rendered to the scratchpad with host addresses).
- `uv run python run_tests.py -m "integration or e2e"`: 161 passed, 1 failed. The failure is `test_migration_runner.py::test_init_db_entry_point_exit_codes`: its `_conf_env` omits SECRET_KEY, which the renderer has required since 02-04. Not caused by this plan; recorded in `deferred-items.md`.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 9 passed. With the default URL (port 8080, a foreign service that answers 401) 8 fail; that is a port issue, not a gate effect. No live frontend test fails because of the gate.
- Container healthcheck stayed `healthy` (`/health`, `/api/v1/system/healthz` public).
- Stack stopped afterwards: 0 devrag-stack containers.

## Deviations from Plan

1. [Rule 3] Router options restructured (see decisions); `settings` in the test file forced the name `engineOptions`.
2. [Rule 1] Python e2e tests that hit Go routes were updated to assert both behaviours: `test_envelope` (go 404 now 401 plus authenticated 404), `test_routing` (version unauthenticated 401, authenticated 200), `test_request_log` (Go probe with a fake bearer is 401; authenticated variant 404 with no token in the log). A session `account` fixture was added to `test/testcases/conftest.py`.
3. [Rule 2] `docker/nginx/proxy.conf` gained `X-Forwarded-Host` (not in the plan's file list).
4. `test_route_policy.py` split so logout and user info are asserted implemented.
5. Secure-cookie rule differs from the plan wording (decision above).
6. `/api/v1/auth/` is a public prefix in the generated table, so an unregistered path under it answers 404 not 401 (no handler can be reached through it; the enumeration test covers real routes).
7. The plan's "signed non-string" token class is covered by the existing 02-06 token vectors rather than the gate test (the helper cannot sign one).

## Known Stubs

None. `api` and `beta` credential types answer 401 until plan 02-20 (by design).

## Threat Flags

None beyond the plan's register (T-02-39..45A mitigated and tested).

## Final checks (as observed)

- `make ci`: 7/7 gates passed
- `uv run python run_tests.py -m unit`: 608 passed, 1 skipped
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean

## Self-Check: PASSED
