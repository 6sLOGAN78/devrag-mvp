---
phase: 02-identity-tenancy-and-authorization
plan: 03
subsystem: decision-register
tags: [decisions, blockers, ci-gate, AUTH-08, SEC-09]
requires: []
provides:
  - DECISIONS rows R-33..R-36, R-40 resolved; R-88..R-114 added (D-01..D-31 traceability)
  - pinned CONFIRMED set extended with the user-decided Phase 2 rows
  - BLOCKERS B-15 landing plans
key-files:
  modified:
    - .planning/DECISIONS.md
    - .planning/BLOCKERS.md
    - scripts/ci/check_decisions.py
    - test/unit_test/test_check_decisions.py
decisions:
  - "Mixed rows were split so every user-confirmed row records only the user's choice; implementation details chosen by research live in auto rows."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 03: Decision and blocker records Summary

Recorded every Phase 2 auth-contract decision with a truthful status: 14 rows pinned `user-confirmed` (choices the user made in person), all research, planner and orchestrator choices `accepted (auto, not user-reviewed)`.

## Commit

- b748370 docs(02-03): Tasks 1, 2 and 3 in one commit (per executor notes, so no commit has a failing gate)

## Rows

- Changed: R-33, R-34, R-35, R-36, R-40 resolved; notes added to R-55 and R-84 (D-19 implemented by plans 02-10 and 02-14); status legend updated.
- Added: R-88..R-114 (27 rows). Total 114 rows.
- User-confirmed (new): R-33, R-36, R-91, R-95, R-98, R-100, R-101, R-102, R-103, R-104, R-105, R-106, R-108, R-109. Basis: the user's answers in the Phase 2 discuss session (D-01..D-16) and post-research approval (D-20..D-23), per 02-CONTEXT.md and 02-DISCUSSION-LOG.md. Pinned set is now {3, 17, 18, 48, 49, 87} plus these, with a dated comment.
- Auto: R-34, R-35, R-40, R-88..R-90, R-92..R-94, R-96, R-97, R-99, R-107, R-110..R-114 (D-24..D-31, enumeration trade-off, rate limits, R-112/R-113/R-114 orchestrator decisions).

## Tests (TDD)

Pre-change failure: with rows marked user-confirmed and CONFIRMED unextended, the gate reported 14 "must not be user-confirmed" errors; new tests failed 15 (14 plus real-repo). After extending CONFIRMED: gate OK (114 rows), 36 check_decisions tests pass (parametrised both directions: each user row demoted fails; each auto row promoted fails).

## Deviations from Plan

1. [Truthfulness] The plan text marked R-91 and R-95 user-confirmed while including details the user did not choose. Per the sources, those details were moved out: the Origin-check mechanism went to R-90; the mailpit tag `v1.31.4` and Go `net/smtp` went to R-96 (auto). R-91 and R-95 record only D-21 and D-05/D-20. R-98 also drops a "no language-detector package" claim in favour of "no package beyond the D-20 set". The pinned set itself matches the plan exactly; no row number was added or removed.
2. R-95 places the mailpit service in `docker/docker-compose.dev.yml` only (plan amendment) although 02-RESEARCH.md suggested `docker-compose-base.yml`.
3. R-97 records what plan 02-01 did (user kept in URL userinfo, password redacted only; 22 vectors; 512-character path cap). B-15: WR-06 and WR-23 are recorded as closed by 02-02, which matches 02-02-SUMMARY.
4. Task 3 touched only B-15; B-08 left for plan 02-19. Status stays open until plan 02-26.

## Final checks (as observed)

- `uv run python scripts/ci/check_decisions.py`: `decisions OK: 114 rows`
- `make ci`: 7/7 gates passed, ruff clean
- `uv run python run_tests.py -m unit`: 447 passed, 1 skipped, 142 deselected

## Known Stubs

None.

## Self-Check: PASSED
