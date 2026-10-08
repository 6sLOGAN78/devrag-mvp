---
phase: 03-models-knowledge-bases-and-upload
plan: 10
subsystem: llm
tags: [provider-service, test-before-save, valkey, rate-limit, ssrf, key-rotation, masked-views]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-02 url_guard; 03-04 tenant_scope; 03-05 chat driver and fake provider; 03-06 embedding driver; 03-09 credential and model structure services"
provides:
  - api/db/services/provider_service.py (ModelRequest, SaveRequest, check_request, check_model_names, save_provider, add_models, delete_provider, provider_dto, instance_dto, model_dto, list_provider_dtos)
  - common/ratelimit.py (FixedWindowLimiter, RateLimited, RateLimitUnavailable)
affects: [03-12 provider routes, 03-11, dataset create, Models page]

tech-stack:
  added: []
  patterns:
    - "Test-before-save: one tiny real call per submitted model with retries off and a short timeout, then one transactional save_instance"
    - "Fail-closed guards in a fixed order (key store, address guard, per-workspace window) all before the first provider request"
    - "Views are plain dicts; last4 and address appear only when the caller passes include_credentials=True"
    - "Provider text reaches a message only as ModelException.safe_message with the submitted key scrubbed out again"

key-files:
  created:
    - api/db/services/provider_service.py
    - common/ratelimit.py
    - test/unit_test/test_provider_policy.py
    - test/integration/test_provider_service.py
    - test/integration/test_ratelimit.py
  modified: []

key-decisions:
  - "The reason constants already existed in api/utils/reasons.py (plan 03-09); no new name was needed, so that file is unchanged"
  - "SaveRequest is keyword-only with defaults (instance=default, api_key/base_url/api_version=None) so the Change key flow can build a request from the current view"
  - "One limiter hit per save or add, however many models are tested (at most two calls per hit)"
  - "Address comparison treats no address and the provider's documented default as equal, and ignores a trailing slash"
  - "add_models refuses a name that already exists on the provider (model_exists) before calling the provider"
  - "instance_dto adds a models list of composite ids beside name/configured; provider_dto keeps the flat models list the plan names"

patterns-established:
  - "Handlers pass include_credentials=scope.subject in {owner, admin}; the service never reads a role"
  - "Tests that use the loopback fake provider must override the service host names in the Settings copy (mysql, redis, minio, es01), because on the dev stack every setting is 127.0.0.1 and internal_hosts() would deny the fake"

requirements-completed: [LLM-16, LLM-19, LLM-24, LLM-25, LLM-27, SEC-02]

duration: ~45min
completed: 2026-10-09
---

# Phase 3 Plan 10: Provider service with test-before-save, limiter and masked views Summary

**A provider is stored only after one tiny real call per model has passed: chat with 16 completion tokens, embedding with one input whose returned vector length (1..4096) becomes the recorded dimension, behind an SSRF guard, a fail-closed per-workspace Valkey window, a key-required-for-new-address rule and typed, key-free refusals.**

## Accomplishments

- `check_request` (pure): key, base URL, API version and model-list rules, including `key_required_for_new_address` keyed on `InstanceInfo.has_key` (a 5-character key leaves an empty `last4` and is still blocked) and the 128-character composite bound through `check_model_names`.
- `save_provider`: key store, SSRF guard (project hosts denied, private ranges only with `llm.allow_private_base_urls`), one limiter hit, tests, then `save_instance(replace_key=bool(key))`. A submitted key re-seals every row of the instance; without a key the stored key is opened in memory for the tests and kept; a keyless instance can move to a new address. A changed embedding dimension surfaces as `dimension_mismatch` and changes nothing.
- `add_models` tests with the stored key and address, `delete_provider` wraps the structure service, and the DTO builders keep key material out of every view.
- `FixedWindowLimiter`: `INCR` + `EXPIRE NX` + `TTL` in one pipeline on a per-call client; any Valkey or socket error becomes `RateLimitUnavailable`.

## Verification (real output)

- Red run before implementation: unit file `ModuleNotFoundError: No module named 'api.db.services.provider_service'`; integration files `ImportError: cannot import name 'provider_service' from 'api.db.services'`.
- `uv run pytest -m integration test/integration/test_provider_service.py test/integration/test_ratelimit.py -q` -> `36 passed in 17.20s` (real MySQL, real Valkey, loopback fake provider).
- `uv run pytest test/unit_test/test_provider_policy.py test/unit_test/test_layering.py -q` -> `33 passed in 0.28s`.
- `uv run ruff check` over the service, limiter, reasons file and the three test files -> `All checks passed!`. `uv run python scripts/ci/check_secrets.py` -> `secrets OK`.
- Mutation checks (restored afterwards): `replace_key=False` made `test_saving_over_an_instance_with_a_new_key_rotates_every_row` fail; removing the address guard failed all three dangerous-address cases and the private-range case.
- After the runs `tenant_model_provider`, `tenant_model` and `tenant_llm` each held 0 rows; Valkey test keys are deleted by exact name.
- Whole-suite checks (`scripts/ci/run_all.py`, full unit tier) were not run; the plan leaves them to the wave-end run.

## Task Commits

1. Task 1 (failing tests): `dfa563a`
2. Task 2 (limiter and pure policy): `5b81383`
3. Task 3 (save flow, add model, delete, views): `80971ac`

## Deviations from Plan

### Auto-fixed / additive

**1. [Rule 3 - Blocking] Test settings must rename the service hosts**
- `tenant_llm_service.internal_hosts(settings)` returns `{127.0.0.1}` on the dev stack, which would deny the loopback fake provider. The integration test builds its `Settings` copy with `mysql`, `redis`, `minio` hosts and `es.hosts` set to service names (the limiter is built from the real Valkey settings and passed in). No production code changed.

**2. [Rule 1 - Tooling] Ruff import order flipped once the module existed**
- The first `ruff --fix` ran before `provider_service` existed and sorted its import as third party; after the module existed ruff wanted it first party. The final commit carries the stable order.

The plan text "Do not commit (the orchestrator commits)" was overridden by the sequential-executor instruction; each task was committed.

## Notes for the next plans

- **03-12 (routes):** map `Kind` to HTTP as the truths state: INVALID 400 (`provider_refused`, `base_url_refused`, `dimension_unsupported`, `models_invalid`, `key_required*`, `provider_unknown`), UNAVAILABLE 503 (`provider_rate_limited` with `retry_after`, `key_store_unavailable`, `rate_limit_unavailable`), RATE_LIMITED 429 (`provider_test_rate_limited`), TIMEOUT 504, BAD_GATEWAY 502, CONFLICT 409 (`model_exists`), NOT_FOUND 404 (`provider_not_configured`). Run all service calls in the bounded executor (they use `Base.chat`, which refuses a running loop).
- Pass `include_credentials=scope.subject in {"owner", "admin"}`.
- The Change key dialog must resend the stored `base_url` and `api_version` (taken from the elevated view) with the new key and one registered model; `save_instance` stores the address exactly as given.
- `save_provider(settings, req, limiter=None)` builds a `FixedWindowLimiter(settings.redis)` when none is given; handlers may share one instance.
- A provider 429 or 503 is `provider_rate_limited` (503 UNAVAILABLE) with `retry_after` possibly `0.0`; do not treat it as falsy.
- `provider_service.py` is 363 lines in one cohesive module; the DTO builders are the natural split if it grows.

## Known Stubs

None.

## Threat Flags

None. T-03-10-01 to -10 are covered by tests: zero-request assertions for the guard, key-store, limiter and unreachable-Valkey cases, the 5-character key case, the 128/129 composite cases, the 8-character window scan of every returned structure, both values of `include_credentials`, the rotation case opening every row with the new key, and the 4096/4097 dimension bound.

## Self-Check: PASSED

- Files present: api/db/services/provider_service.py, common/ratelimit.py, test/unit_test/test_provider_policy.py, test/integration/test_provider_service.py, test/integration/test_ratelimit.py.
- Commits present: dfa563a, 5b81383, 80971ac.
