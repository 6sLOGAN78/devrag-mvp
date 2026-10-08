---
phase: 02-identity-tenancy-and-authorization
plan: 26
subsystem: testing
tags: [exit-gate, clean-room, records, requirements, blockers, validation]
requires: [02-01, 02-02, 02-03, 02-04, 02-05, 02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-12, 02-13, 02-14, 02-15, 02-16, 02-17, 02-18, 02-19, 02-20, 02-21, 02-22, 02-23, 02-24, 02-25, 02-27, 02-28]
provides:
  - three consecutive green clean-room runs of the full Phase 2 suite (gate evidence below)
  - gate stack that includes the dev mail profile and exports the host-run test environment
  - truthful Phase 2 requirement, blocker, decision and validation records
affects: [phase-2 verification, Phase 3 planning]
key-files:
  modified:
    - scripts/clean_room.sh
    - test/unit_test/test_clean_room_guard.py
    - .planning/REQUIREMENTS.md
    - .planning/BLOCKERS.md
    - .planning/DECISIONS.md
    - .planning/phases/02-identity-tenancy-and-authorization/02-VALIDATION.md
key-decisions:
  - "R-128: the gate stack runs the mail profile and exports SERVICE_CONF and MYSQL_ROOT_PASSWORD for the host-run tiers"
requirements-completed: [E2E-01, E2E-02, SEC-01]
metrics:
  tasks: 3
  completed: 2026-10-08
---

# Phase 2 Plan 26: Phase 2 exit gate and truthful records Summary

The full Phase 2 suite passed three consecutive times from a clean rebuild of project `devrag-stack` (web port 8088), and the requirement, blocker, decision and validation records now say what was proven: 45 of 48 Phase 2 requirements ticked (7 annotated, AUTH-23 with blocker), 3 left unticked as partial (TEN-01, TEN-05, UI-42).

## Commits

| Task | Commit |
|------|--------|
| 1 RAM, disk and port check | no commit (read-only measurement, below) |
| 2 Gate stack uses the mail profile and exports the host-run test environment | 63cfbff |
| 3 Records (REQUIREMENTS, BLOCKERS, DECISIONS, VALIDATION, memory record from the gate) | 5f04a0b |

## Task 1: preflight measurements (2026-10-08, stack stopped)

MemAvailable 8510 MB (at least 4096, no pause, `PREFLIGHT_MIN_RAM_MB` untouched); free disk 9 GB; port 8088 free; foreign compose project `compose`: 0 containers running before and 0 after.

## Task 2: test-first record and gate

- Three tests were added to `test/unit_test/test_clean_room_guard.py` first. RED: 2 failed, 1 passed (`test_gate_stack_uses_the_mail_profile_and_the_dev_overlay` and `test_gate_exports_the_environment_host_run_tiers_need_without_printing_it` failed; `test_production_compose_has_no_mail_service_and_r94_rate_limit_defaults` already held, so it is a regression pin). After the change: 32 clean-room guard tests passed.
- `scripts/clean_room.sh` adds `--profile mail` and exports `SERVICE_CONF` (default `conf/service_conf.yaml`) and `MYSQL_ROOT_PASSWORD` (read from the git-ignored `docker/.env`, never printed). The project guard, the `down -v` scope and the readiness helper are unchanged.
- Command: `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 GOTOOLCHAIN=local scripts/clean_room.sh --runs 3` exited 0 with "clean-room: 3 run(s) passed", on the first attempt, no re-run, `PREFLIGHT_MIN_RAM_MB` not lowered, web port 8088. The map-count override (measured 65530, B-02) was recorded each run.

| Run | Start (UTC) | Duration | RAM available at preflight | Time-to-healthy |
|-----|-------------|----------|----------------------------|-----------------|
| 1 | 2026-10-08T08:50:03Z | 386 s | 8451 MB | 35 s |
| 2 | 2026-10-08T08:56:29Z | 358 s | 9719 MB | 37 s |
| 3 | 2026-10-08T09:02:27Z | 364 s | 9966 MB | 44 s |

Per run, identical counts in all three:

| Tier | Result |
|------|--------|
| Python unit | 792 passed, 1 skipped (the docker-collision test in `test_preflight.py`, which skips when no foreign project named `devrag` exists) |
| Python integration | 95 passed |
| Python e2e (not serial) | 181 passed |
| Python e2e (serial) | 4 passed |
| Go race (`./internal/... ./cmd/...`) | PASS (per-package ok, no counts reported) |
| Go integration + e2e tags | PASS |
| Go manual tag | PASS |
| Go cgo tag | PASS |
| vitest unit | 30 files, 581 tests passed |
| vitest live | 8 files, 36 tests passed |
| Memory step | PASS (run 1: total 2002.3 MiB of budget 3891; es01 1506.3, mysql 277.4, app 102.8, minio 79.4, mailpit 30.6, redis 5.8) |

Disk: 8.2 to 8.3 GB free at preflight, 9G after run 1. After the gate the stack was stopped with compose `stop` (0 `devrag-stack` containers running; 0 foreign `compose` containers, unchanged). `uv run python scripts/ci/run_all.py`: 7/7 gates passed. The gate's `record_memory.py --record` step rewrote the "Dev memory budget" table in `DECISIONS.md` (memory record only; kept and committed in 5f04a0b).

## Task 3: records

### Requirement assessment (48 Phase 2 requirements)

Every tick cites a plan SUMMARY and a test tier that ran in the gate.

- **Ticked plainly (37):** AUTH-01, 02, 03, 05, 07, 08, 09, 11, 13, 14, 15, 17, 18, 19, 20, 21, 22; TEN-02, 04, 06, 07, 08, 09, 10, 11; UI-02, 04, 06, 07, 09, 34, 35, 36, 43; SEC-01, SEC-09; E2E-01.
- **Ticked and annotated (7):** AUTH-04 (as decided in D-22), AUTH-06 (model ids empty until configured, D-22), AUTH-10 (as decided in D-21), AUTH-12 (per-route credential policy, R-117), AUTH-16 (proven against the local mail catcher; real SMTP is manual, B-20), UI-08 (four tiers established, agent, chat and document stores arrive with their features), E2E-02 (default model id fields present, values empty until configured).
- **Complete with blocker (1):** AUTH-23, proven on a test-registered route only (B-19, Phase 8).
- **Partial, left unticked, status "Partial" in the traceability table (3):** UI-42 (en and zh only, es, fr, ja deferred, Chinese text unreviewed; B-18, B-20), TEN-01 (filtering enforced and matrix-tested only for the tenant-owned routes that exist; B-22), TEN-05 (permission table generated and tested for all 10 areas, enforced only for team administration; B-22).
- No requirement of another phase was ticked.

### Blockers

- B-15: WR-06, WR-10, WR-20 and WR-23 closed with plan numbers; CR-02, WR-04, WR-16, WR-19, WR-24, WR-25 and WR-26 recorded closed; status set to mitigated because only the informational IN-01..IN-18 backlog remains. WR-20 is closed on a unit test only (no dev server was started).
- B-02 updated with the gate's override. B-08 and B-17 unchanged (B-17 stays open: per-IP limits behind Docker's port proxy need a user deployment decision). B-14 not touched (the measurement forced no pause).
- New open entries: B-18 (es, fr, ja), B-19 (beta token real routes), B-20 (manual: real SMTP, Chinese review), B-21 (BILL-01 plaintext tokens), B-22 (TEN-01, TEN-05 scope), B-23 (405 raw path in logs, R-127), B-24 (old files under `ragflow-logs/`), B-26 (`npm audit`: 8 findings, 5 high and 3 moderate, measured today), B-27 (dev stack secrets printed in the plan 02-19 transcript). New mitigated entry: B-25 (leftover test accounts: older rows were removed by the gate's `down -v`; rows from the last run may remain and were not inspected).

### Decisions and validation

- R-55 and R-84 carry an implementation-status note (D-19 delivered); R-98 notes es, fr, ja deferred and the unreviewed Chinese text; R-128 records the gate setup. No status pinned by `CONFIRMED` changed.
- `02-VALIDATION.md`: every row mapped to plans and tasks and set green (the tiers ran in all three gate runs); Wave 0 and sign-off boxes ticked; `nyquist_compliant: true` and `wave_0_complete: true` because every box holds, including feedback latency (quick tier measured about 46 s: Python unit 17.5 s, Go race 13.9 s, vitest 14.4 s). The Manual-Only table stays open.

### Checks (as observed after the record edits)

- `uv run python scripts/ci/check_decisions.py`: "decisions OK: 128 rows", exit 0.
- D-01..D-31 grep loop over the plan files: printed nothing (every decision cited).
- `make ci`: 7/7 gates passed, ruff passed, exit 0.
- `uv run python run_tests.py -m unit`: 792 passed, 1 skipped, 280 deselected.

## Deviations from Plan

1. **[Rule 3 - Blocking] Gate script exports beyond "add the profile".** The plan asked only for `--profile mail`. Without `SERVICE_CONF` and `MYSQL_ROOT_PASSWORD` in the environment, the Go scratch-database tests skip and the fixture tests fail when the gate runs them from the host, so `clean_room.sh` also exports both (the password is read from `docker/.env` and never printed). Covered by a guard test and recorded as R-128. Commit 63cfbff.
2. **TEN-01, TEN-05 and UI-42 left unticked.** The plan expected TEN-01 and TEN-05 to be ticked; their text names entities and permission areas whose routes do not exist until Phases 3, 7 and 8, so they are recorded as partial with B-22 rather than overstated.
3. **AUTH-06, AUTH-12, AUTH-16, UI-08 and E2E-02 annotated** beyond the two the plan named, for the reasons above.
4. **`npm audit` was run** (read-only, network) to give B-26 real counts; no package was changed.

## Open items

- User: review UI-42 Chinese copy and real SMTP delivery (B-20); supply es, fr, ja reviewers (B-18); decide on B-17 (client IP behind Docker's port proxy), B-26 (`npm audit`), optionally delete old `ragflow-logs/` files (B-24) and rotate local secrets (B-27).
- Later phases: TEN-01 and TEN-05 closure with each new tenant-owned route (B-22); beta token on real Phase 8 routes (B-19); hashed API keys with BILL-01 (B-21); make the web live helper delete its accounts (B-25).
- B-03, B-04, B-07 to B-13 are unchanged and still open; B-02 only gained the gate's override note.
- The Python unit tier has one skipped test (docker-collision test), expected on this host. No Phase 2 test was skipped, weakened or xfailed to reach green.

## Known Stubs

None created by this plan.

## Self-Check: PASSED

Commits 63cfbff and 5f04a0b exist; `02-VALIDATION.md`, `REQUIREMENTS.md`, `BLOCKERS.md` and `DECISIONS.md` carry the edits described above; `check_decisions.py`, `make ci` and the unit tier were re-run after the last record edit.
