---
phase: 02-identity-tenancy-and-authorization
plan: 17
subsystem: auth
tags: [go, password-reset, otp, smtp, mailpit, rate-limit, valkey, enumeration]
requires: [02-05, 02-10, 02-15]
provides:
  - POST /api/v1/auth/password/forgot/otp (emails a 6-digit code; identical response for any well-formed email)
  - POST /api/v1/auth/password/forgot/otp/verify (consumes the code, returns a single-use reset ticket)
  - POST /api/v1/auth/password/reset (ticket or the documented `otp` field, 8 to 128 characters, signs every device out)
  - service.OTP, service.SMTPMailer, service.MailPool, service.PasswordReset
  - dao.Redis OTP primitives (Lua attempt cap, compare-and-delete) and dao.DB.SetPassword
affects: [02-18 forgot-password page, 02-2x frontend]
tech-stack:
  added: []
  patterns:
    - "attempt is counted in Lua before the comparison; a correct code is consumed by compare-and-delete so one caller wins"
    - "unknown and inactive emails get a decoy record so Redis state, limits and failure behaviour match real accounts"
    - "mail is queued to a bounded worker pool; a full queue drops and logs, the response never changes"
key-files:
  created:
    - internal/dao/redis_otp.go
    - internal/service/otp.go
    - internal/service/mail.go
    - internal/service/password_reset.go
    - internal/handler/password_reset.go
    - cmd/mail.go
    - internal/service/mail_test.go
    - internal/service/otp_integration_test.go
    - internal/service/password_reset_integration_test.go
    - internal/router/password_reset_integration_test.go
    - internal/e2e/password_reset_e2e_test.go
    - test/testcases/test_password_reset.py
  modified:
    - internal/dao/user.go
    - internal/router/router.go
    - internal/router/router_test.go
    - internal/common/logger.go
    - internal/common/logger_test.go
    - common/log_utils.py
    - internal/testutil/mail.go
    - test/helpers/mail.py
    - test/unit_test/test_log_redaction.py
    - test/unit_test/test_route_policy.py
    - conf/routes.yaml
    - cmd/ragflow_server.go
    - .planning/DECISIONS.md
key-decisions:
  - "R-119: ticket design, documented `otp` field accepted, decoy records, limits order, lockout cleared on reset, mail transport rules, redacted field names"
requirements-completed: [AUTH-16, AUTH-17, AUTH-18]
duration: one session
completed: 2026-10-08
---

# Phase 2 Plan 17: Go password reset (OTP, SMTP, rate limits) Summary

A user who forgot their password can request an emailed 6-digit code, verify it, and set a new password; a successful reset signs every device out on both engines, and nothing in the responses, timing shape or logs reveals whether an account exists.

## Commits

| Commit | What |
|---|---|
| 192246a | test: failing mail, OTP, reset, router, ingress and Python e2e tests with compile-only stubs; Valkey OTP primitives and `SetPassword` written with the tests |
| 9b48718 | feat: OTP, SMTP mailer and pool, reset service, handlers, routes, registry rows, redactor keys, R-119 |

## What was built

- **Code**: six digits from `crypto/rand` (`rand.Int` over 10^6, zero padded). Stored as `salt:HMAC-SHA256` keyed with a key derived from `SECRET_KEY` (bound to salt and email digest) in one Valkey hash per email, with the configured TTL. The key holds a digest of the email, never the address. A new request replaces the hash (and resets the attempts) in one Lua script.
- **Attempts and single use**: Lua increments the attempt counter before anything is compared; attempts beyond 5 destroy the record; the fifth wrong attempt destroys it; a correct code is consumed by compare-and-delete so exactly one of several parallel callers wins. Comparison is `hmac.Equal`.
- **Ticket**: verify returns a 256-bit random ticket (base64url), stored only as its SHA-256 digest, bound to user and email, 5 minutes, single use (`GETDEL`), one live ticket per user. A mismatched use burns it. Reset also accepts the `otp` field named by `docs/04-api/endpoint-catalog.md` (code verified and consumed in the same call).
- **Enumeration (D-07)**: an unknown or inactive email goes through the same limits and the same Redis work (decoy record, nothing sent); verify and reset failures are one generic 400 even after the attempt cap; a decoy grant resets with the same success and changes nothing; the mail goes to a bounded worker pool and is never sent inline.
- **Limits**: per IP, then per email interval (default 1 per 60 s), then per email per hour (default 5); the hourly counter counts only requests that passed the interval. 429 with Retry-After; Valkey or MySQL failure is 503 and never a send. The client IP is `common.ClientIP`.
- **Reset**: 8 to 128 characters checked before the ticket is consumed; hash and `INVALID_<hex>` token written in one transaction (`SetPassword`); outstanding code and ticket of that user removed; the per-email login lockout is cleared; no session, no cookie.
- **Mail**: stdlib `net/smtp`, 5 s dial and 10 s total deadlines, certificate verification for starttls and tls, no downgrade when STARTTLS is not offered, credentials refused with security none (start-up fails with a clear message, no secret in it), recipient validated as one bare mailbox (CR, LF, display names, quotes, comments rejected), fixed ASCII subject, plain-text body carrying only the code and the lifetime. Send failures are logged with credentials and addresses scrubbed. An empty `SMTP_HOST` starts the server with a warning and delivers nothing.
- **Logs**: `otp` and `ticket` are redacted field names in the Go and Python redactors. The request log never carries bodies, and a real log-capture test shows no code, ticket, password or email.

## Test-first record (failing before implementation)

Run on commit 192246a (stubs only), live MySQL and Valkey from `make infra-up`:

- `go test ./internal/service` (unit): 16 mail tests failed (message building, injection, config validation, delivery, STARTTLS and implicit TLS verification, downgrade, dial and total timeouts, default timeouts, reset mail text, pool bounds, pool logging, pool survival, AUTH PLAIN).
- `go test -tags=integration ./internal/service ./internal/router`: 60+ failures, among them every OTP test (hash storage, TTL, single use, five attempts, replacement, parallel guesses, parallel winners, expiry, tickets), every reset service test (full flow, documented `otp` shape, cross-account, length rule, outstanding removal, lockout, parallel reset, decoy, disabled account) and every router test (identical bodies, latency, interval, hourly, per-IP, spoofed headers, Redis outage, full HTTP flow, verify failures, caps, log capture).
- `internal/common` `TestRedactorCoversOTPAndTicketFields` and the Python `test_otp_and_reset_ticket_fields_masked` failed.
- Ingress and Python e2e tests were written against the same contract; not run in RED (they need the rebuilt app image).

After implementation all of these pass.

## Live verification (observed)

Host MemAvailable was 7642 MiB at the start and 5061 MiB at the app build. Infra started with `make infra-up`; the app image was rebuilt with `docker compose -p devrag-stack ... --profile cpu --profile elasticsearch --profile mail up -d --build`; `scripts/wait_stack.sh` reported every service healthy. Host-run Go tests used `SERVICE_CONF` (git-ignored host conf), `E2E_BASE_URL=http://127.0.0.1:8088` and `MYSQL_ROOT_PASSWORD` read from `docker/.env` (never printed).

- Go e2e through Nginx with Mailpit: 4 new tests pass (full reset reading the real message; byte-identical body for an unknown email with the bounded negative mail wait; five wrong codes destroy the code; 429 with Retry-After on the second request).
- `uv run python run_tests.py -m e2e -t password_reset`: 5 passed (collect-only selected the same 5). In the full flow the old token is 401 on Go `/v1/user/info` and Python `/api/v1/system/status`, the old password login is 401, and the new token works on both.
- `uv run python run_tests.py -m "integration or e2e"`: 246 passed, 741 deselected, 172.90 s.
- `GOTOOLCHAIN=local go test -count=1 -tags=integration,e2e ./...`: all packages ok.
- `cd web && LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live`: 4 files, 17 tests passed.
- App container log: no `mail send failed`, no test email address.
- Integration run with `-race` (service 138 s, router 132 s) also passed before the live stack was started.
- Stack stopped with `docker compose -p devrag-stack ... --profile cpu --profile elasticsearch --profile mail stop` (no `down`, no `-v`); `docker ps --filter name=devrag-stack -q | wc -l` is 0. The foreign `compose` project was not touched.

## Final checks (observed)

- `make ci`: 7/7 gates passed, ruff security selection passed.
- `uv run python run_tests.py -m unit`: 740 passed, 1 skipped, 246 deselected.
- `GOTOOLCHAIN=local go test -count=1 -race ./cmd/... ./internal/...`: all ok.
- `GOTOOLCHAIN=local go vet ./...` and `go vet -tags=integration,e2e ./...`: clean.
- `scripts/gen_routes.py --check`: exit 0 (flipping `implemented` changes no generated file).

## Deviations from Plan

1. [Design, R-119] Keys use a digest of the normalised email (`otp:{digest}`), not the address, and attempts live in the same hash as the code instead of a separate `otp_attempts` key, so replacement is one atomic script. The verify step returns a hashed, single-use `reset_ticket` (hard constraint) instead of a bare `otp_verified:{email}` marker, because an email-keyed marker could be used by anyone who knows the email.
2. [Docs] `docs/04-api/endpoint-catalog.md` gives the reset body as `email`, `otp`, `new_password`; the endpoint accepts that shape in addition to `reset_ticket`.
3. [Rule 2] Decoy records for unknown and inactive emails, so the attempt-cap behaviour cannot reveal existence. Not in the plan.
4. [Rule 2] `otp` and `ticket` added to the log redactors of both engines (the hard constraints require the redactor to cover the fields).
5. The reset also clears the per-email login lockout (`login:email:<digest>`), so a user locked out by failures is not locked out of the password they just set.
6. The OTP limit policies live in `password_reset.go` (reading the existing `RateLimit` config) instead of being added to `ratelimit.go`; the `Limiter` API was enough.
7. `uv run python run_tests.py -m e2e -t password_reset --collect-only -q` is rejected by the wrapper; pass-through arguments go after `--`.
8. Extra test files beyond the plan list: `internal/service/password_reset_integration_test.go`, `internal/router/password_reset_integration_test.go`.
9. Commit trailer is `Co-Authored-By: Claude Sonnet 5.5` (the harness attribution rule for this session).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-75 to T-02-82 are each covered by a named test: brute force (attempt cap, parallel guesses, limits), enumeration (byte-identical bodies, decoys, latency), code readable from Valkey (stored-hash and TTL tests), header injection (message and mailer tests), reset without verification (grant required, cross-account), session surviving reset (token rewrite, 401 on both engines), mail flooding and hanging SMTP (pool, timeouts, fail closed), credentials in logs or plaintext (config refusal, TLS tests, log capture).

## Self-Check: PASSED

Commits 192246a and 9b48718 exist; `internal/service/otp.go`, `internal/service/mail.go`, `internal/service/password_reset.go`, `internal/handler/password_reset.go`, `cmd/mail.go`, `internal/dao/redis_otp.go` and `test/testcases/test_password_reset.py` exist.
