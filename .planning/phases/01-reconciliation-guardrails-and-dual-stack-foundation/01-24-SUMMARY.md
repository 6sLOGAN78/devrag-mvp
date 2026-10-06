---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 24
subsystem: testing
tags: [exit-gate, gap-closure, clean-room, records]
gap_closure: true
requires:
  - phase: 01-16
    provides: real DB pooling and safe retry
  - phase: 01-17
    provides: log redaction fixes
  - phase: 01-18
    provides: frontend token handling fixes
  - phase: 01-19
    provides: route auth markers and enforcement
  - phase: 01-20
    provides: gate script and test-runner fixes
  - phase: 01-21
    provides: container runtime fixes
  - phase: 01-22
    provides: envelope, migration and hook fixes
  - phase: 01-23
    provides: config renderer and CI workflow fixes
provides:
  - Three consecutive clean-room passes after all gap fixes
  - Decision rows R-85, R-86, R-87 and blocker entries B-15, B-16
affects: [phase-02]
tech-stack:
  added: []
  patterns: [gate base URLs derived from SVR_WEB_HTTP_PORT, bounded wait for container health after dependency recovery]
key-files:
  created: []
  modified: [scripts/clean_room.sh, test/testcases/test_dependency_outage.py, scripts/ci/check_decisions.py, .planning/DECISIONS.md, .planning/BLOCKERS.md]
key-decisions:
  - "devRag dev web port on this host is 8088 (user choice, R-87); documented default stays 8080"
  - "RAM threshold not lowered; no PREFLIGHT override other than the recorded map-count one"
requirements-completed: [DATA-03, SEC-04, DEPLOY-12, DEPLOY-14, TEST-01, TEST-10, API-04, UI-03]
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 1 Plan 24: Gap-Closure Exit Gate Summary

**After the gap fixes, three consecutive teardown-and-rebuild cycles of `devrag-stack` passed every suite; getting there took three attempts and exposed two more defects.**

This plan was run inline by the orchestrator (it uses the Docker commands the user allowed for the 01-15 gate).

## Task 1: pre-gate checks

| Check | Result |
|---|---|
| `make ci` | 7/7 gates passed |
| `run_tests.py -m unit` | 349 passed, 1 skipped (B-13) |
| `go test -count=1 -race ./internal/... ./cmd/...` | ok |
| `scripts/gen_routes.py --check` | exit 0 |
| `web: npm run test -- --run` | 59 passed |
| MemAvailable (stack stopped) | 6513 MB, threshold 4096 MB unchanged |
| `devrag-stack` working-dir label | `/home/logan78/desktop x/devRag_@/docker` only (this checkout) |

The memory checkpoint was auto-satisfied; no user action was needed.

## Task 2: gate attempts

| Attempt | Outcome | Cause | Fix |
|---|---|---|---|
| 1 | Failed at preflight on run 1, before any teardown | Host port 8080 held by `compose-gateway-1`, another of the user's projects (not touched) | User chose to move devRag to another port. `SVR_WEB_HTTP_PORT=8088` in the git-ignored `docker/.env`. The gate also had a real defect here: Go e2e, Go manual and vitest live tiers default to 8080 from environment variables and ignored `docker/.env`. `clean_room.sh` now exports `E2E_BASE_URL`, `MANUAL_BASE_URL`, `LIVE_BASE_URL` from `SVR_WEB_HTTP_PORT` (commit `f6a8203`) |
| 2 | Run 1 passed; run 2 failed in `e2e-serial`: `test_doc_store_outage_is_independent_of_go` asserted `app == healthy`, got `unhealthy` | Test race. healthz reports dependency health (D-08), so the app container goes unhealthy during the Elasticsearch outage and Docker flips it back only on its next 10 s probe; the test asserted immediately after the HTTP endpoints recovered | Bounded `wait_until` (60 s) before the unchanged assertion (commit `5000b88`). The serial tier then passed three times in a row on the running stack before the gate was restarted |
| 3 | **Passed: exit 0, 48 of 48 steps, `clean-room: 3 run(s) passed`** | — | — |

Command: `GOTOOLCHAIN=local PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 scripts/clean_room.sh --runs 3`, log at `ragflow-logs/clean_room_gate.log` (git-ignored). No other `PREFLIGHT_*` value was set. 0 `REFUSED` lines; `PASS project-guard` 3 times; `PASS go-race` 3 times.

| Run | Started (UTC) | Time to healthy | Cycle time | Free disk after |
|---|---|---|---|---|
| 1 | 2026-10-06T18:43:24Z | 40 s | 150 s | 24G |
| 2 | 2026-10-06T18:45:54Z | 35 s | 139 s | 24G |
| 3 | 2026-10-06T18:48:13Z | 37 s | 144 s | 24G |

Per run, identical on all three:

| Step | Result |
|---|---|
| Python unit | 349 passed, 1 skipped |
| Python integration | 79 passed |
| Python e2e (non-serial) | 60 passed |
| Python e2e serial | 3 passed |
| Go `-race -count=1` | ok, 0 cached results in the log |
| Go `integration,e2e`, `manual`, `cgo` tiers | ok |
| Frontend unit | 59 passed |
| Frontend live | 9 passed |

Collected by the gate's markers (checked with `--collect-only`): the five live `test_db_core.py` tests for pool reuse, connection cap, retry after KILL, write-after-kill applied once and no replay on a held killed connection are in the `integration` selection; the six parametrised `test_unmarked_auth_route_is_not_public_through_ingress` cases are in the `e2e and not serial` selection. The log is quiet-mode, so their individual names are not printed in it; the evidence is the selection plus zero failures.

Measured memory, run 3, this host only: app 93.1, es01 1482.8, minio 61.0, mysql 264.8, redis 3.9 MiB; total 1905.6 MiB against a 3891 MiB budget.

After the gate: `curl /api/v1/system/status` on port 8088 returned `code 0` with all checks `ok`; `curl -I /health` returned `X-Api-Source: go`.

Foreign Docker resources: the lists of non-`devrag-stack` containers and volumes were identical before attempt 1 and after attempt 3. The `compose` project was not touched.

## Task 3: records

- DECISIONS.md: R-85 (gap-closure behaviour changes), R-86 (interim scope of Go schema verification), R-87 (dev web port 8088 on this host, user-confirmed). `check_decisions.py`: `decisions OK: 87 rows`.
- `scripts/ci/check_decisions.py`: R-87 added to the pinned user-confirmed set with a dated comment, because the user made that choice on 2026-10-07. The checker otherwise rejects any row marked user-confirmed.
- BLOCKERS.md: B-15 (deferred findings WR-06, WR-10, WR-20, WR-23, IN-01..18 with reasons and landing phase), B-16 (port 8080, mitigated), dated updates on B-06 and B-14.
- REQUIREMENTS.md: DATA-03 stays Complete, now backed by the fake-driver pool tests (11 of 17 failed before the fix) and the live pool tests passing in three gate runs. No other row changed.

## Not verified

- `.github/workflows/ci.yml` has never run on GitHub (B-06).
- TLS is verified with a self-signed certificate only (B-10).
- The stack was verified on port 8088 in this gate; port 8080 was last verified in the 2026-10-06 gate, before the gap fixes.
- Timing and memory figures are from one machine.

## Self-Check: PASSED

- Commits `f6a8203` and `5000b88` exist.
- `ragflow-logs/clean_room_gate.log` contains `clean-room: 3 run(s) passed` and no `FAIL` line.
