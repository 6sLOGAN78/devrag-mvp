---
phase: 02-identity-tenancy-and-authorization
plan: 24
subsystem: ui
tags: [react, team, invitations, roles, alert-dialog, native-select, i18n, live-tests]
requires: [02-21, 02-23]
provides:
  - /user-setting/team page (Invitations for you, Your workspace, Workspaces you've joined) in the Account nav group
  - services/team-service.ts and hooks/use-team-request.ts (memberships, members, invite, respond, role, remove, leave)
  - components/ui/native-select.tsx
  - home Team members and Pending invitations stat cards, role card link and the Manage your team link row
affects: [02-25, 02-26, 03]
tech-stack:
  added: []
  patterns:
    - "one ConfirmDialog with no Radix trigger: the opener is recorded and given focus back, except when the row is gone (focus goes to the table caption)"
    - "controlled native select: a change only opens the confirmation, the displayed value stays the listed role until the refetch"
    - "invitations and joined workspaces are both derived from the one GET /v1/tenant/list query"
key-files:
  created:
    - web/src/services/team-service.ts
    - web/src/hooks/use-team-request.ts
    - web/src/components/ui/native-select.tsx
    - web/src/pages/user-setting/team/{index,invitations-card,workspace-card,joined-card,invite-form,members-table,pending-list,confirm-dialog}.tsx
    - web/src/pages/user-setting/team/{errors,format,roles}.ts
    - web/src/pages/user-setting/team/team.test.tsx
    - web/src/pages/user-setting/team/team.live.test.ts
    - web/src/pages/home/stat-card.tsx
  modified:
    - web/src/constants/api-paths.ts
    - web/src/constants/routes.ts
    - web/src/pages/home/index.tsx
    - web/src/pages/home/home.test.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/components/shell-i18n.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - .planning/DECISIONS.md
key-decisions:
  - "R-126: native select, own workspace from the session store, 404 treated as already gone, invite form shows the server message for 400/404/409, member lists use the server default page size"
requirements-completed: []
duration: single session
completed: 2026-10-08
---

# Phase 2 Plan 24: Team page Summary

The Team page lets an owner invite by email, change roles, remove members and withdraw invitations, lets an invitee accept or decline, and lets a member leave, all through confirmations with the safe button focused; the whole cycle is proven live through the real Go API.

## Commits

| Commit | What |
|---|---|
| 649f37b | Task 1: team service and hooks, native select, failing Team page tests |
| 95d6e54 | Task 2: Team page, cards, route, home stat cards, locale keys, registry/nav test updates |
| 50e112e | Task 3: live membership test, decision R-126 |

## Test-first record

- Task 1: `team.test.tsx` (52 tests) failed to load before the page existed (`Failed to resolve import "."`; typecheck: `Cannot find module '.'`).
- Task 2: after the page existed, 5 of 52 failed on the first run. Three were test-design errors (server state changed after the refetch it needed to affect; fixed by changing the fake server before the click). Two were real defects found by the tests: a dialog opened without a Radix trigger does not return focus to the opener (Radix focuses only its own trigger), and `form.setFocus` after `form.reset` finds no registered field. Fixed with an explicit opener ref in `ConfirmDialog` and a direct input ref in the invite form.
- Home: 9 new/changed home tests failed before the cards existed, all pass after.
- Task 3: the live test passed on its first run because the page already existed; it could not be run red.

## What was built

- **Invitations for you** (only when pending): avatar initials, "{owner} invited you to join {workspace}", "Invited {date}", Accept (outline) and Decline (ghost) named "Accept/Decline invitation from {owner}"; both disabled while the request runs, aria-busy on the pressed one; toasts as in the UI-SPEC; decline needs no confirmation.
- **Your workspace**: workspace name, i18n plural member count (people only), owner-only invite form (shared `emailField` schema, server message shown exactly for 400/404/409 in an `alert-form-error` alert with no toast, own copy for 429 with Retry-After seconds and 403, one generic fallback, no double submit, field cleared and refocused on success); semantic members table (sr-only caption, scoped headers, owner row = static badge and no action; owner caller gets a native select named "Role for {nickname}" and "Remove {nickname}"; other callers get static badges); owner-only pending-invitations list with "Withdraw invitation for {email}"; compact empty line when only the owner exists.
- **Workspaces you've joined** (only when the caller belongs to a workspace they do not own): name, "Owned by", role badge, "Leave {workspace}".
- **Confirmations**: role change (Keep current role / Change role, non-destructive), remove, withdraw, leave. Cancel is focused; overlay click does not close; no dismiss while a request runs. After a row disappears focus goes to the members table caption (remove/withdraw) or the workspace card (accept, decline, leave); otherwise it returns to the opener.
- **Errors**: 404 = "no longer available, list refreshed" plus refetch; 403, 429 and others have fixed translated copy and a refetch; `useLeaveWorkspace` drops cached members of the left workspace and refetches the membership list.
- **Home**: Team members and Pending invitations stat cards (own skeleton, own error with retry), role card links to Team, "Manage your team" link row; shared `StatCard` extracted from the tokens card.
- **Nav**: `/user-setting/team`, Account group, `Users` icon, order 5.

## Live results (stack devrag-stack, port 8088, app image rebuilt by `make up` with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, MemAvailable 7164 MiB before start)

- `team.live.test.ts`: 4 passed (health, unknown email answer shown exactly once in the alert, full cycle invite / accept / role change / remove / decline / re-accept / leave / withdraw with server-side checks after each step and 403 for the teammate inviting into the owner's workspace, owner removes while the teammate's page is open).
- `uv run python run_tests.py -m "integration or e2e"`: 255 passed.
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...` with `SERVICE_CONF`, `E2E_BASE_URL=http://127.0.0.1:8088`, `MAILPIT_URL=http://127.0.0.1:8025`, root password read from `docker/.env` (not printed): all packages ok.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 8 files, 36 tests passed.
- Cleanup: all `webteam-%` rows and the 15 accounts recorded for the full live run were deleted by SQL (user, tenant, user_tenant, api_token, tenant_llm); remaining count 0. Older rows from earlier plans were not touched.
- Stack stopped with compose `stop` (profiles cpu, elasticsearch, mail); `docker ps --filter name=devrag-stack -q | wc -l` is 0. No `down`, no volume removal; the foreign `compose` project was not touched.

## Final checks (as observed, after the last code change)

- `make ci`: 7/7 gates passed, ruff clean
- `uv run python run_tests.py -m unit`: 763 passed, 1 skipped, 255 deselected
- `cd web && npm run test -- --run`: 30 files, 581 tests passed
- `cd web && npm run build`: built; `scripts/check-chunks.mjs` ok; `grep -rn dangerouslySetInnerHTML web/src | wc -l` is 0

## Deviations from Plan

1. [Rule 3] Added `web/src/services/team-service.ts` and extra helper files (`confirm-dialog.tsx`, `invite-form.tsx`, `members-table.tsx`, `pending-list.tsx`, `errors.ts`, `format.ts`, `roles.ts`, `home/stat-card.tsx`) beyond the plan's file list, to keep files small and the HTTP calls out of hooks; `api-paths.ts` gained the tenant paths from the generated route table.
2. [Plan-driven test updates] `home.test.tsx` (the "no placeholder tiles" test became the four-card test; token request assertions filter by URL because the page now also requests the member and workspace lists; two tokens tests dispatch by URL), `layouts.test.tsx` and `shell-i18n.test.tsx` (the registry and nav now include Team). No assertion was weakened, skipped or deleted.
3. The plan acceptance `grep -c "user-setting/team" routes.ts` equals 1 reads 2 (the path line and the lazy import line), same as the API tokens route.
4. Plan item "B's invite form is absent": a teammate's own Team page correctly shows the form for the teammate's own workspace, so the live test asserts no form inside the joined card and that the server answers 403 to the teammate inviting into the owner's workspace.
5. The UI-SPEC says zh uses `_other` only for plurals; the locale parity test requires identical key sets, so zh carries `count_one` and `count_other` with the same text.
6. Locale key names `team.withdraw` and `team.leave` from the spec were split to `.action` because they collide with `.title` etc. as objects (JSON cannot hold both).
7. i18next `escapeValue` stays false (existing, T-02-46): React escapes text. Hostile nicknames, emails, workspace names and `{{x}}` text are tested to render as literal text. The spec's "keep escaping on" would show `&lt;` entities literally in React.
8. The invitations card shows nothing while the workspace list loads (it may not exist) and the joined card shows nothing on a list error; the single in-place error for that query is shown in the invitations slot with noun "invitations".

## Known Stubs

None. Member lists use the server default page size of 100 (recorded in R-126).

## Threat Flags

None beyond the plan register. T-02-113 (owner controls by role, server authoritative, unit tests for admin and normal views, live 403), T-02-115 (text-only rendering, grep gate 0, hostile-input tests) and T-02-116 (confirm dialogs with cancel focused, select keeps old value) are mitigated and tested; T-02-114 accepted per R-107.

## Self-Check: PASSED

Commits 649f37b, 95d6e54 and 50e112e exist; `web/src/pages/user-setting/team/index.tsx`, `web/src/hooks/use-team-request.ts`, `web/src/components/ui/native-select.tsx` and `web/src/pages/user-setting/team/team.live.test.ts` exist.
