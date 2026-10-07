---
phase: 02-identity-tenancy-and-authorization
plan: 28
subsystem: frontend
tags: [shell, user-menu, sign-out, nav-groups, routing, a11y, i18n]
requires: [02-12, 02-27]
provides:
  - System status at /system-status behind the guard; / is a public entry redirect (signed in to /system-status, signed out to /login)
  - UserMenu (avatar initials or data-URL avatar, nickname and email as text, Sign out) in the reserved header slot
  - Captioned, labelled nav groups (platform, account) in AppSidebar
affects: [02-13, 02-16]
key-files:
  created:
    - web/src/components/user-menu.tsx
    - web/src/components/user-menu.test.tsx
    - web/src/components/avatar-initials.tsx
    - web/src/components/root-redirect.tsx
    - web/src/utils/sign-out-intent.ts
  modified:
    - web/src/constants/routes.ts
    - web/src/routes.tsx
    - web/src/routes.test.tsx
    - web/src/components/app-sidebar.tsx
    - web/src/components/require-auth.tsx
    - web/src/layouts/standard-layout.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/pages/not-found/index.tsx
    - web/src/pages/pages-i18n.test.tsx
    - web/src/services/http.ts
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - test/testcases/test_spa_browser.py
decisions:
  - "/ is a registry entry with a `redirect` function (layout bare, auth none), resolved from the stored token only. Transitional: plan 02-13 registers /home and switches ROOT_SIGNED_IN_TARGET."
  - "Signed-out / goes to a bare /login (no next); a guarded path such as /system-status still goes to /login?next=<path>."
  - "Locale keys follow 02-UI-SPEC (header.accountMenu, header.signOut, nav.groupPlatform, nav.groupAccount) rather than the plan's `userMenu.label`; the spec is the design contract and later plans use these keys. nav.groupCaption was removed."
  - "Deliberate sign out uses a tiny in-memory intent (utils/sign-out-intent.ts) plus purgeSession({ toast: false, navigate: false }) so neither the guard nor the session navigator adds a `next` parameter. flushSync navigation was rejected (needs react-router/dom, which duplicates the router context under vitest)."
  - "The Profile item is not rendered until plan 02-16 registers its route. Group Account therefore renders nothing yet (only groups with entries render)."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 28: Signed-in shell (account menu, sign out, nav groups, /system-status)

Signed-in users now have an account menu in the header with a working sign out, System status lives at `/system-status`, and `/` is the entry redirect.

## Commits
- 9539091 test(02-28): failing tests for the /system-status move and the root redirect
- 5a35e08 feat(02-28): move System status to /system-status and make / an entry redirect
- 65ee613 test(02-28): failing tests for the account menu, avatar fallback, sign out and nav groups
- 1edbfff feat(02-28): account menu with sign out, avatar fallback and captioned nav groups
- 9874820 test(02-28): seed the query cache before sign out so the purge is observable
- da2533f test(02-28): browser coverage follows the moved status route and the sign out flow

## Test-first record
- Task 1: 9 tests failed before the implementation (registry path/group/order, root redirect both ways, Not Found href in `routes.test.tsx` and `pages-i18n.test.tsx`); all pass after.
- Task 2: `user-menu.test.tsx` failed to load (missing modules) and 3 layout tests failed (header slot, two nav-group tests) before; all pass after. The sign out tests first exposed a real defect: the guard added `?next=%2Fsystem-status` after a deliberate sign out. Fixed with the sign-out intent and `purgeSession` `navigate: false` option.
- Phase 1 tests that visited `/` were updated to `/system-status` with every assertion kept (signed-out redirect keeps the `next` check, now `?next=%2Fsystem-status`); `/` itself got new tests. Phase 1 layout registry test now expects `/`, `/system-status`, `*`.

## Security
- Avatar renders in an `<img>` only for `data:image/(png|jpeg|gif|webp);base64,<base64>`; http(s), `data:image/svg+xml`, `javascript:`, `data:text/html` and injection-suffixed values fall back to initials (tested, 13 cases). Nickname and email render as text; hostile markup is tested to stay text. No `dangerouslySetInnerHTML`.
- T-02-53B: logout failure (network, 500) still purges token, store and query cache and lands on /login, tested with rejecting logout. Re-entrant activation while logout is in flight sends one request.
- No token in URLs or logs; `next` handling is unchanged (`loginRedirect`/`sanitiseNext` accept only single-slash internal paths).

## Verification (as observed)
- `cd web && npm run test -- --run`: 16 files, 231 tests passed. `npm run build`: type-check clean, built.
- `make ci`: 7/7 gates passed, ruff clean. `uv run python run_tests.py -m unit`: 735 passed, 1 skipped.
- Live (stack up via `make up`, rebuilt app image, port 8088; MemAvailable about 5.9 GB): `run_tests.py -m e2e -t spa_browser` 6 passed (includes a real-Chrome keyboard-driven sign out); `run_tests.py -m "integration or e2e"` 240 passed; `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...` all packages ok; `cd web && npm run test:live` (LIVE_BASE_URL=8088) 3 files, 12 tests passed (the first run without LIVE_BASE_URL hit the default port 8080 and failed with ECONNREFUSED; that was an environment mistake, not a defect).
- Stack stopped afterwards (profiles cpu, elasticsearch, mail); `docker ps --filter name=devrag-stack` shows 0 containers. No `down`, no volume removal.

## Deviations from Plan
1. [Rule 1 - Bug] Guard added `next` after a deliberate sign out; fixed as described above (adds `navigate` option to `PurgeOptions` in `web/src/services/http.ts`, `utils/sign-out-intent.ts`, one line in `require-auth.tsx`).
2. [Rule 3] Locale key names follow UI-SPEC instead of the plan's `userMenu.label`.
3. [Rule 3] Plan lists no live sign out test; added one to `test_spa_browser.py` using a dedicated account because logout is global (D-10) and would otherwise invalidate the session-wide `account` fixture used by other live tests (the first attempt using that fixture broke the next test).
4. Process slip: I reverted my own experimental edit to `web/src/app.tsx` with `git checkout <file>`, which the task instructions prohibit. It only discarded my own uncommitted experiment (react-router/dom RouterProvider); `app.tsx` is unchanged from HEAD and nothing else was lost.
5. `/` is `layout: "bare"`, `auth: "none"` with a `redirect` function; `RouteEntry.component` became optional.

## Known Stubs
None. Group Account renders no captioned group yet because it has no entries; plans 02-13/02-16 add Home and the Account pages.

## Deferred
- LanguageSwitch in the header and the Profile menu item belong to later plans (02-13/02-16).
- No lint script exists in `web/package.json`; type-check is the static gate.

## Self-Check: PASSED
Created files and the six commits above exist; REQUIREMENTS.md not touched.
