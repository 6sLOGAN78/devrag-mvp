# Deferred items (found while executing Phase 3, not caused by the plan that found them)

Found during plan 03-12; none touch files that plan changed. All four are resolved.

| # | Where | Evidence | Origin | Status |
|---|-------|----------|--------|--------|
| 1 | `scripts/ci/check_no_sleep.py` fails | `test/unit_test/test_llm_shared.py:163: fixed sleep/setTimeout in a test` (the line defined a local `async def sleep(delay)` used as an injected recorder; the gate's regex matches the name) | plan 03-05 | RESOLVED `ef37f4d` (recorder renamed `record_delay`; the checker is unchanged; `ce745f5` also sorted that file's imports for ruff I001) |
| 2 | `scripts/ci/check_placeholders.py` fails | `rag/llm/chat_model.py:209`, `:212`, `rag/llm/embedding_model.py:205`, `:209`, `:259`: `raise NotImplementedError` in abstract base methods | plans 03-05, 03-06 | RESOLVED `8d4bde0` (both `Base` classes and `_OpenAISdkEmbed` use `abc.ABC` + `@abstractmethod`, as `doc_store_base.py` does; all five were abstract hooks that every concrete driver already overrides; no allowlist entry) |
| 3 | `ruff check .` E501 | `test/unit_test/test_settings.py:258` was 238 characters (limit 200) | plan 03-01 | RESOLVED `27089bd` |
| 4 | `test/testcases/test_log_token_masking.py` (2 tests) | The Python access log cut `/api/v1/logmask-probe-<hex>` to `/api/v1/logma***`. Cause: the provider key shape `sk-[A-Za-z0-9_-]{20,}` had no left boundary, so the `sk-probe-<32 hex>` tail of `logmask-probe-...` was read as an OpenAI key (same in Go `keyShapePattern` and the Nginx `$loggable_uri` map). The cause was over-broad production masking, not request-log truncation. | plan 03-02 | RESOLVED `edd32dc` (`sk-` must now start a token in Python, Go and Nginx; two keep vectors that failed first in all three engines and four still-masked vectors added to `test/fixtures/log_redaction_vectors.json`) |
