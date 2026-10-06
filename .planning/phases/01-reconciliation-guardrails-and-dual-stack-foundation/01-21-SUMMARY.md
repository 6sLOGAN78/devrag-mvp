---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 21
subsystem: container-runtime
tags: [docker, nginx, tls, healthcheck, gap-closure]
requires: []
provides:
  - docker/prepare_runtime.sh (TLS fail-closed, LOG_DIR ownership)
  - healthcheck that probes both backends directly
  - wait_stack.sh TLS mode and --print-probe-urls
  - GO_API_PORT pinned to 9384
affects: [01-24 exit gate]
key-files:
  created: [docker/prepare_runtime.sh, test/unit_test/test_container_scripts.py]
  modified: [docker/entrypoint.sh, Dockerfile, docker/healthcheck.sh, scripts/wait_stack.sh, docker/docker-compose.yml, docker/.env.example]
key-decisions:
  - "Entrypoint now exports APP_UID/APP_GID so prepare_runtime.sh sees the same values as setpriv"
metrics:
  tasks: 3
  completed: 2026-10-06
---

# Phase 1 Plan 21: Container runtime gap closure Summary

NGINX_TLS=1 without a readable cert and key now aborts the container (exit 1) instead of serving HTTP; LOG_DIR is chowned to APP_UID:APP_GID before the children start; the healthcheck needs both backends at 200; GO_API_PORT is fixed at 9384.

## Tasks and commits

| Task | Commit | Finding |
|---|---|---|
| 1 prepare_runtime.sh, entrypoint, Dockerfile | daf804b | WR-11, WR-12 |
| 2 healthcheck.sh, wait_stack.sh | 9bb2273 | WR-13 |
| 3 GO_API_PORT pinned | a837732 | WR-14 |

## TDD record

Tests were written first in `test/unit_test/test_container_scripts.py`. Against the pre-fix scripts: 19 failed, 1 passed (the single pass was the missing-template case, which fails trivially when the script does not exist). After Task 1: 10 failed (healthcheck and wait_stack tests), 10 passed. After Task 2: 20 passed. No test weakened, skipped or xfailed.

## Verification (as observed)

- `uv run python run_tests.py -m unit`: 309 passed, 1 skipped.
- `make ci`: exit 0, 7/7 gates passed.
- `bash -n` on prepare_runtime.sh, entrypoint.sh, healthcheck.sh, wait_stack.sh: clean. shellcheck not run (not confirmed installed).
- `-t` expressions confirmed non-empty with `--collect-only -q` (13 and 10 tests).
- `docker compose config` with `GO_API_PORT=9399` exported renders `GO_API_PORT: "9384"` (dummy secrets supplied for the render only).

## Live check

Not run. Resources were sufficient (about 6 GB available, 25 GB disk free) but the live container check was optional and was left to plan 01-24's exit gate (`test_tls.py`, `test_app_container.py`). Stack state: no devrag-stack containers were running before or after; nothing was started or stopped.

## Deviations from Plan

None. `GO_API_PORT` was removed from `.env.example` entirely because no test or doc required it.

## Self-Check: PASSED
