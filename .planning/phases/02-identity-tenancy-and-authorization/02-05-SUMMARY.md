---
phase: 02-identity-tenancy-and-authorization
plan: 05
subsystem: infra
tags: [npm, react-hook-form, zod, i18next, itsdangerous, mailpit, docker-compose]
requires:
  - phase: 02-identity-tenancy-and-authorization
    provides: SMTP variables (02-03, 02-04)
provides:
  - D-20 npm set installed and locked
  - itsdangerous 2.2.0 declared directly
  - dev-only Mailpit service (profile mail) and Python and Go mail read-back helpers
affects: [02-identity-tenancy-and-authorization]
tech-stack:
  added: [react-hook-form, zod 3, "@hookform/resolvers", i18next, react-i18next, "@radix-ui/react-label", "@radix-ui/react-alert-dialog", axllent/mailpit]
  patterns: [dev-only compose service gated by profile, wait_until-based mail polling]
key-files:
  created: [test/helpers/mail.py, internal/testutil/mail.go]
  modified: [web/package.json, web/package-lock.json, pyproject.toml, uv.lock, docker/docker-compose.dev.yml, Makefile, test/integration/test_compose_infra.py]
key-decisions:
  - "Mailpit HTTP only is published (127.0.0.1:8025); SMTP 1025 stays inside the ragflow network"
  - "Python mail helper uses httpx (already a direct dependency) instead of urllib, which ruff S310 rejects"
requirements-completed: [AUTH-16, AUTH-17, AUTH-18]
duration: 25min
completed: 2026-10-07
---

# Phase 2 Plan 05: Approved dependencies and dev mail catcher Summary

Seven user-approved npm packages installed with exact pins, itsdangerous declared directly with no lock content change, and a pinned dev-only Mailpit with a proven SMTP-to-HTTP read-back.

## Installed versions (D-20)
react-hook-form 7.89.0, zod 3.25.76, @hookform/resolvers 3.10.0, i18next 23.16.8, react-i18next 14.1.3, @radix-ui/react-label 2.1.16, @radix-ui/react-alert-dialog 1.1.24. `npm ls --depth=0` shows only these seven as new top-level entries; 11 transitive packages were added (radix internals, html-parse-stringify, void-elements). No new package has a preinstall, install or postinstall script (checked in node_modules for all 18 new lock entries; `hasInstallScript` count in the lock diff is 0). No peer conflicts. `npm audit` reports 8 vulnerabilities; none fixed (out of scope, no `audit fix`).

## uv.lock diff
Two added lines: `itsdangerous` in the root package dependency list and in `requires-dist` (`==2.2.0`). No `[[package]]` block changed.

## Mail catcher
Image `axllent/mailpit:v1.31.4`, digest `sha256:b68349e3a014b90c5610bfb26b2ae36f3892d7b8cf25ee140c6c71c98d2fcf48`, size 16,842,001 bytes (about 16 MB). Defined in `docker/docker-compose.dev.yml` only, profile `mail`, mem_limit 64m, healthcheck `/mailpit readyz`, HTTP `127.0.0.1:8025` (port verified free). Added `--profile mail` to `make up` and `make infra-up` (development targets only). Round trip: smtplib message to the container IP on 1025, read back via `GET /api/v1/search` and `/api/v1/message/<id>` with `wait_until`, code extracted. Mailpit stopped afterwards (`stop`, not `down`).

## Task Commits
1. Task 1 npm set: 3bfe193
2. Task 2 itsdangerous: d5967de
3. Task 3 Mailpit, helpers, tests: f52b899

## Deviations from Plan
- [Rule 1 - Bug] The first helper version used `urllib`, which failed `make ci` (ruff S310); switched to httpx. Fixed before commit.
- The plan lists `internal/testutil/mail.go` although the orchestrator said no Go changes; it was created as the plan specifies. It was verified with `go vet` only (no Go test consumes it yet).
- The live round-trip test sits in the same integration file as other live tests, so it fails unless the mail profile is up (consistent with the file's convention; `make infra-up` now starts it).

## Known Stubs
None.

## Self-Check: PASSED
