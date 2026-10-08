---
phase: 03-models-knowledge-bases-and-upload
plan: 11
subsystem: llm
tags: [llm-bundle, composite-model-id, usage-accounting, dimension-check, error-mapping]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-05 chat driver and fake provider; 03-06 embedding drivers; 03-09 get_credential, add_used_tokens, internal_hosts; 03-10 error reasons"
provides:
  - api/db/services/llm_service.py (LLMBundle, merge_usage, split_usage, bundle_error, usage_log_fields)
affects: [03-15, dataset create, ingestion, retrieval, chat]

tech-stack:
  added: []
  patterns:
    - "Resolve composite id -> credential -> driver once in the constructor; the plaintext key lives only inside the driver (a closure scrubber is the only other holder)"
    - "One report site: _report_usage is the single caller of add_used_tokens; streams report only after normal exhaustion"
    - "Usage log fields avoid the word 'token' because the log redactor masks any such field name"

key-files:
  created:
    - api/db/services/llm_service.py
    - test/unit_test/test_llm_bundle.py
    - test/integration/test_llm_bundle_flow.py
  modified: []

key-decisions:
  - "bundle_error mirrors provider_service._failure exactly (429/503 or rate-limit code -> provider_rate_limited; ERROR_MAX_RETRIES with no status -> provider_timeout; refusal codes -> provider_refused with the sanitized message), so a retried-out 429 is still a rate limit, not provider_unreachable"
  - "Usage log fields are usage_in, usage_out, usage_total (plan said prompt_tokens/completion_tokens); common.log_utils masks any extra whose name contains 'token', which would have blanked them in production"
  - "A failing counter write (PeeweeException) after a successful provider call is logged as 'llm usage not recorded' and the answer is still returned; the call was already paid for"
  - "A stream that the consumer abandons, or that fails, adds no tokens (usage is unknown)"
  - "The injected async sleep is also honoured by the synchronous embedding retry, driven on a PrivateLoop; with no sleep given the drivers use asyncio.sleep / time.sleep"
  - "The bundle also scrubs the opened key out of a refusal message through a closure (provider_service does the same at save time), so a provider echoing a key of unusual shape cannot reach a message"

patterns-established:
  - "Later plans: LLMBundle(tenant_id, composite_id, 'chat'|'embedding', expected_dimension=<kb dim>) from a worker thread; catch ServiceError only"
  - "Bundle methods raise TypeError when used for the wrong model type (chat methods on an embedding bundle and the reverse); resolution itself reports a wrong type as model_unavailable"

requirements-completed: [LLM-14, LLM-15, LLM-21, LLM-03, LLM-16]

duration: ~35min
completed: 2026-10-09
---

# Phase 3 Plan 11: LLMBundle Summary

**One entry point that turns `model@provider` or `model@instance@provider` into a tenant-keyed chat or embedding call, with typed key-free errors, a vector-size guard and exactly-once token counting, proven against the real MySQL and the loopback provider.**

## Accomplishments

- `LLMBundle(tenant_id, model_id, model_type, *, settings, expected_dimension, sleep)`: parses the composite id, loads the credential through `get_credential` (scoped to tenant, provider, instance and model type), builds `LiteLLMBase` or `build_embedder` once, and exposes `chat`, `chat_streamly`, `async_chat`, `async_chat_streamly`, `encode`, `encode_queries`, `provider`, `model`, `last_usage`.
- Usage: `last_usage` is reset at the start of every call; the provider's usage (estimate only when absent) is added to `tenant_llm.used_tokens` once after success; streams are counted after they end; a failed call or an abandoned stream adds nothing. One structured log line per call (tenant, provider, model, counts, estimated).
- Errors: every `ModelException` becomes a `ServiceError` with the provider service's reasons; unknown, foreign, wrong-type or malformed ids are `model_unavailable`; an empty key store is `key_store_unavailable`, a wrong key or tampered envelope is `key_unreadable`; none carry the key, the envelope or a cause chain.
- `encode` raises `dimension_mismatch` before usage is recorded when any vector differs from `expected_dimension`.

## Verification (real output)

- Red run (Task 1): `ModuleNotFoundError: No module named 'api.db.services.llm_service'` for the unit file and for the integration file at collection (commit `6ccc31c`).
- `uv run pytest test/unit_test/test_llm_bundle.py test/unit_test/test_layering.py -q` -> `35 passed in 0.23s`.
- `uv run pytest -m integration test/integration/test_llm_bundle_flow.py -q` -> `33 passed in 18.13s` (real MySQL, loopback fake provider; run twice, stable).
- `uv run ruff check` on the three files -> `All checks passed!`; `ruff format --check` on the module -> already formatted. `uv run python scripts/ci/check_secrets.py` -> `secrets OK`.
- Acceptance greps: no `str(exc)`, `str(e)`, `logger.exception`, or `quart` in the module; exactly one `add_used_tokens` call site (line 223); module is 295 lines.
- Mutation checks (restored afterwards): removing the dimension check failed `test_a_different_vector_size_raises_dimension_mismatch_and_adds_no_tokens`; reporting usage on every yielded piece failed the stream-count test and the log-line test.
- After the runs `tenant_llm`, `tenant_model`, `tenant_model_instance` and `tenant_model_provider` each held 0 rows.
- Whole-suite checks (`scripts/ci/run_all.py`, full unit tier) were not run; the plan leaves them to the wave-end run.

## Task Commits

1. Task 1 (failing unit and integration tests): `6ccc31c`
2. Task 2 (LLMBundle): `74db2ea`

## Deviations from Plan

### Auto-fixed / additive

**1. [Rule 1 - Bug avoided] Usage log field names**
- The plan names the extras `prompt_tokens` and `completion_tokens`. `common.log_utils.RedactingFilter` replaces the value of any extra whose name contains `token`, so the production log line would have shown the redaction marker instead of counts. Fields are `usage_in`, `usage_out`, `usage_total`; a unit test passes them through the real filter.

**2. [Rule 2 - Missing critical functionality] Counter failure and key scrubbing**
- A database error while adding to the counter is logged (no exception text) and does not discard a successful answer. The opened key is scrubbed from refusal messages with a closure, matching the provider service.

**3. [Plan wording] MAX_RETRIES mapping and credential lookup context**
- The plan's "others to BAD_GATEWAY" would have turned a rate limit that exhausted retries into `provider_unreachable`; the mapping follows `provider_service._failure` (the plan also says "same machine reasons the provider service uses"). `get_credential` opens its own `DB.connection_context()`, so the bundle does not wrap it (nesting closes the connection).

The plan text "Do not commit (the orchestrator commits)" was overridden by the sequential-executor instruction; each task was committed.

## Notes for the next plans

- Call the sync methods and the constructor from a worker thread; `chat` and `chat_streamly` refuse a running loop (driver rule). The async methods run on the caller's loop; their one counter write is a short blocking statement on that loop (the plan forbids using the default executor inside the bundle).
- Pass `expected_dimension=<tenant_model dimension or knowledgebase vector size>` for every embedding bundle that feeds an index.
- `add_used_tokens` is keyed by tenant, provider and model name (no instance), as 03-09 defined it.
- A bundle is cheap but not free (one credential read, one driver); build one per task or per request and reuse it for its batches.

## Known Stubs

None.

## Threat Flags

None. T-03-11-01 to -06 are covered by tests: foreign tenant, wrong type and unknown instance give `model_unavailable` with zero requests; repr and caplog scans for key and envelope; `dimension_mismatch` adds no tokens; retry and stream totals are exact; tampered envelope gives `key_unreadable` with no plaintext.

## Self-Check: PASSED

- Files present: api/db/services/llm_service.py, test/unit_test/test_llm_bundle.py, test/integration/test_llm_bundle_flow.py.
- Commits present: 6ccc31c, 74db2ea.
