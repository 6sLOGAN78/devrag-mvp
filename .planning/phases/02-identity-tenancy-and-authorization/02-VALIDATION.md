---
phase: 2
slug: identity-tenancy-and-authorization
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-07
validated: 2026-10-08
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` § Validation Architecture. Status of every row below is taken from the plan 02-26 exit gate (`scripts/clean_room.sh --runs 3`, 2026-10-08): three consecutive green runs from a clean rebuild, evidence in `02-26-SUMMARY.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python: pytest + pytest-asyncio via `run_tests.py`. Go: stdlib `testing` + `httptest`, build tags `integration`, `e2e`. Frontend: vitest `unit` and `live` projects |
| **Config file** | `pyproject.toml`, `web/vitest.config.ts`, `Makefile` (all exist from Phase 1) |
| **Quick run command** | `uv run python run_tests.py -m unit && GOTOOLCHAIN=local go test -race -count=1 ./internal/... ./cmd/... && (cd web && npm run test -- --run)` |
| **Full suite command** | `scripts/wait_stack.sh && uv run python run_tests.py -m "integration or e2e" && GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./... && (cd web && npm run test:live)` |
| **Measured runtime** | quick: about 46 s on 2026-10-08 (Python unit 17.5 s, Go race 13.9 s, vitest unit 14.4 s; caches warm). Gate: 358 to 386 s per run including the image rebuild and the 35 to 44 s time-to-healthy |

---

## Sampling Rate

- **After every task commit:** quick run command (no stack needed)
- **After every plan wave:** bring the stack up once, run the full suite command
- **Before `/gsd:verify-work`:** `scripts/clean_room.sh --runs 3` green (needs about 4 GB available RAM, B-14; web port 8088 on this host, R-87). Done for Phase 2 on 2026-10-08 (plan 02-26)
- **Max feedback latency:** 60 seconds for the quick tier (measured about 46 s)

Readiness rule: `scripts/wait_stack.sh` and the per-language `wait_until` helper. Mail and OTP reads poll the mail-catcher with `wait_until`. No fixed sleeps; expiry is tested with a short configured TTL, never by waiting.

---

## Per-Task Verification Map

Each row is attached to the plan and task that delivers and verifies it. Green means the tier named in the command ran in all three gate runs and passed (counts per run: Python unit 792 passed and 1 skipped, integration 95, e2e 181 plus 4 serial, Go race, Go integration and e2e, manual and cgo tiers all ok, vitest unit 30 files and 581 tests, vitest live 8 files and 36 tests).

| Ref | Requirement | Plan and task | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|-------------|---------------|------------|-----------------|-----------|-------------------|-------------|--------|
| CR-02 | (Phase 1 carry-over) | 02-01 task 2 (Go mirror: task 3) | T-2-dos | redaction is linear: 100 KB input completes within a fixed bound | unit | `uv run python run_tests.py -m unit -t log_redaction` | ✅ | ✅ green |
| SC-1 | AUTH-01..06, E2E-01, E2E-02 | 02-09 task 3, 02-13 task 3 | T-2-enum | registration is atomic and rolls back; generic login error | integration + e2e | Go `-tags=integration` register tests; `run_tests.py -m e2e -t registration` | ✅ | ✅ green |
| SC-1 | UI-02, UI-06, UI-07, UI-09 | 02-12, 02-28, 02-13 | T-2-guard | protected route redirects when signed out | unit + live | `(cd web && npm run test -- --run && npm run test:live)` | ✅ | ✅ green |
| SC-2 | AUTH-07, AUTH-08, AUTH-12, SEC-09 | 02-06 | T-2-token | expired, future, tampered, wrong-secret, short, empty and `INVALID_` tokens rejected on both stacks | unit | shared vectors `test/fixtures/access_token_vectors.json` in Go and Python | ✅ | ✅ green |
| SC-2 | AUTH-09, SEC-01 | 02-10 task 3, 02-14 task 3 | T-2-authz | logout returns 401 on both servers; every non-public route returns 401 unauthenticated | e2e + unit | route enumeration on `engine.Routes()` and `app.url_map`; `run_tests.py -m e2e -t auth_flow` | ✅ | ✅ green |
| SC-2 | AUTH-10, AUTH-11 | 02-10, 02-14 | T-2-csrf | cookie is HttpOnly, SameSite=Lax; cookie-only POST without matching Origin is refused | unit + e2e | cookie attribute and CSRF tests on both stacks | ✅ | ✅ green |
| SC-3 | AUTH-13..15 | 02-15, 02-25 task 2, 02-16 task 3 | T-2-leak | no password or hash in any response | unit | Go handler/service tests, DTO leak test, response leak sweep | ✅ | ✅ green |
| SC-3 | AUTH-16..18 | 02-17 task 3, 02-18 task 3 (helpers: 02-05 task 3) | T-2-otp | OTP single use, 5 attempts, 10 min, same response for unknown email | e2e | `run_tests.py -m e2e -t password_reset` (reads the mail-catcher; the gate stack runs the `mail` profile) | ✅ | ✅ green |
| SC-3 | AUTH-19..22 | 02-20, 02-21 task 3 (live) | T-2-token | API token resolves only to its own tenant; other tenant's token delete is 404 | integration + e2e | token CRUD tests, `run_tests.py -m e2e -t api_token_flow` | ✅ | ✅ green |
| — | AUTH-23 | 02-14 (Python test blueprint), 02-20 task 3 (Go test-registered route) | T-2-beta | beta token accepted only on its restricted set | unit | Go `httptest` with a test-registered route; Python test blueprint | ✅ | ✅ green (test-registered route only, B-19) |
| SC-4 | TEN-04..11 | 02-22, 02-23, 02-24 task 3 (live) | T-2-authz | owner-only invite and role change; owner cannot be demoted or removed | integration + e2e | membership state-machine tests, `run_tests.py -m e2e -t tenant_membership` | ✅ | ✅ green |
| SC-5 | TEN-01, TEN-02 | 02-25 task 1 | T-2-idor | another tenant's resource is indistinguishable from not-found | e2e | generated cross-tenant matrix from the endpoint registry | ✅ | ✅ green (routes that exist, B-22) |
| — | UI-04, UI-08, UI-34..36 | 02-13, 02-16, 02-21, 02-24 | T-2-xss | no raw HTML rendering of user-supplied profile fields | unit + live | vitest | ✅ | ✅ green |
| — | UI-42, UI-43 | 02-11 (parity en, zh), 02-27, 02-16 task 2 (theme and language persistence) | — | N/A | unit | locale key-parity test (en, zh); theme persistence test | ✅ | ✅ green (en, zh only; Chinese text review open, B-18, B-20) |

### Task mapping (plans 02-01 to 02-28)

| Ref | Plan and task that delivers and verifies it |
|-----|---------------------------------------------|
| CR-02 | 02-01 task 1 (failing vectors and timing) and task 2 (linear redactor); Go mirror 02-01 task 3 |
| SC-1 registration, login, atomic tenant link | 02-09 task 1 (tests), task 2 (services), task 3 (live through Nginx, `-t registration`) |
| SC-1 guard, recovery, login UI, home | 02-12 tasks 1-3, 02-28, 02-13 tasks 1-3 (live `npm run test:live`) |
| SC-2 token contract vectors | 02-06 tasks 1-3 |
| SC-2 logout 401 on both, every non-public route 401 | 02-10 tasks 1-3 (Go enumeration), 02-14 tasks 1-3 (Python enumeration, `-t auth_flow`) |
| SC-2 cookie CSRF | 02-10 task 1-2 (Go), 02-14 task 1-2 (Python) |
| SC-3 profile, password change, no leaks | 02-15 tasks 1-3, 02-16 task 3, 02-25 task 2 (leak sweep) |
| SC-3 password reset with the mail catcher | 02-05 task 3 (helpers), 02-17 tasks 1-3 (`-t password_reset`), 02-18 task 3 (live) |
| SC-3 API tokens and API-token-only resolution | 02-20 tasks 1-3 (`-t api_token_flow`), 02-21 task 3 (live) |
| AUTH-23 beta | 02-14 task 1-2 (Python test blueprint), 02-20 task 3 (Go test-registered route) |
| SC-4 invites and roles | 02-22 tasks 1-3, 02-23 tasks 1-3 (`-t tenant_membership`), 02-24 task 3 (live) |
| SC-5 cross-tenant matrix | 02-25 task 1 and task 3 (`-t cross_tenant`) |
| UI-04, UI-08, UI-34..36 XSS and rendering | 02-12, 02-13, 02-16, 02-18, 02-21, 02-24 unit tests (no raw HTML) |
| UI-42, UI-43 | 02-11 task 1 (key parity en and zh), 02-27, 02-16 task 2 (theme and language persistence) |
| Wave 0 fixtures | vectors 02-06; route registry 02-08; account fixtures 02-07; mail catcher 02-05; vitest harnesses 02-11, 02-12 |
| Exit | 02-26 task 2 (`scripts/clean_room.sh --runs 3`, three green runs on 2026-10-08) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `test/fixtures/access_token_vectors.json` and `test/fixtures/password_vectors.json`, loaded by Go and Python tests (plan 02-06)
- [x] `test/fixtures/go_issued_token.json`, produced by a Go test and verified by Python (plan 02-06)
- [x] Per-endpoint registry in `conf/routes.yaml` and the generator extension, with a test that it agrees with the route-family entries (plan 02-08)
- [x] Two-user and two-tenant fixtures that register through the real endpoint (`test/helpers/`, `internal/testutil/`; plans 02-07, 02-09)
- [x] Mail-catcher service in the dev compose stack and a helper that reads it with `wait_until` (plan 02-05; the gate stack runs the `mail` profile since plan 02-26)
- [x] vitest additions: auth-guard harness, locale parity test (plans 02-11, 02-12)

---

## Manual-Only Verifications

These stay open. Automated rows above do not replace them (BLOCKERS B-20 and B-19).

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Reset email delivered through a real SMTP server | AUTH-16 | Only the local mail-catcher is available here; no production SMTP account | Set the SMTP variables in `docker/.env` to a real server, request a reset for your own address, confirm the email arrives |
| Chinese interface text reads correctly | UI-42 | Translation quality needs a reader of the language | Switch the interface to Chinese and read through login, settings and team pages |
| Beta token on real bot, search-bot and MCP routes | AUTH-23 | Those routes are built in Phase 8; Phase 2 proves the middleware on a test-registered route | Re-check in Phase 8 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** automated rows green in the plan 02-26 gate on 2026-10-08; the three Manual-Only rows, UI-42 es/fr/ja (B-18), TEN-01/TEN-05 for routes that do not exist yet (B-22) remain open and are not covered by this approval.
