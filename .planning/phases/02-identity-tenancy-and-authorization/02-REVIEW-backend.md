---
phase: 02
scope: backend
reviewed: 2026-10-08
depth: deep
files_reviewed: 62
files_reviewed_list:
  - internal/router/middleware.go
  - internal/router/router.go
  - internal/handler/auth.go
  - internal/handler/account.go
  - internal/handler/user.go
  - internal/handler/token.go
  - internal/handler/tenant.go
  - internal/handler/password_reset.go
  - internal/common/token.go
  - internal/common/password.go
  - internal/common/clientip.go
  - internal/common/logger.go
  - internal/common/route_policy_gen.go
  - internal/common/permissions_gen.go
  - internal/service/auth.go
  - internal/service/account.go
  - internal/service/ratelimit.go
  - internal/service/otp.go
  - internal/service/password_reset.go
  - internal/service/mail.go
  - internal/service/token.go
  - internal/service/user.go
  - internal/service/avatar.go
  - internal/service/tenant.go
  - internal/service/tenant_members.go
  - internal/service/tenant_roles.go
  - internal/service/system.go
  - internal/dao/user.go
  - internal/dao/user_tenant.go
  - internal/dao/api_token.go
  - internal/dao/redis.go
  - internal/dao/redis_otp.go
  - internal/dao/db.go
  - internal/dao/tenant.go
  - internal/dao/verify.go
  - internal/server/config.go
  - cmd/ragflow_server.go
  - cmd/mail.go
  - cmd/migrate.go
  - api/apps/__init__.py
  - api/apps/auth.py
  - api/apps/errors.py
  - api/apps/middleware.py
  - api/apps/route_policy_gen.py
  - api/apps/permissions_gen.py
  - api/db/services/auth_service.py
  - api/db/services/superuser_service.py
  - api/ragflow_server.py
  - api/db/database.py
  - common/security/tokens.py
  - common/security/passwords.py
  - common/security/proxy.py
  - common/settings.py
  - common/log_utils.py
  - common/bootstrap/ensure_superuser.py
  - common/health/probes.py
  - conf/routes.yaml
  - conf/permissions.yaml
  - conf/service_conf.yaml.template
  - docker/docker-compose.yml
  - docker/docker-compose.dev.yml
  - docker/nginx/nginx.conf
  - docker/nginx/proxy.conf
  - docker/nginx/ragflow.conf
  - docker/nginx/ragflow.https.conf
  - docker/.env.example
  - scripts/gen_routes.py
  - scripts/render_conf.py
  - scripts/init_env.sh
  - scripts/preflight.sh
  - scripts/clean_room.sh
  - scripts/ci/check_secrets.py
  - scripts/export_openapi.py
  - test/testcases/test_route_enumeration.py
  - test/testcases/test_dependency_outage.py
findings:
  critical: 1
  warning: 7
  info: 9
  total: 17
status: issues_found
---

# Phase 2: Backend Code Review Report

**Reviewed:** 2026-10-08
**Depth:** deep (gate, token, password, reset, tenancy, nginx, config, scripts read end to end; the large Go e2e and integration test files and the `test/` helpers were only pattern-scanned)
**Scope:** `git diff 5c40d8e HEAD` limited to `internal/`, `cmd/`, `api/`, `common/`, `docker/`, `conf/`, `scripts/` and backend tests. `web/` and `.planning/` were not reviewed. `docker/.env` and `conf/service_conf.yaml` were not opened.
**Offline verification run:** `GOTOOLCHAIN=local go vet` and `go test ./internal/... ./cmd/...` all pass; `uv run python run_tests.py -m unit` gives 792 passed, 1 skipped; `scripts/gen_routes.py --check` exits 0 (no generated-file drift). Nothing needing MySQL, Redis or Docker was executed. Findings that depend on database or Nginx behaviour say so.

## Summary

The default-deny gate, the itsdangerous-compatible token, PBKDF2 verification, the Lua-based OTP store, the tenant row-lock transactions and the 404-versus-403 rule hold up well against what the spec asked for. Go and Python resolve the same policy from one generated table, fail closed with 503 on infrastructure errors, and trust forwarded headers only from a loopback peer.

One real authentication-hardening defect stands out. The per-email login throttle is keyed on the typed string, but the database matches emails under an accent-insensitive collation. A single account is therefore reachable through unlimited distinct "emails", each with a fresh failure counter (CR-01). The remaining findings are a TOCTOU in the failure counter, a lockout denial of service, an API token that can reach the Nginx error log, an unauthenticated 1 GB body allowance, login CSRF, and several robustness and test-quality items.

Not re-reported, per instructions: B-17 (per-IP limits behind the Docker proxy), B-21 (plaintext API tokens), B-23 (405 raw path in logs).

## Critical Issues

### CR-01: Login failure throttle and OTP limits are bypassed by collation-equivalent email spellings

**File:** `internal/service/account.go:102-123` (validEmail, emailKey), `internal/service/account.go:208-221` (Login), `internal/dao/user.go:55` (FindUserByEmail), `internal/service/password_reset.go:67-85`
**Issue:** `normaliseEmail` only trims and lowercases, and the limiter key is `sha256(typed email)`. `validEmail` uses `net/mail.ParseAddress`, which accepts non-ASCII local parts. I confirmed this with a scratch Go program: `álice@example.com`, `álice@example.com` and `alice@exámple.com` all parse and round-trip. `FindUserByEmail` then does `WHERE email = ?` on a column whose collation is `utf8mb4_unicode_ci` (the dev compose sets this explicitly) or the MySQL 8 default `utf8mb4_0900_ai_ci`. Both treat `a`, `á`, `à`, and `a` plus a combining mark as equal. The database lookup therefore finds the same account for every variant, while the throttle counters (`login:email:<hash>`, `otp:email:*`) are separate for every variant.
**Scenario:** The attacker knows `alice@corp.com`. They try five passwords for `alice@corp.com`, five for `álice@corp.com`, five for `âlice@corp.com`, and so on. Each variant is a fresh `login:email:` counter, so the "5 failures per 15 minutes per email" control (D-04) never fires. The only remaining bound is the per-IP counter, which a distributed attacker does not share. The password rule is length-only (D-02), so weak passwords fall. The same trick bypasses the OTP per-email interval and hourly caps (mail-flooding the victim and multiplying guesses at the 6-digit code). The final `ResetPassword` equality check (`normaliseEmail(user.Email) != email`) happens to stop the reset itself, but only by accident.
This was verified by reading the code path and by running the Go address parser. The MySQL collation behaviour is standard but was not executed (no database in this review).
**Fix:** Make the throttle key independent of spelling, and stop accepting spellings the mail layer cannot deliver anyway (`cleanAddress` already rejects any byte above 0x7e).
```go
// validEmail: reject non-ASCII so the DB collation cannot alias two distinct strings.
for i := 0; i < len(email); i++ {
    if email[i] > 0x7e || email[i] <= ' ' { return false }
}
```
Additionally, after `FindUserByEmail`, key the failure counter on the resolved `user.ID` (and keep the typed-email key for unknown accounts), and in `RequestReset` key the OTP limits and the OTP record on `user.Email` (the stored canonical value) when the account exists. Add a test that registers `alice@x.test` and asserts that `álice@x.test` shares the lockout.

## Warnings

### WR-01: Login failure counter is check-then-act, so parallel guesses exceed the cap

**File:** `internal/service/account.go:211-221`, `internal/service/user.go:171-184` (ChangePassword)
**Issue:** `Limiter.Check` reads the counter, the PBKDF2 verification runs, and only afterwards `Limiter.Fail` increments. Every request that arrives before the first failure lands sees a count below the cap.
**Scenario:** An attacker (or botnet) fires N simultaneous logins for one email. All N pass `Check` at count 0 and queue on `hashSlots`; all N get verified. The "5 per window" cap becomes "N per burst". Contrast the OTP path, which correctly does an atomic increment-then-compare in Lua.
**Fix:** Reserve the attempt before verifying: `Hit` (atomic INCR) first, refuse when over the cap, and `Delete` the key on success. Apply the same change to `ChangePassword` (key `pwchange:user:`).

### WR-02: Anyone can lock a victim out of login (and out of password change) indefinitely

**File:** `internal/service/account.go:211-221`
**Issue:** The failure lockout is keyed on the email only. Five wrong passwords against a known email make `Check` return 429 for the whole 15-minute window, even for the correct password, and the attacker can renew it every window with five requests.
**Scenario:** A competitor locks the CEO's account out of the product permanently with five requests per 15 minutes from one IP.
**Fix:** Key the failure counter on (email, client IP) for the blocking decision and keep a much higher email-only threshold as an alert/CAPTCHA trigger; or apply progressive delay instead of a hard refusal. Record the choice as a decision, since D-04 only says "rate-limited".

### WR-03: DELETE /api/v1/system/tokens/<token> puts a live API token into the Nginx error log

**File:** `docker/nginx/nginx.conf:2` (`error_log /dev/stderr warn`), `conf/routes.yaml:103`
**Issue:** The access log is masked with the `map $uri` rule, but Nginx error-log lines for upstream failures (`connect() failed`, `upstream prematurely closed connection`, `upstream timed out`) include the full `request: "DELETE /api/v1/system/tokens/ragflow-... HTTP/1.1"` line. That path is not masked. This is standard Nginx behaviour; it was not executed here.
**Scenario:** The Go process restarts while a user deletes a token. The raw credential lands in container stderr and in whatever log shipper collects it.
**Fix:** Preferably carry the token in the request body or an `X-Token` header (record the deviation from the docs path form). Otherwise record this as an accepted risk in BLOCKERS and require the log sink to redact `ragflow-[A-Za-z0-9_-]{20,}`.

### WR-04: Unauthenticated callers can push a 1 GB body through Nginx to the auth endpoints

**File:** `docker/nginx/nginx.conf:30` (`client_max_body_size 1024m`), `docker/nginx/proxy.conf`
**Issue:** The limit is global. `POST /api/v1/auth/login`, `/api/v1/users` and the reset routes accept a body up to 1 GB at the proxy because `proxy_request_buffering` is on by default: Nginx spools the whole body to disk before forwarding, and Go then rejects it after 1 KB. The Python gate runs before the body is read, but Nginx has already buffered it. `proxy_read_timeout 3600s` is also applied to the public auth locations.
**Scenario:** A few unauthenticated clients upload 1 GB each and fill the Nginx temp directory or saturate disk and bandwidth.
**Fix:** Set `client_max_body_size 8k` and short `proxy_read_timeout` / `client_body_timeout` in the generated locations for Go-owned auth, `/api/v1/tenants/`, `/v1/user/` and `/v1/tenant/`. Keep the large limit only on the future upload locations. This needs a field in `routes.yaml` so the generator stays the single source.

### WR-05: Login, register and reset endpoints accept cross-site form posts (login CSRF)

**File:** `internal/handler/account.go:76-87` (bindLimit), `internal/handler/auth.go:79-82` (public routes skip the Origin check)
**Issue:** `bindLimit` decodes JSON regardless of `Content-Type`, and the CSRF Origin rule applies only to cookie-authenticated unsafe requests. A third-party page can submit a `text/plain` form whose body is valid JSON to `/api/v1/auth/login`. The response `Set-Cookie: ragflow_auth` (SameSite=Lax, accepted for a top-level POST navigation) signs the victim's browser in as the attacker.
**Scenario:** A victim with no stored Bearer token visits a hostile page. Later uploads and chats made through the SPA's cookie fallback land in the attacker's workspace.
**Fix:** Require `Content-Type: application/json` on every JSON endpoint (a cross-origin request with that type needs a preflight), and apply `sameOrigin` to the login and register POSTs when an `Origin` header is present and not allowed.

### WR-06: Invalid page values reach SQL as overflowed offsets and become 503

**File:** `internal/service/tenant_members.go:113`, `internal/service/token.go:155`, `internal/handler/token.go:78-87` (intQuery)
**Issue:** `page` has a lower bound only. `(page-1)*pageSize` overflows int64 for large pages (for example `page=9223372036854775807`, `page_size=100` gives an offset of -200). In the member list the negative OFFSET is a SQL error, which `memberStoreFailure` turns into HTTP 503 plus an error log. In the token list GORM silently ignores a negative offset and returns page 1.
**Fix:** Cap `page` (for example `<= 100000`) in both services and return the 400 `ValidationError`.

### WR-07: Python auth lookups can starve the default thread pool during a database stall

**File:** `api/apps/auth.py:32,78`, `common/settings.py:29,300`
**Issue:** The gate wraps the blocking resolver in `asyncio.wait_for(asyncio.to_thread(...), 5.0)`. On timeout the awaiting coroutine is cancelled, but the worker thread keeps blocking on MySQL until the driver's `read_timeout`, which defaults to 30 s. During a database stall every authenticated request leaves a thread behind for up to 30 s, and the default executor has a small cap (about CPU count + 4). The same executor serves the health probes and other `to_thread` users, which can then stop answering. This is inferred from the code and was not load-tested.
**Fix:** Use a dedicated bounded `ThreadPoolExecutor` for auth lookups, and set the auth connection read timeout at or below `LOOKUP_TIMEOUT_SECONDS` (or pass a per-connection timeout).

## Info

### IN-01: Weak assertion in the dependency-outage test cannot fail on the intended condition

**File:** `test/testcases/test_dependency_outage.py:79`
**Issue:** `assert go.json()["code"] == 503 or go.json()["code"] != 0` passes for any non-zero code, so the `== 503` branch is dead and the envelope code is effectively unchecked.
**Fix:** `assert go.json()["code"] == 503`.

### IN-02: ResetPassword compares the typed email with the stored one byte for byte

**File:** `internal/service/password_reset.go:128`
**Issue:** `RequestReset` finds the account through the collation-insensitive lookup, but `ResetPassword` rejects the ticket unless `normaliseEmail(user.Email) == typed`. A user who types a differently accented or composed form of their own address gets a code and then a generic failure.
**Fix:** Fixed by CR-01 (ASCII-only emails). Until then, compare against the email the OTP record was issued for rather than the stored value.

### IN-03: Account existence is still observable without authentication

**File:** `internal/service/account.go:150` (409 on `POST /api/v1/users`), `internal/service/tenant_members.go` (404 `ErrUserNotFound` on invite)
**Issue:** D-04 and D-07 build anti-enumeration into login and reset, but registration answers 409 for a taken email, and any registrant is an owner who can probe addresses through invites (30 per 15 minutes per account). This follows the docs, but it makes the effort in D-04 and D-07 partial.
**Fix:** Record the residual exposure in DECISIONS; or return a uniform response and mail the existing owner.

### IN-04: The HTTPS server block drops the port when redirecting

**File:** `docker/nginx/ragflow.https.conf:5`
**Issue:** `return 301 https://$host$request_uri;` uses `$host` (no port) while compose publishes HTTPS on 8443. The redirect lands on 443, which is not published. There is also no HSTS header and no security headers on API responses (only on `/` and `/index.html`).
**Fix:** Use `$http_host` with the port rewritten, or a configured public URL; add `Strict-Transport-Security` and `X-Content-Type-Options` at server level.

### IN-05: Go server has no read/write/idle timeouts

**File:** `cmd/ragflow_server.go:84`
**Issue:** Only `ReadHeaderTimeout` is set. Nginx buffers request bodies today, which hides this, but a direct connection to :9384 from another container on the compose network can hold goroutines with a trickled body.
**Fix:** Add `ReadTimeout`, `WriteTimeout` (long enough for SSE routes later, or per-route) and `IdleTimeout`.

### IN-06: SMTP defaults point at a dev sidecar and allow plaintext relays

**File:** `docker/docker-compose.yml:32-34`, `conf/service_conf.yaml.template`, `internal/service/mail.go:140-166`
**Issue:** Production compose defaults `SMTP_HOST=mailpit` and `SMTP_SECURITY=none`. If an operator forgets to set SMTP, reset requests answer 200 and the mail silently fails (only a log line). A remote relay with `none` sends reset codes in cleartext, and `NewSMTPMailer` allows it as long as no credentials are set.
**Fix:** Refuse (or loudly warn at startup) when `security=none` and the host is not loopback or a private address; make `SMTP_HOST` required unless the `mail` profile is active.

### IN-07: Go and Python parse the same boolean setting differently

**File:** `internal/server/config.go:184` (`strconv.ParseBool`), `common/settings.py:150-158` (`_bool`)
**Issue:** Go accepts `t`, `T`, `TRUE`, `f`; Python accepts only `1/true/0/false` and aborts startup on the rest.
**Fix:** Use one accepted set in both (`1/true/0/false`, case-insensitive) and add it to the shared fixture.

### IN-08: Handlers map some infrastructure errors to 500 instead of 503

**File:** `internal/handler/user.go:41-47` (Info), `:57-60` (Logout), `internal/service/account.go:287` (`complete` returns a raw `dao.ErrNotFound`)
**Issue:** The gate returns 503 for dependency failures (R-114), but these handlers return 500 `internal error` for the same class, and a user with no own workspace gets a 500 at login instead of `ErrNoTenant`.
**Fix:** Route them through `fail()` and wrap store errors with `ErrUnavailable`; map `dao.ErrNotFound` in `complete` to `ErrNoTenant`.

### IN-09: Smaller items

- `internal/common/password.go:44-50`: `derive` blocks on `hashSlots` without a context, so a cancelled request still runs 600k PBKDF2 iterations later. Select on `ctx.Done()`.
- `scripts/clean_room.sh:56-58`: `MYSQL_ROOT_PASSWORD` is exported into the environment of every step, including `docker compose up --build`, the web tests and `npm`. Export it only for the Go tiers that need it.
- `cmd/ragflow_server.go:50-54`: three separate `Limiter` instances with the same prefix are built; share one.
- `internal/handler/account.go:19` (`maxAccountBody = 1 << 10`) rejects a legitimate register body with multi-byte nickname and password near their maximum (about 1.1 KB); raise to 2 KB.
- OTP guessing: five attempts per code, a verify endpoint with no per-IP limit, so anyone can burn a victim's current code by sending five wrong guesses (recovery denial of service). This follows D-06; consider a per-IP verify limiter.

---

_Reviewed: 2026-10-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
