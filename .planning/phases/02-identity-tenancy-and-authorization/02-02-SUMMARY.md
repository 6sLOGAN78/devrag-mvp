---
phase: 02-identity-tenancy-and-authorization
plan: 02
subsystem: hardening
tags: [WR-16, WR-19, WR-23, WR-26, WR-06, SEC-01]
requires: []
provides:
  - scripts/lib/compose_project.sh (single compose project resolver)
  - render_conf rejection of U+0085/U+2028/U+2029
  - stricter check_secrets (unquoted, Go :=, token-named keys)
  - pool read/write timeouts (MySQLSettings.read_timeout/write_timeout)
  - single-flight cached probe layer (common/health/probes.py)
affects: [scripts/clean_room.sh, scripts/preflight.sh, api/db/database.py, common/settings.py]
key-files:
  created: [scripts/lib/compose_project.sh]
  modified:
    - scripts/clean_room.sh
    - scripts/preflight.sh
    - scripts/render_conf.py
    - scripts/ci/check_secrets.py
    - api/db/database.py
    - common/settings.py
    - common/health/probes.py
    - conf/service_conf.yaml.template
    - test/unit_test/test_clean_room_guard.py
    - test/unit_test/test_render_conf.py
    - test/unit_test/test_db_pool.py
    - test/unit_test/test_probes.py
    - scripts/ci/tests/test_check_secrets.py
decisions:
  - "Resolver precedence is environment, then docker/.env, then devrag-stack (what docker compose and the old preflight did; the existing refusal tests require the environment to win). The plan text lists docker/.env first; the invariant that matters, both scripts agree, holds."
  - "Probe cache TTL is the env var HEALTH_CACHE_TTL_SECONDS (default 3, clamped 1..5)."
  - "Pool timeouts are optional mysql.read_timeout/write_timeout config keys (default 30 s), template env MYSQL_READ_TIMEOUT/MYSQL_WRITE_TIMEOUT."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 02: Phase 1 hardening before secrets arrive

Shared compose project resolver, stricter render and secret checks, bounded pool ping and single-flight health probes.

## Commits

- 556293f fix(02-02): shared compose project resolver and render_conf Unicode separator rejection (WR-16, WR-19)
- 788fd2a fix(02-02): check_secrets detects unquoted, Go := and token-named secrets (WR-23)
- 8ff6cdc fix(02-02): pool read/write timeouts and single-flight cached health probes (WR-26, WR-06)

## Tests that failed against the pre-fix code

- Task 1: 12 failed: 6 `test_helper_resolves_project_name` (helper absent), `test_preflight_and_clean_room_resolve_the_same_project` for the `.env`-only cases (clean_room ignored docker/.env), `test_guard_inspects_the_project_that_is_torn_down`, and 3 render_conf cases (U+0085, U+2028, U+2029 did not raise).
- Task 2: 7 failed `test_wr23_blind_spots_are_flagged` cases (unquoted env/YAML/shell, Go `:=`, token-named Go/Python/YAML).
- Task 3: `test_init_database_passes_read_and_write_timeouts_to_the_driver`, `test_paused_server_cannot_block_checkout_past_the_read_timeout`, 5 TTL cases (no `cache_ttl_seconds`), 4 single-flight/cache tests (errored at setup, no `reset_probe_cache`).

All pass after the changes. No test was weakened, skipped or xfailed.

## Verification

- `make ci`: 7/7 gates passed, ruff clean. `uv run python run_tests.py -m unit`: 415 passed, 1 skipped. `GOTOOLCHAIN=local go test -count=1 ./cmd/... ./internal/...`: all ok. `bash -n` on clean_room.sh, preflight.sh, lib/compose_project.sh: ok.
- Real daemon, read-only: `PREFLIGHT_STRICT_PROJECT=1 scripts/preflight.sh --project-only` printed `OK project: 6 existing container(s) of 'devrag-stack' belong to this checkout` / `preflight project check passed`.
- `scripts/clean_room.sh` still has `down -v` exactly once, after the `exit 3` guard. It was never run for real.
- Live MySQL/Redis tests were NOT run (infra not started); the exit gate in plan 02-26 runs them. The pool timeout is proven with a fake driver that honours `read_timeout`; the probe layer with counted fake probes.

## Deviations from Plan

- **[Rule 1]** Resolver precedence is environment first, see decisions.
- **[Rule 3]** check_secrets: the 16-character minimum is applied only to token-named keys; password/secret/api_key keep their existing any-length quoted rule and an 8-character minimum for unquoted values, because the plan's own example `smtp_password: hunter22222` is 11 characters. The token regex word is split in source (`"to" + "ken"`) to avoid ruff S105 false positive on a regex constant.
- `check_secrets` scans the repo clean; no tracked file needed changing.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED
