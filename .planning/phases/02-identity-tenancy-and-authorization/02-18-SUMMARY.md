---
phase: 02-identity-tenancy-and-authorization
plan: 18
subsystem: auth
tags: [react, forgot-password, otp, mailpit, vitest, i18n, accessibility]
requires: [02-16, 02-17]
provides:
  - /forgot-password public bare route with the three-step flow (email, code, new password)
  - usePasswordResetRequest (plain async calls, no mutation cache), useCountdown
  - ApiError.retryAfter and parseRetryAfter in the HTTP client
  - web/src/test/mail.ts (waitForMail, extractCode, noMailFor, deleteMailFor over the Mailpit API)
  - live reset test (written, NOT yet run)
affects: [02-21, 02-22]
tech-stack:
  added: []
  patterns:
    - "secrets (code, ticket, password) held in component state only; requests are plain async calls so no cache keeps them"
    - "countdown from a clock deadline, interval cleared on unmount"
key-files:
  created:
    - web/src/pages/forgot-password/{index,email-step,code-step,password-step,step-parts,reset-error,schemas}.ts(x)
    - web/src/pages/forgot-password/{forgot-password.test.tsx,schemas.test.ts,forgot-password.live.test.ts}
    - web/src/hooks/{use-countdown,use-password-reset-request}.ts
    - web/src/test/mail.ts
  modified:
    - web/src/services/{http,auth-service,http.test}.ts
    - web/src/constants/{api-paths,routes}.ts
    - web/src/{routes.test,layouts/layouts.test}.tsx
    - web/src/locales/{en,zh}.json
    - .planning/DECISIONS.md
key-decisions:
  - "R-122: reset requests are plain async calls not TanStack mutations; ticket in page state; Retry-After clamped 1..600; five wrong codes or a refused ticket return to step 1 with the email kept"
requirements-completed: []
duration: two sessions (first cut off at handover)
completed: 2026-10-08
---

# Phase 2 Plan 18: Forgot-password page Summary

A public three-step password reset page (email, six-digit code, new password) with a 60 second resend countdown that honours `Retry-After`, no account enumeration, secrets only in component memory, and a live Mailpit test that is written but not yet run.

## Commits

| Commit | What |
|---|---|
| 287f69c | Task 1: failing schema and page tests, Mailpit helper |
| 2bd0920 | Task 2: page, hooks, Retry-After in the client, en/zh keys, R-122 |
| 29811ab | Task 3: live reset test (not run) |

## Review of the previous session's commits

Both commits were reviewed against the plan, 02-UI-SPEC and the hard constraints and needed no fixes: no confirm-password field; identical copy and navigation for every 2xx; 429 and 503 use generic copy; requests are anonymous and silent; code, ticket and password never reach URL, storage, caches or console (test covers it); reload returns to step 1; code input has `one-time-code`, `numeric`, paste handling and a double-submit guard; five wrong attempts return to step 1 with the email kept; the timer is cleaned up on unmount; locale parity green. Pre-existing tests were only changed where behaviour changed (`/forgot-password` formerly rendered Not Found; the route registry list), and the old assertion was split, not weakened. `git diff d459043 -- web/package.json` is empty: no package added. The "Forgot password?" link on the login page already existed from an earlier plan (`sign-in-form.tsx`), so `login/index.tsx` was not modified.

## Verification

- `cd web && npm run test -- --run`: 27 files, 475 tests passed (the stack traces in the output are intentional error-boundary tests).
- `cd web && npm run build`: succeeded (chunk-size warning only). `npm run typecheck`: clean.
- `make ci`: exit 0, 7/7 gates passed. `uv run python run_tests.py -m unit`: 743 passed, 1 skipped.

## Live suites: NOT RUN

Available memory was 4009 MB, below the 4096 MB preflight, so the stack was not started and no threshold was lowered. `web/src/pages/forgot-password/forgot-password.live.test.ts` was written carefully but has never run against the stack. It needs the `mail` profile and `MAILPIT_URL` (default `http://127.0.0.1:8025`). The next plan's live regression must run `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`, plus `uv run python run_tests.py -m "integration or e2e"` and `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`. Unverified assumptions in the live test: `GET /v1/user/info` returns 401 for the revoked token, and the reset mails arrive within the 30 s wait. No live env change was made. `go` and Python suites were not touched by this plan. No stack was started, so 0 containers are running.

## Deviations from Plan

- Task 3 live run skipped for memory (above). The `login/index.tsx` edit was unnecessary (link pre-existing).
- None of the hard constraints conflicted with 02-UI-SPEC.

## Known Stubs

None.

## Self-Check: PASSED
