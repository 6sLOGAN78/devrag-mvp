---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 18
subsystem: frontend-http-client
tags: [axios, auth, 401, same-origin, gap-closure, security]
provides:
  - Bearer token attached only to same-origin or relative request URLs (isSameOrigin)
  - 401 purge only when the failing request carried a token still equal to the current token (sentToken)
key-files:
  modified: [web/src/services/http.ts, web/src/services/http.test.ts]
requirements-completed: [UI-03, TEST-10]
metrics:
  tasks: 2
  completed: 2026-10-06
---

# Phase 1 Plan 18: Frontend HTTP client token handling Summary

The shared axios client no longer leaks the bearer token to other origins and no longer wipes sessions on tokenless or stale 401s (closes WR-21, WR-22).

## Tasks

| Task | Commit |
|------|--------|
| 1. Failing tests for origin restriction and token-aware purge | df39a93 |
| 2. isSameOrigin gate, sentToken recorded on config, shouldPurge guard | ceb0324 |

## RED evidence (observed against pre-fix code)

7 failed, 17 passed in `src/services/http.test.ts`:
- never attaches the token to another origin
- never attaches the token to a protocol-relative URL
- keeps state and shows the server message on a tokenless 401 (HTTP 401)
- keeps state and shows the server message on a tokenless 401 (envelope 401 with HTTP 200)
- does not purge a newer login on a late 401 (HTTP 401)
- does not purge a newer login on a late 401 (envelope 401 with HTTP 200)
- shows no toast for a silent tokenless 401

Relative, same-origin absolute and purge-when-current cases passed before and after, as intended.

## After the fix (as observed)

- `npm run typecheck`: clean.
- `npm run test -- --run`: 6 files, 59 tests passed.
- `npm run build:check`: built, chunk check printed its entry/lazy chunk list.
- `make ci`: 7/7 gates passed, ruff clean.
- The `live` vitest project was not run (needs the app stack); plan 01-24's exit gate runs it.

## Deviations from Plan

None. No existing test needed changing: the existing 401 purge test already stored a token first. No new npm packages; `web/package-lock.json` unchanged. No Docker or dev server started.

## Self-Check: PASSED
