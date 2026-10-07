---
phase: 02-identity-tenancy-and-authorization
plan: 14
subsystem: auth
tags: [default-deny, quart, before_request, itsdangerous, api-token, beta-token, csrf, 503-fail-closed, route-enumeration]
requires: [02-08, 02-10]
provides:
  - Python before_request default-deny gate driven by the generated policy (exact, then longest prefix, then default jwt); unknown paths under the /api/ and /v1/ catch-alls answer 401
  - auth_service.resolve_principal for jwt (shared itsdangerous token, 30-day max age, AUTH-08, stored-token equality, status 1), api (ragflow- token, own tenant only) and beta credentials
  - AuthInfrastructureError and the 503 envelope: infrastructure failure is never a 401
  - create_app keyword-only principal_resolver seam (tests and offline OpenAPI export), proven absent from production code
  - common/security/proxy.py loopback-peer rule shared in meaning with Go internal/common/clientip.go (R-115, R-116)
  - /api/v1/system/status and /system/status authenticated; marker set empty; openapi.json authenticated (R-113)
  - Python url_map enumeration test and the Go-to-Python cross-stack auth-flow test
affects: [02-15, 02-16, 02-20, 03]
tech-stack:
  added: []
  patterns:
    - "api/apps never imports models: the gate calls api/db/services/auth_service through asyncio.to_thread under a 5 s wait_for"
    - "cheap checks (length, signature, max age, AUTH-08, shape) run in precheck() before any database connection is opened"
key-files:
  created:
    - api/apps/auth.py
    - common/security/proxy.py
    - test/unit_test/test_auth_gate.py
    - test/testcases/test_route_enumeration.py
    - test/testcases/test_auth_flow.py
    - web/src/test/live/account.ts
  modified:
    - api/apps/__init__.py
    - api/apps/errors.py
    - api/db/services/auth_service.py
    - conf/routes.yaml
    - scripts/export_openapi.py
    - test/helpers/app.py
    - test/unit_test/test_route_auth_markers.py
    - internal/common/clientip.go
    - internal/handler/auth.go
    - internal/e2e/system_e2e_test.go
    - test/testcases/test_dependency_outage.py
    - test/testcases/test_openapi.py
    - test/testcases/test_request_log.py
    - web/src/pages/system-status/system-status.live.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-115 / R-116: X-Forwarded-Host and X-Forwarded-Proto are trusted only from a loopback peer in both servers"
  - "R-117: Python gate details (5 s lookup timeout, any unexpected resolver error is 503, beta rows also accept access and API tokens, resolver seam keyword only, static_folder=None, constant-time re-comparison)"
requirements-completed: [AUTH-07, AUTH-08, AUTH-10, AUTH-11, AUTH-12, AUTH-22, AUTH-23, SEC-01, SEC-09]
duration: continuation after a rate-limit cut-off (review, live verification, summary)
completed: 2026-10-07
---

# Phase 2 Plan 14: Python default-deny auth gate Summary

The Python server now enforces the same default-deny gate as Go: a Go-issued access token is accepted by protected Python routes, logout kills it on both servers, API and beta credentials resolve to their own tenant only, and every non-public Python route (including unknown paths and `openapi.json`) answers 401 without credentials.

## Commits

The plan was executed in two sessions; the first was cut off by a rate limit after five commits and wrote no summary. This session reviewed those commits against the plan and security checklist, ran the live verification, and wrote this summary. No new code commit was needed.

| Commit | What |
|---|---|
| f71e3a2 | test: fake SECRET_KEY for the init_db entry-point test (closes the 02-10 deferred item) |
| 250586e | fix: X-Forwarded-Proto / X-Forwarded-Host trusted only from a loopback peer in Go (R-115, R-116) |
| ce97b62 | test: gate (about 50 cases), enumeration, cross-stack, marker tests |
| d8b0628 | feat: gate, auth_service, errors, proxy rule, create_app seam, routes.yaml, export_openapi |
| fb76551 | test: Phase 1 tests assert both 401 and the authenticated expectation; MySQL-down 503 test; live account helper |

## Review of the earlier commits (done / missing / wrong)

Done and checked by reading the code against the plan:

- Default deny: `before_request` runs `policy_for` (unmatched means jwt); only an explicit `none` row passes; OPTIONS passes. Probed `policy_for` for HEAD, trailing-slash, double-slash and unknown paths: healthz variants are only public on the exact registry paths, everything else is jwt or api.
- Credential types per row: jwt (header, then cookie on jwt rows only), api (access or `ragflow-` token), beta (beta value on beta rows only, then access and API tokens as in the reference). Beta, api and cookie credentials are refused where the row does not allow them.
- Constant-time comparison (`hmac.compare_digest`), one generic 401 message, `INVALID_`, empty, short, tampered and over-long tokens rejected by `precheck` before any DB call; user status `1` and exact stored-token match required; invite-only membership means no tenant (identical to Go `FindOwnMembership`: owner and status 1).
- 401 only for credential failures: store errors, timeouts and unexpected resolver exceptions all give the 503 envelope with a coarse log category (R-114).
- Cookie fallback and the CSRF Origin/Referer check match Go. Python is slightly stricter (the netloc includes userinfo), never looser.
- `principal_resolver`: keyword-only; AST tests prove no module under `api/` or `common/settings.py` passes it, that `api/ragflow_server.py` calls `create_app` with positional settings only, and that the environment cannot select it.
- Status route has no `public_until_phase`; the marker set is empty and asserted; openapi.json is `api`-authenticated; `scripts/export_openapi.py` uses the stub resolver and `--check` passes.
- Request-log secrecy: unit test on the real `ragflow.access` records for header, cookie and garbage credentials, plus live tests against `ragflow_server.log`.
- Frontend live test: the System status page registers and logs in through the real API, with the original assertions unchanged, plus a 401 assertion.
- `docker/healthcheck.sh` and `scripts/wait_stack.sh` only probe `/health` and `/api/v1/system/healthz` (also asserted by `test_container_probes_only_use_public_routes`).

Missing: nothing from the plan. Wrong: nothing found that needed a code fix. I added decision row R-117 for Python gate choices that the docs do not fix (the only edit in this session besides this summary and state files).

Forwarded-header rule verified: `docker/entrypoint.sh` runs Nginx in the same container as both servers, `docker/nginx/ragflow.conf` proxies to `127.0.0.1:9384` and `127.0.0.1:9380`, so the peer for ingress traffic is loopback and the rule works in production. The Go (`common.IsLoopbackPeer`) and Python (`is_loopback_peer`, including `::1` and `::ffff:127.0.0.1`) rules are the same, and `proxy.conf` overwrites `X-Forwarded-Host`/`X-Forwarded-Proto` for every proxied location. Quart's `request.remote_addr` is the socket peer.

## Route enumeration

The real app's `url_map` (built with the real factory) is walked; every (method, rule) has a registry row (`undeclared_rules(app) == []`), the implicit `static` route is removed (`static_folder=None`), and a deliberately undeclared route is detected and still answers 401. Each protected Python row answers 401 with `{"code":401,"message":"unauthorized","data":null}` and `X-API-Source: python`; the two healthz rows are the only public ones. Live, through Nginx, status, `/system/status`, `openapi.json` and unknown `/api/v1/` and `/v1/` paths are 401 and healthz is 200. The live run reported 40 enumeration tests passing.

## Live verification (observed)

Host MemAvailable was 7860 MiB before start. `make up` (with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`) rebuilt the app image; all six services including `app` reported healthy; web port 8088.

- `uv run python run_tests.py -m "integration or e2e"`: 228 passed, 713 deselected, 96.6 s (includes the serial outage tests: Redis, Elasticsearch and the new MySQL-down test showing 503 and not 401 on both engines; the session survives the outage).
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`: all packages ok.
- `cd web && npm run test:live` with `LIVE_BASE_URL=http://127.0.0.1:8088`: 3 files, 12 tests passed.

Harness note (not a code defect): the first Go live runs failed because I had not exported `E2E_BASE_URL` (default port 8080) and `MYSQL_ROOT_PASSWORD`; the first of those timed out after 10 minutes on `waitReady`. With `E2E_BASE_URL=http://127.0.0.1:8088`, `SERVICE_CONF` pointing at the git-ignored host-side `conf/service_conf.yaml` and `MYSQL_ROOT_PASSWORD` read from `docker/.env` (never printed), everything passed. The earlier session's note that `SERVICE_CONF` is needed for the Go tier still applies.

Stack stopped afterwards with `docker compose -p devrag-stack ... stop` for profiles cpu, elasticsearch, mail (no `down`, no volume removal); `docker ps --filter name=devrag-stack` is empty. The foreign `compose` project was not touched. No Chrome or server process of this plan remains (`pgrep`).

## Final checks (observed)

- `make ci`: 7/7 gates passed, ruff security selection passed.
- `uv run python run_tests.py -m unit`: 712 passed, 1 skipped, 228 deselected.
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok.
- `GOTOOLCHAIN=local go vet ./...`: clean.
- `cd web && npm run test -- --run`: 15 files, 195 tests passed.
- `scripts/gen_routes.py --check` and `scripts/export_openapi.py --check`: exit 0.

## Test-first record

The tests were written and committed first by the earlier session (ce97b62, with the implementation in d8b0628). The failing output of that RED state was not recorded, and I could not observe the pre-change failures: I did not check out the old tree, because that would have meant discarding or moving working-tree state. In this session no new behaviour was added, so there was no new RED step. Task 3's adapted Phase 1 tests were validated by the live run above.

## Deviations from Plan

1. [Rule 1 - Bug] Go gate trusted `X-Forwarded-Host` and `X-Forwarded-Proto` from any peer (plan 02-10). Fixed in 250586e with the loopback-peer rule and tests; recorded as R-115, R-116 (the orchestrator's task B).
2. [Rule 3 - Blocking] `test_init_db_entry_point_exit_codes` failed on a missing `SECRET_KEY`; fixed in f71e3a2 (the orchestrator's task A) and the deferred-items file removed.
3. The plan's Task 2 listed `api/db/services/__init__.py` and `api/apps/route_policy_gen.py` as modified; neither needed a change (the policy resolver was generated by plan 02-08).
4. Plan item "beta accepts only api_token.beta" is implemented as "beta rows accept the beta value, and also access and API tokens" as the plan's own task text says (reference behaviour); beta values are accepted only on beta rows. Recorded in R-117.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-02-59 to T-02-64B are all covered by tests listed above).

## Self-Check: PASSED

All five commit hashes exist in `git log`; `api/apps/auth.py`, `api/db/services/auth_service.py`, `common/security/proxy.py`, `test/testcases/test_route_enumeration.py`, `test/testcases/test_auth_flow.py` exist.
