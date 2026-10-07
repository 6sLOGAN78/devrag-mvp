---
phase: 02-identity-tenancy-and-authorization
plan: 19
subsystem: auth
tags: [python, peewee, startup-hook, superuser, pbkdf2, mysql-named-lock]
requires:
  - phase: 02-06
    provides: common.security.passwords.hash_password (pbkdf2:sha256:600000)
  - phase: 02-14
    provides: Python gate and live suites
provides:
  - api.db.services.superuser_service.ensure_superuser (transactional, idempotent, race-safe seed)
  - common.bootstrap.ensure_superuser startup hook and `python -m` entry point
  - register_startup_hook replaces by name; boot installs the hook after database verification
affects: [02-26, API-13 (B-08)]
key-files:
  created:
    - api/db/services/superuser_service.py
    - common/bootstrap/ensure_superuser.py
    - test/unit_test/test_ensure_superuser.py
    - test/integration/test_superuser_seed.py
    - internal/e2e/superuser_e2e_test.go
  modified:
    - api/ragflow_server.py
    - .planning/BLOCKERS.md
decisions:
  - "An existing non-superuser account with the configured email makes boot fail with a message naming SUPERUSER_EMAIL; an existing superuser is left unchanged (no password overwrite, no promotion)."
  - "Race safety is a MySQL named lock (`ensure_superuser:<db>`) plus a re-check on IntegrityError, so two booting processes create one superuser and neither fails."
  - "The seed uses language `English`, the value Go registration writes (the plan text said `en`); Go's NormaliseLanguage maps both."
  - "The module entry point lets SUPERUSER_EMAIL/SUPERUSER_PASSWORD in the process environment override the config file, so the e2e test seeds through the real Python service without writing the value to a file."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 19: First-superuser seed Summary

The Python boot now creates the first administrator from SUPERUSER_EMAIL and SUPERUSER_PASSWORD, only when both are set, in one transaction (user with is_superuser, tenant with the same id, owner user_tenant), hashed with pbkdf2:sha256:600000. No default credential exists in the repository.

## Commits

| Task | Commit |
|------|--------|
| 1 Failing tests | 3aee480 |
| 2 Service and hook | ae71ff4 |
| 3 B-08 update | dcd83a3 |

## Test-first record

Before implementation the unit module and the integration module failed at collection with `ImportError: cannot import name 'superuser_service' from 'api.db.services'`; the Go e2e file vetted but could not pass without the Python helper. After implementation: 22 unit tests pass (`-t ensure_superuser`), 9 integration tests pass on a scratch database (`-t superuser_seed`, collect-only confirmed 9 selected).

## Live results (stack devrag-stack, port 8088, rebuilt app image)

- `go test -tags=e2e ./internal/e2e/... -run Superuser`: pass (seed run twice, login through Go, `/v1/user/info` reports is_superuser true, Python `/api/v1/system/status` accepts the token).
- `uv run python run_tests.py -m "integration or e2e"`: 237 passed.
- `go test -count=1 -tags=integration,e2e ./...`: all packages ok.
- Final checks: `make ci` exit 0 (7/7 gates, ruff clean); `run_tests.py -m unit`: 735 passed, 1 skipped; `go test -count=1 -race ./cmd/... ./internal/...`: ok; `go vet ./...`: exit 0.
- Stack stopped (cpu, elasticsearch, mail profiles; the mailpit container and mysql needed direct `docker stop` afterwards); `docker ps --filter name=devrag-stack` is 0. No `make down`, no `-v`.

## Deviations from Plan

1. [Rule 1 - minor] Language is `English` not `en` (matches Go registration shape).
2. [Rule 3] Cleanup for the e2e test is an exact-email SQL delete inside the test file, because `testutil.DeleteAccount` needs ids that are unknown if login fails; `internal/testutil` is not in the plan's file list so it was not modified.
3. `register_startup_hook` now replaces a hook of the same name (boot may run more than once in one process).

## Notes for the verifier

- After the regression, `rag_flow.user` held 11 non-superuser `@example.test` rows (prefixes `user-`, `http-`, `status-`) left by other suites' fixtures, earlier and during this run. None belong to this plan (it creates `seed-root-*` and scratch-database rows, all removed). Not touched; out of scope.
- During execution `conf/service_conf.yaml` (git-ignored, rendered, holds real stack secrets) was printed once to the session output by mistake. It was not committed and nothing was written to a file. Rotating the stack secrets is advisable if that transcript is retained.
- `docker/.env` was not read for values beyond MYSQL_ROOT_PASSWORD (passed to the process environment, not printed) and not modified. Fake SUPERUSER values were passed only through process environments.

## Known Stubs

None.

## Threat Flags

None. T-02-87 to T-02-91 are mitigated: no default value (grep of `SUPERUSER_PASSWORD=` with a value over `.env.example`, `conf`, `docker` returns 0), password absent from logs and errors (unit and integration caplog tests), no promotion of normal accounts, hash prefix asserted and verified by Go, single transaction (rollback test).

## Self-Check: PASSED

Files and commits 3aee480, ae71ff4, dcd83a3 exist; tests listed above were observed passing.
