---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 10
subsystem: frontend
tags: [vite, react18, tailwind3, axios, sonner, zustand, vitest]
requires:
  - phase: 01-02
    provides: approved npm package set
  - phase: 01-05
    provides: web/src/constants/api-routes.generated.json
provides:
  - SPA scaffold (Vite 7, React 18.3.1, Tailwind 3.4.19) with UI-SPEC tokens and hand-written shadcn components.json
  - Axios client with bearer injection, envelope unwrap, ApiError, deduped toasts, 401 purge
  - vitest unit and live projects and the single frontend wait helper
affects: [01-12, 01-13, 01-15]
tech-stack:
  added: [react 18.3.1, vite 7.3.6, vitest 5.0.3, jsdom 30.1.2, react-router 7.18.4, "@tanstack/react-query 5.104.1", axios 1.20.0, zustand 4.5.7, sonner 1.7.4, tailwindcss 3.4.19, lucide-react 1.52.0]
  patterns: [single token util, ApiError with envelope data, waitUntil sole polling site]
key-files:
  created: [web/package.json, web/package-lock.json, web/vite.config.ts, web/vitest.config.ts, web/tailwind.config.ts, web/src/services/http.ts, web/src/services/notify.ts, web/src/utils/authorization.ts, web/src/stores/user-store.ts, web/src/test/wait-until.ts, web/src/services/http.live.test.ts]
  modified: [.planning/DECISIONS.md]
key-decisions:
  - "Token storage key is `Authorization` (docs do not name it; matches the reference); only utils/authorization.ts touches it"
  - "A 2xx body that is not a {code,data} envelope is returned as is (health routes may not use the envelope)"
  - "Envelope code 401 with HTTP 200 is treated like HTTP 401"
requirements-completed: [UI-03, TEST-10]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 10: SPA scaffold and HTTP client Summary

Vite + React 18 + Tailwind 3 scaffold and an envelope-unwrapping Axios client (bearer injection, ApiError, deduped sonner toasts, 401 purge of token, store and query cache), with vitest `unit` and `live` projects.

## Commits
- 649904d: scaffold, lockfile, tokens, components.json
- 5f7e8a1: envelope types, authorization util, user store, notify, http client, 16 tests (vitest config and setup included here because the tests need them)
- c36f007: waitUntil helper and live test

## Verification (observed)
- `npm run typecheck`: exit 0
- `npm run test -- --run`: 19 passed in 3 files (unit project)
- `npx vitest list --project live`: lists the 4 tests of `src/services/http.live.test.ts`
- `make ci`: 6/6 gates PASS (including placeholders scanning web/src and no_sleep) and ruff clean
- localStorage grep gate: no output outside the util, theme and tests
- Disk free on `/` before `npm install`: 23767M; after all work: 23191M
- Installed versions: react 18.3.1, tailwindcss 3.4.19, vite 7.3.6, vitest 5.0.3 (first choice resolved), lucide-react 1.52.0; all others as planned.

## Not run
- The `live` project (`npm run test:live`) is authored and collected only. It needs the stack from plan 01-13 and has NOT been run. Not counted as passing.
- `npm run build` not run (no `src/main.tsx` until plan 01-12; plan states this).

## Deviations from Plan
1. vitest.config.ts and src/test/setup.ts were committed with Task 2 rather than Task 3, since the Task 2 tests cannot run without them.
2. Radix primitives were not installed; the plan defers them to later shadcn adds, and the approved list does not name them.
3. UI-SPEC checker flag 3 applied (401 copy). Flags 1, 2, 4, 5 concern later components and were not applicable to this plan.

## Known issues
- `npm audit` reports high-severity `braces` via tailwindcss 3.4.19 (chokidar, micromatch), no fix available; dev-time only, `audit fix --force` not run.
- Spec says top-center toasts below 768px; relies on sonner's built-in mobile layout, not explicitly configured.

## Known Stubs
None.

## Self-Check: PASSED
