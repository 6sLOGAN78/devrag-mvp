---
phase: 03-models-knowledge-bases-and-upload
plan: 09
subsystem: llm
tags: [aes-gcm, secretbox, peewee, mysql, tenant-model, composite-model-id, defaults]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-01 secret box and LlmSettings; 03-02 url_guard; 03-05 provider registry (resolve_provider)"
provides:
  - common/model_ref.py (ModelRef, parse_model_ref, format_model_ref, InvalidModelRef, 128-character composite bound)
  - api/utils/reasons.py (machine reason constants) and api/db/services/service_errors.py (Kind, ServiceError)
  - api/db/services/tenant_llm_service.py (seal_key, open_key, ModelCredential, get_credential, add_used_tokens, internal_hosts)
  - api/db/services/tenant_model_service.py (save_instance upsert/rotation, add_models, reads, delete_provider, get/set_defaults)
affects: [03-10 provider API, 03-11, 03-12, LLMBundle, dataset create, embedding model resolution]

tech-stack:
  added: []
  patterns:
    - "Sealed envelope in tenant_llm.api_key only; instance row holds a display mask (********+last4) and extra JSON {last4, api_base, api_version}"
    - "Reads reduce the envelope to a boolean inside SQL (api_key LIKE 'v1:%') so it never reaches Python on the list path"
    - "One public function = one DB.connection_context(); internal helpers take no context (peewee closes the connection on nested exit)"
    - "ServiceError.__str__ is the reason only; message is fixed, user-safe text"

key-files:
  created:
    - common/model_ref.py
    - api/utils/reasons.py
    - api/db/services/service_errors.py
    - api/db/services/tenant_llm_service.py
    - api/db/services/tenant_model_service.py
    - test/unit_test/test_model_ref.py
    - test/integration/test_provider_key_at_rest.py
    - test/integration/test_tenant_model_service.py
  modified:
    - test/helpers/accounts.py

key-decisions:
  - "save_instance stores api_base and api_version exactly as given (None clears). The Change key dialog must resend the stored address; the service does not merge"
  - "replace_key=True with an empty key clears the envelope and mask (keyless providers); 03-10 owns the key_required policy"
  - "An embedding NewModel must carry a dimension (1..65536) and a chat model must not, else models_invalid; max_tokens must be 1..2147483647; duplicate names in one request are models_invalid"
  - "Existing models keep max_tokens on a re-save (only new names get the request's value), so Change key cannot overwrite a tuned value"
  - "Added reason INSTANCE_INVALID for instance names the composite id or the AAD cannot hold ('|', '@', whitespace, over-long)"
  - "configured on InstanceInfo = has at least one model and (holds a sealed key or the provider needs none)"
  - "A first-save unique-index race is retried once, then mapped to model_exists"

patterns-established:
  - "Later plans call tenant_llm_service.get_credential(llm, tenant_id, ModelRef, model_type) to get an opened key in memory; it returns None when the model is not on that exact instance"
  - "Composite ids for defaults and knowledgebase.embd_id come from ModelInfo.composite (format_model_ref), never hand-built"

requirements-completed: [SEC-03, LLM-16, LLM-29, TEN-12]

duration: ~70min
completed: 2026-10-09
---

# Phase 3 Plan 09: Encrypted credential store, model structure rows and workspace defaults Summary

**Provider keys reach MySQL only as AES-256-GCM envelopes bound to tenant, provider and instance in `tenant_llm`, with provider/instance/model structure, composite model ids, atomic upsert and key rotation, workspace defaults and an atomic capped usage counter, all proven against the real MySQL.**

## Accomplishments

- Composite ids `model@provider` / `model@instance@provider` with a total bound of 128 characters (the width of `tenant.llm_id`, `tenant.embd_id`, `knowledgebase.embd_id`); `save_instance` and `add_models` refuse a model whose canonical composite would exceed it with `models_invalid` before any write.
- `save_instance` is one transaction over provider, instance, `tenant_model` and `tenant_llm`. Existing instance: upsert that keeps `tenant_model.id` and `used_tokens`; `replace_key=True` re-seals every `tenant_llm` row of the instance whether listed or not; `replace_key=False` keeps envelopes byte for byte and replaces only address fields on the instance and every row; a changed embedding dimension is `dimension_mismatch` with nothing changed; a name owned by another instance is `model_exists`.
- `InstanceInfo.has_key` comes from the stored envelope, so a 5-character key (empty `last4`) still reports `has_key` true.
- Defaults store the composite id and the `tenant_model.id`; `delete_provider` clears every default that pointed at the provider.
- `add_used_tokens` is one `LEAST(used_tokens + %s, 2147483647)` statement; 8 threads x 25 x 3 ends at exactly 600 and the cap holds.
- Test cleanup (`delete_accounts`) now removes `tenant_model`, `tenant_model_instance` and `tenant_model_provider` rows through the tenant's recorded provider ids.

## Verification (real output)

- Red run before implementation: unit file `ModuleNotFoundError: No module named 'common.model_ref'`; integration files `ImportError: cannot import name 'tenant_llm_service' from 'api.db.services'`.
- `uv run pytest -m integration test/integration/test_provider_key_at_rest.py test/integration/test_tenant_model_service.py -q` -> `32 passed in 10.20s` (real MySQL, infra stack up).
- `uv run pytest test/unit_test/test_model_ref.py test/unit_test/test_layering.py test/unit_test/test_account_helpers.py -q` -> `53 passed`.
- `uv run ruff check` over `common/model_ref.py api/db/services api/utils/reasons.py` and the four test/helper files -> `All checks passed!`.
- `uv run python scripts/ci/check_secrets.py` -> `secrets OK`.
- Mutation check: restricting the re-seal to listed models made `test_rotation_reseals_every_row_of_the_instance` fail (then restored), so the rotation test does bite.
- After the runs, no orphan `tenant_llm`, `tenant_model_provider` or `tenant_model` rows remained (three counts of 0).
- Whole-suite checks (`scripts/ci/run_all.py`, full unit tier) were not run, as the plan leaves them to the wave-end run.

## Task Commits

1. Task 1 (failing tests, account cleanup): `4ef81de`
2. Task 2 (model_ref, reasons, service errors, credential service): `529cbbb`
3. Task 3 (model structure service): `c2483e3`

## Deviations from Plan

### Auto-fixed / additive

**1. [Rule 2 - Missing validation] INSTANCE_INVALID reason and stricter input checks**
- The reason list in the plan has no name for a bad instance name. Added `INSTANCE_INVALID` to `api/utils/reasons.py` (the file says later plans add names) and used it for instance names containing `|` (which the AAD cannot bind), `@`, whitespace or over-length. Also added `models_invalid` checks for embedding dimension range, chat with a dimension, max_tokens range and duplicate names, and a `base_url_invalid` guard when the address would not fit `tenant_llm.api_base` (255) or the instance `extra` column (512). No schema change.

**2. [Rule 1 - Bug avoided] Nested `connection_context` closes the connection**
- Public functions open one `DB.connection_context()`; helpers such as `_find` and `_load` take none, because peewee closes the connection on inner exit (set_defaults calls the find logic).

Otherwise the plan was executed as written. The plan text "Do not commit (the orchestrator commits)" was overridden by the sequential-executor instruction; each task was committed.

## Notes for the next plans

- **03-10 (provider API):** call `save_instance(llm, tenant_id, provider, instance, api_key=, api_base=, api_version=, models=, replace_key=)`. Resend the stored `api_base` on Change key (the service stores exactly what it is given). `ServiceError` kinds/reasons to map: `provider_unknown`, `instance_invalid`, `models_invalid`, `model_exists` (CONFLICT), `dimension_mismatch`, `model_unavailable`, `key_store_unavailable` (UNAVAILABLE, 503), `key_unreadable`, `provider_not_configured` (NOT_FOUND). The policy "keyed instance + new address needs a new key" is not enforced here.
- Embedding dimension is recorded in `tenant_model.extra.dimension` and returned as `ModelInfo.dimension`; the dataset plan reads it from `find_model`.
- `internal_hosts(settings)` is ready to pass as `deny_hosts` to the URL guard.
- `get_credential` returns `None` for a model that is not on the named instance, and raises `ServiceError` `key_unreadable` if the envelope was moved.
- `tenant_model_service.py` is 511 lines. It is one cohesive module as the plan specifies; if it grows further, the read side (`_load`, `list_*`) is the natural split.
- Out of scope, left alone: `common/security/secretbox.py` `mask_last4` returns "" under 8 characters by design, which is why `has_key` exists.

## Known Stubs

None.

## Threat Flags

None. T-03-09-01 to -08 are covered by tests: raw-SQL 8-character window scan, `test_copied_envelope_fails`, row-count rollback proofs, the 8-thread counter, tenant-scoped `find_model`, `key_store_unavailable`, the 128/129 cases and the 5-character `has_key` case.

## Self-Check: PASSED

- Files present: common/model_ref.py, api/utils/reasons.py, api/db/services/service_errors.py, tenant_llm_service.py, tenant_model_service.py, the three test files, test/helpers/accounts.py.
- Commits present: 4ef81de, 529cbbb, c2483e3.
