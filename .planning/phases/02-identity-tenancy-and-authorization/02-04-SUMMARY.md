---
phase: 02-identity-tenancy-and-authorization
plan: 04
subsystem: configuration
tags: [config, secrets, rate-limit, SEC-09, AUTH-04]
requires: ["02-02"]
provides:
  - init_env.sh --append-missing mode (SECRET_KEY generated as 64 hex, never regenerates)
  - .env.example catalogue for security, auth, mail, models, rate limits
  - service_conf.yaml sections security, auth, mail, models, ratelimit
  - typed Go (internal/server/config.go) and Python (common/settings.py) readers with SECRET_KEY validation
key-files:
  modified:
    - scripts/init_env.sh
    - docker/.env.example
    - conf/service_conf.yaml.template
    - scripts/render_conf.py
    - docker/docker-compose.yml
    - docker/docker-compose.dev.yml
    - internal/server/config.go
    - common/settings.py
    - test/helpers/app.py
  created:
    - test/unit_test/test_rate_limit_config.py
decisions:
  - "Renderer rejects a SECRET_KEY shorter than 32 characters in addition to the Go and Python readers, so a bad key fails at init before any server starts."
  - "Python Settings.security is required (no default); auth, mail, models, ratelimit have safe defaults. Test helper memory_settings supplies an obviously fake key."
metrics:
  tasks: 3
  completed: 2026-10-07
---

# Phase 2 Plan 04: Security, mail, models and rate-limit configuration Summary

Configuration plumbing from `docker/.env` through compose `x-app-env` and `render_conf.py` into `service_conf.yaml`, read and validated by both servers. No feature behaviour yet.

## Inherited work

A previous executor left uncommitted Task 1 edits (init_env.sh, .env.example, two test files). I reviewed the diff against the plan and kept it unchanged: append mode, `ENV_EXAMPLE`/`ENV_TARGET` test overrides, operator-supplied secrets (SUPERUSER_PASSWORD, SMTP_PASSWORD) left empty, and the catalogue. One cosmetic quirk remains: the append-mode message counts "generated secrets" for keys that already exist and are not appended. Committed as 2bac8aa. Tasks 2 and 3 were done by me.

## Commits

- 2bac8aa Task 1: init_env append-missing mode and env catalogue
- 768a227 Task 2: render the new sections, compose x-app-env, dev overlay
- 52e82c9 Task 3: typed Go and Python readers

## Variable names added to docker/.env.example

SECRET_KEY, REGISTER_ENABLED, SUPERUSER_EMAIL, SUPERUSER_PASSWORD, OTP_TTL_SECONDS, SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, DEFAULT_CHAT_MODEL, DEFAULT_EMBEDDING_MODEL, DEFAULT_RERANK_MODEL, DEFAULT_MODEL_FACTORY, DEFAULT_MODEL_BASE_URL, RATE_LIMIT_REGISTER_PER_IP, RATE_LIMIT_REGISTER_WINDOW_SECONDS, RATE_LIMIT_LOGIN_FAILURES_PER_EMAIL, RATE_LIMIT_LOGIN_PER_IP, RATE_LIMIT_LOGIN_WINDOW_SECONDS, RATE_LIMIT_OTP_EMAIL_INTERVAL_SECONDS, RATE_LIMIT_OTP_PER_EMAIL_PER_HOUR, RATE_LIMIT_OTP_PER_IP_PER_HOUR, RATE_LIMIT_OTP_WINDOW_SECONDS. A commented DEV_RATE_LIMIT_PER_IP_MAX line documents the dev-only override. Secrets (SECRET_KEY, SMTP_PASSWORD, SUPERUSER_PASSWORD) and SUPERUSER_EMAIL are empty.

## Git-ignored docker/.env

The earlier executor had not changed it (only variable names compared; no values read). At the start 28 catalogued names were missing, including pre-existing APP_UID, APP_GID, LOG_DIR. I ran `scripts/init_env.sh --append-missing` once: it appended the 28 missing names, so every name in `.env.example` is now present. SECRET_KEY exists once with 64 characters; existing lines (including SVR_WEB_HTTP_PORT=8088) were not touched. The file is git-ignored and not committed.

## Test-first evidence

Observed failing before the change:
- Task 2: `test_cli_renders_phase2_sections`, `test_cli_missing_secret_key_exits_1_naming_only_the_key`, `test_cli_short_secret_key_exits_1_without_echoing_value`, `test_production_compose_defaults_equal_r94`, `test_dev_overlay_raises_only_the_three_per_ip_keys` (5 failed). The other rate-limit tests passed immediately because they pin values that were already true or absent (the example defaults, and the absence of dev values in production compose); they are regression pins.
- Task 3 Python: collection failed with ImportError for RateLimitSettings. After implementing, two of my own test cases failed because the echo assertion matched words in the error message ("short", "secret"); the test was corrected to use unique fake values. No test was weakened.
- Task 3 Go: package failed to compile (undefined SecurityConfig etc.); the same echo-assertion artifact was fixed in the test.

Task 1 (inherited): the pre-change failure was not observed when written. I demonstrated meaningfulness afterwards in a scratch copy outside the repo: the HEAD `init_env.sh` exits 2 on `--append-missing`, and the two new catalogue tests fail with AssertionError against the HEAD `.env.example`. Only the new tests that exercise `--append-missing` and the catalogue were checked this way; the plain-mode assertions in `test_plain_mode_still_refuses_existing_env_and_leaves_operator_secret_empty` were not run against HEAD.

## Final checks (as observed)

- `make ci`: exit 0, 7/7 gates passed, ruff clean.
- `uv run python run_tests.py -m unit`: 502 passed, 1 skipped, 142 deselected.
- `GOTOOLCHAIN=local go test -count=1 ./cmd/... ./internal/...`: all packages ok.
- `GOTOOLCHAIN=local go vet ./...`: exit 0.
- `docker compose -p devrag-stack --env-file docker/.env -f docker/docker-compose.yml config -q`: exit 0. The dev overlay renders per-IP values 100000 for app only; production config shows 10, 30, 20.
- Go `-race` run of `./internal/server/` passed. Integration tests were not run (stack not started, per plan).

## Deviations from Plan

**1. [Rule 3 - Blocking] test/helpers/app.py** was modified because `Settings` now requires `security`. It supplies an obviously fake key. Not in the plan's file list.
**2. [Rule 2] render_conf.py length check** (above, under decisions) is an addition beyond the plan text, backing the "short or missing key exits non-zero" criterion.

## Not done / notes

- Existing `docker/.env` values were not validated beyond name presence.
- The `init` service in the dev overlay keeps production rate-limit values; only `app` is raised.

## Known Stubs

None.

## Self-Check: PASSED
Commits 2bac8aa, 768a227 and 52e82c9 exist; all listed files exist.
