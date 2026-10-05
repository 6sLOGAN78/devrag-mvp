---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 14
subsystem: testing
tags: [e2e, nginx, ingress, outage, tls, vitest-live]
requires:
  - phase: 01-13
    provides: running devrag-stack with Nginx ingress, TLS override
provides:
  - Live Python e2e suite (ownership, envelope, CORS, request log, OpenAPI, outage, TLS)
  - Go e2e tier test against the ingress
  - Serial-safe parallel mode in run_tests.py
affects: [01-15]
tech-stack:
  added: []
  patterns: [routes.yaml-driven probes, try/finally service restoration, serial tests ordered last]
key-files:
  created: [test/testcases/__init__.py, test/testcases/_routes.py, test/testcases/conftest.py, test/testcases/test_routing.py, test/testcases/test_route_ownership.py, test/testcases/test_system_routes.py, test/testcases/test_envelope.py, test/testcases/test_cors.py, test/testcases/test_request_log.py, test/testcases/test_openapi.py, test/testcases/test_dependency_outage.py, test/testcases/test_tls.py, internal/e2e/system_e2e_test.go]
  modified: [run_tests.py, test/unit_test/test_run_tests.py, web/src/services/http.live.test.ts, web/src/test/live/spa-shell.live.test.ts]
key-decisions:
  - "Serial-marked tests run last in the same session and, under -p, in a second non-parallel pytest pass"
requirements-completed: [TEST-02, TEST-04, DEPLOY-12, API-02, API-04, API-05, API-09, API-10, API-11, SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07]
metrics:
  tasks: 3
  completed: 2026-10-05
---

# Phase 1 Plan 14: Live ingress, outage and TLS tests Summary

Live tests through the real Nginx ingress prove route ownership from `conf/routes.yaml`, one error envelope on both engines, safe CORS, structured redacted request logs, OpenAPI, dependency outage/recovery and the TLS variant.

## Results observed (stack up, project devrag-stack)
- `run_tests.py -m e2e`: 56 passed, 0 failed, 0 skipped (53 non-serial plus 3 serial: redis outage, es01 outage, TLS).
- `run_tests.py -m "e2e and serial"`: 3 passed.
- `run_tests.py -m integration`: 73 passed (see deviation 3).
- Go `go test -tags=e2e ./internal/e2e/...`: 2 tests passed; `go test -tags=integration,e2e ./...` all packages ok; `go vet -tags=e2e ./...` clean.
- Vitest `npm run test:live`: 9 passed of 9 (first ever run; see deviations 1-2).
- `make ci`: 7/7 gates and ruff passed. `grep secret-token ragflow-logs`: 0 matches.
- Manual TLS check: `curl --cacert docker/nginx/certs/server.crt https://127.0.0.1:8443/health` returned 200 with the override; plain HTTP `/health` returned 200 after restore.
- Disk free: 15881M at start, 15931M at end.

## Deviations from Plan
1. **[Rule 1 - Bug, test] http.live.test.ts**: `fetch("/health")` has no base URL in Node, so the wait timed out after 60 s. Now resolves against `window.location.origin`.
2. **[Rule 1 - Bug, test] spa-shell.live.test.ts**: lazy chunk regex expected `assets/<name>.js`, Vite emits `./index-<hash>.js`. Regex accepts both.
3. **[Rule 3] Stale host-side `conf/service_conf.yaml`** (gitignored local file) had container hostnames for minio and es01, so 5 older integration tests (01-08) saw storage/doc_store down from the host. Re-rendered with 127.0.0.1 hosts; no product code changed.
4. **[Rule 1] test race in TLS test**: waited only for Go before asserting Python; now waits for both engines. Also pinned the cert via `ssl.create_default_context(cafile=...)` (httpx deprecates `verify=<str>` and warnings are errors).
5. **run_tests.py edit (plan 01-02 file)**: `-p` now runs `-m "(m) and not serial" -n auto` then `-m "(m) and serial"` without xdist; exit code 5 (nothing collected) is tolerated. Unit test added.
6. Added helper `test/testcases/_routes.py` (not in plan file list).

## Notes
- Go `/health` reports database and redis only; Python status reports four checks. Independence of engines proven by the es01 outage (Python 503, Go 200).
- TLS healthcheck inside the container still probes plain HTTP 80, which redirects (curl -f accepts 3xx); not changed.

## Commits
- 0d64508 routing, ownership, system-route tests
- eb31f8d envelope, CORS, request-log, OpenAPI tests and Go e2e tier
- fd5f3bb serial outage and TLS tests, runner change
- 5e4f331 live vitest fixes
- style commit: line wrap in conftest

Stack left STOPPED (`stop`, no `down`, no volumes removed).

## Self-Check: PASSED
