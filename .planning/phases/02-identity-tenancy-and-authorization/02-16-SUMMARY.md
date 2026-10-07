---
phase: 02-identity-tenancy-and-authorization
plan: 16
subsystem: frontend
tags: [react, profile, avatar, password-change, i18n, theme, vitest, live-tests]
requires: [02-11, 02-13, 02-15, 02-28]
provides:
  - /user-setting/profile page (profile card, password card), registry entry, sidebar item and Profile item in the account menu
  - avatar helper (magic-byte type check, decode, 256x256 canvas re-encode, 256 KB cap)
  - language and theme persistence with a silent best-effort server write; server Dark applied when no local theme choice
  - "Manage your account" card on the home page
affects: [02-21, 02-24 (home link rows), later settings pages]
tech-stack:
  added: []
  patterns:
    - "passwords go through a plain async function, never a TanStack mutation, so they are not kept in the mutation cache"
    - "shared shouldUseDark rule tested against the inline first-paint script in index.html"
key-files:
  created:
    - web/src/pages/user-setting/profile/index.tsx
    - web/src/pages/user-setting/profile/profile-card.tsx
    - web/src/pages/user-setting/profile/password-card.tsx
    - web/src/pages/user-setting/profile/password-schema.ts
    - web/src/pages/user-setting/profile/profile-error.ts
    - web/src/pages/user-setting/profile/avatar.ts
    - web/src/pages/user-setting/profile/avatar.test.ts
    - web/src/pages/user-setting/profile/profile.test.tsx
    - web/src/pages/user-setting/profile/password.test.tsx
    - web/src/pages/user-setting/profile/profile.live.test.ts
    - web/src/hooks/use-profile-request.ts
    - web/src/utils/theme.test.ts
    - web/src/components/theme-toggle.test.tsx
  modified:
    - web/src/constants/routes.ts
    - web/src/constants/api-paths.ts
    - web/src/services/user-service.ts
    - web/src/components/user-menu.tsx
    - web/src/components/language-switch.tsx
    - web/src/components/theme-toggle.tsx
    - web/src/components/require-auth.tsx
    - web/src/utils/theme.ts
    - web/index.html
    - web/src/pages/home/index.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - .planning/DECISIONS.md
key-decisions:
  - "R-120: avatar pipeline, password form without confirmation (UI-SPEC), server Dark rule, password-change sign-out flow"
requirements-completed: [UI-34, UI-42, UI-43]
duration: one session
completed: 2026-10-08
---

# Phase 2 Plan 16: Profile and settings page Summary

A signed-in user can edit nickname and avatar, change the password (which signs this browser out and lands on a bare /login with "Password changed"), and have language and theme persist locally and, silently, on the server.

## Commits

| Commit | What |
|---|---|
| 6630fbb | Task 1: avatar helper, profile card, route, nav entry, menu item, en/zh copy |
| 659cfd3 | Task 2: language and theme persistence, first-paint script, home account card |
| b84ca86 | Task 3: password card, live tests, R-120 |

No context split was needed.

## What was built

- **Avatar** (`avatar.ts`): type decided by the first bytes (PNG, JPEG, WebP; SVG and GIF refused, file name and browser type ignored), decoded by loading it as an image, centred square crop drawn on a 256x256 canvas, encoded again by the app (PNG first for PNG/WebP sources, then JPEG at falling quality) to at most 256 KB decoded. Result is checked against the same safe data-URL rule the renderer uses. Object URLs are revoked on every path. Three inline messages: wrong type, unreadable file (new key `errors.avatar.decode`), still too large.
- **Profile card**: nickname (1 to 64, same rule as the server), email read-only with `aria-readonly` and helper, staged avatar preview saved with the form, "Remove avatar" only when an avatar exists. Save is `aria-disabled` until dirty and valid, double submit blocked, request carries only the edited fields (`nickname`, `avatar`). Success updates the user store and the cached session user, toast "Profile saved". Failure shows an inline alert (no request toast).
- **Password card**: current and new (8 to 128), each with the show/hide toggle, no confirmation field (UI-SPEC); `current-password` / `new-password` autocomplete; plain async request (no mutation cache); a wrong current password (HTTP 400) shows the server message in the alert, marks the field `aria-invalid` with `aria-describedby`, clears and focuses it, and keeps the session; success calls `purgeSession({ toast: false, navigate: false })`, navigates to `/login` (no `next`), shows "Password changed".
- **Language and theme**: `saveSettingQuietly` writes `language` / `color_schema` only when a user is in the store, silently, swallowing every failure. Theme storage access is wrapped; `shouldUseDark` is the single rule and a unit test runs the inline script from `index.html` against it. A server `Dark` is applied after session recovery only when no local theme exists (R-120).
- Route `/user-setting/profile` (auth required, account group, `UserRound`, order 3), Profile item in the account menu, and the "Manage your account" card with the "Edit your profile" row on the home page.

## Test-first record (failing before implementation)

- Task 1: `avatar.test.ts` and `profile.test.tsx` failed to load (module and page missing), 0 tests ran; 46 passed after (one test-side assertion on a `role=alert` parent was fixed, not the code).
- Task 2: 35 failed before (theme helpers missing: shouldUseDark, colourSchemaFor, applyUserColourSchema; home links; ThemeToggle and LanguageSwitch server writes; require-auth theme); all passing after.
- Task 3: `password.test.tsx` 16 of 16 failed before; 16 passed after (17 tests after the confirmation correction).
- Live: `profile.live.test.ts` (6 tests) written after the implementation, passed first run.

## Verification (observed)

MemAvailable was 8124 MiB at the gate. No `devrag-stack` containers were running before `make up` (`PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, app image rebuilt, web port 8088); `scripts/wait_stack.sh` reported all services healthy.

- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 5 files, 23 tests passed (includes the 6 new ones).
- `uv run python run_tests.py -m "integration or e2e"`: 246 passed, 741 deselected.
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`: every package ok.
- Live accounts created by this run (`webprofile-*`, `webauth-*`) were deleted by recorded email (tenant_llm, user_tenant, tenant, user). Two older `webauth-muyg01mxti46f071` rows from a previous session (created 18:30 UTC, before this run) remain; they are not this plan's and were left alone.
- Stack stopped with `docker compose -p devrag-stack ... stop` (profiles cpu, elasticsearch, mail); `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no `-v`, foreign `compose` project untouched.

Final checks, run after the last code change:

- `make ci`: 7/7 gates passed, ruff security selection passed.
- `uv run python run_tests.py -m unit`: 740 passed, 1 skipped, 246 deselected.
- `cd web && npm run test -- --run`: 25 files, 414 tests passed (after the confirmation correction).
- `cd web && npm run build`: built (the existing chunk-size warning only).
- `npm run typecheck`, `scripts/ci/check_no_sleep.py`, `grep -rn dangerouslySetInnerHTML web/src | wc -l` (0): clean.

## Deviations from Plan

1. **Correction after completion:** the first version added a confirm-password field because the task instruction asked for one. The coordinator corrected this (UI-SPEC line 212: no confirm-password field). The field, its zod refinement, the keys `profile.password.confirm` and `errors.password.mismatch` (en and zh) and the confirmation tests were removed; the live test no longer fills it and was edited without being run live. R-120 point (2) no longer records a deviation.
2. **Existing tests updated for the new route (behaviour change, nothing weakened):** `layouts.test.tsx`, `shell-i18n.test.tsx` (registry and sidebar now include Profile; the "only groups that have entries" case now filters to the platform group; a new case covers Platform + Account), `user-menu.test.tsx` (menu now has Profile and Sign out), `home.test.tsx` (the single profile link replaces "no links").
3. Files outside the plan list were touched or added where needed: `api-paths.ts`, `user-service.ts` (the two Go endpoints), `require-auth.tsx` (apply server Dark), `profile-card.tsx`, `password-card.tsx`, `password-schema.ts`, `profile-error.ts`, `password.test.tsx`, `theme-toggle.test.tsx`.
4. `grep -c "user-setting/profile" web/src/constants/routes.ts` is 2, not 1: the path and the lazy component import both contain the string.
5. The hidden file input has `tabIndex={-1}` and an accessible name; the visible "Change avatar" button is the keyboard path to it (a second invisible tab stop would break the visible-focus rule).
6. Wrong-current-password feedback is the form alert (server message, English) plus `aria-invalid` and `aria-describedby` on the field; the server message is not translated.
7. The live avatar test replaces only the browser's pixel work (Image, canvas) because jsdom has none; the returned data URL is a real 1x1 PNG, so the server's own validation ran on it.

## Known Stubs

None. Home shows only the profile row; the tokens and team rows are added by plans 02-21 and 02-24.

## Threat Flags

None beyond the plan's register. T-02-71 (text/validated image only, grep gate 0), T-02-72 (live test: old token 401), T-02-73 (no mutation cache, storage, query key or console holds the values; tested), T-02-74 (magic bytes, re-encode, 256 KB cap; server validator mirrors it) are each covered by a named test.

## Self-Check: PASSED

Commits 6630fbb, 659cfd3, b84ca86 exist; the created files listed above exist on disk.
