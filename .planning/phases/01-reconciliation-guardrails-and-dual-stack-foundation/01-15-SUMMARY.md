---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 15
subsystem: testing
tags: [exit-gate, clean-room, docker-compose, memory-budget, headless-chrome]
requires:
  - phase: 01-13
    provides: app image and full compose stack
  - phase: 01-14
    provides: live e2e suites through Nginx
  - phase: 01-03
    provides: CI gates
provides:
  - Guarded clean-room script that rebuilds devrag-stack from empty volumes and runs every suite
  - Measured dev memory budget recorded in DECISIONS.md
  - Headless-Chrome check of the System status page
  - Final blocker statuses for Phase 1
affects: [phase-02, phase-03]
tech-stack:
  added: []
  patterns: [stop-own-stack-before-preflight, tests isolated from inherited PREFLIGHT_* variables]
key-files:
  created: [scripts/clean_room.sh, scripts/record_memory.py, test/unit_test/test_clean_room_guard.py, test/testcases/test_spa_browser.py]
  modified: [test/unit_test/test_preflight.py, .planning/DECISIONS.md, .planning/BLOCKERS.md]
key-decisions:
  - "clean_room.sh stops its own stack before preflight; preflight is not valid against a running devrag-stack"
  - "RAM threshold was not lowered; the user freed memory instead (B-14)"
requirements-completed: [DEPLOY-02, DEPLOY-13, TEST-01, TEST-02, TEST-03, TEST-04, TEST-10, SEC-04, UI-01, UI-03]
metrics:
  tasks: 2
  completed: 2026-10-06
---

# Phase 1 Plan 15: Clean-Room Exit Gate Summary

**Three consecutive teardown-and-rebuild cycles of `devrag-stack` passed every suite on 2026-10-06, after two defects found by the gate itself were fixed.**

## How this plan was executed

- Task 1 (commit `2102013`) was done by an executor that was then cut off by a provider rate limit.
- A second executor verified Task 1 and attempted Task 2; its Docker commands were denied by the permission system and it made no changes.
- After the user allowed the commands, the orchestrator ran Task 2 inline. Everything below was observed in that session.

## Defects found by the gate and fixed

1. **`clean_room.sh` ran preflight against its own running stack** (commit `5eb86ff`). Preflight checks free ports and available RAM, so it failed on the project's own ports. Fix: `docker compose stop` for this project before preflight. Non-destructive; the single `down -v` is unchanged and still behind the project-name guard.
2. **`test_preflight.py` inherited `PREFLIGHT_*` variables from the caller** (commit `05c70c2`). The gate exports `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` and then runs the unit suite, so `test_low_map_count_fails_and_names_sysctl` saw the override and failed. Fix: the test helper drops inherited `PREFLIGHT_*` variables. Assertions unchanged. Verified with and without the overrides exported: 237 passed, 1 skipped both ways.

First gate attempt: run 1 failed at the unit step because of defect 2 (1 failed, 236 passed); runs 2 and 3 did not start. Per the flake rule all three were restarted from scratch after the fix.

## Gate result (second attempt, all from scratch)

Command: `GOTOOLCHAIN=local PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 scripts/clean_room.sh --runs 3` — exit 0, 45 of 45 steps PASS.

| Run | Started (UTC) | Time to healthy | Cycle time | Free disk after |
|---|---|---|---|---|
| 1 | 2026-10-06T13:49:45Z | 37 s | 154 s | 9G |
| 2 | 2026-10-06T13:52:19Z | 39 s | 155 s | 9G |
| 3 | 2026-10-06T13:54:54Z | 42 s | 157 s | 9G |

Per run, identical on all three:

| Step | Result |
|---|---|
| Python unit | 237 passed, 1 skipped |
| Python integration | 73 passed |
| Python e2e (non-serial) | 54 passed |
| Python e2e serial (Redis outage, ES outage, TLS) | 3 passed |
| Go `-race` | ok |
| Go `integration,e2e` tiers (`-count=1`) | ok |
| Go `manual`, `cgo` tiers | ok |
| Frontend unit | 48 passed (6 files) |
| Frontend live | 9 passed (3 files) |

The one skip is the numpy-gadget regression test (B-13).

**Caveat:** the `go-race` step has no `-count=1`, so in runs 2 and 3 most Go unit packages reported `(cached)` rather than re-executing. Those tests do not touch the stack; the stack-dependent Go tiers do use `-count=1` and ran every time.

Overrides: `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` (B-02). The disk override was not used. The RAM threshold was not lowered.

## Measured memory (run 3, `docker stats --no-stream`, this host only)

| Container | Limit MiB | Measured MiB |
|---|---|---|
| app | 768 | 91.5 |
| es01 | 2048 | 1494.0 |
| init | 256 | not running (one-shot, exited) |
| minio | 256 | 70.7 |
| mysql | 640 | 255.6 |
| redis | 160 | 4.0 |

Total 1915.8 MiB against a 3891 MiB budget. Recorded in `.planning/DECISIONS.md`; R-72 is now `accepted (auto, not user-reviewed)`.

## Success-criteria evidence

| SC | Check | Result |
|---|---|---|
| 1 | `scripts/ci/check_decisions.py` | `decisions OK: 82 rows` |
| 1 | `scripts/ci/run_all.py` | 7/7 gates passed |
| 1 | `git check-ignore -q "docs/apikey llm.md"` | exit 0; `git ls-files docs` prints 0 |
| 2 | clean-room `down -v` then `up`, three times | healthy in 37 to 42 s; total 1915.8 MiB |
| 3 | schema from empty by `init`, Go verify | covered by the integration and Go tier steps each run |
| 4 | `curl /api/v1/system/status` through Nginx | `code 0`, four checks `ok` (database, redis, storage, doc_store), engine python |
| 4 | `curl -I /health` | `X-Api-Source: go` |
| 5 | `test/testcases/test_spa_browser.py` (real headless Chrome) | 1 passed, also run explicitly after the gate |
| 5 | three harnesses against the live stack | all green on three runs |

Static check `grep -rEn 'dangerouslySetInnerHTML|innerHTML|rehype-raw' web/src` printed nothing.

## Foreign Docker resources

A snapshot of the 16 non-`devrag-stack` containers and 13 non-`devrag-stack` volumes taken before the first gate attempt matched after the last run (empty diff). Compose project `devrag` still has 6 containers. Only the four `devrag-stack_*` volumes were removed and recreated. No images or build cache were removed; no prune was run.

## Blockers

- B-02 open: `vm.max_map_count` still 65530; override used.
- B-03 open: free disk on this host changed several times for reasons outside this project; 9 GB at gate time.
- B-05 mitigated: earlier projects untouched (evidence above).
- B-06, B-07, B-08, B-11, B-13 open and unchanged.
- B-14 new: the gate needs 4 GB of available RAM; only 2.8 GB was available until the user closed other programs.

## Not verified

- `.github/workflows/ci.yml` has never run (B-06).
- TLS is verified with a self-signed certificate only (B-10).
- The memory and timing figures are from one machine on one day.

## Self-Check: PASSED

- `scripts/clean_room.sh`, `scripts/record_memory.py`, `test/unit_test/test_clean_room_guard.py`, `test/testcases/test_spa_browser.py` exist.
- Commits `2102013`, `5eb86ff`, `05c70c2` exist.
