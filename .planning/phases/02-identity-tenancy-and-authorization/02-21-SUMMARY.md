---
phase: 02-identity-tenancy-and-authorization
plan: 21
subsystem: ui
tags: [react, api-tokens, masking, clipboard, alert-dialog, radix, tanstack-query, i18n]
requires: [02-18, 02-20]
provides:
  - API tokens page at /user-setting/api (list, create, show/hide, copy, delete)
  - shared masking rule (maskToken, tokenTail) in web/src/pages/user-setting/api/mask.ts
  - dialog, alert-dialog and table blocks (shadcn style, Tailwind v3)
  - home "API tokens" stat card and "Manage API tokens" link (owner only)
affects: [02-22, 02-25]
tech-stack:
  added: []
  patterns:
    - "one masking function used by every place that shows a token in hidden form"
    - "token values only in query cache and component state; purgeSession clears them"
    - "aria-disabled (not disabled) on pending buttons so focus survives"
key-files:
  created:
    - web/src/pages/user-setting/api/index.tsx
    - web/src/pages/user-setting/api/token-row.tsx
    - web/src/pages/user-setting/api/created-dialog.tsx
    - web/src/pages/user-setting/api/delete-dialog.tsx
    - web/src/pages/user-setting/api/clipboard.ts
    - web/src/pages/user-setting/api/errors.ts
    - web/src/pages/user-setting/api/mask.ts
    - web/src/pages/user-setting/api/mask.test.ts
    - web/src/pages/user-setting/api/api-tokens.test.tsx
    - web/src/pages/user-setting/api/api-tokens.live.test.ts
    - web/src/hooks/use-api-token-request.ts
    - web/src/services/api-token-service.ts
    - web/src/components/ui/dialog.tsx
    - web/src/components/ui/alert-dialog.tsx
    - web/src/components/ui/table.tsx
  modified:
    - web/src/constants/routes.ts
    - web/src/constants/api-paths.ts
    - web/src/pages/home/index.tsx
    - web/src/pages/home/home.test.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/components/shell-i18n.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - .planning/DECISIONS.md
key-decisions:
  - "R-124: tokens.action.* for button labels (the UI-SPEC key names collide with tokens.delete.*), owner-only forbidden state, owner-only home card, own messages for 409/429/403, aria-disabled pending, caption focus after delete, 404 on delete refreshes silently, short or odd values fully masked"
requirements-completed: []
duration: single session
completed: 2026-10-08
---

# Phase 2 Plan 21: API tokens page Summary

The owner can create, list (masked), reveal, copy and delete API tokens from `/user-setting/api`; the deleted token gets 401 at once, proven through the real SPA against the real stack.

## Commits

| Commit | What |
|---|---|
| 07636be | Task 1: mask rule and tests, dialog, alert-dialog, table blocks, failing page tests, `dialog.close` key |
| 487b945 | Task 2: page, hook, service, route, home card and link, locale keys, updated registry tests |
| fddf8c7 | Task 3: live lifecycle test |

## Test-first record

- `mask.test.ts` failed with `Failed to resolve import "./mask"` (mask.ts moved aside to show the red), then 9 passed.
- `api-tokens.test.tsx` failed with `Failed to resolve import "."` (no page yet); `tsc` also failed on the missing module at the red commit (the Task 1 acceptance line "typecheck passes" could not hold while the page tests import a page that does not exist). After Task 2: 42 passed in the api folder (two test-helper bugs fixed first: `rowFor` used a single-match query, and the loading test released the request before it reached the adapter).
- Home and registry tests were changed because the plan changes behaviour: `home.test.tsx` "renders no placeholder tiles" now expects the tokens card and row (and still no members or invitations tile), with a QueryClientProvider and an HTTP stub; `layouts.test.tsx` and `shell-i18n.test.tsx` list the new route and nav entry. No assertion weakened, skipped or deleted.
- First `make ci` after Task 2 failed the secrets gate on `token-row.tsx` (a ternary of two i18n keys read as a secret literal); fixed by naming (two `t()` calls), exemptions untouched.

## What was built

- Masking rule in one place (`mask.ts`): `ragflow-` + eight bullets + last 4; values under 13 characters or without the prefix are fully masked. Table, accessible-name tails and the dialogs all use it. Full value is in the DOM only while revealed or in the created dialog; reveal state is row-local, so leaving the page resets it.
- Copy: async Clipboard API only; on rejection or a missing API the token is revealed and the "Couldn't copy" toast shows (no `execCommand`, no hidden input). Toasts never contain a token.
- Create: one click, immediate call, dialog with read-only field and "Copy token", no "shown once" wording (D-12). Button is `aria-disabled` while pending (a double click sends one request). Focus returns to Create on close.
- Delete: per-row AlertDialog, initial focus on "Keep token", no overlay close, id sent is the row's own token, 404 refreshes silently, other failures show a fixed toast; focus goes to the table caption afterwards.
- Own messages: 409 cap, 429 rate limit, 403 owner only, generic otherwise; a non-owner sees an owner-only state with no token data.
- Query cache: key `["api-tokens"]` has no token; `purgeSession` clears query and mutation caches (tested); create mutation `gcTime: 0`.
- Home: tokens stat card (count, skeleton, per-card error with retry) and "Manage API tokens" row, for the owner only.

## Live results (stack devrag-stack, port 8088, app image rebuilt by `make up` with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, MemAvailable 8289 MiB before start)

- `api-tokens.live.test.ts`: 4 passed on the first run (404 before delete, 401 after delete; foreign delete 404 and token still works; owner page refreshes cleanly on 404).
- `uv run python run_tests.py -m "integration or e2e"`: 251 passed.
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`: all packages ok (SERVICE_CONF, E2E_BASE_URL, root password read from `docker/.env`, never printed).
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 7 files, 32 tests passed.
- Account cleanup: the web live tests recorded their e-mails (`LIVE_ACCOUNTS_FILE`); those 13 rows plus 2 `webreset-` rows from the forgot-password live test of this run were deleted by e-mail, final count 0. Older `webprofile-`/`webauth-` rows from earlier plans were not touched.
- Stack stopped with `docker compose -p devrag-stack ... --profile cpu --profile elasticsearch --profile mail stop`; `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal; the foreign `compose` project was not touched.

## Final checks (as observed, after the last code change)

- `make ci`: 7/7 gates passed
- `uv run python run_tests.py -m unit`: 764 passed, 1 skipped, 251 deselected
- `cd web && npm run test -- --run`: 29 files, 523 tests passed
- `cd web && npm run build`: built (the existing chunk-size warning only)
- `grep -rn dangerouslySetInnerHTML web/src`: 0; `check_no_sleep.py`: OK

## Deviations from Plan

1. [Rule 3] Locale key names: UI-SPEC lists `tokens.delete` (button label) and `tokens.delete.title` (dialog), impossible in nested JSON. Button labels are `tokens.action.show/hide/copy/delete`. UI-SPEC otherwise followed exactly; nothing in the user's constraints conflicted with it.
2. [Rule 2] Owner-only forbidden state for a 403 list, owner-only home card and link, own 409/429/403 create messages, loading status text, `tokens.created.field` and `dialog.close` keys. All in R-124.
3. Page split into token-row, created-dialog, delete-dialog, clipboard and errors files (no giant files), plus `services/api-token-service.ts`, none in the plan's file list. `web/src/pages/home/home.test.tsx`, `layouts.test.tsx`, `shell-i18n.test.tsx` updated for the new route.
4. Acceptance `grep -c "user-setting/api" routes.ts` equals 1 is not met literally: it is 2 (the path line and the lazy import), the same pattern as the profile entry.
5. Task 1 acceptance "typecheck passes" could not hold at the red commit (see test-first record).
6. The plan's "no token in URL" has one necessary exception inherited from plan 02-20: the DELETE API path carries the token (percent-encoded); it never appears in the browser URL, router state, title, toast or logs.

## Known Stubs

None. The beta value returned by the API is dropped in the service layer and not shown (UI-SPEC).

## Threat Flags

None. T-02-98..101 mitigated and tested (masked default and row-local reveal; no token in URL, title, toast, storage, console; AlertDialog with safe focus and no overlay dismissal; text-only rendering, grep gate 0).

## Self-Check: PASSED

Commits 07636be, 487b945, fddf8c7 exist; the page, mask, hook, service, dialog blocks and live test files exist.
