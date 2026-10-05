---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 02
subsystem: testing
tags: [python, uv, pytest, ruff, test-runner]
requires:
  - phase: 01-01
    provides: decision register and scripts/ci/check_decisions.py
provides:
  - Python 3.13 uv environment with all Phase 1 Python dependencies locked
  - run_tests.py documented pytest wrapper
  - test/helpers/wait.py wait_until readiness helper
  - Unit tests for hygiene, decision gate, runner, wait helper
affects: [all later plans that run pytest]
tech-stack:
  added: [quart 0.23.1, hypercorn 0.18.0, quart-schema 0.25.0, quart-cors 0.8.0, pydantic 2.13.5, peewee 3.19.0, PyMySQL 1.2.3, valkey 6.1.1, minio 7.2.20, elasticsearch 8.19.3, PyYAML 6.0.3, httpx 0.28.1, pytest 9.1.1, ruff 0.16.10]
  patterns: [strict pytest markers, single polling site, list-form subprocess only]
key-files:
  created: [pyproject.toml, uv.lock, .python-version, run_tests.py, test/conftest.py, test/helpers/wait.py, test/unit_test/test_repo_hygiene.py, test/unit_test/test_check_decisions.py, test/unit_test/test_run_tests.py, test/unit_test/test_wait.py]
  modified: []
key-decisions:
  - "Package set approved by user at the Task 1 checkpoint (reply: \"Approved\"), no removals or replacements; covers Python, Go and npm lists"
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 02: Python toolchain and test runner Summary

Python 3.13 uv environment, strict-marker pytest config, documented `run_tests.py` wrapper and a single-site `wait_until` helper, with 19 passing unit tests.

## Task 1 (checkpoint)
The user approved the full Python, Go and npm package set on 2026-10-05: "Approved". No installs ran before approval. No package outside the approved list was installed.

## Commits
- ad5f166: feat(01-02) environment, runner, helper
- 05b9f25: test(01-02) unit tests

## Verification (observed)
- `uv run python --version`: Python 3.13.11
- `uv run python run_tests.py -m unit`: 19 passed, 0 skipped
- `uv run ruff check .`: all checks passed (warning: S403 has no effect without preview mode)
- `uv run pytest --markers`: all five markers listed; `--help` lists all flags; no torch/pymupdf/litellm in pyproject; no sleep calls in test/unit_test
- Disk free on /: 4151M before, 4103M after (about 48M used)
- `uv lock` resolved with the planned pins; no fallback to reference pins needed.

## Deviations from Plan
**1. [Rule 1 - Bug] Hygiene negative test removes two gitignore lines.** The plan said removing `!docker/.env.example` should break the check, but `!.env.example` (no slash) already un-ignores that file at any depth, so removing one line changes nothing. The test removes both exception lines and asserts the check then fails.

Also: `-p no:anyio` and `filterwarnings = ["error"]` produced no real third-party warnings, so no ignores were added. `wait_until` uses `time.sleep` internally (the sole permitted site).

## Known Stubs
None.

## Self-Check: PASSED
