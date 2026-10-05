---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 03
subsystem: testing
tags: [ci-gates, security, pickle, placeholders, secrets, makefile]
requires:
  - phase: 01-02
    provides: Python 3.13 uv environment, run_tests.py, wait helper
provides:
  - check_placeholders, check_pickle, check_no_sleep, check_secrets gates with fixture self-tests
  - scripts/ci/run_all.py runner
  - Makefile (ci, test-unit, test-live, init-env, preflight, up, infra-up, down, clean-room, gen)
  - .github/workflows/ci.yml (unverified here)
affects: [all later plans, every production tree]
tech-stack:
  added: []
  patterns: [stdlib-only gates with --root for fixtures, gate-ok reason escape, skipped: tree absent]
key-files:
  created: [scripts/ci/_walk.py, scripts/ci/check_placeholders.py, scripts/ci/check_pickle.py, scripts/ci/check_no_sleep.py, scripts/ci/check_secrets.py, scripts/ci/run_all.py, test/unit_test/test_unpickle.py, Makefile, .github/workflows/ci.yml]
  modified: [pyproject.toml, .planning/BLOCKERS.md]
key-decisions:
  - "Pickle gate also rejects subclasses of pickle.Unpickler in production; gate-ok is honoured only in test trees"
  - "Secrets gate excludes scripts/ci/, .planning/ and .serena/ besides rejecting docs/ before any open"
requirements-completed: [SEC-05, SEC-10]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 03: CI guardrail gates Summary

Four fixture-proven gates (placeholders/fakes, pickle, fixed sleeps, secrets), a `run_all.py` runner and `make ci` as the single entry point.

## Commits
- 3fa10d9: placeholder and pickle gates with 41 fixture tests
- 178c7ab: no-sleep and secrets gates, runner, SEC-05 regression test, B-13
- 9489033: Makefile, workflow, ruff config

## Verification (observed)
- `uv run pytest scripts/ci/tests test/unit_test/test_unpickle.py`: 70 passed, 1 skipped
- `make test-unit`: 89 passed, 1 skipped; Go and web legs print "skipped: ... absent"
- `make ci`: 5/5 gates PASS (decisions, no_sleep, pickle, placeholders, secrets) and ruff `S,ASYNC,FIX001,FIX002` clean
- placeholders gate on the real repo prints `skipped: tree absent` (no production trees exist yet)
- Bad-fixture checks: pickle.loads in `api/x.py` exit 1 and prints `api/x.py:2`; sleep in `test/test_x.py` exit 1, same content in `test/helpers/wait.py` exit 0
- `grep 'down -v' Makefile`: nothing; `make -n up` shows `-p devrag-stack` and `--env-file docker/.env`; workflow parses as YAML
- Disk free on /: 4101M

## Deviations from Plan
**1. [Rule 3 - Blocking] Ruff command and config.** The planned `ruff check --select S,...` flagged 96 pytest asserts and list-form subprocess calls (S101, S603, S607). Added `ignore = ["S603","S607"]` and per-file S101 ignore for test trees in `pyproject.toml` (not in the plan's file list); the Makefile passes `--ignore S603,S607` because CLI `--select` overrides config ignores. Shell variants S602/S605 stay enforced.

**2. [Rule 2] Unpickler subclass detection** added to `check_pickle.py` (a `pickle.Unpickler` subclass is the allow-list pattern R-38 rejects and is not a call).

## Known limitations
- The numpy-whitelist gadget test skips: numpy is not in the user-approved package set (recorded as B-13). The gadget logic has therefore never executed here.
- `.github/workflows/ci.yml` is unverified (B-06).
- `make up`, `infra-up`, `down`, `clean-room`, `gen`, `init-env`, `preflight`, `test-live` reference scripts created by later plans and were only checked with `make -n`.
- The placeholder gate's Go/TS scanner is token-level, not a real parser; regex literals containing quotes could confuse it.

## Known Stubs
None.

## Self-Check: PASSED
