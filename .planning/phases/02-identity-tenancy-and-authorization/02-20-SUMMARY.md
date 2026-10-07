---
phase: 02-identity-tenancy-and-authorization
plan: 20
subsystem: auth
tags: [go, gin, api-token, beta-token, auth-gate, tenant-isolation, request-log, rate-limit]
requires: [02-10, 02-14, 02-17]
provides:
  - POST/GET /api/v1/system/tokens and DELETE /api/v1/system/tokens/:token (Go, jwt-only, tenant-scoped)
  - Go gate resolves api and beta credential types per route policy (cookie on jwt routes only)
  - service.Auth.WithTokens, service.Token, dao api_token queries with exact (BINARY) matching
  - request log writes the route template (the DELETE path never carries the token)
affects: [02-21, 02-22, 02-25, 08]
tech-stack:
  added: []
  patterns:
    - "token cap enforced in a transaction that locks the tenant row (no race past the cap)"
    - "optional TokenLookup on Auth: without it only jwt resolves, existing tests unchanged"
key-files:
  created:
    - internal/dao/api_token.go
    - internal/service/token.go
    - internal/handler/token.go
    - internal/service/token_integration_test.go
    - internal/handler/auth_api_beta_test.go
    - internal/e2e/token_e2e_test.go
    - test/testcases/test_api_token_flow.py
  modified:
    - internal/service/auth.go
    - internal/handler/auth.go
    - internal/handler/auth_test.go
    - internal/router/router.go
    - internal/router/middleware.go
    - internal/router/router_test.go
    - cmd/ragflow_server.go
    - conf/routes.yaml
    - internal/common/route_policy_gen.go
    - api/apps/route_policy_gen.py
    - internal/common/logger.go
    - common/log_utils.py
    - api/db/services/auth_service.py
    - internal/testutil/fixtures.go
    - test/helpers/accounts.py
    - test/unit_test/{test_route_policy,test_auth_gate,test_log_redaction}.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-121: management is owner-session only; 20 creations per hour and 50 tokens per tenant (constants, 409 at the cap); exact BINARY matching; token principals never carry superuser (Go and Python); route-template request log; beta joins the redacted keys"
requirements-completed: [AUTH-19, AUTH-20, AUTH-21, AUTH-22, AUTH-23]
duration: single session
completed: 2026-10-08
---

# Phase 2 Plan 20: API tokens Summary

Signed-in owners can create, list and delete API tokens (`ragflow-` plus 32 random bytes, and a 32-hex beta value), and a request carrying only an API token now resolves to the owning tenant on both the Go and the Python gate; a deleted token stops working at once on both.

## Commits

| Commit | What |
|---|---|
| 2a85723 | Task 1: failing tests (service integration, handler gate, router log, Go e2e, Python flow, redaction) |
| 048c8d0 | Tasks 2 and 3: DAO, service, handlers, gate extension, registry rows, redaction, decision R-121 |
| 5ca8af1 | Live-run test fixes (envelope compared by value, no empty Bearer header) |

## Test-first record

Before implementation: `go vet -tags=integration,e2e ./internal/...` failed with `undefined: Token` (service), `undefined: WithTokens` (router), `undefined: dao.ErrTokenLimit` and `WithTokens` (handler); `run_tests.py -m unit -t log_redaction` failed `test_beta_token_fields_and_fragments_masked`; `-t api_token_flow --collect-only` selected 5 tests. Later, `test_a_token_principal_never_carries_superuser_rights` was written after the Python fix and shown to fail when the fix is reverted. After implementation all pass.

## What was built

- Create returns `token`, `beta`, `create_time` (ms); list is newest first, `page`/`page_size` (default and max 100, bad values 400), plain array; no `dialog_id`, no tenant id, `Cache-Control: no-store`. The POST body is size-capped and ignored (a `tenant_id` or `token` in it has no effect).
- Management needs a jwt principal with an own workspace (role owner): API or beta credentials are 401 at the gate (their resolver never sees them) and `ErrForbidden` in the service; no workspace is 403.
- Delete of another tenant's token, a missing token, an over-long value and `%` are the same 404 `token not found`, and nothing changes. Deleting and looking up use `col = ? AND BINARY col = ?`, so MySQL's case-insensitive collation cannot match a case variant.
- Gate: route auth value maps to accepted types (jwt: access token; api: access or API token; beta: beta value, access token, API token). Cookie only on jwt routes. Over-1024, empty, wrong prefix (API needs `ragflow-` and at most 255), non-32-alnum beta are refused before any database call. Lookup failure is 503 (R-114). An API or beta token resolves to its owner user in the token's tenant, owner must be active.
- AUTH-23 is proven on routes registered by the tests under `/api/v1/searchbots/` (unit gate and live through Nginx: valid beta gives 404 from Go, meaning the gate passed; wrong, empty, short, junk and absent give HTTP 401 with body code 401). The real beta handlers arrive in Phase 8.
- Logging: matched routes log the template (`/api/v1/system/tokens/:token`); unmatched requests under the token family log the template too; `beta` joins the redacted keys in Go and Python. Live test reads `ragflow-logs/ragflow_go.log` and `ragflow_server.log` and finds no token, beta value or session token.
- Storage stays plaintext as documented (D-12, T-02-97 accepted; hash-plus-prefix is BILL-01, Phase 8).

## Live results (stack devrag-stack, port 8088, image rebuilt by `make up`, MemAvailable 8204 MiB)

- `uv run python run_tests.py -m e2e -t api_token_flow`: 5 passed (first run had one test bug, fixed in 5ca8af1).
- `uv run python run_tests.py -m "integration or e2e"`: 251 passed.
- `go test -count=1 -tags=integration,e2e ./...`: all packages ok (first run: `TestAPITokenLifecycleThroughIngress` failed because Go and Python serialise the 401 envelope with different spacing; the test now compares by value). Integration tests ran with `SERVICE_CONF`, `E2E_BASE_URL=http://127.0.0.1:8088` and the MySQL root password read from `docker/.env`.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 5 files, 23 tests passed, including `src/pages/user-setting/profile/profile.live.test.ts` (edited in plan 02-16 without a live run; it passes unchanged, with React `act(...)` warnings on stderr only).
- Stack stopped with `docker compose -p devrag-stack ... --profile cpu --profile elasticsearch --profile mail stop`; `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal; the foreign `compose` project was not touched.

## Final checks (as observed)

- `make ci`: 7/7 gates passed
- `uv run python run_tests.py -m unit`: 743 passed, 1 skipped, 251 deselected
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean
- `scripts/gen_routes.py --check`: exit 0

## Deviations from Plan

1. [Rule 2] Per-tenant cap (50), creation rate limit (20 per hour) and list pagination bounds were added although the plan names none; the hard constraints for this run require them. Recorded in R-121.
2. [Rule 2] Token principals never carry superuser rights, changed in Python too (`auth_service._principal_for_token`) for parity (plan 02-14 had copied the owner flag).
3. [Rule 1] `internal/handler/auth_test.go::TestCookieIsOnlyHonouredOnJWTRoutes` had asserted that an access token in the header on a beta route (`/api/v1/mcp`) is 401 "because beta resolution is not built yet". This plan builds it and the reference accepts access tokens on beta routes, so that line now asserts 200; the cookie assertion (401) is unchanged. No other existing assertion was changed or weakened.
4. [Rule 3] `test/unit_test/test_route_policy.py`: the token rows moved from the "unimplemented" test to a new "implemented and jwt-only, roles owner" test (same pattern as plan 02-15). Registry rows now say `roles: [owner]` and `implemented: true`.
5. Test fixtures (`testutil.DeleteAccount`, `delete_accounts`) also delete the account's `api_token` rows.
6. `internal/router/middleware.go` and `internal/common/logger.go`, `common/log_utils.py` were touched although not in the plan's file list (logging and redaction requirements).
7. Constant work for a miss versus a hit: an API or beta miss costs one indexed lookup, a hit costs the lookup plus the owner and membership reads; not equalised (not practical, noted).
8. The plan listed `internal/handler/auth_api_beta_test.go` and others as the only test files; the log test was added to `internal/router/router_test.go` and `fullEngine` there now registers the token routes.

## Known Stubs

None.

## Threat Flags

None beyond the plan register (T-02-92..96 mitigated and tested; T-02-97 accepted, BILL-01).

## Self-Check: PASSED

Commits 2a85723, 048c8d0, 5ca8af1 exist; `internal/dao/api_token.go`, `internal/service/token.go`, `internal/handler/token.go`, `test/testcases/test_api_token_flow.py` exist.
