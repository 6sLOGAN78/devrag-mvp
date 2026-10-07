---
phase: 02-identity-tenancy-and-authorization
plan: 22
subsystem: auth
tags: [go, gin, permissions, tenancy, invitations, tenant-isolation, rate-limit, codegen]
requires: [02-20]
provides:
  - conf/permissions.yaml generated into Go (Allowed) and Python (allowed) by scripts/gen_routes.py, under --check
  - GET and POST /api/v1/tenants/{tenant_id}/users and PATCH /api/v1/tenants/{tenant_id} (Go, jwt only)
  - service.Tenant ListMembers, Invite, Respond; dao FindMemberRole, ListTenantMembers, CreateInvite, AcceptInvite, DeclineInvite
affects: [02-23, 02-24, 02-25, 03]
tech-stack:
  added: []
  patterns:
    - "one shared 404 for non-member, invitee-only and nonexistent tenant; 403 only for a member lacking the role"
    - "invitations serialised by a tenant-row lock because user_tenant has no unique key"
    - "hand-written oracle fixture walked by both the Go and the Python table tests"
key-files:
  created:
    - conf/permissions.yaml
    - internal/common/permissions_gen.go
    - api/apps/permissions_gen.py
    - internal/common/permissions_test.go
    - test/unit_test/test_permissions_table.py
    - test/fixtures/permission_cases.json
    - internal/service/tenant_members.go
    - internal/service/tenant_members_integration_test.go
    - internal/router/team_integration_test.go
    - internal/e2e/tenant_invite_e2e_test.go
  modified:
    - scripts/gen_routes.py
    - internal/dao/user_tenant.go
    - internal/service/tenant.go
    - internal/handler/tenant.go
    - internal/router/router.go
    - internal/router/router_test.go
    - cmd/ragflow_server.go
    - conf/routes.yaml
    - internal/testutil/fixtures.go
    - test/unit_test/{test_gen_routes,test_route_policy,test_gen_go_entities}.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-123: permission matrix keyed (area, action); membership excludes invite; one 404 for every invisible tenant; owner also sees pending invitations; invite takes only email; invite attempts rate limited per caller and per tenant with the login-class numbers; PATCH accept or decline matches only role invite"
requirements-completed: []
duration: single session
completed: 2026-10-08
---

# Phase 2 Plan 22: Permission table, member list, owner-only invite, accept and decline Summary

The shared permission matrix is generated into Go and Python under the existing drift gate, and the Go server now lists a workspace's members, lets only the owner invite an existing account by email, and lets the invitee accept or decline, with every non-member answered by one identical 404.

## Commits

| Commit | What |
|---|---|
| 430c217 | Task 1: permission table, generator output, shared oracle, failing service and e2e tests |
| 86fb96f | Task 2: DAO and membership service |
| 0e477db | Task 3: handlers, routes, main wiring, registry rows, router integration tests, decision R-123 |
| (fix) | `test(02-22)`: drift-gate fixture copies the new generated Go file |

## Test-first record

- Before the table existed: `run_tests.py -m unit -t permissions_table` selected 19 tests, 18 failed (no `conf/permissions.yaml`, no generated modules, no validation), 1 passed.
- Before the service existed: `go vet -tags=integration,e2e ./internal/...` failed with `undefined: Allowed` (common) and `Tenant has no field or method WithInvites` (service); the e2e tests could not be run before the routes existed (the handlers were absent from the build).
- After implementation: all of them pass (below).

## What was built

- **Permission table.** `conf/permissions.yaml` holds the 10 rows of `docs/16-auth/permissions.md`, keyed (area, action), subjects owner, admin, normal, beta_token, api_token, plus `enforced_in`. Team Admin is owner-only (D-13). `gen_routes.py` validates it (unknown subject, `invite`, duplicate, missing documented area, extra field, bad name all exit 2), emits `internal/common/permissions_gen.go` and `api/apps/permissions_gen.py` with do-not-edit headers, and `--check` (also run by `scripts/ci/check_generated.py` inside `make ci`) fails on drift. Any unlisted subject, area or action is denied. Go and Python are compared against the hand-written `test/fixtures/permission_cases.json`.
- **Membership.** Active owner, admin or normal row in an active tenant. `invite` is never membership. Role is read from the database in the request; the tenant id in the path is only a lookup key.
- **Member list.** id, nickname, email, avatar, role, joined_time; `page` and `page_size` (maximum 100); owner first. Only the owner also sees pending invitations.
- **Invite.** Owner only (403 for admin or normal, 404 for non-members). Body field `email` only. Unknown or disabled email 404 `no active account with that email`; self, already a member and already invited are three distinct 409s; none names another tenant. Rate limited per caller id and per tenant id with `login_per_ip` over `login_window_seconds` (429 with Retry-After; 503 when Redis is down). The tenant row is locked and the inviter's ownership and the target's rows are re-read inside the transaction.
- **Accept or decline.** `PATCH /api/v1/tenants/{id}` with optional `{action}`; an `UPDATE ... WHERE role='invite'` or `DELETE ... WHERE role='invite'` for the caller only, so an owner or admin calling it changes nothing (404, D-27).
- **Jwt only.** The routes sit under the `/api/v1/tenants/` jwt family; API and beta tokens are 401 at the gate (live test).

## Live results (stack devrag-stack, port 8088, image rebuilt by `make up`, MemAvailable 7449 MiB before start)

- `go test -count=1 -tags=integration,e2e ./...`: all packages ok. The service integration tier passes 19 new membership tests (also under `-race`), including the 12-way parallel invite leaving exactly one row; the e2e tier passes members and 404 equivalence (stranger, invitee-only and random id bodies byte-identical), invite, accept, decline, D-27, 8-way parallel invites through the ingress (one 200, seven 409), and API and beta credentials refused (401).
- `uv run python run_tests.py -m "integration or e2e"`: 251 passed.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 6 files, 28 tests passed.
- **`web/src/pages/forgot-password/forgot-password.live.test.ts` (plan 02-18, first live run): PASSED**, 4 of 4 tests (health and Mailpit wait, account and token, unknown email like any other with no mail, real emailed-code reset signing out every device and creating no session, old token and old password refused and new password accepted). No change to the test or the page was needed.
- Stack stopped with `docker compose -p devrag-stack ... --profile cpu --profile elasticsearch --profile mail stop`; `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal; the foreign `compose` project was not touched.

## Final checks (as observed, after the last code change)

- `make ci`: 7/7 gates passed, ruff clean
- `uv run python run_tests.py -m unit`: 764 passed, 1 skipped, 251 deselected
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok
- `GOTOOLCHAIN=local go vet ./...`: clean
- `scripts/gen_routes.py --check`: exit 0

## Deviations from Plan

1. [Rule 2] Owner-only visibility of pending invitations in the member list (role `invite`), because the owner must see whom to withdraw (UI-SPEC, plan 02-23); recorded in R-123. Members who are not the owner never see them.
2. [Rule 2] Rate limiting of invitations per caller and per tenant, store failures mapped to 503 with only the error type logged, 1 KiB body caps, and bounded pagination: required by the hard constraints of this run, not named in the plan text.
3. [Rule 3] Membership code lives in new `internal/service/tenant_members.go` rather than `tenant.go` (no giant files); `tenant.go` only gained the store interface methods and the invite limiter wiring.
4. [Rule 3] Existing test fixtures that copy only `routes.yaml` (`test_gen_routes.py`, `test_route_policy.py`, `test_gen_go_entities.py`) also copy `permissions.yaml` and the generated Go file; no assertion was changed. `test_route_policy.py` moved GET `/tenants/{id}/users` from the "unimplemented" list into a new implemented-and-jwt-only test (same pattern as plans 02-15 and 02-20). `internal/router/router_test.go::fullEngine` registers `WithTeam`.
5. `internal/testutil`: added `SetMemberRole` (creates admin members until plan 02-23) and `DeleteAccount` now also removes `user_tenant` rows by tenant id.
6. The planned live rate-limit e2e test was dropped: the dev compose overlay raises the login-class limit to 100000, so it cannot be exhausted through the ingress. The limit is proven in the service tier and through the router (`TestInviteIsRateLimitedWith429AndRetryAfter`, `TestInviteFailsClosedWith503WhenRedisIsDown`).
7. Enumeration: the unknown-email answer is distinguishable by design (D-14, R-107); it is limited by the rate limit above and by owner-only access.

## Known Stubs

None. Rows of the permission table other than Team Admin are recorded with `enforced_in` and enforced as their routes land (datasets phase 3, agents phase 7, search bots and MCP phase 8).

## Threat Flags

None beyond the plan register (T-02-102..107 mitigated and tested; T-02-105 accepted as R-107 and rate limited).

## Self-Check: PASSED

Commits 430c217, 86fb96f and 0e477db exist; `conf/permissions.yaml`, `internal/common/permissions_gen.go`, `api/apps/permissions_gen.py`, `internal/service/tenant_members.go` and `internal/e2e/tenant_invite_e2e_test.go` exist.
