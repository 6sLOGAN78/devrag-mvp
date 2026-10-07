---
phase: 02-identity-tenancy-and-authorization
plan: 08
subsystem: auth
tags: [routes, policy, default-deny, nginx, codegen]
requires: [02-03]
provides:
  - "conf/routes.yaml endpoints: registry (31 rows)"
  - "Go PolicyFor(method, path) and Python policy_for(method, path), generated"
affects: [02-10, 02-14]
key-files:
  created: [internal/common/route_policy_gen.go, api/apps/route_policy_gen.py, test/unit_test/test_route_policy.py, internal/common/route_policy_test.go, test/fixtures/route_policy_cases.json]
  modified: [conf/routes.yaml, scripts/gen_routes.py, docker/nginx/ragflow.conf, docker/nginx/ragflow.https.conf, web/src/constants/api-routes.generated.json, test/unit_test/test_gen_routes.py, test/unit_test/test_gen_go_entities.py]
decisions:
  - "Policy precedence: registry row (method + path, {param} = one non-empty segment), exact family, longest prefix family, default jwt with empty owner (deny). OPTIONS resolves via families only and sets Preflight."
  - "Role vocabulary in registry rows: owner, admin, normal, invite (pending invitee), self; empty list means any authenticated caller."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 08: Route registry and generated policy Summary

One registry in `conf/routes.yaml` now drives Nginx, the Vite proxy JSON, a Go resolver and a Python resolver; unmatched paths resolve to jwt (deny) in both languages. No runtime behaviour changed and no auth is enforced yet.

## Registry
31 rows. By owner: go 26, python 5. By auth: jwt 17, none 11, beta 2, api 1. `implemented: true` 10 (health, ping, config, language, system version and status with the `/system/status` alias, healthz with its alias, openapi.json); 21 are `implemented: false`. Family changes: exact `/api/v1/auth/logout` (jwt), exact `/api/v1/system/tokens` and prefix `/api/v1/system/tokens/` (go, jwt), prefix `/api/v1/tenants/` (go, jwt); Python catch-alls `/api/` and `/v1/` moved jwt to api. The two `public_until_phase` markers are untouched.

## TDD record
Task 1 (commit a186817): 35 Python tests failed (no registry, no generated module), Go test package did not compile (`undefined: PolicyFor`). After Task 2 all 74 selected Python tests and the Go common tests pass. Validation tests cover owner/auth disagreement, unknown auth/scope/method/role, wrong bool type, extra field, duplicate row, row matched by no family, and stale generated files failing `--check`.

## Deviations from Plan
1. [Rule 3] `test_gen_routes.py` CASES expected `/api/v1/system/tokens` owned by python; the plan moves it to Go, so the expectation was changed (plus new cases). The assertion `"location ^~ /api/v1/system/" not in conf` was a substring of the new `/api/v1/system/tokens/` location; it now checks the exact broad location `^~ /api/v1/system/ {`. Intent (no broad system prefix) is preserved.
2. [Rule 3] `test_gen_go_entities.py` copies generated outputs into a temp root for a drift test; the new Go policy file was added to that copy list (the Python one arrives through the `api/` symlink).
3. Tasks 2 and 3 were committed together (66d295e) because the Task 3 tests live in a file whose edits were interleaved with Task 2.
4. `ruff format` reformatted `scripts/gen_routes.py` and `test/unit_test/test_gen_routes.py` (both edited by me), enlarging that diff.
5. `test/testcases/test_route_ownership.py` probes now include new Go families; it needs the live stack and was not run (no Docker per constraints).

## Known Stubs
None. Rows with `implemented: false` declare future handlers only.

## Verification (as observed)
- `make ci`: 7/7 gates passed, ruff clean
- `run_tests.py -m unit`: 602 passed, 1 skipped
- `go test ./cmd/... ./internal/...`: all ok; `go vet ./...` ok
- web `npm run typecheck` clean; `npm run test -- --run` 59 passed

## Self-Check: PASSED
