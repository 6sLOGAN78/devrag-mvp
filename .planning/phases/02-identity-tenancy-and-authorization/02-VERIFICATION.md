---
phase: 02-identity-tenancy-and-authorization
verified: 2026-10-08
status: human_needed
score: 5/5 success criteria verified; 45/48 requirements satisfied (3 honestly partial, 0 gaps)
overrides_applied: 0
gaps: []
human_verification:
  - test: "Real SMTP delivery of the password-reset OTP (AUTH-16, B-20)"
    expected: "With real SMTP settings in docker/.env, requesting a reset for your own address delivers the email with a working code"
    why_human: "Only the local Mailpit catcher exists here; no real provider account"
  - test: "Read the Chinese interface (login, profile, API tokens, team, forgot password) in web/src/locales/zh.json (UI-42, B-18, B-20)"
    expected: "Text reads correctly; corrections go into zh.json"
    why_human: "Strings were written by the agent; nobody has reviewed them as a Chinese reader"
  - test: "Visual and accessibility pass of the SPA in light and dark theme (UI-43, UI-SPEC)"
    expected: "Layout, contrast, focus ring, skip link and dialogs match 02-UI-SPEC.md"
    why_human: "Only the register-to-home flow, sign-out, guard redirect and status page run in a real Chrome; the profile, token, team and reset pages are exercised by jsdom against the live stack, not rendered by a browser"
---

# Phase 2: Identity, Tenancy and Authorization Verification Report

**Phase goal:** Users can create an account and securely access their own workspace through either server, and no user can see or change another tenant's data.
**Verified:** 2026-10-08
**Status:** human_needed. Every success criterion is backed by code and by a test that exercises it against the live stack. The remaining items need a person (real SMTP, Chinese text, visual review).
**Re-verification:** No, initial verification.

Method note: the SUMMARY claims were not taken as evidence. Each criterion was traced from `conf/routes.yaml` through the Go and Python gates, services and DAOs, and the SPA route, page, hook and service, then matched to a test file that was read. The Docker stack was not started. Live results (two gate runs of 3 clean-room runs each on 2026-10-08) are cited only where the test files cover the behaviour.

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Register in the SPA, atomic tenant plus owner link, log in, land on home; a refresh keeps the session; a protected route while signed out redirects to login | VERIFIED | `dao.CreateAccount` (`internal/dao/user.go`) inserts user, tenant, owner membership and any `tenant_llm` rows in one transaction. `TestRegisterRollsBackWhenThirdInsertFails` (`internal/service/account_integration_test.go`) forces a real third-insert failure and checks nothing remains. `test/testcases/test_registration_flow.py` checks the three rows and their ids against MySQL. `test_register_land_on_home_reload_and_guard_in_real_browser` (`test/testcases/test_spa_browser.py`) runs real Chrome: register, `/home`, reload, storage cleared, redirect to `/login?next=%2Fhome`. SPA wiring: `web/src/constants/routes.ts`, `web/src/components/require-auth.tsx` (`SessionRecovery` refetches `/v1/user/info`). `web/src/test/live/auth.live.test.ts` covers the same flow through the ingress. |
| 2 | A Go-issued token is accepted by a protected Python route; after logout it is 401 on both servers; every non-public route on both servers is 401 without credentials, checked by enumerating the route tables | VERIFIED | `test_go_token_is_accepted_by_python_and_logout_kills_it_on_both` (`test/testcases/test_auth_flow.py`). Go gate: `handler.AuthGate` (`internal/handler/auth.go`) is installed before routing, so `NoRoute` is also 401. Python gate: `register_auth_gate` (`api/apps/auth.py`), a `before_request` hook. Policy comes from the generated `PolicyFor` / `policy_for`; an unmatched path defaults to jwt. Enumeration: `TestEveryEngineRouteIsDeclaredAndGated` and `TestEveryGoFamilyIsDeniedUnlessPublic` (`internal/router/router_test.go`) walk `e.Routes()` and the family table. `test/testcases/test_route_enumeration.py` walks `app.url_map.iter_rules()` and every family probe. Both include a negative check that an undeclared route is detected and still denied. `cmd/ragflow_server.go` wires every router option, and `api/apps/__init__.py` always installs the gate. |
| 3 | Change a password, reset with an OTP, create, list and delete API tokens in settings; an API-token-only request resolves to the owning tenant | VERIFIED | Password change: `service.User.ChangePassword` (atomic attempt counter, hash swap and token rewrite in one transaction). `profile.live.test.ts` covers the wrong current password, then success, then old token dead and new password works. Reset: `internal/service/password_reset.go`, `otp.go`. `test/testcases/test_password_reset.py` and `forgot-password.live.test.ts` use the real emailed code from Mailpit. Tokens: `internal/handler/token.go`, `internal/dao/api_token.go`, `api-tokens.live.test.ts`, `test_api_token_flow.py`. Tenant resolution: `Auth.tokenPrincipal` sets `TenantID = row.TenantID`. Tests: `TestAPITokenResolvesToOwningTenantOnApiRoutesOnly` (`internal/service/token_integration_test.go`), `TestAPITokenAuthenticatesApiRoutesAsTheOwningTenant`, and `test_api_token_resolves_to_its_own_tenant` (`test/unit_test/test_auth_gate.py`). |
| 4 | Owner invites, member accepts, owner changes the role; actions outside the matrix return 403 | VERIFIED | `internal/service/tenant_roles.go` and `tenant_members.go`. Enforcement goes through the generated `common.Allowed(role, "team_admin", "manage_members")`. `conf/permissions.yaml` matches the table in `docs/16-auth/permissions.md`. The tests are `test_tenant_membership_full_cycle` (`test/testcases/test_tenant_membership.py`), `internal/e2e/tenant_invite_e2e_test.go`, `tenant_roles_e2e_test.go` and `team.live.test.ts`. Members without the role get 403 in `test_cross_tenant_matrix_members_without_the_role_are_refused`. API and beta credentials are refused on the team routes. |
| 5 | Another tenant's resource by id is indistinguishable from not-found on every existing tenant-owned route, via a matrix generated from the route table | VERIFIED | `test/testcases/test_cross_tenant_matrix.py` and `_matrix_fixtures.py` load the registry rows with `scope: tenant` and `implemented: true` (8 rows: 3 token routes, 5 membership routes). A row with no fixture fails (`coverage_problems`, with a proof against a synthetic registry). Callers tried are a stranger, a pending invitee, another tenant's API token, and an admin and a normal member of the target tenant; ids are also supplied in other positions. The Go side has `TestCrossTenantRegistryCoverage` (`internal/e2e/cross_tenant_matrix_e2e_test.go`). Every DAO query on these routes filters by `tenant_id`. |

## Requirement coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| AUTH-01, 02, 03, 05, 07, 08, 09, 11, 13, 14, 15, 17, 18, 19, 20, 21, 22 | SATISFIED | Registration and login: `internal/service/account.go`, `internal/common/password.go` (PBKDF2-SHA256, 600000 rounds, checked in the live test). Token validation: `internal/common/token.go` (`ValidInner` rejects blank, shorter than the minimum, and `INVALID_`). Logout: `Auth.Logout`. Profile and password: `service/user.go`. Reset: `service/password_reset.go`. API tokens: `service/token.go`. Tests are those listed under criteria 1 to 3. |
| AUTH-04, 06 | SATISFIED as decided (D-22) | Default model ids come from optional config. `tenant_llm` rows are written only when a provider is configured (`TestRegister...` for the configured case, `rows["tenant_llm"] == []` live). Annotated honestly in REQUIREMENTS.md. |
| AUTH-10 | SATISFIED as decided (D-21) | HttpOnly `ragflow_auth` cookie fallback on jwt routes with an Origin check (`auth.go`, `api/apps/auth.py`). It replaces the documented Redis `_user_id` session. `test_python_cookie_only_unsafe_request_needs_a_matching_origin`. |
| AUTH-12 | SATISFIED as decided (R-117) | Per-route credential policy: `acceptedTypes` in `auth.go` and `ACCEPTED_TYPES` in `api/apps/auth.py`. |
| AUTH-16 | SATISFIED (local mail catcher) | Real SMTP delivery is manual (B-20). |
| AUTH-23 | SATISFIED WITH BLOCKER (B-19) | `ResolvePrincipal` handles the beta value. It is proven on test-registered routes and live under `/api/v1/searchbots/` (`internal/e2e/token_e2e_test.go`, `internal/handler/auth_api_beta_test.go`). The real bot, search-bot and MCP handlers do not exist until Phase 8; the tick is annotated. |
| TEN-02, 04, 06, 07, 08, 09, 10, 11 | SATISFIED | See criteria 4 and 5. `dao/user_tenant.go`, `handler/tenant.go`, `conf/routes.yaml`. |
| TEN-01 | PARTIAL, honestly unticked (B-22) | Filtering is enforced and matrix-tested for the 8 tenant-owned routes that exist. Datasets, documents, tasks, dialogs, canvases and files arrive with their routes. The matrix guard fails a new tenant-scoped row that has no fixture. |
| TEN-05 | PARTIAL, honestly unticked (B-22) | The 10-area table is generated into Go and Python under a drift gate and oracle-tested. It matches `docs/16-auth/permissions.md`. Enforced today only for `team_admin`. |
| UI-02, 04, 06, 07, 09, 34, 35, 36, 43 | SATISFIED | SPA routes in `web/src/constants/routes.ts`. Pages are under `web/src/pages/{login,home,user-setting/*,forgot-password}`. Services and hooks are real; the home dashboard shows real counts from the token and member lists. |
| UI-08 | SATISFIED (tiers established) | The user store, server-state hooks, URL params and form state are present; the agent, chat and document stores come with their features. |
| UI-42 | PARTIAL, honestly unticked (B-18, B-20) | en and zh with a key-parity test. es, fr and ja deferred. The zh copy is unreviewed. |
| SEC-01 | SATISFIED | Default-deny gates on both servers plus route enumeration tests. |
| SEC-09 | SATISFIED | HMAC-signed itsdangerous-compatible token with a 30-day max age (`VerifyAccessToken`) and shared test vectors (`test/fixtures/access_token_vectors.json`). |
| E2E-01, E2E-02 | SATISFIED | `test_registration_flow.py`, `test_auth_flow.py`; no mocks. Model id fields are present and empty until configured (annotated). |

No orphaned requirements: REQUIREMENTS.md maps the same 48 ids to Phase 2 as the ROADMAP lists, and every id is covered above.

## Offline checks run by the verifier (Docker not started)

| Command | Result |
|---------|--------|
| `make ci` | exit 0, "7/7 gates passed", ruff "All checks passed!" |
| `uv run python run_tests.py -m unit` | exit 0, 833 passed, 1 skipped, 313 deselected in 17.99s |
| `GOTOOLCHAIN=local go test -count=1 ./cmd/... ./internal/...` | exit 0, every package `ok` |
| `GOTOOLCHAIN=local go vet ./...` | exit 0, no output |
| `cd web && npm run test -- --run` | exit 0, 32 files and 621 tests passed |
| `cd web && npm run build` | exit 0, built in 8.36s; only the Vite chunk-size advisory (index chunk 592.70 kB) |
| `uv run python scripts/gen_routes.py --check` | exit 0 (generated files are in sync) |

`git status` was clean after the runs. The live evidence (Python unit 833, integration 97, e2e 212 plus 4 serial, Go tiers PASS, vitest live 36) is the recorded 02-26 gate on the final code. The unit count matches the 833 recorded there. The Go scratch-database tests skip without `MYSQL_ROOT_PASSWORD` (`internal/testutil/scratch.go`), so offline Go results do not exercise them. The gate exports it (R-128, with a guard test).

## Anti-pattern scan

- Debt markers (TBD, FIXME, XXX, TODO, HACK) and "not implemented" in `internal/`, `cmd/`, `api/`, `common/` and `web/src`: none in phase code. Hits are only in the CI checker scripts and its tests, in `coming soon` negative assertions, and in a benign `contextlib.suppress(NotImplementedError)` for signal handlers (`api/ragflow_server.py:117`).
- Skipped or xfailed tests in phase code: none. Existing skips are all outside Phase 2: numpy gadget test (B-13), docker daemon and foreign-project checks in `test_preflight.py`, a docs-absent guard in `test_env_catalog.py`, and the `MYSQL_ROOT_PASSWORD` scratch skip in Go described above. The gate recorded no Phase 2 test skipped.
- Stub handlers: none. All 29 implemented rows have real handlers. The two `implemented: false` rows (`POST /api/v1/searchbots/ask` and `/retrieval_test`) are gated by the beta family policy and are deliberate Phase 8 items.
- Generated files: `gen_routes.py --check` is clean.
- Largest Go source file is 353 lines (`internal/dao/verify.go`); no giant files.

## Review fixes confirmed in code

- CR-01 (collation-equal emails bypass limits): fixed in 73dfd6f. `common.CanonicalEmail` (`internal/common/email.go`) and the Python `canonical_email` (`common/security/emails.py`) share `test/fixtures/email_canonical_vectors.json`. `Account.Login` keys the failure counter on the resolved account (`accountSubject`). New accounts are limited to printable ASCII.
- WR-01 (check-then-act counter): `Login` and `ChangePassword` call `limiter.Hit` before the password check and `Reset` on success.
- WR-03 to WR-07 (Nginx error log, body caps, JSON-only and Origin guard, page overflow, auth executor): commits exist (b08cbb6, 521bde3, 811da11, 60a22e6, 9207a20). The Go `BodyLimitMiddleware`, `WriteGuard` and the dedicated `AUTH_LOOKUP_EXECUTOR` are in the router and gate code read above.
- WR-F01 to WR-F06: token storage never throws, with an in-memory fallback (`web/src/utils/authorization.ts`), and sign-out intent (`web/src/utils/sign-out-intent.ts`) were read. The others are recorded fixed with commits.
- Deferred items are in BLOCKERS: WR-02 and IN-03, 04, 06, 09 in B-17 and B-29; IN-F01, F02, F10, F13 in B-30; WR-07 residual in B-28.

## Gaps

None. Nothing found breaks the phase goal or a requirement ticked as complete.

Observations that are not gaps:
- AUTH-23 is ticked "complete with blocker". The middleware is real and tested, but no real consumer route exists. This is annotated honestly; Phase 8 must add a live check on each real route (B-19).
- The only real-browser tests cover register, home, reload, guard, sign-out and the status page. The profile, password, token, team and reset pages are exercised by jsdom against the live stack, not by a browser. That is the human visual item above.
- A password change signs out every device, including the current one. The SPA handles this by returning to `/login`, covered by `profile.live.test.ts`.

## Known accepted limitations

- B-17 (decided under R-135, implementation pending): per-IP rate limits are effectively shared behind Docker's port proxy until a trusted proxy range is configured, so in the shipped compose a registration limit of 10/hour per IP is global. The per-email lock stays and a reset is the way out. This is a production deployment item.
- B-18: es, fr and ja are not shipped; the language switch offers en and zh.
- B-19: the beta token is proven on test-registered routes only (Phase 8 real routes).
- B-21: API tokens are stored in plaintext (the documented table); BILL-01 in Phase 8 replaces this with hash plus prefix.
- B-22: TEN-01 and TEN-05 cover only the routes that exist; each later route must add its matrix fixture and enforce its area.
- Also open and recorded: B-20 (manual checks), B-23 (405 logs the raw path), B-26 (`npm audit` 8 findings), B-28, B-29 and B-30 (info).

---
_Verified: 2026-10-08_
_Verifier: Claude (gsd-verifier)_
