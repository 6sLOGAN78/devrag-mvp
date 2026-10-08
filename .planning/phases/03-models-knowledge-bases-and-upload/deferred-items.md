# Deferred items (found while executing Phase 3, not caused by the plan that found them)

Found during plan 03-12; none touch files that plan changed. Listed with the evidence so the owning plan or the wave-end run can pick them up.

| # | Where | Evidence | Likely origin |
|---|-------|----------|---------------|
| 1 | `scripts/ci/check_no_sleep.py` fails | `test/unit_test/test_llm_shared.py:163: fixed sleep/setTimeout in a test` (the line defines a local `async def sleep(delay)` used as an injected recorder; the gate's regex matches the name) | plan 03-05 |
| 2 | `scripts/ci/check_placeholders.py` fails | `rag/llm/chat_model.py:209`, `:212`, `rag/llm/embedding_model.py:205`, `:209`, `:259`: `raise NotImplementedError` in abstract base methods | plans 03-05, 03-06 |
| 3 | `ruff check .` E501 | `test/unit_test/test_settings.py:258` is 238 characters (limit 200) | plan 03-01 |
| 4 | `test/testcases/test_log_token_masking.py` (2 tests) | The Python access log now truncates a long path (`/api/v1/logma***`, `truncate_field`), so `probe in line` and the marker request are never found: `TimeoutError ... the request lines did not appear in the container logs` / `the marker request did not appear in the Python log`. The Nginx and Go lines are present. | request-log truncation work (test_request_log_truncation.py) landed after the test was written |

`scripts/ci/run_all.py` therefore reports 5/7 gates until items 1 and 2 are fixed.
