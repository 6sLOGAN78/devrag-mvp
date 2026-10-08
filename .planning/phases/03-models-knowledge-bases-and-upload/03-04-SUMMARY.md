---
phase: 03-models-knowledge-bases-and-upload
plan: 04
subsystem: api
tags: [routes, permissions, nginx, tenancy, python, go]
requires:
  - phase: 02
    provides: route registry generator, permission table, Principal and auth gate
provides:
  - Phase 3 endpoint registry rows (providers, models, datasets, documents), all implemented false
  - tenant_settings view_models and set_default_models permission rows in Go and Python
  - Nginx body-limit families (upload 101m, JSON 1m)
  - api/db/services/tenant_scope.py acting-workspace, visibility and object rules
affects: [03-12, 03-13, 03-14, 03-16, 03-17, 03-18, 03-19]
tech-stack:
  added: []
  patterns:
    - "A registry row may tighten an api or beta family to jwt (key-writing methods)"
    - "Permission subject derived from auth_type, never the token owner's role"
key-files:
  created:
    - api/db/services/tenant_scope.py
    - test/unit_test/test_tenant_scope.py
    - test/integration/test_tenant_scope.py
  modified:
    - conf/routes.yaml
    - conf/permissions.yaml
    - scripts/gen_routes.py
    - api/apps/permissions_gen.py
    - api/apps/route_policy_gen.py
    - internal/common/permissions_gen.go
    - internal/common/route_policy_gen.go
    - docker/nginx/ragflow.conf
    - docker/nginx/ragflow.https.conf
    - web/src/constants/api-routes.generated.json
    - test/fixtures/permission_cases.json
    - test/fixtures/route_policy_cases.json
    - internal/common/permissions_test.go
    - test/unit_test/test_permissions_table.py
    - test/unit_test/test_nginx_limits.py
    - test/unit_test/test_route_policy.py
    - test/unit_test/test_probes.py
key-decisions:
  - "gen_routes.py accepts a registry row with auth jwt over a family with auth api or beta (tighten only, never loosen)"
  - "dataset_visible requires workspace membership even for the creator"
requirements-completed: [TEN-12, TEN-13, TEN-16, LLM-23, LLM-28]
duration: 25min
completed: 2026-10-09
---

# Phase 3 Plan 04: Route contracts, permission rows and acting-workspace rule Summary

All Phase 3 routes are declared in the registry, the two new permission rows are enforced identically in Go and Python, Nginx caps upload and JSON bodies separately, and `tenant_scope` resolves the acting workspace against the real MySQL.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests and oracle cases | e09fb6f | 10 expected failures recorded (oracle rows, route cases, 101m location), tenant_scope import missing |
| 2 Registry, permissions, limits, regeneration | 6eeaf8d | `gen_routes.py --check` clean; 123 unit tests and the Go permission/policy tests pass |
| 3 tenant_scope service | 47b5d39 | 26 unit (with layering) and 6 live-MySQL integration tests pass; ruff clean |
| Fix of a stale test | 874e9e2 | `test_probes` limited to implemented Python exact routes |

## Verification

- `uv run pytest test/unit_test -m unit`: 978 passed, 1 skipped.
- `uv run pytest -m integration test/integration/test_tenant_scope.py` (live stack, `LIVE_BASE_URL=http://127.0.0.1:8088`): 6 passed.
- `GOTOOLCHAIN=local go test ./internal/common/ -count=1`: ok (whole package).
- `uv run python scripts/gen_routes.py --check`: exit 0.

## Deviations from Plan

**1. [Rule 3 - Blocking] Generator forbade a row stricter than its family.** `scripts/gen_routes.py` required row auth to equal the family auth, so `PUT /api/v1/providers` (jwt) and `GET /api/v1/providers` (api) could not share the `/api/v1/providers` family. Fix: a row may tighten `api` or `beta` to `jwt`; loosening and every other mismatch are still rejected (header comment in routes.yaml updated; test added in `test_route_policy.py`). Not in the plan's file list. Commit 6eeaf8d.

**2. [Rule 1 - Bug] `test_probes.py::test_blueprint_urls_match_python_exact_routes`** assumed every Python exact family is a health path. It now counts only exact families that have an implemented endpoint row. Commit 874e9e2.

**3. Registry notes name the landing plans from the actual plan files** (providers 03-12, models 03-13, dataset create/list/detail 03-14, upload 03-16, document list/delete 03-17, dataset update/delete 03-18), not the numbers in the research draft.

Also: `internal/common/permissions_test.go` row-count check moved from 10 to 12; the Go route-policy test shares the new cases file.

## Decisions

- `dataset_visible` returns False for everyone outside the workspace, including the creator (a former member sees nothing).
- `can_remove_document` is the uploader, or anyone who may manage the dataset (its creator, owner, admin).
- `joined_tenants` returns the own workspace through its owner row, so a user whose owner row is missing has no workspace.

## Notes for next plans

- Handlers get the subject with `resolve_scope(...).subject` and call `permissions_gen.allowed(subject, area, action)`; `None` from `resolve_scope` or `scope_for_tenant` means the single 404.
- Because the family auth is `api`, the gate admits API tokens on `PUT/DELETE/POST` provider rows only if policy_for reads the row; it reads the registry row first, so they get `jwt`. Plans 03-12 and 03-19 must still test it end to end.
- Live integration tests need `LIVE_BASE_URL=http://127.0.0.1:8088`.
- The running stack was not rebuilt; the regenerated Nginx files apply on the next image build.

## Known Stubs

None. All Phase 3 registry rows are `implemented: false` by design.

## Self-Check: PASSED

Created files exist; commits e09fb6f, 6eeaf8d, 47b5d39 and 874e9e2 are in `git log`.
