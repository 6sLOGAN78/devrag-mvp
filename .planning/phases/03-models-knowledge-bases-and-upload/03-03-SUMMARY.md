---
phase: 03-models-knowledge-bases-and-upload
plan: 03
subsystem: ui
tags: [react, zustand, radix-dropdown, workspace, tenancy, vitest, i18n]

requires:
  - phase: 02-auth-and-tenancy
    provides: memberships endpoint, invite/accept routes, user store with own tenant
provides:
  - useWorkspaceStore (activeTenantId, memberships, lost, initialise, setActive, setMemberships, clearLost, reset)
  - useWorkspaces / useActiveWorkspace hooks (ordered list, active workspace, lost-access toast)
  - WorkspaceSwitch header component and DropdownMenuRadioGroup / DropdownMenuRadioItem exports
  - en/zh locale keys for the workspace selector and shared common.* additions
affects: [03-04, models-pages, datasets-pages, upload]

tech-stack:
  added: []
  patterns:
    - "Persisted client choice is keyed by userId and validated against the server list before use"
    - "Storage access is wrapped in try/catch with an in-memory fallback"

key-files:
  created:
    - web/src/stores/workspace-store.ts
    - web/src/stores/workspace-store.test.ts
    - web/src/hooks/use-workspaces.ts
    - web/src/components/workspace-switch.tsx
    - web/src/components/workspace-switch.test.tsx
    - web/src/test/live/workspace.live.test.ts
  modified:
    - web/src/components/ui/dropdown-menu.tsx
    - web/src/layouts/standard-layout.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/services/http.ts
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "No new npm package (D-21): radio items hand-written on the already installed Radix dropdown-menu"
  - "Chinese strings are drafts; review is deferred under B-18"

patterns-established:
  - "Workspace selection: active tenant id lives in useWorkspaceStore and is the single source for Phase 3 page data keys"
  - "Sign-out and 401 purge (dropSessionState) reset the workspace store"

requirements-completed: [TEN-13]

duration: closed out after an interrupted run
completed: 2026-10-09
---

# Phase 3 Plan 03: Workspace Selector Summary

**Header workspace selector backed by a userId-keyed persisted Zustand store, with a membership-derived list, safe fallback when access is lost, and a live test using two real accounts through the ingress.**

## Performance

- **Duration:** original run 2026-10-08 22:32 to 22:43 +0530; closed out 2026-10-09 after an interruption
- **Tasks:** 3 of 3
- **Files modified:** 12

## Accomplishments
- Users in more than one workspace get a header menu (own workspace first, then admin/normal memberships by locale-aware name, `invite` never listed); single-workspace users see plain text with a visually hidden `Workspace:` prefix and no menu.
- Active workspace persists in `devrag.workspace` as `{userId, tenantId}`; another user's entry is ignored, blocked storage falls back to memory, sign-out resets, and a vanished workspace falls back to the own one with an info toast.
- Switching is announced through a `role=status` region, with no toast, and focus stays on the trigger. Wordmark text is `hidden sm:inline` so the selector fits at 320px.

## Task Commits

1. **Task 1: failing unit tests (RED)** - `fff5131` (test)
2. **Task 2: store, hook, component, layout, locales (GREEN)** - `725d048` (feat)
3. **Task 3: live test with two real accounts** - `83570fe` (test)

No fix commits were needed during close-out.

**Plan metadata:** the docs commit following this summary.

## Verification (close-out run, real output)

- Acceptance greps: `devrag.workspace` present in the store; `DropdownMenuRadioItem` appears 3 times in dropdown-menu.tsx; `useWorkspaceStore` imported and called in `dropSessionState` of http.ts; no `dangerouslySetInnerHTML` in workspace-switch.tsx; `git diff` of package.json and package-lock.json empty; the live test has no `vi.mock`, `setTimeout` or `adapter` override.
- `npm run test -- --run src/stores src/components src/layouts src/locales src/constants`: 11 files, 130 tests passed.
- Full unit suite `npm run test -- --run`: 34 files, 649 tests passed.
- `npm run typecheck`: clean (no output).
- Live: `LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live -- src/test/live/workspace.live.test.ts`: 1 file, 4 tests passed against the real stack.

## Decisions Made
None beyond the plan. The live test needs `LIVE_BASE_URL` set to this checkout's ingress port (8088); the vitest default of 8080 does not match the `.env` port.

## Deviations from Plan

None in code. Process notes:
- The plan was closed out after an interrupted run. All three task commits already existed; they were verified against the plan and not re-implemented.
- Task 3's verify command (`npm run test:live` without `LIVE_BASE_URL`) fails with ECONNREFUSED on 127.0.0.1:8080 because the ingress listens on 8088 here. Re-running with `LIVE_BASE_URL=http://127.0.0.1:8088` passed. Not a code defect.
- Task 3 said not to rebuild the stack. The stack had stopped after a host restart, so it was restarted with `make up` (which includes `--build`) as instructed by the close-out request.
- `scripts/preflight.sh` failed on `vm.max_map_count` (65530, the host setting reset after restart; needs sudo to raise). The documented override `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` was used and the script records it in `ragflow-logs/preflight-overrides.log`. Elasticsearch came up healthy.

## Issues Encountered
- Stack containers (mysql, es01, minio, redis) were down and the app was crash-looping only because MySQL was unreachable. `make up` restored everything and `scripts/wait_stack.sh` reported all services healthy.

## Known Stubs
None.

## Threat Flags
None. T-03-03-01 to T-03-03-03 are mitigated as planned: stored tenant accepted only if in the server membership list for that user, the entry is keyed by userId and reset on sign-out, and names render as text nodes.

## Next Phase Readiness
Plan 03-04 and the Phase 3 pages can read `useActiveWorkspace().tenantId` and `useWorkspaceStore`. The server (03-04 tenant_scope) remains authoritative for tenant access.

## Self-Check: PASSED

All created files exist and commits `fff5131`, `725d048`, `83570fe` are present in git history.
