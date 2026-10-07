---
phase: 02-identity-tenancy-and-authorization
plan: 15
subsystem: auth
tags: [go, profile, avatar, password-change, tenant-info, tenant-list, rate-limit, mass-assignment]
requires: [02-10, 02-14]
provides:
  - POST /v1/user/setting (nickname, avatar, language, color_schema) acting only on the caller
  - POST /v1/user/setting/password (old password check, 8 to 128 rule, per-user rate limit, every device signed out)
  - GET /v1/user/tenant_info (own workspace with default model ids) and GET /v1/tenant/list (memberships and pending invitations)
  - service.ValidateAvatarDataURL (PNG, JPEG, WebP by magic bytes, 256 KB)
  - testutil.InsertPendingInvite (pending-invitation rows until plan 02-22)
affects: [02-16, 02-22, 02-2x frontend settings and team pages]
tech-stack:
  added: []
  patterns:
    - "request DTO lists the only settable fields; unknown JSON fields are never read, the user id comes from the gate principal"
    - "password replacement is a compare-and-swap on the old hash and rewrites access_token to INVALID_<hex> in the same transaction"
key-files:
  created:
    - internal/service/avatar.go
    - internal/service/avatar_test.go
    - internal/service/user.go
    - internal/service/tenant.go
    - internal/service/user_integration_test.go
    - internal/service/tenant_integration_test.go
    - internal/handler/tenant.go
    - internal/router/user_integration_test.go
    - internal/e2e/user_e2e_test.go
  modified:
    - internal/dao/user.go
    - internal/dao/user_tenant.go
    - internal/handler/user.go
    - internal/handler/account.go
    - internal/router/router.go
    - internal/router/router_test.go
    - internal/router/account_integration_test.go
    - internal/service/auth.go
    - internal/service/account.go
    - internal/testutil/fixtures.go
    - cmd/ragflow_server.go
    - conf/routes.yaml
    - test/unit_test/test_route_policy.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-118: field names old_password/new_password (docs), wrong current password is 400 not 401, settings field set, nickname and avatar rules, tenant list shape"
requirements-completed: [AUTH-13, AUTH-14, AUTH-15, TEN-06, TEN-07]
duration: one session
completed: 2026-10-07
---

# Phase 2 Plan 15: Go profile, password change, tenant info and tenant list Summary

A signed-in user can now edit their profile, change their password (which signs every device out on both engines) and read their own workspace and memberships, all acting only on the principal from the gate.

## Commits

| Commit | What |
|---|---|
| 2ae425c | test: failing avatar, service, router and ingress tests plus compile-only stubs |
| e92b3bb | feat: avatar validator, `User` and `Tenant` services, DAO methods |
| 2c7d980 | feat: handlers, routes, registry rows flipped, wired in the Go server |
| 934ea87 | test: the Phase 2 registry unit test now expects the four rows implemented |

## What was built

- **Avatar**: `data:image/{png,jpeg,webp};base64,` only; the declared type must match the decoded magic bytes (PNG signature, FFD8FF, RIFF....WEBP); at most 262144 decoded bytes; the encoded length is checked before decoding; the payload must re-encode identically (rejects line breaks and non-canonical tails). SVG, GIF and HTML fail. The error never echoes input. An empty avatar removes it.
- **Settings**: nickname 1 to 64 characters (no control, format or angle-bracket characters; the same rule now applies to registration), language `en` or `zh` (legacy labels accepted, stored as codes), color_schema `Bright` or `Dark`. The request struct holds four fields; `id`, `tenant_id`, `email`, `is_superuser`, `status`, `password`, `access_token` in a body are never read. Body cap 400 KB.
- **Password change**: body `old_password`, `new_password` (docs endpoint catalogue). Per-user limit `pwchange:user:<id>` using `LoginFailuresPerEmail` and `LoginWindowSeconds` from config (fails closed, 429 with Retry-After); wrong current password is 400 code 101 (not 401, so the SPA is not signed out by a typo); hash verification and hashing go through the shared PBKDF2 semaphore; the hash and `INVALID_<hex>` token are written in one transaction guarded by compare-and-swap on the old hash; the cookie is expired with Max-Age=0. Body cap 2 KiB.
- **Tenant info and list**: info resolves the caller's own tenant from the principal, unconfigured model ids are empty strings, an invite-only principal gets 404. The list reads only `user_tenant` rows whose `user_id` is the caller, status 1, tenant active, with tenant name, owner nickname and avatar, role (`invite` for pending), and joined time; no other user's email.
- `/v1/user/info` and login now read the stored language as a locale code (`English` reads `en`, `Chinese` reads `zh`, unknown reads `en`).

## Test-first record (failing before implementation)

Run after commit 2ae425c's stubs, against live MySQL and Valkey (infra started with `make infra-up`):

- Unit: `TestValidateAvatarDataURL` failed (25 failures: the parent and 24 subtests) against the stub validator.
- Service and router integration: 25 tests failed, among them `TestUpdateSetting*`, `TestChangePassword*` (wrong current, length, signs out, rate limit, Redis down), `TestLegacyLanguageLabelsReadBackAsCodes`, `TestAvatarIsStoredAndCanBeRemoved`, `TestTenantInfo*`, `TestMembershipList*`, `TestInviteRoleIsNotMembershipForTenantInfo`, `TestSettingUpdatesOnlyTheAllowedFieldsOfTheCaller`, `TestSettingValidationErrorsAre400WithoutInternals`, `TestSettingBodyCapIs400KB`, `TestAvatarRoundTripsThroughInfoAsPlainData`, `TestPasswordChangeFlowSignsEveryDeviceOut`, `TestPasswordChangeBodyCapAndMassAssignment`, `TestPasswordChangeIsRateLimitedPerUser`, `TestTenantInfoAndListReturnOnlyTheCallersOwnData`. A few guard tests (route auth, request-log secrecy) passed already because the stubs answer 501 behind the gate.
- The ingress e2e test was not run in its RED state (the app image of that moment had no routes registered; it was written against the same contract and passed after the rebuild).

After implementation all of the above pass.

## Live verification (observed)

Host MemAvailable was 4669 MiB at the gate (above 4096), 4110 MiB when the app was added. `make up` refused to start because its port preflight saw the ports of this project's own already-running infra containers; I started the same compose command (profiles cpu, elasticsearch, mail, `--build`, project `devrag-stack`) directly and ran `scripts/wait_stack.sh` (all services healthy). Host-run Go tests used `SERVICE_CONF` (git-ignored host conf), `E2E_BASE_URL=http://127.0.0.1:8088` and `MYSQL_ROOT_PASSWORD` read from `docker/.env` (never printed).

- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`: all packages ok (including `internal/e2e`, `internal/router`, `internal/service`, `internal/dao`).
- `uv run python run_tests.py -m "integration or e2e"`: 228 passed, 713 deselected, 106.95 s.
- Ingress e2e `TestProfilePasswordAndTenantsThroughIngress`: after the password change the old token is 401 on Go `/v1/user/info` and on Python `/api/v1/system/status`; the cookie is cleared; the old password login is 401; the new login works on both engines.
- Stack stopped with `docker compose -p devrag-stack ... stop` for profiles cpu, elasticsearch, mail (no `down`, no `-v`); `docker ps --filter name=devrag-stack -q | wc -l` is 0. The foreign `compose` project was not touched.

## Final checks (observed)

- `make ci`: 7/7 gates passed, ruff security selection passed.
- `uv run python run_tests.py -m unit`: 713 passed, 1 skipped, 228 deselected (after the registry test fix below).
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok.
- `GOTOOLCHAIN=local go vet ./...`: clean.
- `scripts/gen_routes.py --check`: exit 0 (no generated file changed; the registry rows only flip `implemented`).

## Deviations from Plan

1. [Rule 1 - Bug] `test_registry_has_phase2_endpoints_unimplemented` still listed `GET /v1/tenant/list` as unimplemented; the first unit run after flipping the rows failed. Moved that row out and added a test that the four rows read `implemented: true` (934ea87).
2. Registration now uses the shared nickname rule (no control, format or angle-bracket characters). The plan only named the settings route; the same stored field would otherwise bypass the rule (Rule 2).
3. Plan said the password handler takes an unspecified body; I used `old_password` and `new_password` because `docs/04-api/endpoint-catalog.md` fixes them. A wrong current password returns 400 rather than a 401-style "generic" error so the SPA does not purge the session (R-118).
4. `handler.NewSettings` takes only the service (the planned cookie lifetime argument is unused because the cookie is expired, not set).
5. The acceptance grep `grep -rn "http.Client\|gin\." internal/service/*.go | wc -l` prints 3, all false positives on the word "login." in comments of the pre-existing `account.go`; the real layering test (`internal/layering_test.go`) passes.
6. `tenant_info` includes `role` and `ocr_id` in addition to the documented model id fields; `GET /v1/tenant/list` uses field names `tenant_name`, `owner_nickname`, `owner_avatar`, `joined_time` (not in docs; R-118).
7. Commit trailer is `Co-Authored-By: Claude Sonnet 5.5` (the harness attribution rule for this session) rather than the Opus 5.5 trailer named in the plan prompt.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model; T-02-65 to T-02-70 are each covered by a test named above (avatar magic bytes and size, DTO leak check on every response, current-password and rate-limit tests, token rewrite and cookie expiry, mass-assignment and cross-user tests, body caps).

## Self-Check: PASSED

Commits 2ae425c, e92b3bb, 2c7d980 and 934ea87 exist; `internal/service/avatar.go`, `internal/service/user.go`, `internal/service/tenant.go`, `internal/handler/tenant.go`, `internal/router/user_integration_test.go`, `internal/e2e/user_e2e_test.go` exist.
