---
phase: 03-models-knowledge-bases-and-upload
plan: 21
subsystem: ui
tags: [models-page, provider-dialogs, test-before-save, key-handling, error-classification, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-20 Models page, ProviderRow, model-service reads, query keys; 03-12 provider routes; 03-10 provider service rules"
provides:
  - web/src/services/model-service.ts (saveProvider, addModel, deleteProvider, registeredModelFor, PROVIDER_TEST_TIMEOUT_MS)
  - web/src/hooks/use-llm-request.ts (useSaveProviderRequest, useAddModelRequest, useDeleteProviderRequest, clearMutation)
  - web/src/pages/user-setting/model (ProviderDialog, AddModelDialog, DeleteProviderDialog, schemas, errors, dialog-parts)
affects: [03-22 defaults card and the live Models journey]

tech-stack:
  added: []
  patterns:
    - "A provider call result is classified by HTTP status plus data.reason into one i18n key; only a 400 provider_refused carries server text (bounded to 300, text node)"
    - "Dialog content owns the form: closing, Esc and success unmount it, which clears the typed key, aborts the request and resets the mutation"
    - "Change key / Change address send exactly one registered model taken from the provider view (registeredModelFor) plus a typed key or the new address"

key-files:
  created:
    - web/src/pages/user-setting/model/provider-dialog.tsx
    - web/src/pages/user-setting/model/add-model-dialog.tsx
    - web/src/pages/user-setting/model/delete-provider-dialog.tsx
    - web/src/pages/user-setting/model/dialog-parts.tsx
    - web/src/pages/user-setting/model/schemas.ts
    - web/src/pages/user-setting/model/schemas.test.ts
    - web/src/pages/user-setting/model/errors.ts
    - web/src/pages/user-setting/model/errors.test.ts
    - web/src/pages/user-setting/model/provider-dialogs.test.tsx
  modified:
    - web/src/services/model-service.ts
    - web/src/services/model-service.test.ts
    - web/src/hooks/use-llm-request.ts
    - web/src/pages/user-setting/model/index.tsx
    - web/src/pages/user-setting/model/provider-row.tsx
    - web/src/pages/user-setting/model/models-page.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "http.ts needed no change: the error interceptor already copies the envelope data (so data.reason) onto ApiError for non-2xx answers, and a 400 never reaches the 401 purge"
  - "providerErrorKey returns {key, text?, field?, refusal}; a provider refusal is the only answer with server text, every other answer has fixed copy chosen by status and reason"
  - "Three extra copy keys (models.error.modelExists, addressRefused, dimension) so the 409 model_exists and the 400 base_url_refused / dimension_* answers are not worded as a generic failure"
  - "The test-duration line says up to 40 seconds (two 20 s server tests), under the 45 s client timeout (checker flag 5)"
  - "Dialogs stay mounted with open=false after closing so Radix runs onCloseAutoFocus; their content, and therefore every typed value, is unmounted on close"
  - "Mutation onSettled returns the invalidation promise, so the dialog closes after the list has been refetched and the new row buttons exist when focus returns"

patterns-established:
  - "Pattern: the Models page decides focus return: the opening button if still connected, else the row's first button, else the Providers title (after a delete, always the title)"

requirements-completed: [LLM-24, LLM-25, LLM-27, SEC-02, SEC-03]

duration: ~1h30m
completed: 2026-10-09
---

# Phase 3 Plan 21: Provider dialogs Summary

**Owners and admins can set up, re-key, re-address, extend and delete a provider from the Models page: the primary button is "Test and save", the typed key lives only in a hardened password field and leaves memory on close, and a refused key is shown inline without touching the session.**

## Accomplishments

- `model-service.ts`: `saveProvider` (PUT, body only, 45 s, silent, abortable), `addModel` (POST to `/providers/{slug}/instances` with models only), `deleteProvider` (DELETE with `tenant_id` param, 30 s), `registeredModelFor` (first chat model, else first embedding model, name and type only). Blank key, address and version are omitted from the body.
- `use-llm-request.ts`: three mutations with `retry: false`, `gcTime: 0`, `onSettled` invalidating the providers, models and defaults keys of the tenant the call was made for; `clearMutation` calls `reset()` in the dialogs' `finally`.
- `schemas.ts`: `providerSchema(spec, mode, current)` (URL rule, Ollama `/v1`, Azure endpoint and version, key rules, at least one model with the error under the second field; change mode has no model rule and requires a newly typed key when the address or API version changed for a keyed provider) and `addModelSchema`.
- `errors.ts`: status and `data.reason` table. 400 `provider_refused` shows the provider's reason (<= 300 characters) under "{provider} refused this configuration"; 429, 503 `provider_rate_limited` (busy copy), 503 `key_store_unavailable` and others (model settings unavailable), 504 and client timeout, 502 and network, 403, 409 `model_exists`, 400 `key_required*` (key field error), and a catch-all. No copy uses session, sign in or unauthorized.
- Dialogs: `ProviderDialog` (set up, change key, change address), `AddModelDialog`, `DeleteProviderDialog` (AlertDialog, focus on "Keep provider", plural body, inline failure), sharing `dialog-parts.tsx` (shell with pending-aware overlay, failure alert that takes focus, status line, footer). Pending state: fields read-only, button `aria-busy` and `aria-disabled`, one request only, Esc and Close abort.
- `ProviderRow` gets the actions (owner and admin only; absent for members). `ModelsPage` holds dialog state, closes on workspace or role change and returns focus.
- en and zh keys added with parity (zh drafts, B-18).

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests (schemas, errors, service writes, dialogs, updated page test) | `fc5c891` | red run below |
| 2 Service writes, hooks, schemas, errors, locale keys | `716666a` | 130 tests green for the targeted files |
| 3 Dialogs, row actions, page wiring | `fd5f897` | full suite green |

## Verification (real output)

Red run (before implementation), `npm run test -- --run src/pages/user-setting/model src/services/model-service.test.ts`:

- `Test Files  5 failed | 1 passed (6)`, `Tests  56 failed | 11 passed (67)`.
- Failures by cause: `TypeError: saveProvider is not a function` (4), `registeredModelFor is not a function` (3), `addModel`/`deleteProvider is not a function`, and `Unable to find an accessible element with the role "button" and name "Set up OpenAI"` (and the Change key, Add model, Delete and Ollama variants) for the dialogs. `schemas.test.ts` and `errors.test.ts` could not import `./schemas` and `./errors`.

Green runs:

- After Task 2: `npm run test -- --run src/pages/user-setting/model/schemas.test.ts src/pages/user-setting/model/errors.test.ts src/services src/locales` -> `Test Files  6 passed (6)`, `Tests  130 passed (130)`.
- After Task 3, `src/pages/user-setting/model`: `Test Files  5 passed (5)`, `Tests  115 passed (115)`.
- Final, `cd web && npm run test -- --run`: `Test Files  40 passed (40)`, `Tests  784 passed (784)` (the stderr lines `Error: chunk failed` and `Error: shell failed` come from the existing route-error-boundary tests).
- `npm run typecheck` exit 0, no diagnostics. `npm run build` exit 0 (`built in 8.93s`, only the existing large-chunk advisory).
- `grep` for `dangerouslySetInnerHTML`, `localStorage`, `sessionStorage`, `console.` in the model page sources, hook, service and errors module: nothing. `git diff --stat -- web/package.json web/package-lock.json`: empty.

Not run: the live web tier (`LIVE_BASE_URL=http://127.0.0.1:8088`); this plan adds no live test and the stack was not rebuilt (plan 03-22 owns the live Models journey).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Locale keys moved from Task 3 to Task 2**
- **Found during:** Task 2 (the errors test resolves each returned key against en.json)
- **Issue:** the Task 2 verify command could not pass without the keys the error classification returns.
- **Fix:** all en and zh keys were added in the Task 2 commit instead of Task 3.
- **Commit:** `716666a`

**2. [Rule 1 - Bug] Page test file left with a syntax error by the first edit**
- **Found during:** Task 2 typecheck (`models-page.test.tsx(322,1): error TS1005`)
- **Issue:** replacing the "renders no action button" test dropped the closing `});` of its describe block; the Task 1 commit therefore carried a file that did not parse (it was part of the red run).
- **Fix:** closing brace restored in the Task 2 commit; the test now asserts the exact owner button list.

### Additive decisions

- Three copy keys beyond the UI-SPEC table: `models.error.modelExists` ("That model is already added."), `models.error.addressRefused`, `models.error.dimension`. The plan said "anything else gives the generic fallback"; those three answers have clear causes and the generic sentence would mislead.
- Change dialogs send the address and API version only for providers whose table row has them (Azure, Ollama, OpenAI-compatible); OpenAI and OpenRouter send no `base_url`, as the plan states, even though the elevated view returns the documented default address.
- `instance_name` is always `"default"`; the Models page manages that one instance, as the provider routes default to it.
- `dialog-parts.tsx` is a new file (shared shell, alert, status line and footer), not in the plan's file list, to keep the three dialogs small.

## Known Stubs

None. Every dialog is wired to the provider routes of plan 03-12.

## Threat Flags

None. T-03-21-01 (key retention): `provider_key` password input with autofill opt-outs, `gcTime: 0` plus `reset()`, form unmounted on close, tests read the mutation cache, the query cache and the DOM for the key. T-03-21-02: change mode requires a typed key after an address or version change and shows the server's `key_required_for_new_address` under the key field. T-03-21-03: tests assert the token, user store, page, title and toasts are unchanged after a 400 refusal and that a real 401 still ends the session. T-03-21-04: reason text is a text node, bounded to 300 characters, markup stays text. T-03-21-05: `inFlight` guard and `aria-disabled`; a second click sends no request. T-03-21-06: buttons are absent for members and the 403 answer has its own copy.

## Notes for plan 03-22

- `ModelsPage` (`index.tsx`) now holds `dialog`/`open` state and the Providers `CardTitle` has `ref`, `tabIndex={-1}` and `data-testid="providers-title"`; the defaults card should be a second `Card` after the Providers card.
- All write mutations invalidate `providersQueryKey`, `["ws", tenantId, "models"]` and `defaultsQueryKey` of the call's tenant, so a defaults card using `useModelsRequest(type)` and `useDefaultsRequest()` refreshes after any provider write or delete.
- Locale keys already present: `models.action.*`, `models.dialog.*`, `models.field.*`, `models.help.*`, `models.submit`, `models.testing`, `models.refused.*`, `models.rateLimited`, `models.timeout`, `models.providerBusy`, `models.providerDown`, `models.keyStoreDown`, `models.error.*`, `models.saved`, `models.savedHint` ("Choose default models below ..."), `models.updated`, `models.modelAdded`, `models.delete.*`, `models.deleted`, `errors.provider.*`, `errors.model.*`. Still to add: `models.defaults.*`, `models.errorNoun.defaults` and `.settings`.
- Test ids available for the live test: `provider-setup`, `provider-add-model`, `provider-change`, `provider-delete`, `provider-dialog`, `provider-form`, `field-provider-key`, `field-base-url`, `field-api-version`, `field-chat-model`, `field-embedding-model`, `field-model-id`, `field-model-type`, `provider-submit`, `provider-test-status`, `provider-refusal` (provider said no), `provider-error` (any other failure), `provider-delete-dialog`, `provider-delete-error`.
- The live "bad key" assertion needs a server that really refuses: the dialog shows `provider-refusal`, the path stays `/user-setting/model`, the stored token is unchanged and no "Session expired" toast exists. After a refusal the key field still holds the typed value (hidden), by design.
- A saved key's mask after set up comes from the refetched list (`provider-mask`, last four); the SPA never holds it.

## Self-Check: PASSED

- Files present: provider-dialog.tsx, add-model-dialog.tsx, delete-provider-dialog.tsx, dialog-parts.tsx, schemas.ts, errors.ts and the three new test files (checked with `ls`).
- Commits present in `git log`: fc5c891, 716666a, fd5f897.
