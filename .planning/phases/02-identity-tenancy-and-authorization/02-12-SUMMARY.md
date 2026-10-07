---
phase: 02-identity-tenancy-and-authorization
plan: 12
subsystem: frontend
tags: [auth-guard, session-recovery, 401, open-redirect, cdp, headless-chrome]
requires: [02-10, 02-27]
provides:
  - RequireAuth layout route (token present AND GET /v1/user/info succeeded) with a 150 ms delayed session skeleton and an in-place error state
  - client-side 401 redirect (registerNavigate) that purges only for the token that was sent; 5xx and network errors never purge
  - sanitiseNext / loginRedirect open-redirect guard
  - typed user store, user-service (getUserInfo, logout), use-user-info-request hook (query key [user, info])
  - purgeSession({ toast }) exported for sign out (02-28) and password change (02-16)
  - stdlib-only headless Chrome DevTools-pipe helper and real-browser guard tests
affects: [02-13, 02-16, 02-18, 02-28]
key-files:
  created:
    - web/src/components/require-auth.tsx
    - web/src/components/require-auth.test.tsx
    - web/src/components/session-skeleton.tsx
    - web/src/hooks/use-authorization.ts
    - web/src/hooks/use-user-info-request.ts
    - web/src/interfaces/user.ts
    - web/src/layouts/public-standard-layout.tsx
    - web/src/services/user-service.ts
    - web/src/stores/user-store.test.ts
    - web/src/utils/safe-next.ts
    - web/src/utils/safe-next.test.ts
    - test/helpers/chrome_cdp.py
  modified:
    - web/src/app.tsx
    - web/src/constants/api-paths.ts
    - web/src/constants/routes.ts
    - web/src/i18n/index.ts
    - web/src/layouts/bare-layout.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json
    - web/src/routes.tsx
    - web/src/routes.test.tsx
    - web/src/services/http.ts
    - web/src/services/http.test.ts
    - web/src/stores/user-store.ts
    - web/src/utils/authorization.ts
    - web/src/utils/authorization.test.ts
    - test/testcases/test_spa_browser.py
decisions:
  - "The guard decides from the stored token AND the fetched user, and content renders only after the store holds the recovered user; a user in the store without a token still redirects (tested)"
  - "The token store is subscribable (same-tab notify plus the storage event) and read through useSyncExternalStore: after a purge the in-flight recovery query is removed from the cache, so nothing else would re-render the guard"
  - "Public routes declared in the standard layout (Not Found) render in BareLayout when signed out, via PublicStandardLayout, instead of editing the registry"
  - "BareLayout treats any defined children (including null) as replacing the Outlet"
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 12: SPA auth guard, session recovery, 401 redirect, browser helper

A signed-out visitor is redirected to `/login?next=<path+search>`; with a stored token the SPA fetches `GET /v1/user/info` before rendering a guarded route; a 401 for the current token purges and navigates client-side; a 503, 5xx or network failure never signs anyone out.

## Commits
- a365a1b feat: safe-next sanitiser, typed user store, user info hook, purgeSession toast option (Task 1)
- cd6001b test: failing tests for RequireAuth, session recovery, navigate-on-401, public Not Found layout (RED)
- 3baffad feat: RequireAuth guard, session recovery, client-side 401 redirect (Task 2)
- a751ada test: headless Chrome over the DevTools pipe, browser test behind the guard (Task 3)
- 9cc6f9c test: reword chrome_cdp docstring so the no-fixed-delay grep gate is clean

## Tests: failing before, passing after
- `safe-next.test.ts` (24 cases): failed before with "Failed to resolve import ./safe-next" (verified by moving the module away), 24 pass after.
- RED commit cd6001b, observed before implementation: `require-auth.test.tsx` could not resolve its component (whole suite failed); 8 `http.test.ts` navigation cases failed (`registerNavigate is not a function`); 2 `authorization.test.ts` subscription cases failed; 3 `routes.test.tsx` guard cases failed (no `layout-bare`, and a timeout on the no-flash case). 13 failed tests plus the unresolved suite.
- After Task 2: 15 files, 195 tests pass (was 14 files, 169 before the plan). Re-run 3 times, stable.
- The `purgeSession` option and the 503/5xx/network no-purge tests in Task 1 were written after the `purgeSession` export in the same task, so I did not observe them failing first (the export did not exist, so they could not have passed before). They are in commit a365a1b and pass.
- A real defect was caught by the no-flash test during Task 2: `BareLayout` used `children ?? <Outlet />`, so a guard that passed `null` children rendered the protected route inside the skeleton shell. Fixed in `bare-layout.tsx` (a defined `children`, even null, replaces the Outlet).
- `no-hardcoded-copy.test.ts` flagged `=> void | Promise<void>` in http.ts as JSX text; the type is now `=> unknown`.

## Browser and live results (stack brought up with `make up`, web port 8088, then stopped)
- Chrome pipe transport worked with the fd 3/4 detail from the executor notes (`os.dup2` onto 3 and 4 in `preexec_fn` and `pass_fds=(3, 4)`; the source ends are parked above fd 10 first). No fallback was needed and nothing was added to BLOCKERS.md.
- `uv run python run_tests.py -m e2e -t spa_browser`: 3 passed (Healthy cards behind the guard with the real token set via `localStorage`; signed-out redirect to `/login?next=%2F`; server-rejected token purged from `localStorage` and redirected). The three original Healthy-card assertions are kept.
- `LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 3 files, 9 tests passed.
- Stack stopped with `docker compose -p devrag-stack ... stop` for profiles cpu, elasticsearch, mail: 0 containers running, 0 devrag-chrome or google-chrome processes. The foreign `compose` project was not touched.

## Final checks (as observed)
- `web`: `npm run typecheck` clean; `npm run test -- --run` 15 files / 195 tests pass; `npm run build:check` built, 1 entry chunk and 2 lazy chunks.
- Root: `make ci` 7/7 gates passed and ruff clean; `uv run python run_tests.py -m unit` 608 passed, 1 skipped, 164 deselected.
- `grep -rEn 'dangerouslySetInnerHTML|innerHTML|rehype-raw' web/src` prints nothing; `grep -v '^ *//' web/src/services/http.ts | grep -c window.location` is 0.

## Deviations from Plan
**1. [Rule 3 - Blocking] `/` registry entry changed to `auth: "required"`.** The plan says the registry is not edited, but `/` was `auth: "none"`, so the guard never applied to it and the signed-out redirect and the browser tests could not work. One word changed in `web/src/constants/routes.ts`; System status still lives at `/` and plan 02-28 moves it.

**2. [Rule 3 - Blocking] `utils/authorization.ts` gained `subscribeAuthorization`, plus `hooks/use-authorization.ts`.** Not in the plan's file list. After a purge the recovery query is removed from the cache, so the guard would not re-render and redirect. It also makes a sign out in another tab take effect (storage event).

**3. [Rule 3] `isSameOrigin` now reads `globalThis.location.origin`** instead of `window.location.origin` so that the plan's `window.location` grep for http.ts is 0. It is a read of the origin, not a navigation; behaviour is identical.

**4. [Rule 3] `PublicStandardLayout` (new file) and `applyUserLanguage` in `i18n/index.ts`.** Needed for "Not Found in BareLayout when signed out" without editing the registry, and for "apply user.language if no explicit local choice" without persisting it. `pages/not-found/index.tsx` needed no change.

**5. Existing route tests set a token.** `routes.test.tsx` cases that render standard-layout routes (`/`, `/slow`, `/broken`) now sign in first, and the refusing adapter answers `/v1/user/info` with a real user; no assertion was weakened. Public standard-layout routes show the shell only when signed in, which is the new behaviour.

**6. Session-expired toast copy left unchanged.** UI-SPEC wants "Sign in again to continue." now that a redirect happens, but `http.test.ts` and `pages-i18n.test.tsx` assert "Your session ended. Reload the page to continue." and the plan forbids touching passing assertions. The copy swap (key and tests together) belongs with plan 02-13 when `/login` is a real page.

**7. Commit trailer.** The task text asked for `Co-Authored-By: Claude Opus 5.5`; the five task commits carry that. Later commits use the harness attribution.

## Known gaps carried to later plans
- `/login` is not registered until 02-13, so the redirect lands on the public Not Found page (bare layout); the browser test asserts on location, as the plan specifies. The Not Found action link to System status points at `/`, which redirects back to `/login` while signed out.
- `HOME_PATH` (`/home`) is the sanitiser fallback; the Home route arrives in 02-13.
- `purgeSession` always redirects to `/login?next=<current path>`; sign out and password change (02-28, 02-16) may want a bare `/login` and can extend the options then.
- UI-08 evidence here: user store (global), `use-user-info-request` (server state, key `[user, info]`), guard skeleton timer and retry (local), `next` parameter (URL). The sign-in mode parameter comes with 02-13. REQUIREMENTS.md was not touched, per instruction.

## Known Stubs
None.

## Threat Flags
None beyond the plan's threat model; T-02-49 (open redirect), T-02-50 (no shell flash), T-02-51 (stale 401), T-02-53 (no token in URL, logs or toasts) and T-02-53A (503 never purges) each have tests.

## Self-Check: PASSED
