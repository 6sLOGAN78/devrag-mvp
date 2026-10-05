---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 04
subsystem: infra
tags: [docker-compose, mysql, valkey, minio, elasticsearch, preflight, env]
requires:
  - phase: 01-02
    provides: uv environment, run_tests.py, wait_until helper
provides:
  - docker/docker-compose-base.yml (mysql, redis/valkey, minio, es01, infinity profile) under project devrag-stack
  - docker/docker-compose.dev.yml memory caps and lowered ES watermarks
  - docker/.env.example catalog with empty secrets, scripts/init_env.sh generator
  - scripts/preflight.sh and scripts/wait_stack.sh
  - 13 live integration tests, 12 unit tests
affects: [01-13 (docker-compose.yml includes the base file), later plans needing live services]
key-files:
  created: [docker/docker-compose-base.yml, docker/docker-compose.dev.yml, docker/.env.example, docker/init.sql, scripts/init_env.sh, scripts/preflight.sh, scripts/wait_stack.sh, test/unit_test/test_env_catalog.py, test/unit_test/test_preflight.py, test/integration/__init__.py, test/integration/test_compose_infra.py]
  modified: [Makefile]
key-decisions:
  - "Secret marker is a '# secret' comment on the line before an empty key, so the example keeps bare KEY= lines"
  - "Redis volume redis_data added so Valkey data survives restarts"
requirements-completed: [DEPLOY-02, DEPLOY-04, DEPLOY-11, DEPLOY-13, DEPLOY-15]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 04: Infrastructure compose, env catalog and preflight Summary

MySQL 8.0.40, Valkey 8, MinIO (pgsty) and Elasticsearch 8.11.3 reach healthy from empty volumes under compose project `devrag-stack`, with generated secrets, loopback-only ports and a preflight that reports host readiness.

## Commits
- 8b060ab: base compose, dev override, env catalog, init.sql, init_env.sh
- 1d656f9: preflight and wait_stack scripts with tests
- 8340417: live integration tests and `make infra-up` on base+dev compose

## Observed results
- Live bring-up from empty volumes: all four services healthy in about 28 s (`make infra-up`, includes wait_stack).
- Integration tests: 13 passed. Unit suite: 101 passed, 1 skipped (numpy gadget, B-13). ruff clean.
- `docker stats --no-stream` MEM USAGE: mysql 191.5 MiB, es01 1.533 GiB, redis 18.4 MiB, minio 131.1 MiB; total about 1.87 GiB (< 3.0 GiB budget, no limit changes needed; R-72 stands).
- Disk free on /: 23940M before bring-up, 23738M after (about 200M used by volumes). The host had more free space than the 4.2 GB recorded in B-03 at run time.
- Foreign `devrag` compose project: 6 containers before and after, untouched. `infiniflow/infinity:v0.7.2-x64-v3` not present locally (never pulled).
- Final state: stack stopped with `docker compose -p devrag-stack ... stop` (containers and volumes kept, no `-v`).
- Preflight on this host with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`: passes, `OVERRIDE recorded` for vm.max_map_count 65530 (B-02). No override needed for disk.

## Deviations from Plan
**1. [Rule 3 - Blocking] `make infra-up` pointed at docker/docker-compose.yml, which plan 01-13 creates.** The target now uses `docker-compose-base.yml` plus `docker-compose.dev.yml`. Plan 01-13 may switch it back when the top-level file exists.

**2. [Rule 1 - Bug] `PREFLIGHT_PORTS=""` fell back to defaults** with `:-`; changed to `-` so an empty value means no port checks (needed by tests).

**3. Secret marker placement.** The plan's acceptance grep requires bare `KEY=` lines, so `# secret` sits on the preceding line rather than trailing. OpenSearch and ClickHouse passwords are also marked secret and generated.

**4. ES base heap default** is `-Xms2g -Xmx2g` (documented-scale); the dev override sets 1g.

## Known Stubs
None.

## Self-Check: PASSED
