---
phase: 03-models-knowledge-bases-and-upload
plan: 06
subsystem: llm
tags: [embeddings, openai-sdk, azure, ollama, tiktoken, ssrf, retry, fake-provider]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-05 rag.llm registry, ModelException/LLMErrorCode, run_with_retries, Usage/usage_from, fake provider; 03-02 url_guard"
provides:
  - rag/llm/embedding_model.py with Base, OpenAIEmbed, AzureEmbed, OllamaEmbed, build_embedder, truncate_to_tokens, classify_embedding_error
  - encode(texts) -> (vectors, total_tokens); the dimension is len(vectors[0]) as the provider returned it
  - offline tokenizer: TIKTOKEN_CACHE_DIR set from litellm's vendored cl100k_base file
affects: [03-10, 03-11, LLMBundle, provider test endpoint, KB-02 dimension recording, Phase 4 indexing]

tech-stack:
  added: []
  patterns:
    - "Sync driver, one SDK client per encode() call, closed in a context manager; service layer runs it in its bounded executor"
    - "Validate the base URL fully before any client exists, then assert_unchanged before every attempt"
    - "SDK exceptions are classified by type/status; the failure is raised outside the except block so no cause chain carries provider text"

key-files:
  created:
    - rag/llm/embedding_model.py
    - test/unit_test/test_llm_embeddings.py
  modified:
    - test/helpers/fake_provider.py

key-decisions:
  - "Token limit = min(8191, model_meta.max_tokens); the same limit applies to Ollama (the reference does not truncate there, but a uniform bound keeps input size capped)"
  - "Construction does no I/O and no validation: the Ollama /v1 refusal, missing base URL, missing Azure api_version and SSRF checks all surface as ModelException(ERROR_INVALID_REQUEST) on the first encode(), before any request"
  - "A response whose vector count differs from the batch, or whose vectors differ in length across batches, is ERROR_GENERIC; the driver otherwise returns lengths untouched (callers compare with the recorded dimension, T-03-06-03)"
  - "Provider usage of zero total is treated as missing and estimated (marked estimated=True), as the chat driver does"
  - "Ollama client strips or overrides the Authorization header per request, so an OLLAMA_API_KEY in the process environment is never sent to a tenant-chosen host"
  - "tiktoken cache dir is found with importlib.util.find_spec('litellm') (no litellm import) and set only if the cl100k file (sha1 name 9b5ad71b...) exists there"

patterns-established:
  - "Later plans build embedders with build_embedder(spec, model, key, base, version, llm_settings=, allow_private=, deny_hosts=, sleep=, timeout=) and record len(vectors[0]) as the dimension"
  - "Fake provider models: fake-redirect and fake-no-usage now also work on /v1/embeddings, the Azure embeddings path and /api/embed"

requirements-completed: [LLM-03, LLM-04, LLM-05, LLM-19, LLM-21]

duration: ~35min
completed: 2026-10-09
---

# Phase 3 Plan 06: Embedding drivers Summary

**OpenAI-SDK, Azure and Ollama embedding drivers behind `build_embedder`: batches of 16, index-ordered results, real vector length and provider token usage, tiktoken truncation that works offline, no redirects, per-attempt SSRF check, shared bounded retry, redacted errors; proven over loopback HTTP against the recording fake provider.**

## Accomplishments

- Task 1 red run: `ModuleNotFoundError: No module named 'rag.llm.embedding_model'` at collection (commit `01c5cf7`).
- `OpenAIEmbed` serves OpenAI, OpenRouter and OpenAI-compatible with `encoding_format="float"`, `max_retries=0`, `follow_redirects=False`, the settings timeout; `AzureEmbed` hits `/openai/deployments/<d>/embeddings?api-version=` with the `api-key` header (no Authorization); `OllamaEmbed` posts `model` and `input` to `/api/embed` and reads `prompt_eval_count`.
- Empty strings become a single space; 40 inputs make requests of 16, 16, 8; shuffled provider rows are re-sorted by index; a 1536-dimension and a 384-dimension fake both came back at their real length.
- Usage is the provider's; with none (or zero) it is estimated and `last_usage.estimated` is True.
- Truncation: a 20000-token text is cut to exactly 8191 tokens in a subprocess with no `TIKTOKEN_CACHE_DIR`, proxies pointed at an unroutable address and an empty `TMPDIR`; nothing was downloaded. Character fallback (`text[:limit*3]`) is tested.
- Errors: 401 gives ERROR_AUTHENTICATION with one request and no sleep; 429-once retries once; persistent 429 ends in ERROR_MAX_RETRIES after exactly `max_retries` retries; 404 and 500 are not retried; refused connection is ERROR_CONNECTION; 302 not followed for the OpenAI and Ollama paths; metadata, `es01`, `minio` and loopback-when-disallowed are refused before any request; an echoed key never appears in `safe_message`, `str`, `repr`, captured logs, and there is no chained cause.

## Verification (real output)

- `uv run pytest test/unit_test/test_llm_embeddings.py -q` -> `41 passed`
- `uv run pytest test/unit_test/test_llm_embeddings.py test/unit_test/test_llm_drivers.py test/unit_test/test_llm_registry.py test/unit_test/test_llm_shared.py test/unit_test/test_layering.py -q` -> `175 passed` (run twice, stable)
- `uv run pytest -m unit --collect-only -q test/unit_test/test_llm_embeddings.py` -> `41 tests collected`
- `uv run ruff check rag/ test/unit_test/test_llm_embeddings.py test/helpers/fake_provider.py` -> `All checks passed!`
- `uv run python scripts/ci/check_secrets.py` -> `secrets OK`
- `wc -l rag/llm/embedding_model.py` -> 361 lines; no `str(exc)`/`str(e)`; `import rag.llm.embedding_model` loads none of litellm, openai, ollama (subprocess test)

## Task Commits

1. Task 1 (failing tests, fake provider embedding scripts): `01c5cf7`
2. Task 2 (drivers, factory, truncation): `9934fb2`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fake provider lacked redirect and no-usage scripts for embeddings**
- **Found during:** Task 1
- **Issue:** the plan requires a 302-not-followed test and a usage-estimation test, but `fake-redirect` and `fake-no-usage` only worked on chat routes.
- **Fix:** added both to `/v1/embeddings`, the Azure embeddings route and `/api/embed` in `test/helpers/fake_provider.py` (plan 03-05's file; 03-09 does not touch it). Chat behaviour unchanged, 03-05 driver tests still pass.
- **Commit:** `01c5cf7`

**2. [Rule 2 - Missing critical functionality] Ollama SDK reads `OLLAMA_API_KEY` from the environment**
- `ollama.Client` attaches that key to every request, which would send a server-wide secret to a tenant-chosen base URL. A request hook now sets the tenant's key or removes Authorization. Test added.

### Plan wording not followed literally

- The plan said to locate the vendored rank directory "with importlib.resources". `importlib.resources.files("litellm....")` imports the heavy litellm package, so `importlib.util.find_spec("litellm")` is used instead (no import); the result is the same directory.
- Task text says refuse an Ollama `/v1` base URL "with ERROR_INVALID_REQUEST"; it is raised on the first `encode()` (before any request), not in the constructor.

## Notes for the next plans

- `encode` is synchronous and blocking; call it from a bounded executor. `last_usage` holds `Usage(prompt, 0, total, estimated)`.
- Callers must record `len(vectors[0])` as the dimension and compare later vectors against it (T-03-06-03); the driver guarantees all vectors in one call share a length.
- No new filterwarnings were needed for the openai and ollama SDKs.
- LLM-04 and LLM-05 are now complete on both chat (03-05) and embedding sides.

## Known Stubs

None.

## Threat Flags

None. No new network surface beyond the outbound provider call covered by T-03-06-01 through T-03-06-05.

## Self-Check: PASSED

- Files present: rag/llm/embedding_model.py, test/unit_test/test_llm_embeddings.py, test/helpers/fake_provider.py.
- Commits present: 01c5cf7, 9934fb2.
