---
phase: 03-models-knowledge-bases-and-upload
plan: 20
subsystem: ui
tags: [models-page, providers, workspace-scoped, secret-mask, llm-select, info-alert, i18n, nav-order]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-03 workspace store and useActiveWorkspace; 03-12 provider routes (credential fields only for owner and admin); 03-13 models and defaults routes; 03-27 last stack-rebuilding backend plan"
provides:
  - web/src/pages/user-setting/model (ModelsPage, ProviderRow, PROVIDERS constant, maskSecret)
  - web/src/services/model-service.ts (listProviders, listModels, getDefaults and the ProviderView, InstanceView, ModelView, DefaultsView types)
  - web/src/hooks/use-llm-request.ts (workspace-keyed query hooks and keys)
  - web/src/components/llm-select (LlmSelect) and Alert variant="info"
  - nav entry Models (/user-setting/model, Cpu, Account group, order 5)
affects: [03-21 provider dialogs, 03-22 defaults card, 03-23+ dataset forms (LlmSelect)]

tech-stack:
  added: []
  patterns:
    - "Model data keys on [\"ws\", tenantId, ...] and reads the tenant from useActiveWorkspace(), so a workspace switch changes data and role together"
    - "Services copy explicit field lists and tolerate malformed bodies; no key field exists in any model-service type"
    - "Credential line is drawn for owner and admin only; the SPA shows only what the API supplied (last4 as maskSecret)"

key-files:
  created:
    - web/src/services/model-service.ts
    - web/src/services/model-service.test.ts
    - web/src/hooks/use-llm-request.ts
    - web/src/components/llm-select/index.tsx
    - web/src/pages/user-setting/model/index.tsx
    - web/src/pages/user-setting/model/provider-row.tsx
    - web/src/pages/user-setting/model/providers.ts
    - web/src/pages/user-setting/model/secret-mask.ts
    - web/src/pages/user-setting/model/secret-mask.test.ts
    - web/src/pages/user-setting/model/models-page.test.tsx
  modified:
    - web/src/constants/api-paths.ts
    - web/src/constants/routes.ts
    - web/src/components/ui/alert.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/components/shell-i18n.test.tsx
    - web/src/routes.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "Provider display names are literals in providers.ts except OpenAI-compatible, which uses the UI-SPEC key models.provider.compatible.name (the literal would trip the no-hardcoded-copy locale scan)"
  - "ModelView carries provider: the list-models route sends it, the providers route nests models under the provider so the mapper fills it from the provider name"
  - "No Default models card or placeholder is rendered; plan 03-22 adds the card. The page already reads the defaults (useDefaultsRequest) only to draw the Default chat and Default embedding badges; a failing defaults request just drops the badges"
  - "The page test seeds the workspace store with camelCase memberships (the store's shape), not the raw snake_case server rows"

patterns-established:
  - "Plan 03-21 mounts its action buttons in ProviderRow (a marked slot in the doc comment) and its dialogs from ModelsPage; query keys to invalidate are providersQueryKey(tenantId), modelsQueryKey(tenantId, type?) and defaultsQueryKey(tenantId)"

requirements-completed: [LLM-23, LLM-28, TEN-13, SEC-02]

duration: ~1h
completed: 2026-10-09
---

# Phase 3 Plan 20: Models page, model service and shared components Summary

**The Models page (`/user-setting/model`, Account group, order 5) lists the active workspace's five providers with status, description and models; owners and admins see the masked key tail and address, members see neither and only configured providers; data is keyed per workspace, and `LlmSelect` plus `Alert variant="info"` are ready for the dialogs and defaults card.**

## Accomplishments

- `model-service.ts`: `listProviders`, `listModels(tenantId, type?)`, `getDefaults`, all `GET` with `params: { tenant_id }` and `silent: true`; explicit-field mappers (a hostile `api_key` on provider, instance and model never reaches the mapped object); non-arrays become `[]`; credential fields are `null` for member views.
- `use-llm-request.ts`: `providersQueryKey`, `modelsQueryKey`, `defaultsQueryKey` (all start with `["ws", tenantId]`), `useProvidersRequest`, `useModelsRequest(type?)`, `useDefaultsRequest`, `useModelTenantId`; `retry: false`; enabled only with a tenant id.
- `ModelsPage`: title, intro with workspace name, member-only `models-readonly-notice`, Providers card with five skeleton rows while pending, in-place `ErrorState` (noun "model providers", working Try again), member empty state ("No models configured yet"), document title "Models - devRag". `ProviderRow` shows status badge, description, credential line (owner/admin, `provider-mask` and base URL; Ollama has no key line) and model rows with type badge, dimensions and default badge.
- `Alert` gains `variant="info"` (role status, muted stripe, Info icon); the default destructive form is unchanged. `LlmSelect` renders a native select with "Not set" and one optgroup per provider, value is the composite id; unknown value shows "Not set".
- Nav orders are Home 1, System status 3, Profile 4, Models 5, API tokens 6, Team 7; the three order-pinned tests were updated deliberately. en and zh locale keys added with identical sets, including `models.refused.generic` and `models.delete.failed`.

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests (service, mask, page, nav order) | `138aed7` | red run recorded below |
| 2 Paths, service, hooks, mask, providers, alert, LlmSelect | `aed48bf` | service and mask tests green, typecheck clean except the not-yet-existing page import |
| 3 Page, row, route, locales | `202580c` | full suite green |

## Verification (real output)

Red run (before implementation), `npm run test -- --run src/services/model-service.test.ts src/pages/user-setting/model src/layouts/layouts.test.tsx src/components/shell-i18n.test.tsx src/routes.test.tsx`:

- `Error: Failed to resolve import "./model-service" from "src/services/model-service.test.ts"`, same for `"."` (models page) and `"./secret-mask"`.
- Nav-order failures: `expected [ <a ...> ] to have a length of 6 but got 5`, `expected [ '/', '/login', ...(7) ] to deeply equal [ '/', '/login', ...(8) ]`, `Unable to find an element by: [data-testid="nav-item-user-setting-model"]`, `expected [ Array(5) ] to deeply equal [ Array(6) ]`.
- `Test Files  6 failed (6)`, `Tests  6 failed | 44 passed (50)`.

Green runs:

- After Task 2: `Test Files  8 passed (8)`, `Tests  169 passed (169)` (service, mask, team, api and profile pages including the Alert consumers).
- Final, `cd web && npm run test -- --run`: `Test Files  37 passed (37)`, `Tests  677 passed (677)`.
- `npm run typecheck` exit 0 with no output beyond the banner. `npm run build` exit 0 (`built in 10.15s`, only the existing large-chunk advisory).
- `grep -rn dangerouslySetInnerHTML web/src/pages/user-setting/model` returns nothing; `grep api_key web/src/services/model-service.ts` returns nothing; `git diff --stat -- web/package.json web/package-lock.json` is empty.

Not run: the live web tier (`LIVE_BASE_URL=http://127.0.0.1:8088`); this plan adds no live test and the stack was not rebuilt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Page test fed the workspace store raw server rows**
- **Found during:** Task 3 (4 member and switching tests failed with the notice missing)
- **Issue:** `initialise` expects camelCase `Membership` objects; the first version of the test passed snake_case rows through `as never`, so `setActive("t9")` was refused.
- **Fix:** a `stored()` mapper in the test; no `as never` on store input.
- **Files modified:** web/src/pages/user-setting/model/models-page.test.tsx
- **Commit:** `202580c`

### Plan interpretation

- The plan's Task 3 text says the Default models card shell "renders the heading and ... nothing else"; the same sentence says "do not add a placeholder". Followed the second: no defaults card exists yet (plan 03-22). The `errorNoun.defaults`/`.settings` and `models.defaults.*` keys are therefore not added here either.
- Plan 03-20 lists UI-37 as a requirement but only delivers the view side; UI-37 stays pending in REQUIREMENTS.md until 03-21 and 03-22 land. LLM-23, LLM-28, TEN-13 and SEC-02 were already complete from the backend plans.

## Known Stubs

None. The page renders no disabled action; actions arrive with plan 03-21.

## Threat Flags

None. No new network endpoint or storage; T-03-20-01 to -04 are covered by the hostile-DTO tests, the member-view test (no mask, last four or address in the DOM), the grep for `dangerouslySetInnerHTML` and the `["ws", tenantId]` keys.

## Notes for plans 03-21 and 03-22

- Components and hooks: `ModelsPage` (`web/src/pages/user-setting/model/index.tsx`), `ProviderRow` (`provider-row.tsx`, props `spec`, `provider`, `defaults`, `elevated`), `PROVIDERS`, `providerName`, `findProvider` and the field rules in `providers.ts`, `maskSecret`, `LlmSelect({ models, type, value, onChange, id, disabled, notSetLabel })`, `Alert variant="info"`.
- Where to mount: row actions go in `ProviderRow` after the description (elevated only; absent, not disabled, for members); dialogs mount in `ModelsPage` (state lives there so focus can return to the row). The defaults card is a second `Card` after the Providers card in `ModelsPage`; it can use `useModelsRequest(type)` and `useDefaultsRequest()`.
- Query keys to invalidate after a write: `providersQueryKey(tenantId)`, `modelsQueryKey(tenantId, type?)` (prefix `["ws", tenantId, "models"]`), `defaultsQueryKey(tenantId)`. Tenant from `useModelTenantId()`. Path helpers already exist in `api-paths.ts`: `providersPath`, `providerPath`, `providerModelsPath`, `providerInstancesPath`, `providerInstancePath`, `modelsPath`, `modelsDefaultPath`.
- Locale prefixes in use: `models.*` (title, documentTitle, intro, readOnly, loading, providers.title, provider.*, status.*, credential.*, type.*, dimensions, badge.*, empty.*, errorNoun.providers, refused.generic, delete.failed) and `nav.models`. All other keys of the UI-SPEC "Model settings keys" table (action, dialog, field, help, submit, testing, refused.title and fallback, rateLimited, timeout, saved and friends, delete.title/body/keep/confirm, deleted, defaults.*, errors.provider.*, errors.model.*) are still to be added by 03-21 and 03-22 with their code. `models.refused` and `models.delete` already exist as parents, so add children, never a string at those keys.
- Test ids already in use: `models-page`, `models-readonly-notice`, `provider-row-{slug}`, `provider-status`, `provider-mask`, `provider-credentials`, `model-row`, `providers-list`, `providers-skeleton`. The page test asserts no button exists in the page; 03-21 must update that test (`renders no action button`) when it adds actions.
- The ModelView `provider` is the display name from the server (for example `OpenRouter`), used as the optgroup label.

## Self-Check: PASSED

Created files present (checked with `ls`), commits `138aed7`, `aed48bf`, `202580c` present in `git log`.
