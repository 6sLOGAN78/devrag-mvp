---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 12
subsystem: frontend
tags: [react18, react-router7, tailwind3, shadcn, tanstack-query, openapi-typescript, vitest]
requires:
  - phase: 01-08
    provides: Python status/healthz payload and exported OpenAPI
  - phase: 01-09
    provides: Go /health route
  - phase: 01-10
    provides: SPA scaffold, HTTP client, vitest projects
provides:
  - Typed lazy route registry, three layouts, honest Not Found, route/shell error boundaries
  - Live System status page (Go and Python cards) backed by the generated route table
  - OpenAPI-generated TS types (npm run gen:api), RetCode parity test, live shell/status tests (authored)
affects: [01-13, 01-15, Phase 2 UI]
tech-stack:
  added: ["@radix-ui/react-slot 1.3.3", "@radix-ui/react-separator 1.1.15", "@radix-ui/react-tooltip 1.2.16", "@radix-ui/react-dropdown-menu 2.1.24", "@radix-ui/react-dialog 1.1.23"]
  patterns: [registry-driven nav and router, silent queries with per-card error isolation, build:check chunk assertion]
key-files:
  created: [web/src/constants/routes.ts, web/src/routes.tsx, web/src/layouts/*, web/src/components/*, web/src/pages/*, web/src/hooks/use-system-status-request.ts, web/src/services/system-service.ts, web/src/constants/api-paths.ts, web/scripts/check-chunks.mjs, web/src/interfaces/openapi.d.ts, test/unit_test/test_retcode_parity.py]
  modified: [web/package.json, web/package-lock.json, web/index.html, web/tsconfig.json, web/tsconfig.node.json, web/src/constants/copy.ts]
key-decisions:
  - "Query failures are thrown (not returned) so retry: 1 applies; a 503 with an envelope data keeps the dependency list as Degraded"
  - "Page-level errorElement renders inside the layout; layout-level errorElement renders in BareLayout"
  - "Sidebar responsiveness is CSS only (hidden/md/lg classes); mobile Sheet mounts on open"
requirements-completed: [UI-01, API-08]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 12: SPA shell and System status page Summary

Registry-driven React shell (standard, full-bleed, bare layouts, lazy routes) with a real System status page reading the Go `/health` and Python `/api/v1/system/status` routes, plus OpenAPI-generated types and a Python/Go/TS RetCode parity test.

## Commits
- fd022eb: registry, layouts, shared states, shadcn blocks, Radix deps, 15 layout tests
- 870be5a: status page, hook, service, app wiring, error boundaries, chunk check, tsconfig emit fix, routes and status tests
- e2f5b3a: generated-type usage, RetCode parity test, two live tests

## Observed results
- `npm run typecheck`: exit 0
- `npm run test -- --run`: 6 files, 48 tests passed (unit project)
- `npm run build:check`: build ok; 4 JS files emitted, 1 entry chunk plus 2 lazy route chunks (check-chunks exit 0; chunk names are all `index-*.js`)
- `uv run pytest test/unit_test/test_retcode_parity.py`: 5 passed
- `make ci` (run_all.py): 7/7 gates passed; ruff S/ASYNC/FIX clean
- `npm run gen:api` second run: no diff in openapi.d.ts
- `npx vitest list --project live`: lists 3 live files (http.live, system-status.live, spa-shell.live)
- Disk free on `/`: 6177M at start, 5172M at end. No dev server was started; process check shows none.

## Not run
- The `live` vitest project (spa-shell and status-page live tests) is authored and collected only. It needs the stack and ingress (plans 01-13/01-15) and has NOT been run, so it is not counted as passing.

## Deviations from Plan
1. [Rule 3] shadcn blocks were hand-written for Tailwind 3 instead of `npx shadcn add`, per the task constraint not to run a CLI that rewrites config; sonner was already present. Only the five Radix primitives named in the constraint were added, exact-pinned.
2. [Rule 1] `tsc -b` emitted `.js/.d.ts/.tsbuildinfo` files into `web/` (including `vite.config.js` beside the TS config). Fixed by setting outDir/tsBuildInfoFile under `node_modules/.tmp`, `emitDeclarationOnly`, and listing the generated route JSON in tsconfig.node.json. Stray files were deleted before commit.
3. Query failures throw instead of returning an "unreachable" value, so the specified `retry: 1` is effective.
4. Task 1's commit is not independently typecheck-clean: `constants/routes.ts` lazily imports pages committed in Task 2. Tests in that commit pass.
5. UI-SPEC checker flags 1, 4, 5 applied (named empty state heading, overall badge ordered first, accent only on active nav icon, indicator and primary button); flag 3 already applied in 01-10; flag 2 concerns later dialogs.
6. The Go card shows only database and redis (Go reports only those two); the Python card shows four rows.
7. Acceptance grep for `/health` and `/api/v1/system/status` in non-test source matches `api-paths.ts` (the two lookup keys), as the plan allows.

## Known Stubs
None.

## Threat Flags
None. Server text is rendered only as React text; no `dangerouslySetInnerHTML`.

## Self-Check: PASSED
