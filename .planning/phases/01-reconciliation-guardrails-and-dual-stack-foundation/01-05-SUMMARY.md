---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 05
subsystem: infra
tags: [nginx, routing, codegen, tls, sse]
requires:
  - phase: 01-02
    provides: uv environment, run_tests.py, CI gate runner
provides:
  - conf/routes.yaml single route-ownership list
  - scripts/gen_routes.py generator with --check drift gate
  - generated Nginx HTTP and TLS server blocks and Vite proxy JSON
  - SSE-safe proxy.conf, nginx.conf, scripts/gen_selfsigned.sh
affects: [01-14 live routing tests, web dev proxy, make gen, make ci]
tech-stack:
  added: []
  patterns: [generated config with drift gate, exact and ^~ locations only]
key-files:
  created: [conf/routes.yaml, scripts/gen_routes.py, scripts/gen_selfsigned.sh, scripts/ci/check_generated.py, docker/nginx/nginx.conf, docker/nginx/proxy.conf, docker/nginx/ragflow.conf, docker/nginx/ragflow.https.conf, web/src/constants/api-routes.generated.json, test/unit_test/test_gen_routes.py, test/integration/test_nginx.py]
  modified: []
key-decisions:
  - "Go ownership uses exact matches only under /api/v1/system/ so Python-documented siblings are never swallowed (R-53)"
metrics:
  tasks: 2
  completed: 2026-10-05
---

# Phase 1 Plan 05: Route ownership and Nginx ingress Summary

One YAML list generates the Nginx ingress (HTTP and self-signed TLS) and the Vite proxy JSON; CI fails on drift, and the config validates under the real `nginx -t`.

## Commits
- 55954e5: routes.yaml, generator, drift gate, ownership tests
- 330f2a8: Nginx base files, SSE-safe proxy settings, TLS helper, nginx -t tests

## Verification (observed)
- `uv run pytest test/unit_test/test_gen_routes.py`: 27 passed
- `gen_routes.py --check`: exit 0; 18 `location =`/`^~` blocks, 0 regex locations
- `run_tests.py -m integration -t test_nginx`: 9 passed (`nginx -t` reported "syntax is ok" and "test is successful" for HTTP and HTTPS, using the already-local `nginx:alpine`, `--rm`, no published ports)
- `scripts/ci/run_all.py`: 6/6 gates passed; ruff security selection clean
- `docker/nginx/certs/server.key` is git-ignored

## Deviations from Plan
None. Notes: `nginx.conf` sets `pid /tmp/nginx.pid`; `check_generated.py` passes `--root` to `gen_go_entities.py` when plan 01-11 adds it, so that script must accept `--root`.

## Known Stubs
None.

## Self-Check: PASSED
