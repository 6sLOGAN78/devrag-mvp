---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 19
subsystem: api-routing
tags: [routes, auth-markers, WR-05, gap-closure]
requires: [01-16]
provides:
  - "public_until_phase: 2 marker on /api/v1/system/version (R-84)"
  - "Marker-rule enforcement tests (static, Python in-process, Go in-process, live ingress)"
affects: [conf/routes.yaml, web/src/constants/api-routes.generated.json]
key-files:
  modified:
    - conf/routes.yaml
    - web/src/constants/api-routes.generated.json
    - test/testcases/_routes.py
    - test/testcases/test_route_ownership.py
    - internal/router/router_test.go
    - .planning/DECISIONS.md
  created:
    - test/unit_test/test_route_auth_markers.py
decisions:
  - "R-84: /system/version deliberately public until Phase 2 because no login exists yet (accepted, auto, not user-reviewed)"
metrics:
  completed: 2026-10-06
---

# Phase 1 Plan 19: version route public-until marker and enforcement tests Summary

`/api/v1/system/version` now carries `public_until_phase: 2` plus a note, with DECISIONS row R-84, and tests fail for any other `auth != none` route that answers 200 unauthenticated without a marker.

## Commits
- RED: test(01-19) enforcement tests
- GREEN: fix(01-19) marker, regenerated JSON, R-84

## RED (observed before the marker)
- `test_route_auth_markers.py::test_marker_rules_hold_for_routes_yaml` failed: `/api/v1/system/version: expected public_until_phase marker is missing`.
- Go `TestUnmarkedAuthRoutesNeverAnswer200Unauthenticated` failed: `/api/v1/system/version is auth=jwt, answers 200 unauthenticated, and has no public_until_phase marker`.
- Mutation test `test_marker_removal_is_detected` (removes the marker in a temp copy) and `test_marker_on_auth_none_route_is_rejected` pass, proving the rule reports the path.

## GREEN
- Both pass after the marker; `gen_routes.py --check` exits 0; generated JSON has exactly three non-null `publicUntilPhase` entries (status, its /system/status alias, version), version = 2. Nginx confs unchanged.
- `make ci`: 7/7 gates passed. `run_tests.py -m unit`: 349 passed, 1 skipped. `GOTOOLCHAIN=local go test ./cmd/... ./internal/...`: all ok.
- `-t route_auth_markers` selects 4 tests (non-empty).

## Not run
The live ingress test `test_unmarked_auth_route_is_not_public_through_ingress` (marker `e2e`) is authored but has NOT been run; it needs the full stack and is left to plan 01-24's exit gate. No containers were touched.

## Deviations
None. Note: the plan's "flagged for review" list gained an R-84 line.

## Self-Check: PASSED
