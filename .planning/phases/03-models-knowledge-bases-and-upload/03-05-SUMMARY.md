---
phase: 03-models-knowledge-bases-and-upload
plan: 05
subsystem: llm
tags: [litellm, providers, chat-driver, ssrf, retry, stream-sanitizer, fake-provider]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-01 LlmSettings and litellm 1.103.2 pin; 03-02 common.net.url_guard and key-shape redaction"
provides:
  - rag/llm provider registry (five providers, slug, LiteLLM prefix, default base URL, key/base-URL requirements, Ollama /v1 shape check)
  - ModelException and LLMErrorCode (rag/llm/errors.py), bounded retry loop (retry.py), Usage and StreamSanitizer (stream.py)
  - LiteLLMBase chat driver with whitelist, reasoning-model handling, error classification, no-redirect clients, per-attempt SSRF guard
  - test/helpers/fake_provider.py recording loopback provider (OpenAI, Azure, Ollama shapes, scripted failures) reused by later driver and route tests
affects: [03-06, 03-10, 03-11, LLMBundle, provider test endpoint, embedding drivers, live tests]

tech-stack:
  added: []
  patterns:
    - "Per-call httpx.AsyncClient(follow_redirects=False) with a response hook that captures the failed body, handed to litellm as client= (OpenAI/Azure via openai SDK clients, Ollama via an AsyncHTTPHandler whose client is replaced)"
    - "Failure text comes from the captured error body and passes through ModelException (parse, redact, truncate to 200); the provider exception text is discarded"
    - "Fake third-party server: Quart under Hypercorn on an inherited ephemeral-port socket (fd:// bind) in its own thread, readiness by wait_until"

key-files:
  created:
    - rag/llm/__init__.py
    - rag/llm/model_meta.py
    - rag/llm/errors.py
    - rag/llm/retry.py
    - rag/llm/stream.py
    - rag/llm/chat_model.py
    - test/helpers/fake_provider.py
    - test/unit_test/test_llm_registry.py
    - test/unit_test/test_llm_shared.py
    - test/unit_test/test_llm_drivers.py
  modified:
    - pyproject.toml

key-decisions:
  - "402 maps to ERROR_INVALID_REQUEST (must_haves truth and RESEARCH table); the task text said ERROR_QUOTA. provider_status=402 stays on the exception so the API edge can say credits are exhausted. ERROR_QUOTA remains in the enum, unused"
  - "max_tokens is not on the documented ALLOWED_GEN_CONF_KEYS set, so sanitize_gen_conf keeps it explicitly for ordinary models and converts it to max_completion_tokens for o1/o3/o4 names; the whitelist itself is exactly the documented 20 keys"
  - "A retryable error with max_retries=0 propagates unchanged; ERROR_MAX_RETRIES wraps only when at least one retry happened (it keeps provider_status and retry_after so the edge can still answer 503 with Retry-After)"
  - "Retry-After is capped at 30 s so a hostile or buggy header cannot park a worker"
  - "extra_headers is on the whitelist but is dropped by the driver unless it was built with trust_extra_headers=True (server code only), because it can override Authorization (T-03-05-04)"
  - "Connection failures: litellm reports a refused connection as a 500 InternalServerError; with no captured error response the driver maps it to ERROR_CONNECTION (non-retryable), not ERROR_SERVER"
  - "Sync chat_streamly runs the async generator on a private event loop; sync chat/chat_streamly raise RuntimeError inside a running loop"
  - "Streaming: opening the stream is retried, a failure mid-stream is raised and not replayed (replay would duplicate shown text); async_chat_streamly yields str deltas only and sets last_usage"
  - "The documented public default base URLs skip the URL guard (public https hosts); every other base URL is validated before each attempt and re-validated with assert_unchanged on retries"
  - "pytest filterwarnings: two third-party pydantic warnings raised inside litellm (ReadOnly TypedDict item; deprecated instance attribute access) are ignored. With filterwarnings=error they turned the first streamed chunk into a failure"

patterns-established:
  - "Later plans import ModelException and LLMErrorCode from rag.llm.errors, run_with_retries/arun_with_retries from rag.llm.retry, Usage from rag.llm.stream, resolve_provider and validate_base_url_shape from rag.llm"
  - "Driver construction: LiteLLMBase(spec, model, api_key, api_base, api_version, llm_settings=, allow_private=, deny_hosts=, sleep=, timeout=, trust_extra_headers=)"
  - "Contract tests use the fake_provider fixture (one server per test) or running_fake_provider() for module scope; model names fake-401, fake-402, fake-404, fake-429, fake-429-once, fake-500, fake-filter, fake-secret-echo, fake-redirect, fake-no-usage select scripted behaviour; slow_url never answers until teardown"

requirements-completed: [LLM-01, LLM-02, LLM-17, LLM-18, LLM-19, LLM-20, LLM-22]

duration: ~75min
completed: 2026-10-09
---

# Phase 3 Plan 05: Provider registry and LiteLLM chat driver Summary

**Five-provider registry plus a LiteLLM chat driver that never follows redirects, re-validates the base URL on every attempt, maps failures by type and status with redacted provider messages, retries only rate limits and timeouts through one bounded loop, and is proven over real loopback HTTP against a recording fake provider.**

## Accomplishments

- Task 1 red run: all three new modules failed at collection with `ModuleNotFoundError: No module named 'rag.llm'`; the fake provider imports and serves on its own (checked with a scratch client against every endpoint shape).
- Registry: OpenAI, Azure-OpenAI, Ollama, OpenRouter, OpenAI-API-Compatible with slugs, prefixes (`openai/`, `azure/`, `ollama_chat/`, `openai/`, `openai/`), default base URLs for OpenAI and OpenRouter only, key and base-URL requirements, `validate_base_url_shape` (`base_url_required`, `ollama_base_url_has_v1`). Model metadata seeded for the five documented models with a conservative default.
- Shared modules stay small and SDK-free: `errors.py` (codes, exception, redact-then-truncate `safe_text`), `retry.py` (delay `min(8, 0.5*2^n)` plus jitter, raised to a capped Retry-After; sync and async loops with injected sleep), `stream.py` (Usage, control-character stripping, partial JSON fragments ignored, usage taken from any chunk including a final empty-choices chunk).
- Driver: Bearer to `/v1/chat/completions` for OpenAI, OpenRouter and compatible; `api-key` header plus `api-version` query to `/openai/deployments/{d}/chat/completions` for Azure; `/api/chat` without `/v1` for Ollama. Streaming sends `stream_options.include_usage` and yields content deltas only; usage is reported for streamed and non-streamed calls, estimated with tiktoken (marked `estimated`) only when the provider reports none or all zeros.
- Safety verified by tests: 302 not followed (OpenAI path and Ollama path), `169.254.169.254`, `[fd00:ec2::254]`, `es01`, `minio` refused before any request, loopback refused when private is not allowed, fake key echoed by the provider masked in `safe_message`, `str`, `repr` and captured logs, `extra_headers` dropped for untrusted callers, and `import rag.llm.chat_model` (and every other `rag.llm` module) imports neither `litellm` nor `openai` (subprocess check).

## Verification (real output)

- `uv run pytest test/unit_test/test_llm_registry.py test/unit_test/test_llm_shared.py test/unit_test/test_llm_drivers.py test/unit_test/test_layering.py -q` -> `134 passed` (run three times, stable)
- `uv run pytest -m unit --collect-only -q <the three files>` -> `127 tests collected` (no file deselected for a missing marker)
- `uv run pytest test/unit_test scripts/ci/tests -m unit -q` -> `1196 passed, 1 skipped` (full unit tier, after the pyproject warning-filter change)
- `uv run ruff check rag/llm test/helpers/fake_provider.py test/unit_test/test_llm_*.py` -> `All checks passed!`
- `uv run python scripts/ci/check_secrets.py` -> `secrets OK`
- `wc -l rag/llm/chat_model.py` -> 369 lines (limit 400)
- greps: no top-level litellm/openai import in `rag/llm`, no `str(exc)`/`str(e)`, no `class LLMErrorCode|ModelException|StreamSanitizer|def run_with_retries` in `chat_model.py`

## Task Commits

1. Task 1 (fake provider and red tests): `a733be9`
2. Task 2 (registry, metadata, errors, retry, stream): `5083efe`
3. Task 3 (chat driver, fake and test refinements, pyproject warning filters): `969519a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Third-party pydantic warnings failed streamed calls under filterwarnings=error**
- **Found during:** Task 3 first full run
- **Issue:** litellm builds pydantic models lazily on the first streamed chunk; pydantic 2.12 emits a UserWarning (ReadOnly TypedDict item) and DeprecationWarnings (instance `model_fields` access) from litellm's own code. The project sets `filterwarnings = ["error"]`, so the warning became an exception inside litellm's stream handler and surfaced as ERROR_SERVER.
- **Fix:** two message-scoped `ignore` lines in `pyproject.toml` with comments naming the source. The global `error` default is unchanged.
- **Commit:** `969519a`

**2. [Rule 1 - Bug] Plan conflict on HTTP 402**
- **Issue:** the must_haves truth and the RESEARCH error table say 402 maps to ERROR_INVALID_REQUEST; the Task 3 action text says ERROR_QUOTA.
- **Fix:** followed the truth and the research table (tests assert it); `provider_status` keeps 402. Plan 03-10 should treat `provider_status == 402` as "credits exhausted" when building the 400 message.

**3. [Rule 1 - Bug] litellm connection errors look like server errors**
- **Issue:** a refused connection surfaces as `litellm.InternalServerError` (status 500).
- **Fix:** the response hook records whether any error response arrived; none means ERROR_CONNECTION. Test added.

**4. [Rule 2 - Missing critical functionality] Defence for `extra_headers`**
- The plan only documented the risk; the driver now strips `extra_headers` unless `trust_extra_headers=True`. Test added.

**5. [Rule 1 - Bug] Fake provider details found while running the driver**
- The Ollama endpoint ignored JSON without a content type (litellm sends none), the Ollama path lacked the redirect script, and a `fake-no-usage` model was added so the missing-usage path is reachable. Hypercorn closes the inherited socket itself, so teardown ignores the second close.

### Plan wording not followed literally

- Task 3 asked for a no-redirect client "when litellm accepts it", else `litellm.client_session`. litellm accepts `client=` for OpenAI/Azure (openai SDK clients) and for Ollama (an `AsyncHTTPHandler` whose `client` is replaced), so the global-session fallback was not needed.
- The unit tests for estimation call `_estimate_usage` directly, because litellm itself fills in token counts for a stream that reports none; the driver's own estimate only applies when usage is absent or all zero.

## Notes for the next plans

- litellm logs `LoggingWorker: event loop changed ... revived N logging task(s)` at WARNING when a process uses more than one event loop (the test suite does). Harmless in the app (one loop per worker); it appears only in tests.
- Redirects and other 3xx responses surface as a ModelException with code ERROR_GENERIC/ERROR_SERVER class (no body); the API edge should answer 502 with a generic message.
- Embedding drivers (OpenAI SDK, Ollama SDK) are not in this plan; LLM-04 and LLM-05 are therefore left open in REQUIREMENTS until the embedding plan covers their embedding side. The fake already serves `/v1/embeddings`, Azure and `/api/embed` (configurable `embedding_dim`, `shuffle_embeddings`, `usage.prompt_tokens`).
- Residual DNS-rebinding window between `assert_unchanged` and the SDK connect remains accepted (T-03-02-02).
- litellm 1.103.2 needed no fallback pin.

## Known Stubs

None.

## Threat Flags

None. The only new network surface is the outbound provider call already covered by T-03-05-01 through T-03-05-05; the fake provider binds 127.0.0.1 in tests only.

## Self-Check: PASSED

- Files present: rag/llm/__init__.py, model_meta.py, errors.py, retry.py, stream.py, chat_model.py, test/helpers/fake_provider.py, the three test modules.
- Commits present: a733be9, 5083efe, 969519a.
