---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 20
subsystem: exit-gate-scripts
tags: [clean-room, preflight, run_tests, gap-closure, guardrails]
provides:
  - run_tests.py treats pytest exit 5 as failure unless serial second pass or --allow-empty
  - clean_room.sh validates --runs as a positive integer (exit 2 before Docker)
  - preflight.sh --project-only and PREFLIGHT_STRICT_PROJECT=1; all working-dir labels checked, space-safe
  - clean_room.sh project-guard step before stop; go-race runs with -count=1
key-files:
  modified: [run_tests.py, scripts/clean_room.sh, scripts/preflight.sh, test/unit_test/test_run_tests.py, test/unit_test/test_clean_room_guard.py, test/unit_test/test_preflight.py]
requirements-completed: [TEST-01, TEST-03, DEPLOY-11]
metrics:
  tasks: 2
  completed: 2026-10-06
---

# Phase 1 Plan 20: Gate scripts and test runner Summary

The exit gate can no longer pass vacuously (zero runs, empty test selection), reuse cached Go race results, or stop/remove another checkout's `devrag-stack` project (closes WR-15, WR-16, WR-17).

## Tasks

| Task | Commit |
|------|--------|
| 1. run_tests.py exit-5 narrowing, `--allow-empty` (tests first) | 983a3e9 |
| 2. --runs validation, project-guard, strict preflight, -count=1 | 74b07d3 |

## RED evidence (observed)

- Task 1, against pre-fix `run_tests.py`: 4 failed, 8 passed (single-command exit 5, parallel first-pass exit 5, `--allow-empty` unrecognised x2).
- Task 2, clean_room tests run against the pre-fix scripts (copied from HEAD, via `GUARD_TEST_SCRIPTS_DIR`): 8 failed, 8 passed (6 invalid `--runs` cases, foreign-checkout refusal, foreign-among-local refusal). The accept cases and the go-race source test passed pre-fix by design (go-race test reads the repo script).
- Task 2, new preflight tests against pre-fix `preflight.sh`: 3 failed, 8 passed (strict mode, `--project-only`, unknown argument).
- After the fix: 27 passed in clean_room_guard + preflight files.

## Verification (as observed)

- `bash -n` on clean_room.sh and preflight.sh: OK. shellcheck not installed.
- `make ci`: 7/7 gates passed.
- `uv run python run_tests.py -m unit`: 289 passed, 1 skipped, 134 deselected.

## run_tests.py callers checked

`uv run pytest -m <expr> --collect-only -q` selects at least one test for every caller: `unit` 269, `integration` 77, `e2e and not serial` 54, `e2e and serial` 3, `integration or e2e` 134 (Makefile lines 17 and 22, clean_room.sh steps unit/integration/e2e/e2e-serial). CI workflow has no direct run_tests.py call. No expression needed fixing and `--allow-empty` was not added anywhere.

## Notes

- Tests run clean_room.sh and preflight.sh from a copy under `<tmp>/desktop x/devRag_@/` with a fake `docker` first on PATH (fake `stop` exits 1 so the accept cases halt right after `stop`). Own-checkout label with a space and `@` is accepted; `/elsewhere/docker` is refused with no `stop`/`down` logged. No real Docker state-changing command was run and clean_room.sh was not run for real.
- `down -v` still appears once, after `exit 3` and after `project-guard`.
- `GUARD_TEST_SCRIPTS_DIR` is a test-only override used to prove RED against old scripts; it defaults to the repo scripts.

## Deviations from Plan

None. One minor point: the real-daemon working-dir label was not queried, since the fake-docker tests cover the space and `@` shape.

## Self-Check: PASSED
