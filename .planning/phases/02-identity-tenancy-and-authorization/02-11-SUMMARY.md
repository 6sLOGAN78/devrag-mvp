---
phase: 02-identity-tenancy-and-authorization
plan: 11
subsystem: frontend
tags: [i18n, i18next, react-i18next, zh, en]
requires: [02-05]
provides:
  - i18n runtime (en, zh) initialised before first render
  - shared shell copy as translation keys
affects: [02-27]
key-files:
  created:
    - web/src/i18n/index.ts
    - web/src/i18n/language.ts
    - web/src/i18n/language.test.ts
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - web/src/locales/locales.test.ts
    - web/src/components/shell-i18n.test.tsx
  modified:
    - web/src/main.tsx
    - web/src/index.css
    - web/src/test/setup.ts
    - web/src/constants/routes.ts
    - web/src/components/{app-sidebar,empty-state,error-state,theme-toggle,skip-link}.tsx
    - web/src/components/ui/sheet.tsx
    - web/src/layouts/{standard-layout,full-bleed-layout,layouts.test}.tsx
decisions:
  - "Language detection is own code (stored devrag.lang, then navigator.language, then en); user language slot exists in detectLanguage for the auth plans"
  - "Route registry stores labelKey; ui/sheet close label translated (nav.closeMenu)"
metrics:
  tasks: 2
  completed: 2026-10-07
---

# Phase 2 Plan 11: i18n runtime (en, zh) and shared shell migration

i18next 23 plus react-i18next 14 with bundled en and zh, own language detector, key-parity test, and the shared shell (sidebar, empty/error state, theme toggle, skip link, layouts, route labels) moved off `copy.ts`.

## Commits
- 89291d2 i18n bootstrap, detection, parity test, CJK font stack
- c0fe2e9 shell migration

## Keys
19 leaf keys per locale (app, nav, a11y, theme, errorState, emptyState). Page, toast and status copy stays in `copy.ts` until plan 02-27, which also deletes it and fixes WR-20.

## Tests
- Task 1: language.test.ts and locales.test.ts failed before implementation (modules missing); 9 pass after.
- Task 2: shell-i18n.test.tsx failed 3 of 4 before migration; after, full unit suite is 72 of 72 passing. One existing assertion (`nav.label` in layouts.test.tsx) now asserts the English text through `i18n.t(labelKey)` against the real instance; no assertion weakened.
- `web/src/test/setup.ts` resets to English before every test.

## Checks (as observed)
`npm run typecheck` clean; `npm run test -- --run` 9 files, 72 tests pass; `npm run build:check` passes; root `make ci` 7/7 gates and ruff pass. `grep -rEn 'dangerouslySetInnerHTML|innerHTML|rehype-raw' web/src` prints nothing. `web/package-lock.json` unchanged. The `live` vitest project was not run (needs the stack).

## Needs review
The Chinese text in `zh.json` is a DRAFT and needs review by a Chinese reader. UI-42 is NOT recorded complete; REQUIREMENTS.md untouched (exit-gate plan 02-26 sets requirements).

## Deviations
- [Rule 2] `ui/sheet.tsx` hard-coded "Close" was translated (not in the plan's file list); it is shared shell chrome.
- Added `errorState.defaultNoun` key (replaces the hard-coded "data" fallback).
- Bare layout needed no change (no copy).

## Not done
Page and HTTP-client migration, `copy.ts` deletion, WR-20: plan 02-27 by design. No visual language switcher yet (`setLanguage` exists for it).

## Self-Check: PASSED
