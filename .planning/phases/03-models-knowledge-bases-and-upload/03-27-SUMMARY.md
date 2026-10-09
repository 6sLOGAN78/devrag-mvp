---
phase: 03-models-knowledge-bases-and-upload
plan: 27
subsystem: verification
tags: [live-provider, openrouter, live_model, gate, preflight, usage, dimension, bad-key, leak-scan]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-11 LLMBundle and usage recording; 03-12/03-13 provider and model routes with error mapping; 03-14 dataset create with the model's dimension; 03-19 leak scanner patterns"
provides:
  - "the live_model pytest marker (strict markers) and the live-model clean-room gate step after e2e-serial"
  - "preflight key-presence check that prints present or missing only, required by the gate through PREFLIGHT_REQUIRE_LIVE_KEY=1"
  - "test/testcases/test_live_models.py: six tests against the real OpenRouter account"
  - "gc_at_loop_teardown moved to test/conftest.py so unit and live tiers share it"
affects: [03-29, Phase 3 verification]

key-files:
  created:
    - test/testcases/test_live_models.py
  modified:
    - pyproject.toml
    - scripts/clean_room.sh
    - scripts/preflight.sh
    - test/conftest.py
    - test/unit_test/test_clean_room_guard.py
    - test/unit_test/test_preflight.py
    - test/unit_test/test_run_tests.py
    - test/unit_test/test_llm_drivers.py

key-decisions:
  - "The bad-key case sends a made-up key for a second instance name (badkey) with only the chat model, so it costs one provider call and the counts of provider and model rows can be compared before and after."
  - "The recorded dimension is read from the dataset the API returns (the dimension lives on the model row, not on knowledgebase), and the embedding batch is built with expected_dimension equal to it."
  - "The leak scan counts occurrences of the key and of every 12-character window of it in every recorded response (body and headers) and in the app container logs since the module started; failures print counts only."
  - "Evidence lines (model names, dimension, token counts, call counts, the sanitized bad-key message) are printed once from the last test; none of them is derived from the key."

requirements-completed: [LLM-03, LLM-16, LLM-19, LLM-21, LLM-24, KB-02, KB-03, SEC-02, SEC-03, E2E-03]

completed: 2026-10-09
---

# Phase 3 Plan 27: Live provider tier Summary

**The platform is now proven against the user's real OpenRouter account: the provider saves through the product API after real test calls from the app container, the live 1024-dimension embedding gives a real `q_1024_vec` field, chat, streamed chat and an embedding batch run through `LLMBundle` with `used_tokens` rising, a bad key is a 400 `provider_refused` that keeps the session, and neither the key nor any 12-character window of it appears in a response or in the app logs.**

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `51a49f3` | `live_model` marker, `live-model` gate step, preflight key-presence check, guard tests |
| 2 | `82a143a` | live tier test file, shared GC fixture, fixed-message and no-skip guards |

## What was built

- **Marker and gate.** `live_model` is registered. `scripts/clean_room.sh` has `step live-model uv run python run_tests.py -m live_model` between `e2e-serial` and `go-race`, and runs preflight as `env PREFLIGHT_REQUIRE_LIVE_KEY=1 scripts/preflight.sh`. No non-comment line of the script mentions `OPENROUTER` or exports a key. The default selections (`unit`, `integration`, `e2e and not serial`, `e2e and serial`) are proven not to pick up a test marked only `live_model`, so GitHub CI (no key) stays offline.
- **Preflight.** `OK openrouter key: present`, or `INFO openrouter key: missing`, or with the requirement set `FAIL openrouter key: missing` plus an ACTION line naming `OPENROUTER_API_KEY` and `docker/.env`. The value is never stored in a variable or printed; a test with a fake key value checks stdout and stderr for it and for a fragment of it.
- **Live tier (six tests, one module-scope workspace).**
  1. Provider save through `PUT /api/v1/providers` (two real calls from the container), masked tail matches, recorded dimension equals `LIVE_EXPECTED_DIM`.
  2. Defaults, dataset create without `embd_id`, dataset detail dimension, and the Elasticsearch mapping of `q_1024_vec` (dense_vector, cosine, hnsw m 16, ef_construction 200).
  3. `LLMBundle.chat` and `chat_streamly` with the key opened from the sealed row; `used_tokens` rises after each; deltas non-empty.
  4. `encode(["alpha", "beta"])` returns two vectors of the live dimension, equal to the dataset's recorded dimension; `used_tokens` rises.
  5. Bad key: 400, `reason == "provider_refused"`, response free of the bad key, provider and model row counts unchanged, `/v1/user/info` still 200 with the same token.
  6. Budget ceiling (6 chat-class, 3 embedding) and the leak scan over recorded responses and app container logs.
- **Missing key.** The module fixture calls `pytest.fail("OPENROUTER_API_KEY is missing from docker/.env; ...")`. A unit test points the lookup at an empty environment, runs the real file in a subprocess and asserts a non-zero exit, the fixed message and no "skipped". The file contains neither `skip` nor `xfail`.

## Live results (real output, no secret)

Two full runs of the tier were made (the second added the evidence lines). Both: `6 passed`. Second run:

```
LIVE-EVIDENCE chat model=meta-llama/llama-3.1-8b-instruct used_tokens_after_chat=30
LIVE-EVIDENCE stream pieces=1 used_tokens_after_stream=61 estimated=False
LIVE-EVIDENCE embedding model=baai/bge-m3 dimension_observed=1024 dimension_recorded=1024 used_tokens=7
LIVE-EVIDENCE bad key: http=400 reason=provider_refused message='Missing Authentication header'
LIVE-EVIDENCE calls: chat_class=4/6 embedding=2/3; response_hits=0 log_hits=0
```

- Models actually used: the researched pair, no fallback needed (`meta-llama/llama-3.1-8b-instruct`, `baai/bge-m3`). Embeddings work on OpenRouter with this key, so the D-06 blocker did not occur.
- The real key was accepted (no 401 or 402). The made-up key came back through the product as HTTP 400, never 401.
- Provider calls per run: 4 chat-class (save test, chat, stream, bad key) and 2 embedding (save test, batch); roughly 12 calls in total over the two runs, plus none ad hoc.

## Deviations from Plan

- **[Decision] Stack not rebuilt.** The plan's verify command contains `make up`; no product code changed in this plan and the running stack already ran every committed line. The live tier ran against that healthy stack on port 8088.
- **[Decision] `gc_at_loop_teardown` moved** from `test/unit_test/test_llm_drivers.py` to `test/conftest.py` (as the live rules asked); the 52 driver tests still pass. `test/conftest.py` and `test_llm_drivers.py` were not in the plan's file list.
- **[Decision] Dimension source.** The plan said to compare with the dataset's recorded dimension; the value is read from the dataset API response because no `knowledgebase` column holds it.
- **[Decision] Bad-key instance name.** The case uses instance `badkey` so "no additional provider row" is a meaningful comparison; one chat model only, one provider call.
- The `live-model` step was proven by running its exact command (`run_tests.py -m live_model`); the full `clean_room.sh` gate was not run (plan 03-29).

## Observations (not changed)

- LiteLLM prints "You are sending unauthenticated requests to the HF Hub" on the first chat call in the test process (a tokenizer lookup inside the library). It is a warning only and was not a failure; whether the app container reaches Hugging Face for the same lookup was not examined here.
- The unit tier shows 1 skipped test, an existing docker project-collision test that skips when no foreign project exists; it is not part of this plan.

## Test results

- `uv run python run_tests.py -m unit`: 1799 passed, 1 skipped, 0 failed.
- `uv run python run_tests.py -m live_model`: 6 passed (twice).
- `uv run python scripts/ci/run_all.py`: 7/7 gates passed; `ruff check .` clean; `scripts/ci/check_secrets.py` OK.

## Known Stubs

None.

## Threat Flags

None. T-03-27-01 and -02 by the in-process key read, count-only assertions and the window scan (0 hits in responses and logs); -03 by the budget constants and ceiling test; -04 by the fixed failure and the no-skip guards; -05 by `check_secrets.py` and the bad key built from parts.

## Self-Check: PASSED

Commits `51a49f3` and `82a143a` exist on `master`; `test/testcases/test_live_models.py` exists; the runs above were green.
