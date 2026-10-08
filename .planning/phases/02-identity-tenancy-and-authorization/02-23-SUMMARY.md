---
phase: 02-identity-tenancy-and-authorization
plan: 23
subsystem: auth
tags: [go, gin, tenancy, membership, roles, transactions, race-tests]
requires: [02-22]
provides:
  - PATCH /api/v1/tenants/{tenant_id}/users/{user_id} (role change, owner only) and DELETE /api/v1/tenants/{tenant_id}/users (remove, withdraw, leave), Go, jwt only
  - service.Tenant ChangeRole and RemoveMember; dao ChangeMemberRole and RemoveMember (one transaction, tenant row locked)
affects: [02-24, 02-25, 03]
tech-stack:
  added: []
  patterns:
    - "tenant row lock, then caller and target rows read under it, then a role-conditional UPDATE or DELETE that can never match the owner row"
    - "a non-owner naming another user is 403, never a silent self-removal"
key-files:
  created:
    - internal/service/tenant_roles.go
    - internal/service/tenant_roles_integration_test.go
    - internal/e2e/tenant_roles_e2e_test.go
    - test/testcases/test_tenant_membership.py
  modified:
    - internal/dao/user_tenant.go
    - internal/service/tenant.go
    - internal/handler/tenant.go
    - internal/router/router.go
    - internal/router/team_integration_test.go
    - conf/routes.yaml
    - test/unit_test/test_route_policy.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-125: role change and removal details (owner immutable, leave vs remove rules, accept-vs-withdraw race outcome, rate limits, removed-member behaviour)"
requirements-completed: []
duration: interrupted run plus one continuation session
completed: 2026-10-08
---

# Phase 2 Plan 23: Role change, removal, withdrawal and leave Summary

The workspace owner can promote and demote members between admin and normal, remove members and withdraw invitations, and members can leave, with the owner row provably immutable under parallel requests; the full cycle is proven through Nginx on the live stack.

## Review of the interrupted run (commits 4929cfa, d078ade, b2e1b92, 4b138b5)

The four commits were started by an interrupted run and reviewed critically by this continuation. No defect was found, so no corrective commit was needed. Checked against the security list: every mutation runs in one transaction that locks the tenant row and reads the caller's role and the target's rows under that lock; decisions use the generated permission table (`common.Allowed` through `canManageMembers`); the UPDATE only matches admin or normal rows and the DELETE only admin, normal or invite rows; the owner row is refused before the write and excluded by the write; roles `owner`, `invite` and unknown values are rejected; unknown body fields are ignored (handlers decode only `role` or `user_id`); a non-owner naming another user is 403; mutations are rate limited per caller and per tenant and fail closed; store failures are 503 with only the error type logged. Accept and decline were delivered by plan 02-22 (`PATCH /api/v1/tenants/{id}`); nothing was rebuilt here, and this plan's tests cover their interaction with withdrawal and repeats. Pre-existing assertions: the only removed test is `test_registry_has_phase2_endpoints_unimplemented`, whose single remaining row (this plan's PATCH route) is now asserted implemented and jwt-only in the extended registry test (same pattern as plans 02-15, 02-20, 02-22). In `team_integration_test.go` the 503 table gained the two new routes and its request body gained `role` and `user_id` fields (extended, no assertion weakened).

## Tasks

| Task | Commit | Notes |
|---|---|---|
| 1 Failing tests | 4929cfa, 4b138b5 | service integration, Go e2e, Python e2e (selector `tenant_membership`, 4 tests) |
| 2 DAO and service | d078ade | |
| 3 Handlers, routes, registry | b2e1b92 | registry rows flipped to implemented, route policy test updated |

Test-first record: the tests were committed first (4929cfa) by the interrupted run, before the DAO/service and handlers existed. The exact failure output was not preserved by that run, so it is not reproduced here; the tests reference `ChangeRole` and `RemoveMember` that did not exist until d078ade and the routes that did not exist until b2e1b92.

## Race tests (real MySQL, parallel requests)

Owner removes while the member leaves (exactly one succeeds, the other 404, member not resurrected, 4 rounds); two role changes on one row (both succeed, final role is one of the two, owner untouched); role change racing removal (removal always wins, no resurrection); accept racing withdrawal (either the withdrawal wins and accept is 404, or accept wins and the owner's removal then deletes the new member; both end with no row, never a duplicate); 16 racing removals and demotions targeting the owner row (all refused, exactly one owner remains).

## Live results (stack devrag-stack, port 8088, app image rebuilt by `make up` with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, MemAvailable 6123 MiB before start)

- `uv run python run_tests.py -m e2e -t tenant_membership`: 4 passed (collect-only selects the 4).
- `go test -race -tags=integration ./internal/service/... ./internal/dao/... ./internal/router/...`: ok.
- `go test -count=1 -tags=integration,e2e ./...` with `SERVICE_CONF`, `E2E_BASE_URL=http://127.0.0.1:8088`, `MAILPIT_URL=http://127.0.0.1:8025` and the docker env loaded: all packages ok. A first run without `E2E_BASE_URL` (default port 8080) timed out in the e2e package; that was an environment mistake, not a defect.
- `uv run python run_tests.py -m "integration or e2e"`: 255 passed.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 7 files, 32 tests passed.
- Cleanup: the web live run was started without a recorded accounts file, so its 10 `web*` accounts were deleted by SQL (users created in the last 90 minutes, with their tenant, user_tenant, api_token and tenant_llm rows), final count 0. Older `web*` rows from earlier plans were not touched.
- Stack stopped with compose `stop` (profiles cpu, elasticsearch, mail); `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal; the foreign `compose` project was not touched.

## Final checks (as observed, after the last code change)

- `make ci`: 7/7 gates passed, ruff clean
- `uv run python run_tests.py -m unit`: 763 passed, 1 skipped, 255 deselected (one fewer than plan 02-22 because the superseded unimplemented-registry test was removed)
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean; `go vet -tags=integration,e2e ./...` clean
- `scripts/gen_routes.py --check`: exit 0

## Deviations from Plan

1. [Rule 2] Mutations rate limited per caller and per tenant, store failures mapped to 503, 1 KiB body caps, and a pending-invitation role target refused (400): required by the run's hard constraints, not named in the plan text.
2. [Rule 3] The service code lives in new `internal/service/tenant_roles.go` rather than `tenant.go` (no giant files); `tenant.go` only gained the store interface methods.
3. The plan says an API token of a removed member's own tenant is unaffected; this is asserted live. Tokens a member "created in the tenant they left": none can exist, because token management is owner-only (R-121); recorded in R-125.
4. The `E2E_BASE_URL` and `MAILPIT_URL` variables must be set for the Go e2e tier against port 8088 (default is 8080).

## Known Stubs

None.

## Threat Flags

None beyond the plan register (T-02-108..111 mitigated and tested; T-02-112 accepted).

## Self-Check: PASSED

Commits 4929cfa, d078ade, b2e1b92 and 4b138b5 exist; `internal/service/tenant_roles.go`, `internal/e2e/tenant_roles_e2e_test.go` and `test/testcases/test_tenant_membership.py` exist.
