---
phase: 02
scope: frontend
reviewed: 2026-10-08
depth: deep
diff_range: 5c40d8e..HEAD -- web/
files_reviewed: 118
files_reviewed_list:
  - web/src/services/http.ts
  - web/src/services/auth-service.ts
  - web/src/services/user-service.ts
  - web/src/services/team-service.ts
  - web/src/services/api-token-service.ts
  - web/src/services/system-service.ts
  - web/src/utils/authorization.ts
  - web/src/utils/safe-next.ts
  - web/src/utils/sign-out-intent.ts
  - web/src/utils/theme.ts
  - web/src/stores/user-store.ts
  - web/src/hooks/*.ts (use-auth-request, use-authorization, use-countdown, use-password-reset-request, use-profile-request, use-system-config-request, use-team-request, use-user-info-request, use-api-token-request)
  - web/src/components/require-auth.tsx
  - web/src/components/user-menu.tsx
  - web/src/components/avatar-initials.tsx
  - web/src/components/password-input.tsx
  - web/src/components/language-switch.tsx
  - web/src/components/theme-toggle.tsx
  - web/src/components/app-sidebar.tsx
  - web/src/components/session-skeleton.tsx
  - web/src/components/ui/{alert,alert-dialog,dialog,form,native-select,sheet}.tsx
  - web/src/layouts/*.tsx
  - web/src/routes.tsx
  - web/src/constants/{routes,api-paths}.ts
  - web/src/i18n/{index,language}.ts
  - web/src/locales/{en,zh}.json
  - web/src/pages/login/*
  - web/src/pages/forgot-password/*
  - web/src/pages/home/*
  - web/src/pages/user-setting/profile/*
  - web/src/pages/user-setting/api/*
  - web/src/pages/user-setting/team/*
  - web/src/pages/system-status/index.tsx, web/src/pages/not-found/index.tsx, web/src/pages/route-error/index.tsx
  - web/index.html, web/package.json, web/tsconfig.json, web/vite.config.ts, web/vitest.config.ts
  - tests read selectively (http, require-auth, user-menu, routes, authorization, no-hardcoded-copy, profile)
findings:
  critical: 0
  warning: 6
  info: 13
  total: 19
status: issues_found
---

# Phase 02: Frontend Code Review

**Reviewed:** 2026-10-08
**Depth:** deep (call chains traced across http client, guard, stores, hooks and pages)
**Verification run:** `npm run typecheck` clean; `npm run test -- --run` 30 files / 581 tests pass (the live tier was not run). Passing tests do not exercise any of the warnings below.

## Summary

The security-critical surface is in good shape. Checked and found sound:

- **Open redirect.** `sanitiseNext` rejects `//host`, `/\host`, control characters (tab/newline strip), absolute URLs and `javascript:`. The `next` value is only ever passed to react-router `navigate`, never to `location.href`.
- **Token attachment.** `isSameOrigin` gates token attachment, and protocol-relative and absolute cross-origin URLs get no `Authorization` header. The `anonymous` flag works. `sentToken` correctly prevents a stale or tokenless 401 from purging a newer session.
- **XSS.** There is no `dangerouslySetInnerHTML`, no `Trans`, and no `href`/`src` built from user data. Avatars only render through a strict base64 raster data-URL regex, SVG is not accepted, and the upload path re-encodes through a canvas after a magic-byte sniff with a 256 KB cap. The object URL is revoked in `finally`. Nickname, email and workspace names render as React text, so `escapeValue: false` is safe here.
- **Secrets in memory.** Sign-in, sign-up, password change and the three reset steps are plain async calls, not mutations, so passwords, OTP and the reset ticket never reach the mutation cache, query keys, URL or storage. The user store is not persisted. `purgeSession` clears the token, the user store and the query cache.
- **Locales.** en and zh key sets are identical, every `t()` key resolves, and interpolation variables match.

No Critical findings. The defects found are session-lifecycle and robustness gaps:

- Storage access is unguarded.
- Cross-tab token changes leave stale identity and data.
- Sign-out with an expired token violates the UI-SPEC.
- A 404 for a signed-in visitor has no session recovery.
- The session-expired copy is wrong.
- The server theme is re-applied after profile save.

## Warnings

### WR-F01: Token storage access is not guarded; blocked localStorage bricks the whole app

**File:** `web/src/utils/authorization.ts:11-24`, `web/src/services/http.ts:157-158`, `web/src/hooks/use-authorization.ts:6`

**Issue:** `getAuthorization`, `setAuthorization` and `removeAuthorization` call `localStorage` with no try/catch. Theme (`theme.ts:8-14`) and language (`i18n/index.ts:7-13`) were hardened for storage failures; the token module was not. `getAuthorization` is the `useSyncExternalStore` snapshot (`use-authorization.ts`), the request interceptor's first call, and the initial state of `LoginPage` (`login/index.tsx:116`).

**Scenario:** In a browser with site data blocked (Chrome "Block all cookies", some enterprise policies), `window.localStorage` throws `SecurityError`.
- `RootRedirect`, `RequireAuth` and `LoginPage` throw during render and land in the error boundary ("Something went wrong").
- Even `POST /auth/login` fails, because the request interceptor calls `getAuthorization()` before checking `anonymous`.
- When `setItem` throws on quota or policy after a successful login, the server has already issued a token the client cannot keep. The user sees a generic failure on every attempt.
- Nothing tests this.

**Fix:** Wrap the three storage calls in try/catch. `get` returns `null` on failure. `set` falls back to an in-memory variable held in the module, so the session works for the tab's lifetime. `remove` clears both. Add unit tests that stub `Storage.prototype.getItem/setItem` to throw.

```ts
let memoryToken: string | null = null;
export function getAuthorization(): string | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && v.length > 0 ? v : memoryToken;
  } catch {
    return memoryToken;
  }
}
export function setAuthorization(token: string): void {
  memoryToken = token;
  try { localStorage.setItem(STORAGE_KEY, token); } catch { /* memory only */ }
  notify();
}
export function removeAuthorization(): void {
  memoryToken = null;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  notify();
}
```

### WR-F02: Token change or removal in another tab does not purge the user store or query cache; stale identity and cached data survive

**File:** `web/src/utils/authorization.ts:30-43`, `web/src/components/require-auth.tsx:30-66`, `web/src/hooks/use-user-info-request.ts:8-16`

**Issue:** The `storage` event only re-renders `useAuthorization` subscribers. Nothing clears `useUserStore` or `queryClient` when the token is removed, or replaced by a different one, by another tab. `SessionRecovery` renders `<Outlet/>` whenever `data && user.id === data.id`. `data` is cached with `staleTime: Infinity`, so it never refetches.

**Scenarios (verified by tracing the code):**
1. **Account switch.** Tab 1 is signed in as owner A. Tab 2 signs in as B, which overwrites the `Authorization` key. Tab 1 keeps rendering A's nickname, role, invite form and workspace id. Every request now silently carries B's token: the interceptor reads storage per request. The Team page sends `tenantId(A)` with B's token, and the tokens page lists B's tokens under A's identity. The server rejects cross-tenant access, but the UI misattributes actions and data.
2. **Cross-tab sign-out then sign-in on the same machine.** Tab 1 is redirected to `/login` because the token is null. The API-token values, member emails and memberships of user A stay in the in-memory query cache. When user C signs in on that tab, `useApiTokensRequest` and `useMembershipsRequest` show A's cached rows first (default `staleTime: 0` refetches in the background, but cached data renders until the response arrives and is kept if the refetch errors, for example a 403 for a non-owner). This leaks A's token values and member list to C.

**Fix:** In `App` or `authorization.ts`, subscribe once and, when the stored token becomes null or differs from the last seen value and the change did not originate here, run a local purge. Also make the session-user query key depend on the token (or compare a token fingerprint held in the store) so a different token forces a refetch.

```ts
// app.tsx
useEffect(() => {
  let last = getAuthorization();
  return subscribeAuthorization(() => {
    const now = getAuthorization();
    if (now !== last) {
      last = now;
      useUserStore.getState().reset();
      client.clear();          // new token: refetch everything; null: guard redirects
    }
  });
}, [client]);
```

Add a test that dispatches a `storage` event with a new token and asserts the cache is empty and the user is refetched.

### WR-F03: Deliberate sign-out with an already-expired token shows the "Session expired" toast and performs an extra `next` redirect

**File:** `web/src/components/user-menu.tsx:31-48`, `web/src/services/http.ts:121-133`, `web/src/services/http.ts:186-190`

**Issue:** `signOut` calls `logout()` while the token is still stored and before `beginSignOut()`. `/api/v1/auth/logout` is jwt-gated (`conf/routes.yaml:32`), so an expired or revoked token returns 401. The response interceptor takes the purge path because `sentToken === getAuthorization()`. `purgeSession()` runs with default options: it toasts "Session expired" and navigates to `/login?next=<current path>`. Then `finally` runs the intentional purge and navigates to bare `/login`. UI-SPEC (line 153) requires "no toast on deliberate sign-out". An expired session followed by clicking Sign out is the most common way people sign out.

**Evidence:** `user-menu.test.tsx:239-263` covers only a network failure and a 500, never a 401 on logout.

**Fix:** Call `beginSignOut()` before `await logout()` and have the interceptor's purge consult `isSigningOut()` (skip toast and navigation). Alternatively, give `logout()` a request option such as `noSessionPurge: true` honored in `shouldPurge`. Add a test for logout answering 401.

### WR-F04: "Session expired" toast copy is wrong and the test locks the wrong copy in

**File:** `web/src/locales/en.json:100-103`, `web/src/locales/zh.json:100-103`, `web/src/services/http.test.ts:123-124`

**Issue:** UI-SPEC (lines 284 and 504) specifies "Session expired" / "Sign in again to continue." The shipped description is "Your session ended. Reload the page to continue." (zh: "请重新加载页面以继续"). This is leftover Phase 1 copy. Phase 2 redirects client-side to `/login` (no reload), so telling the user to reload is incorrect and contradicts the contract. `http.test.ts:124` asserts the old English string literally, so the test enforces the deviation.

**Fix:** Change the description to "Sign in again to continue." (zh: "请重新登录以继续。"). Update the test to use the key or the new copy.

### WR-F05: A signed-in visitor on an unknown URL gets the app shell with no session recovery, no account menu and no sign-out

**File:** `web/src/routes.tsx:21-23`, `web/src/layouts/public-standard-layout.tsx:6-8`, `web/src/components/user-menu.tsx:26`, `web/src/constants/routes.ts` (`path: "*"`, `auth: "none"`)

**Issue:** The `*` route is `auth: "none"` and the layout is chosen by `useAuthorization() === null` alone. It renders `StandardLayout` whenever a token string exists, but the `SessionRecovery` that fills `useUserStore` never runs on this branch.
- A fresh load of `/typo` (bookmark, pasted link, or an old route) with a stored token shows header and sidebar with `UserMenu` returning `null` (`user === null`). There is no way to sign out from the page.
- A revoked or expired token is never detected here. The shell looks signed in until another page is opened.

**Evidence:** `routes.test.tsx:101-106` only asserts `layout-standard` exists and does not check the user menu or the session request.

**Fix:** Make the public-standard branch run session recovery when a token exists, for example render `<RequireAuth/>`'s `SessionRecovery` around `StandardLayout` for the signed-in case, or have `PublicStandardLayout` call `useUserInfoRequest()` and show the bare layout until it resolves. Extend the test to assert the account menu appears.

### WR-F06: Saving the profile re-applies the server's stored theme and can override the user's "System" choice

**File:** `web/src/components/require-auth.tsx:36-41`, `web/src/hooks/use-profile-request.ts:27-31`, `web/src/utils/theme.ts:60-65`

**Issue:** The `SessionRecovery` effect depends on `[data]` and calls `applyUserLanguage` and `applyUserColourSchema` on every change of the cached user. `useProfileRequest.onSuccess` calls `queryClient.setQueryData(USER_INFO_QUERY_KEY, apply)`, which creates a new `data` object. If the user previously chose Dark (written to the server) and later chose System (stores nothing and removes the local key), then saving a nickname makes `readStored()` null and the cached `colorSchema === "Dark"`, so `applyTheme("dark")` fires. The page flips to dark under a light OS theme without any theme action. `saveSettingQuietly` also updates only the Zustand copy, not the cache, so the cache keeps the stale value (this field is otherwise unread, see IN-F13).

**Fix:** Apply the server preferences once per session recovery, keyed on `data.id` (or on first load), not on every cache update:

```ts
const appliedFor = useRef<string | null>(null);
useEffect(() => {
  if (!data) return;
  useUserStore.getState().setUser(data);
  if (appliedFor.current !== data.id) {
    appliedFor.current = data.id;
    applyUserLanguage(data.language);
    applyUserColourSchema(data.colorSchema);
  }
}, [data]);
```

## Info

### IN-F01: API token appears in the DELETE URL path

**File:** `web/src/constants/api-paths.ts:40-42`, `web/src/services/api-token-service.ts:33`

`DELETE /api/v1/system/tokens/{token}` places a live credential in the request URL. This is mandated by `docs/04-api/system-api.md:79` and R-127 masks it in Nginx, Go and Python logs. The residual exposure is browser devtools, any intermediary that logs full URLs, and crash reports. No change is needed now. Record it as accepted risk and make sure no future client telemetry captures request URLs.

### IN-F02: Access token is persisted in localStorage, and the copied token stays on the clipboard

**File:** `web/src/utils/authorization.ts:2`, `web/src/pages/user-setting/api/clipboard.ts:12`

Docs mandate localStorage (`docs/02-frontend/api-client.md:9`; UI-SPEC line 256), so this is by design. Any XSS therefore exfiltrates the session token. No XSS sink was found, but the page ships no CSP (`index.html`), so there is no defence in depth. Recommend a strict CSP at the Nginx layer in a later phase (outside this review's scope). The Clipboard API cannot be cleared reliably, so the copied API token persists until overwritten.

### IN-F03: Successful registration followed by a failed auto sign-in leaves the form in a misleading state

**File:** `web/src/hooks/use-auth-request.ts:28-31`, `web/src/pages/login/sign-up-form.tsx:41-53`

`signUp` runs `register` then `signIn`. If `signIn` fails (429, 503, network), `authErrorMessage(..., "register")` shows a generic or throttle message and the sign-up form keeps all fields. The account already exists, so a retry is answered by the duplicate-email message. Distinguish the two phases: after a successful register, a sign-in failure should switch to the sign-in form (email prefilled) with "Account created. Sign in to continue."

### IN-F04: Concurrent 401 handling can double toast for non-silent requests (latent), and the test cannot detect it

**File:** `web/src/services/http.ts:108-110, 186-190`, `web/src/services/http.test.ts:110-125`

After the first 401 purges, later in-flight 401s no longer match `shouldPurge` (the stored token is gone), so they fall through to `toastFor(error, silent)`. Every Phase 2 service call is `silent: true`, so this does not reproduce today. A later phase that adds a non-silent request will show "Request failed / Code 401" next to "Session expired". The test at lines 110-125 issues two sequential requests and only counts the session-description text, so it would pass even with the extra toast. Treat any 401 on a request that sent a token (stale or current) as session-ending and never toast it separately.

### IN-F05: Completing a password reset purges an unrelated local session

**File:** `web/src/hooks/use-password-reset-request.ts:18`

`resetPassword` always calls `purgeSession({toast:false,navigate:false})`. The page is public, and a signed-in visitor can reset another account's email. The server only invalidates tokens for the account being reset, so the local session of the unrelated signed-in user is dropped unnecessarily. Purge only when `useUserStore.getState().user?.email` equals the reset email, and otherwise leave the session alone.

### IN-F06: Any 400 on the final reset step is treated as "ticket refused"

**File:** `web/src/pages/forgot-password/password-step.tsx:46-49`

`isRefusal` is any HTTP 400. If the server ever rejects the new password with a 400 validation message (policy or character rules the client schema does not mirror), the page discards a still-valid ticket and sends the user back to step 1 to request a new emailed code. R-119 says reset failures are one generic 400, so whether the server distinguishes the two is unverified (backend scope). If it does distinguish them, key the bounce on the envelope code or message rather than on the status.

### IN-F07: Service mappers dereference a possibly null `data`

**File:** `web/src/services/team-service.ts:86`, `web/src/services/api-token-service.ts:29`

`toMember(await request(...))` and `toApiToken(await request(...))` throw a `TypeError` if the server answers success with `data: null` or no `data` field. A body without `data` is also not recognised as an envelope by `isEnvelope`, so the whole body would be passed through. The invite or create has already succeeded server-side, but the UI shows a failure and (for create) loses the token display. Guard with a type check and treat a malformed success as a distinct error.

### IN-F08: Confirmation dialogs render blank title and body during the close animation

**File:** `web/src/pages/user-setting/team/workspace-card.tsx:123,166-168`, `web/src/pages/user-setting/team/joined-card.tsx:84-85`

`describe(null, ...)` returns empty strings, and `JoinedCard` passes `target?.tenantName ?? ""`. When `setPending(null)` or `setTarget(null)` runs after the request, the dialog is still animating out (`data-[state=closed]:animate-out`), so the title flashes empty and the remaining text reads "Leave ''?". Keep the last non-null value in a ref while the dialog is closing.

### IN-F09: String-system test scans only four files

**File:** `web/src/constants/no-hardcoded-copy.test.ts:12`

`MIGRATED` lists `system-status`, `not-found`, `route-error` and `http.ts`, so none of the Phase 2 pages or components are covered. The per-page `pages-i18n.test.tsx` partly compensates, but a hard-coded English string added to login, team or tokens pages is not caught. Extend the scan to `/src/pages/**` and `/src/components/**`, excluding the endonyms in `language-switch.tsx`.

### IN-F10: Node types leak into browser source

**File:** `web/tsconfig.json:23`

Adding `"node"` to `types` for the whole `src` tree means Node globals (`process`, `Buffer`, `NodeJS.Timeout` typing for `setTimeout`) typecheck in browser code. `token-row.tsx:28` already works around the timer type. Scope Node types to test, config and tooling files using a second tsconfig (the removed `tsconfig.node.json` role).

### IN-F11: Copy-confirmation timer can be armed after unmount

**File:** `web/src/pages/user-setting/api/token-row.tsx:41-48`

The cleanup effect clears the timer only at unmount. `copy()` awaits the clipboard and then calls `setCopied(true)` and arms a new timeout. If the row is deleted or unmounted while the write is pending, the timer is created after cleanup and runs `setCopied(false)` on an unmounted component. It is harmless in React 18 but sloppy. Guard with a mounted ref.

### IN-F12: Account-enumeration surface in copy

**File:** `web/src/pages/login/auth-error.ts:19-21`, `web/src/pages/user-setting/team/errors.ts:43-49`

These are documented and accepted designs: sign-up shows the server message for duplicate email (UI-SPEC flag 1), and the invite form shows the server's "no active account" message (R-107, R-126). Login and forgot-password copy is properly generic ("If an account exists for {{email}}..."). Noted for the record only. The throttle messages (429) are fixed text.

### IN-F13: Dead store fields and a hidden duplicate file control

**File:** `web/src/hooks/use-profile-request.ts:53-58`, `web/src/pages/user-setting/profile/profile-card.tsx:101-111`

- `saveSettingQuietly` updates `language` and `colorSchema` in the Zustand user, but nothing reads those fields. They are only used from the fetched `data` in the recovery effect (see WR-F06). Either remove the writes or have the effect read the store.
- The hidden `<input type=file>` carries an `aria-label` and `sr-only` styling with `tabIndex=-1`. Screen reader virtual-cursor users still reach a second, duplicate "Change avatar" control. Add `aria-hidden="true"` to the input (the button is the accessible path).

---

_Reviewed: 2026-10-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

## Fix status

Fixed on 2026-10-08. Every fix landed test-first; the only pre-existing expectation changed is the session-expired toast text (WR-F04), corrected to the approved UI-SPEC copy. Frontend decisions are recorded as R-134 in `.planning/DECISIONS.md`.

| Finding | Status | Commit or reference |
|---|---|---|
| WR-F01 | fixed: token storage never throws, in-memory fallback | 51e1e07 |
| WR-F02 | fixed: cross-tab token change drops user store and query cache | 23cb5a5 |
| WR-F03 | fixed: sign-out intent set before logout, a 401 on logout shows no toast and no `next` | 0a4e2d5 |
| WR-F04 | fixed: toast copy matches UI-SPEC | 23a29cb |
| WR-F05 | fixed: session recovery wraps the shell on the public Not Found page | d6d313d |
| WR-F06 | fixed: server theme and language apply once per recovered user | 3f5a415 |
| IN-F01 | deferred to B-30: the token in the DELETE path is mandated by docs and masked server-side (R-127, R-131); client telemetry must redact it | B-30 |
| IN-F02 | deferred to B-30: localStorage is mandated by docs; a strict CSP is a Nginx hardening decision | B-30 |
| IN-F03 | fixed | b7f3cf0 |
| IN-F04 | fixed | 04b45a8 |
| IN-F05 | fixed | c889cd4 |
| IN-F06 | fixed | 53b6c80 |
| IN-F07 | fixed | 68affb0 |
| IN-F08 | fixed | 30288a9 |
| IN-F09 | fixed | d4a7109 |
| IN-F10 | deferred to B-30: a second tsconfig changes the `tsc -b` build graph | B-30 |
| IN-F11 | fixed | d467a27 |
| IN-F12 | no change: documented, accepted design (UI-SPEC flag 1, R-107, R-126) | none needed |
| IN-F13 | deferred to B-30: the `aria-hidden` input and the mirrored store fields are pinned by existing tests | B-30 |

Backend follow-through (R-129, R-130): the register form validates and canonicalises email like the server (583e658), and a 413 on profile or avatar save shows a translated sentence (8dc8202). 415 and 403 answers fall through to the generic or short server message and do not crash.

Verification: `npm run test -- --run` (32 files, 621 tests), `npm run typecheck`, `npm run build`, live `npm run test:live` (36), `run_tests.py -m "integration or e2e"` (313, includes the real-browser SPA tests) and `go test -tags=integration,e2e ./...` all passed against the stack rebuilt from HEAD.
