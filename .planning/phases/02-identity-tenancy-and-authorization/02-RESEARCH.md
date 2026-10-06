# Phase 2: Identity, Tenancy and Authorization - Research

**Researched:** 2026-10-07
**Domain:** Cross-language (Go issues, Python verifies) token auth, password hashing, multi-tenant authorization, OTP password reset over SMTP, SPA auth/i18n/settings screens
**Confidence:** HIGH for the token and password contracts (reproduced by execution in both languages); MEDIUM for route/endpoint ownership (docs conflict, see Open Questions); MEDIUM for frontend package choices (versions checked on the registry, no slopcheck run)

Provenance tags: `[VERIFIED: ...]` = reproduced by running code or reading installed source in this session; `[CITED: file]` = stated in `docs/` or the reference repo; `[ASSUMED]` = from training knowledge, not verified here.
Research was read-only: nothing was installed, pulled, started or committed. Scratch scripts lived under the session scratchpad. No resume was needed: no earlier `02-RESEARCH.md` existed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Every decision below marked **(user)** was chosen by the user in the discuss session on 2026-10-07. The planner must update the matching rows in `.planning/DECISIONS.md` to `user-confirmed` and add their numbers to the pinned set in `scripts/ci/check_decisions.py` with a dated comment (as was done for R-49 and R-87).

#### Sign-up and login
- **D-01 (user):** Self-registration is open by default and controlled by a config switch (RAGFlow's `REGISTER_ENABLED`); when off, `POST /api/v1/users` refuses with a clear envelope error and the SPA hides the sign-up form.
- **D-02 (user):** Password rule is minimum 8 characters, length only, no composition rule. The same rule applies at registration, password change and password reset, enforced on the server and mirrored in the SPA.
- **D-03 (user):** A first superuser is created by a one-shot init from an email and password set in `docker/.env`. If either is unset, nothing is created. No default credential ships in the repository. This delivers the superuser part of API-13 that Phase 1 left open (BLOCKERS B-08).
- **D-04 (user):** Failed login returns one generic message ("Email or password is incorrect") for both unknown email and wrong password. Repeated failures are rate-limited.

#### Password reset
- **D-05 (user):** The reset code is sent by email through configurable SMTP settings. The dev compose stack includes a local mail-catcher so the whole flow is verified for real; production points at the user's SMTP server. The mail-catcher is a new dev-only service: check it against `docs/` and record it as a decision.
- **D-06 (user):** The reset code is 6 digits, expires after 10 minutes, is invalid after 5 wrong attempts, is single use, and a new request replaces the previous code. Stored in Redis.
- **D-07 (user):** A reset request for an email with no account gets the same response as a real one and sends nothing.
- **D-08 (user):** A successful password reset or password change invalidates the stored access token, signing the user out on every device.

#### Sessions and tokens
- **D-09 (user):** The login token follows RAGFlow's format as documented in `docs/apikey llm.md`: a UUID access token stored on the user row, wrapped in an itsdangerous-`URLSafeTimedSerializer`-compatible payload (zlib, timestamp, HMAC-SHA1) that Go creates and Python verifies with its standard library. Not a standard JWT. Go and Python share test vectors. Resolves R-33.
- **D-10 (user):** One stored token per user, shared across devices: a second login reuses the current valid token; logout on any device rewrites it to `INVALID_<hex>` and signs out all devices.
- **D-11 (user):** The signed wrapper is rejected after 30 days, forcing a fresh login. The docs claim an expiry check without a value, so 30 days is a new recorded decision. Supports SEC-09.
- **D-12 (user):** API tokens are generated, stored and listed as documented (`ragflow-` plus 32 random bytes, URL-safe base64; beta token is a 32-character hyphen-stripped UUID). Moving to hash-plus-prefix, shown once, is deferred to the billing phase (BILL-01) to avoid doing it twice.

#### Team invites and roles
- **D-13 (user):** Only the owner may invite members, following `docs/16-auth/permissions.md` over `authorization.md`. Resolves R-36.
- **D-14 (user):** Invitations target existing accounts only, by email, as the documented API implies. No sign-up-by-invite email.
- **D-15 (user):** An invited person can accept or decline; the owner can withdraw a pending invitation. Decline and withdraw are small additions to the documented accept-only flow, to be recorded as decisions.
- **D-16 (user):** The owner can remove a member and a member can leave a tenant. The owner cannot leave or be removed.

#### Carried from Phase 1 (locked)
- **D-17:** Go owns register, login, password and user/tenant routes; Python verifies the same token; neither server proxies to the other (Phase 1 D-01, D-05, D-06).
- **D-18:** Envelope `{code, message, data}`; Peewee owns the schema; Go verifies only; routes come from `conf/routes.yaml`; no mocks or fixed sleeps; the web port on this host is 8088 (R-87).
- **D-19:** `/api/v1/system/status` and `/api/v1/system/version` carry `public_until_phase: 2` and must become authenticated in this phase; the marker tests then need the routes removed from the public set (R-55, R-84).

### Claude's Discretion
- Password hashing scheme and parameters, provided hashes are salted, verifiable in both Go and Python with shared test vectors, and never unsalted SHA-256 (R-34). Research must settle the exact scheme from `docs/16-auth/authentication.md` and the reference.
- Client token storage (R-35): the recorded default is a Bearer header from `localStorage`, with the documented cookie and Redis session only as the fallback path and CSRF protection if a cookie is ever used for auth.
- Rate-limit numbers for login and OTP requests, avatar handling in the profile, the mail-catcher image, i18n library wiring and which locales ship first (UI-42 lists zh, en, es, fr, ja), theme persistence, and the home dashboard content for a tenant with no data yet.

### Deferred Ideas (OUT OF SCOPE)
- Hash-plus-prefix API keys shown once - billing phase (BILL-01, Phase 8)
- Inviting people who have no account yet by email
- Independent per-device sessions with separate logout
- OAuth / SSO login and the Go `--admin` service - Phase 8
- Password composition rules beyond length
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01, AUTH-03, AUTH-04 | Register; atomic user+tenant+owner link(+tenant_llm); default models | Go `Register` service in one GORM transaction; tenant id == user id; default model ids come from config and may be empty (section 11, Open Question 3) |
| AUTH-02, AUTH-05, AUTH-06 | Salted hash; login; tenant/role/default models | `pbkdf2:sha256:600000` werkzeug-format, Go stdlib `crypto/pbkdf2` + Python werkzeug, vectors verified (section 2) |
| AUTH-07, AUTH-08, AUTH-12 | Bearer auth on both servers; token validation; resolution order | Section 1 (token) and section 3 (resolution algorithm, one contract for both stacks) |
| AUTH-09, AUTH-10, AUTH-11 | Logout rewrite; cookie fallback; `ragflow_auth` cookie | Section 3.4: single HttpOnly `ragflow_auth` cookie carrying the same signed token (deviation from literal Redis `_user_id` session, Open Question 1) |
| AUTH-13, AUTH-14, AUTH-15 | user info, setting, password change | Go-owned `/v1/user/*` (section 4) |
| AUTH-16, AUTH-17, AUTH-18 | OTP forgot/verify/reset | Go-owned `/api/v1/auth/password/*`; Redis keys; SMTP stdlib; Mailpit (sections 6, 7) |
| AUTH-19, AUTH-20, AUTH-21, AUTH-22 | API token create/list/delete; API-token auth | Go-owned `/api/v1/system/tokens*` (section 4); `api` auth type resolves to owner tenant |
| AUTH-23 | Beta token auth | `beta` auth type in both gates; no beta route exists until Phase 8, so the accept path is proven with a test-registered route (section 10) |
| TEN-01, TEN-02 | tenant_id on every owned entity; cross-tenant denial | Cross-tenant matrix generated from the endpoint registry (section 3.6) |
| TEN-04, TEN-05 | Three roles; permission matrix, 403 | Shared permission table, owner-only team admin (D-13) (section 3.5) |
| TEN-06, TEN-07 | tenant_info, tenant list | Go-owned, section 4 |
| TEN-08, TEN-09, TEN-10, TEN-11 | list members, invite, accept, change role | Go-owned `/api/v1/tenants/...`; invitation = `user_tenant.role='invite'`; no migration (section 5) |
| UI-02, UI-04, UI-06, UI-07, UI-08, UI-09 | Guard, 401 redirect, login/register, session recovery, forgot password (UI-08 assumed), dashboard | Section 8 |
| UI-34, UI-35, UI-36 | Profile, API key dialog, team | Section 8 |
| UI-42, UI-43 | i18n, theme | Section 8 (theme toggle already exists) |
| SEC-01, SEC-09 | Every non-public endpoint behind auth; HMAC token with expiry | Default-deny gate generated from the route table; 30-day max-age (sections 1, 3) |
| E2E-01, E2E-02 | Registration and login flows on the real stack | Section 10 |
</phase_requirements>

## Summary

The token and password contracts are fully determined and reproduced. The login token is `base64url(zlib?(json(uuid_hex))) "." base64url(unix_ts_bigendian_minimal) "." base64url(HMAC-SHA1(SHA1("itsdangerous"+"signer"+secret), "payload.ts"))`. I generated tokens with the installed `itsdangerous 2.2.0` at fixed timestamps and reproduced them byte for byte with a hand-written Python implementation of that layout, so the layout below is confirmed against the real library. Go's `compress/zlib` does not emit the same compressed bytes as Python's `zlib` (verified: 32 vs 28 byte streams for the same JSON), so Go cannot be tested by byte-comparing its output with a Python token; it is tested by (a) verifying every Python vector and (b) round-tripping Go output through Python. Passwords: werkzeug's default is `scrypt:32768:8:1`, but `pbkdf2:sha256:600000$salt$hex` is produced and verified identically by Python (`werkzeug`/`hashlib`) and by **Go standard library `crypto/pbkdf2`** (present in the host's Go 1.25.5; verified by execution, identical digest), so no new Go dependency is needed. Python must always pass `method="pbkdf2:sha256:600000"` explicitly or it will write scrypt hashes that Go cannot verify.

The existing code base shapes the plan: the Go `router` package may only import `handler`, so the auth middleware must live in `internal/handler`; Python `api/apps` may not import models or Peewee, so the gate calls an `api/db/services` auth service. `conf/routes.yaml` is a family-level ownership list (prefixes and exact paths), not an endpoint list, so it cannot by itself generate the 401-enumeration and cross-tenant tests. The plan needs a per-endpoint registry (method, path, auth set, roles, tenant scope) kept consistent with the family list by a test, plus a default-deny gate on both servers so unimplemented routes under protected prefixes still answer 401.

Two findings should change the plan's first tasks. (1) CR-02 is worse than Phase 1 measured: the Python redactor is cubic on repeated sensitive words (`"token"*500`, 2,500 characters, took 14.8 s here) and a second quadratic regex (URL userinfo) exists beside it; a linear replacement is prototyped and handles 100 KB in about 6 ms. (2) The reference's tenant endpoints have authorization bugs the plan must not copy: `PATCH /tenants/<id>` rewrites the caller's row to `normal` regardless of current role (an owner or admin demotes themselves) and `DELETE` lets the owner remove themselves.

**Primary recommendation:** Build in this order: CR-02 linear redactor and carried hardening; token+password contract modules in Go and Python against the shared vector files; the default-deny gate generated from the route table on both servers; Go register/login/logout/me; tokens and tenants; OTP and mail; then SPA (guard, login, settings, dashboard, i18n); finish with the generated 401 and cross-tenant suites and E2E-01/02.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Register, login, logout, password change/reset, token issue | API / Backend (Go Gin) | Database (MySQL), Redis (OTP, rate limits) | D-17: Go issues the token; credentials and hashing never touch the SPA beyond TLS transport |
| Token verification on every protected request | API / Backend (both Go and Python) | Database (user row lookup) | Both servers verify independently; no proxying (D-17) |
| Route protection (default deny) | API / Backend, driven by generated policy table | Nginx only routes, never authenticates | SEC-01: gate must hold even when a prefix has no handler yet |
| Role / permission checks (owner/admin/normal) | API / Backend service layer | — | Must hold for API tokens and curl, not only the UI |
| Tenant isolation (tenant_id filtering, not-found on foreign ids) | Database / DAO layer | API service layer | TEN-01/02: every query filtered by caller tenant |
| Session recovery, guard, 401 redirect | Browser / SPA | API (`GET /v1/user/info`) | UI-02/04/07; server remains the authority |
| Token storage | Browser (`localStorage`, Bearer header) | HttpOnly `ragflow_auth` cookie as fallback | R-35 default |
| OTP generation, rate limits, mail send | API / Backend (Go) | Redis (state), SMTP server | D-06: state in Redis; Go owns the routes |
| Mail capture for tests | Dev infrastructure (Mailpit) | — | D-05 |
| Locale files, theme | Browser / SPA | `user.language`, `user.color_schema` persisted server-side | UI-42/43 |
| Superuser seeding | API / Backend (Python boot hook) | Database | API-13 and B-08 place it on the Python boot path |

## Standard Stack

### Core (no new Python or Go modules are needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| itsdangerous | 2.2.0 | Python verification of the login token (`URLSafeTimedSerializer`) | Already in `uv.lock` as a required dependency of `quart 0.23.1` and `flask`; installed in `.venv`. [VERIFIED: uv.lock, .venv/site-packages/itsdangerous-2.2.0.dist-info] It is transitive, so declare it explicitly in `pyproject.toml` (`itsdangerous==2.2.0`), which changes no lock content; flag for the user as a direct-dependency declaration |
| werkzeug | 3.1.9 (installed) | Python `generate_password_hash`/`check_password_hash` | Already installed transitively [VERIFIED: .venv]. CLAUDE.md warns 3.1.5 corrupts multipart; 3.1.9 is past that |
| Go stdlib `crypto/pbkdf2` | Go 1.25.5 host, `go.mod` says 1.25.0 | Go PBKDF2 | Added to the standard library in Go 1.24; `src/crypto/pbkdf2/pbkdf2.go` is present on this host [VERIFIED: GOROOT listing]; digest matched Python [VERIFIED: execution] |
| Go stdlib `crypto/hmac`, `crypto/sha1`, `compress/zlib`, `encoding/base64`, `crypto/rand` | 1.25.5 | Token create/verify | Matches the reference's `internal/utility/token.go` approach [CITED: ragflow/internal/utility/token.go] |
| Go stdlib `net/smtp` | 1.25.5 | Send OTP mail | Frozen but present; avoids a new dependency [ASSUMED: "frozen" status from Go docs knowledge] |
| `github.com/redis/go-redis/v9` | v9.22.0 (already direct in go.mod) | OTP state, rate-limit counters | Already locked [VERIFIED: go.mod] |
| `valkey` (Python) | 6.1.1 (already direct) | Python-side rate limits if any | Already locked [VERIFIED: pyproject.toml] |

Not available in `go.mod`: `github.com/google/uuid` [VERIFIED: grep of go.mod]. Generate the 32-hex UUID with `crypto/rand` (16 bytes, set version-4 and variant bits, hex-encode); no dependency.
`golang.org/x/crypto v0.48.0` is already in `go.sum` and `go.mod` as `// indirect` (pulled by gin via `sha3`) [VERIFIED]. It is only needed if scrypt verification of RAGFlow-origin hashes is wanted; recommended not to.

### New frontend packages (user must approve at a checkpoint; none installed)

| Package | Pin | Purpose | Notes |
|---------|-----|---------|-------|
| react-hook-form | 7.89.0 | Forms | Named in CLAUDE.md stack; registry latest 7.89.0, peer deps React 16-19, no postinstall [VERIFIED: npm view]. CLAUDE.md's 7.69.0 is only a "start here" pin |
| zod | 3.25.76 | Validation (must stay v3) | CLAUDE.md forbids zod 4; `zod@3` resolves to 3.25.76 [VERIFIED: npm view] |
| @hookform/resolvers | 3.10.0 | zod adapter | Peer `react-hook-form ^7.0.0`; 3.x targets zod 3 [VERIFIED: npm view] |
| i18next | 23.16.8 | i18n core | CLAUDE.md pin matches registry [VERIFIED: npm view] |
| react-i18next | 14.1.3 | React bindings | Peer `i18next >= 23.2.3` [VERIFIED: npm view] |
| @radix-ui/react-label | 2.1.16 | Accessible form labels (shadcn Label) | Same family as installed Radix packages |
| @radix-ui/react-alert-dialog | 1.1.24 | Confirm delete token / remove member / logout-all | Same family |

Deliberately not added: `@radix-ui/react-select` (use a native `<select>` for the role picker), `@radix-ui/react-tabs` (settings navigation is by route), `@radix-ui/react-avatar` (an `<img>` with initials fallback), `i18next-browser-languagedetector` (a ten-line detector reads `user.language`, then `localStorage`, then `navigator.language`). Each avoided package is one fewer approval.
Installed versions already differ from the CLAUDE.md "start here" table (react-router 7.18.4, axios 1.20.0, vitest 5.0.3, ...); exact pins as in `web/package.json` is the established pattern.

### Infrastructure

| Item | Version | Notes |
|------|---------|-------|
| `axllent/mailpit` | `v1.31.4` (16.8 MB amd64 on Docker Hub, pushed 2026-10-03) | Not local (`docker image ls` shows no mail catcher). A pull is required; this research did not pull. Pin the tag, never `latest`. [CITED: hub.docker.com/v2/repositories/axllent/mailpit/tags, queried 2026-10-07] |

**Installation (all gated behind the checkpoints below):**
```bash
# frontend (after user approval)
cd web && npm install --save-exact react-hook-form@7.89.0 zod@3.25.76 @hookform/resolvers@3.10.0 i18next@23.16.8 react-i18next@14.1.3 @radix-ui/react-label@2.1.16 @radix-ui/react-alert-dialog@1.1.24
# python: declare existing transitive dependency, then `uv lock` must show no other change
#   itsdangerous==2.2.0
```

## Package Legitimacy Audit

slopcheck was not run: installing it with `pip` is an install and the research contract forbids installs. Per the protocol, every package below is therefore `[ASSUMED]` for provenance even where the name comes from the user-locked CLAUDE.md stack, and the planner must gate the frontend installs behind a `checkpoint:human-verify` (the user must approve new npm packages anyway).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| react-hook-form | npm | long-lived [ASSUMED] | high [ASSUMED] | github.com/react-hook-form/react-hook-form [ASSUMED] | not run | Needs checkpoint; name is in CLAUDE.md stack; `npm view` ok, no postinstall |
| zod | npm | long-lived [ASSUMED] | high [ASSUMED] | github.com/colinhacks/zod [ASSUMED] | not run | Needs checkpoint; v3 line only |
| @hookform/resolvers | npm | long-lived [ASSUMED] | high [ASSUMED] | github.com/react-hook-form/resolvers [ASSUMED] | not run | Needs checkpoint |
| i18next | npm | long-lived [ASSUMED] | high [ASSUMED] | github.com/i18next/i18next [ASSUMED] | not run | Needs checkpoint |
| react-i18next | npm | long-lived [ASSUMED] | high [ASSUMED] | github.com/i18next/react-i18next [ASSUMED] | not run | Needs checkpoint |
| @radix-ui/react-label | npm | same family as installed Radix packages | high [ASSUMED] | github.com/radix-ui/primitives (confirmed by `npm view repository.url`) | not run | Needs checkpoint |
| @radix-ui/react-alert-dialog | npm | same | high [ASSUMED] | same | not run | Needs checkpoint |

`npm view <pkg>@<ver> scripts.postinstall` returned empty for react-hook-form, zod, @hookform/resolvers, i18next, react-i18next, @radix-ui/react-label [VERIFIED: npm view]. Not checked for alert-dialog.
**Packages removed due to slopcheck [SLOP]:** none (not run). **Packages flagged [SUS]:** none known.
Python and Go need no new third-party modules. `axllent/mailpit` is a container image, not a package; the user approves the pull.

## Architecture Patterns

### System Architecture Diagram

```
Browser (SPA)                      Nginx :80/:8088 (routes from conf/routes.yaml, never authenticates)
 login form  --POST /api/v1/auth/login-->  Go :9384
 localStorage token                          | 1 rate limit (Redis)  2 user lookup (MySQL)  3 PBKDF2 verify
 Bearer <wrapped token>                      | 4 reuse or create user.access_token  5 wrap + sign (HMAC-SHA1)
        |                                    | 6 Set-Cookie ragflow_auth (HttpOnly) 7 envelope {code,message,data}
        |
        +--any protected request-->  Nginx --> Go or Python by ownership
                                       |
                    GATE (default deny, generated from route table)
                    exact entry > longest prefix > default "jwt"
                         |
                    resolve credential: header Bearer|raw, else cookie (jwt type only)
                         | beta?  -> api_token.beta == tok     -> owner user, AUTH_BETA
                         | jwt?   -> verify wrapper (secret, 30d) -> inner uuid -> AUTH-08 rules
                         |          -> user.access_token == uuid AND status '1' -> AUTH_JWT
                         | api?   -> api_token.token == tok   -> owner user, AUTH_API
                         | none   -> HTTP 401 envelope (generic)
                         v
                    role check (permission table) -> 403 if member lacks role
                    tenant scope -> 404 (same as nonexistent) if caller is not a member
                         v
                    handler -> service -> dao (GORM, Go)  |  api/apps -> services -> models (Peewee, Python)

Password reset:  SPA -> Go /auth/password/forgot/otp -> Redis (HMAC-hashed code, TTL 10m, attempts) -> SMTP -> Mailpit (dev)
                 SPA -> Go /auth/password/forgot/otp/verify -> Redis -> short-lived "verified" marker
                 SPA -> Go /auth/password/reset -> set hash, rewrite access_token to INVALID_<hex>
```

### Recommended Project Structure
```
internal/
  common/route_policy_gen.go      # generated by scripts/gen_routes.py from conf/routes.yaml + endpoints
  common/token.go                 # DumpAccessToken / VerifyAccessToken (stdlib only, clock injected)
  common/password.go              # HashPassword / VerifyPassword (pbkdf2 werkzeug format)
  handler/auth.go                 # AuthGate middleware (must live in handler: router may not import service)
  handler/user.go tenant.go token.go
  service/user.go tenant.go token.go otp.go mail.go ratelimit.go
  dao/user.go tenant.go user_tenant.go api_token.go
api/apps/auth.py                  # before_request gate (imports quart)
api/apps/route_policy_gen.py      # generated
api/db/services/auth_service.py   # resolve_principal(): pure, no quart
common/security/tokens.py         # itsdangerous wrapper with clock injection
common/security/passwords.py      # always pbkdf2:sha256:600000
common/bootstrap/ensure_superuser.py  # called from a startup hook
conf/routes.yaml                  # families (existing) + endpoints: section (new)
test/fixtures/access_token_vectors.json, password_vectors.json
web/src/{locales,pages/login,pages/home,pages/user-setting,hooks,lib/auth}/...
```

### Pattern 1: Cross-language token contract (byte-level)

[VERIFIED: generated with itsdangerous 2.2.0 and reproduced by an independent Python implementation, assertions passed; Go PBKDF2/zlib behaviour verified separately]

Producing a token (`DumpAccessToken(inner, secret, now)`):

1. `inner` = 32 lowercase hex characters (a UUID4 without hyphens), stored verbatim in `user.access_token`.
2. JSON: compact separators, so the payload is the 34 bytes `"<inner>"` including the double quotes (`json.dumps(inner, separators=(",", ":"))`; Go `json.Marshal` of a string produces the same bytes for hex input).
3. Compression: `c = zlib.compress(json)` (default level, zlib header `78 9c`). If `len(c) < len(json) - 1` then payload = `"." + b64url(c)` else payload = `b64url(json)`. For a 34-byte UUID JSON the compressed form is always chosen. Decoders must accept both forms, and must treat the leading `.` as the compression marker only on the payload segment.
4. base64url = RFC 4648 URL-safe alphabet (`-` `_`), **no `=` padding** when encoding; decoders re-pad.
5. Timestamp: `int(now)` Unix epoch seconds (not the 2011 epoch of itsdangerous 1.x; confirmed `1700000000` -> bytes `6553f100` -> `ZVPxAA`), big-endian, **minimal length** (leading zero bytes stripped), then base64url no padding.
6. Signed value: `payload + "." + ts`.
7. Key derivation ("django-concat", SHA-1): `key = SHA1(salt || "signer" || secret)` where `salt = "itsdangerous"` (the **Serializer** default; `Signer`'s own default `itsdangerous.Signer` is not used because the serializer passes its salt) and `secret` is the UTF-8 bytes of the secret string. The Go reference does exactly `sha1("itsdangerous" + "signer" + secretKey)` [CITED: token.go `getAccessTokenSignature`] and my Python reproduction matches the library.
8. Signature: `b64url(HMAC-SHA1(key, signed_value))`, no padding (27 characters).
9. Token = `signed_value + "." + signature`. Parsing: split on the **last** `.` for the signature, then the last `.` of the remainder for the timestamp; the rest is the payload (a leading `.` belongs to the payload).

Verifying (both languages, clock injected for tests): bound the token length first (reject above 1,024 characters before any HMAC); recompute the signature and compare in constant time (`hmac.Equal`, itsdangerous does the same); only after the signature is valid decode the timestamp and decompress; reject if `age = now - ts` is greater than `2,592,000` (30 days, D-11) or less than 0; accept `age == max_age` (verified: `valid_at_max_age` passes, one second later is `SignatureExpired`); decode payload; require the JSON value to be a **string** (itsdangerous happily returns an int or object for a validly signed non-string payload; the caller must reject, vectors included); then apply AUTH-08 on the inner string: trimmed non-empty, length >= 32, not starting with `INVALID_`; then look up `user.access_token = inner AND status = '1'`.
The reference's Go side uses a 1-day max age (`accessTokenExpireSeconds = 86400`) and its Python side uses no max age; D-11 overrides both with 30 days.

Secret source: one required value `SECRET_KEY` (>= 32 characters, rejected when empty or when equal to a known placeholder) in `docker/.env.example` under `# secret`, injected through the existing `x-app-env`, rendered by `scripts/render_conf.py` into `service_conf.yaml` under a new `security:` section, and read by both `internal/server/config.go` and `common/settings.py`. Do not copy the reference's auto-generated key stored in Redis (its own comment notes Redis eviction would then 401 every request; this stack's Valkey runs `allkeys-lru`). Rotating the secret signs everyone out; document it.
**Operational trap:** `scripts/init_env.sh` refuses to touch an existing `docker/.env` and generates `token_hex(16)` (32 chars, exactly the minimum). This host's `.env` already exists without `SECRET_KEY`, so compose will fail fast with `${SECRET_KEY:?}`. Add an append-missing-keys mode to `init_env.sh` (do not tell the user to `--force`, which would regenerate database passwords against existing volumes) and make the generated length for this key 64 hex characters.

Reference test vectors (fake secret; assertions executed with itsdangerous 2.2.0; these belong in `test/fixtures/access_token_vectors.json`, which is a test path and so exempt from `check_secrets`):

```
secret        = "test-secret-key-0123456789abcdef0123456789abcdef"   (obviously fake)
inner uuid    = "0123456789abcdef0123456789abcdef"
max_age       = 2592000
signed_at     = 1700000000
valid token   = .eJxTMjA0MjYxNTO3sExMSk5JTUPnKwEAkmIJCQ.ZVPxAA.2hzReVQugqcZwv9Chnimhl5Rv90
```

| id | token (abbreviated where long, full values in scratch JSON) | verify at `now` | expected |
|----|-------|-----|----------|
| valid_fresh | the valid token above | 1700000060 | ok -> inner uuid |
| valid_day29 | same | 1700000000 + 29*86400 | ok |
| valid_at_max_age | same | 1700000000 + 2592000 | ok (age == max_age accepted) |
| expired_by_one_second | same | 1700000000 + 2592001 | rejected (expired) |
| future_timestamp | same | 1699999999 | rejected (age < 0) |
| tampered_payload | valid token with `eJxT` -> `eJxU` | 1700000001 | rejected (bad signature) |
| tampered_signature | last two chars changed | 1700000001 | rejected |
| wrong_secret | `.eJxTMjA0MjYxNTO3sExMSk5JTUPnKwEAkmIJCQ.ZVPxAA.kDPeT7xwsC4YN9EmPHTz-aQW1s8` | 1700000001 | rejected |
| no_signature / empty / garbage | `<payload>.<ts>`, `""`, `not-a-token` | any | rejected |
| valid_uncompressed_payload | `IjAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmIg.ZVPxAA.KQBuYfEuoM7E9yJZUEDr74kI6Vg` | 1700000001 | ok (decoders accept the no-dot form) |
| signed_non_string_payload_number | `MTIzNDU.ZVPxAA.3YgR0UEV3o5MjXgkz5ulNeOOG2c` | 1700000001 | signature valid, **caller must reject** (payload is `12345`) |
| signed_bad_zlib | `.bm90emxpYg.ZVPxAA.wOY1Shu3ADakSjgQpkbqo8-EJv8` | 1700000001 | rejected (bad payload) |
| signed_invalid_prefix_value | `.eJxT8vQLc_TxdIlPJACUADPqDss.ZVPxAA.e__5fbcRsgJLKjUCKXDVwqDCpi0` | 1700000001 | token layer ok, **AUTH-08 rejects** (`INVALID_aaaa...`) |
| signed_short_value | `.eJxTSsQPlADMVAwE.ZVPxAA.diMlI5IBP8nLQtQX1YfDmq9BSQw` | 1700000001 | token layer ok, AUTH-08 rejects (31 chars) |
| signed_whitespace_value | `IiAgICI.ZVPxAA.tB6z0cHRCIS0zQfXrJpTlQhSFGw` | 1700000001 | token layer ok, AUTH-08 rejects |

More valid positive vectors: inner `ffffffffffffffffffffffffffffffff` at `1700000000` is `.eJxTSiMAlADj6A0F.ZVPxAA.H5QVTFWWL0v9X34v4q5XqaMP0Co`; at `1760000000` is `.eJxTSiMAlADj6A0F.aOd4AA.cMspKyn2jrfoKdAuCn2P3zxg_IE`; `0123...cdef` at `1760000000` is `.eJxTMjA0MjYxNTO3sExMSk5JTUPnKwEAkmIJCQ.aOd4AA.DDF0MzrUF4gGxxQWbhuMDPM9Af4`. Non-compressed example for a 36-character hyphenated UUID: `IjAxMjM0NTY3LTg5YWItY2RlZi0wMTIzLTQ1Njc4OWFiY2RlZiI.ZVPxAA.1XLtiB-L3F9u5xeKJJTNWpm_kPc` (use only as an interop probe; do not issue hyphenated values).

**Test strategy that follows from the zlib finding:** Go's `zlib.NewWriter` output differs from CPython's (Go: `eJxSMjA0MjYxNTO3sExMSk5JTUPnKwECAAD__5JiCQk` is 32 raw bytes; Python: 28 bytes). Both inflate to the same JSON and both are valid. So: (1) Go unit test verifies every vector above (clock injected); (2) Go unit test dumps with an injected clock, then decodes its own output and checks structure and signature against an independently computed HMAC; (3) a Python test shells out to or reads a Go-produced token fixture (generated by a Go test and checked into `test/fixtures/` as Go-produced) and verifies it with `itsdangerous` with the same max age; (4) the live E2E logs in through Go and calls a Python protected route with the issued token. Do not write a Go test that asserts byte equality with the Python-produced token string.

Python implementation shape (verified working with clock injection):
```python
# common/security/tokens.py (sketch)
from itsdangerous import TimestampSigner, URLSafeTimedSerializer, BadData
def _serializer(secret: str, now: int | None):
    class _Signer(TimestampSigner):
        def get_timestamp(self) -> int:
            return now if now is not None else super().get_timestamp()
    return URLSafeTimedSerializer(secret, signer=_Signer)
def verify(token: str, secret: str, max_age: int = 2_592_000, now: int | None = None) -> str | None:
    if not token or len(token) > 1024: return None
    try: value = _serializer(secret, now).loads(token, max_age=max_age)
    except BadData: return None
    return value if isinstance(value, str) else None
```
Verified in scratch: `signer=<subclass>` is accepted by `URLSafeTimedSerializer` in 2.2.0 and gave the results in the table.

### Pattern 2: Password hashing contract (R-34)

[VERIFIED by execution in Python 3.13/werkzeug 3.1.9 and Go 1.25.5]

- Scheme: werkzeug-format string `pbkdf2:sha256:600000$<salt>$<hex digest>` with a 16-character alphanumeric salt (werkzeug's own generator output) and a 32-byte derived key hex-encoded (64 chars). 600,000 iterations is the OWASP-recommended count for PBKDF2-HMAC-SHA256 [ASSUMED: OWASP Password Storage Cheat Sheet figure from training knowledge]; werkzeug 3.1.9's own default for pbkdf2 is 1,000,000 [VERIFIED: `DEFAULT_PBKDF2_ITERATIONS`]. 600,000 keeps one verification near 75 ms (Python) to 95 ms (Go) on this host, which matters for login throughput (see Pitfall 6). Record the iteration count in config so it can be raised; verification reads the count from the stored string.
- Salt is used as **its UTF-8 bytes, not hex-decoded**, in both languages (`hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), n)`; Go `pbkdf2.Key(sha256.New, password, []byte(salt), n, 32)` note the Go 1.24+ signature takes the password as `string` and the salt as `[]byte`).
- `werkzeug.security.generate_password_hash(pw)` with no `method` writes `scrypt:32768:8:1$...` (verified), which Go (stdlib only) cannot verify. Python code must always pass `method="pbkdf2:sha256:600000"`; add a unit test asserting the prefix of every hash the code can produce (including the superuser seeder).
- Go `VerifyPassword`: parse `pbkdf2:sha256:<n>$<salt>$<hex>`, accept only `sha256`, bound `n` to a sane range (for example 100,000 to 10,000,000), compare with `subtle.ConstantTimeCompare`, reject any other scheme (including `scrypt:`) as not verified. Importing RAGFlow's scrypt rows would need `golang.org/x/crypto/scrypt`; not required here (fresh schema) so it is not recommended.
- No client-side RSA. The reference encrypts passwords in the browser with a bundled RSA key and a hard-coded key passphrase (`RSA.importKey(..., "Welcome")` in `api/utils/crypt.py`, with a matching Go `DecryptPassword`) [CITED: ragflow/api/utils/crypt.py, internal/service/user.go]. `docs/` never mention RSA; the documented request bodies carry the plain password over TLS (`"password": "Password123!"` in `docs/04-api/authentication-api.md`). Follow docs: plain password in JSON over TLS, so `pycryptodomex` is not needed. This breaks wire compatibility with the reference's own SPA, but D-09's compatibility goal is the token format only. Record as a decision.
- Never log or echo the password; reject bodies above a small cap (for example 1 KiB for auth routes); enforce 8 to 128 characters (D-02 sets only the minimum; a maximum bounds PBKDF2 input cost and is a new recorded decision).

Vectors (fake passwords; digests computed by Python `hashlib` and `werkzeug.check_password_hash`, and reproduced by Go `crypto/pbkdf2`):

| password | hash | verifies |
|----------|------|----------|
| `correct horse battery` | `pbkdf2:sha256:600000$saltSALT01234567$f25da603a9a15fe8f477700a34086621b89dd29b890f1a39763d9d6b1d7bc01e` | werkzeug True, Go digest identical |
| `pässwörd-密码-12` | `pbkdf2:sha256:600000$abcdefgh12345678$d0a1a2d38598714e2c59ec47c0bd94bf24242e64275afa54edb620820413950d` | werkzeug True (UTF-8 bytes) |
| wrong password `x` against the first hash | same hash | False |
| werkzeug-generated (salt `rxR6mprAjJXRtX7C`) for `pw12345678` | `pbkdf2:sha256:600000$rxR6mprAjJXRtX7C$2dcb4439ef2a2ac6e1ecd86c747c3c60701674ec2b8ab9263d27f81b0e431022` | round trip |

Also add negative vectors: `scrypt:32768:8:1$pc3y17hCSY9JhkwM$44ea...` must be rejected by Go; `pbkdf2:sha1:...`, `pbkdf2:sha256:5$...` (below floor), missing `$` sections, empty password, non-ASCII salt.

### Pattern 3: Default-deny auth gate driven by the route table

- One policy resolver, identical on both stacks: exact entry beats prefix, longest prefix wins, **anything unmatched is `jwt`** (deny by default, never public by omission). The gate runs before routing, so an unimplemented protected path (for example `/api/v1/searchbots/x` on Go, or an unknown path under the Python `/api/` catch-all) returns 401, not 404, and does not reveal which paths exist.
- Auth values: keep the existing `none | jwt | beta | api` vocabulary but define them as the set of **credential types accepted**: `none` (public), `jwt` (access token or `ragflow_auth` cookie only), `api` (access token or API token: the docs' "JWT / API Key" level, used by the Python catch-alls and later dataset/agent/chat routes), `beta` (beta token, plus access token and API token as in the reference's beta middleware). Management routes (tokens, tenants, team, user settings) are `jwt` only: an API token must not mint further API tokens or change roles (permission matrix: API Token column is X for Team Admin and Tenant Settings).
- Generation: `scripts/gen_routes.py` already expands routes.yaml; extend it to emit `internal/common/route_policy_gen.go` and `api/apps/route_policy_gen.py` and keep `--check` as the drift gate. Do not `go:embed` the YAML: embed cannot reach `conf/` from `internal/...` and the container must not depend on the file.
- Public `OPTIONS` preflight must bypass the gate (as the existing Go CORS middleware already short-circuits preflight) or CORS-enabled deployments break; test it. On Python, verify the order of `quart-cors` and the `before_request` hook with a test rather than assuming.
- Error shape: HTTP 401 with envelope `{"code":401,"message":"unauthorized","data":null}` and a generic message for every failure cause. This follows AUTH-12 and success criterion 2. The reference's beta middleware returns a business code with HTTP 200 for beta failures; do not copy that, it would break the enumeration test.

### Pattern 4: Principal and tenancy

- Registration sets `tenant.id == user.id` and an owner row `user_tenant(user_id=id, tenant_id=id, role='owner', invited_by=id)` [CITED: ragflow/internal/service/user.go Register]. The caller's "own tenant" is resolved from the owner row rather than assuming equality, but equality is what makes `AUTH_API` work: an API token row stores `tenant_id` and the principal is "the user whose id equals that tenant id" [CITED: api/apps/__init__.py `UserService.query(id=objs[0].tenant_id)`].
- Request context carries: `user_id`, `tenant_id` (own), `role` (in own tenant), `auth_type`, `is_superuser`. Tenants the user merely joined appear in `GET /v1/tenant/list`; acting inside a joined tenant's data is Phase 3 (TEN-13).
- Cross-tenant rule: a caller who is **not a member** of tenant T gets the same response for T's resources as for a nonexistent id (HTTP 404, code 404, message `not found`). A **member lacking the role** gets 403. This is what reconciles criterion 4 (403 for matrix violations) with criterion 5 (indistinguishable from not-found): the 403 is only reachable by someone who already knows the tenant exists.
- Permission table: one data file (`conf/permissions.yaml`, generated into both languages like the route policy) covering the 10 functional areas of `docs/16-auth/permissions.md`. In this phase only Team Admin (owner only, D-13) and token/user routes are enforceable; the dataset, agent, search-bot, MCP, tenant-settings and enterprise-admin rows are recorded now and enforced as their routes land. TEN-12 (default models) is Phase 3.

### Anti-Patterns to Avoid
- **Copying the reference's tenant routes verbatim.** `PATCH /tenants/<id>` filter-updates the caller's `user_tenant` row for that tenant to `normal` without checking the current role, so an owner or admin who calls it demotes themselves; `DELETE` allows `current_user.id == tenant_id` (the owner) to delete their own owner row; GET members checks `current_user.id != tenant_id` and so excludes members [CITED: ragflow/api/apps/restful_apis/tenant_api.py]. The plan must require `role == 'invite'` for accept/decline, forbid owner removal/leave (D-16), and allow any active member to list members.
- **Serialising the GORM entity.** `entity.User` has `json:"password"` and `json:"access_token"` tags [VERIFIED: internal/entity/user.go]. Every handler returns a response DTO; add a test that no response body contains `password`, `access_token` (except the login response's token field) or a `$`-delimited hash.
- **Per-IP limits that all see 127.0.0.1.** Go sets `SetTrustedProxies(nil)` and Nginx runs in the same container, so `c.ClientIP()` is always `127.0.0.1` and an IP bucket would throttle every user together. Trust only loopback and read the client address from `X-Real-IP`/`X-Forwarded-For` that Nginx sets (`docker/nginx/proxy.conf` already sets both).
- **Using `request.path` in logs for token-bearing URLs.** `DELETE /api/v1/system/tokens/<token>` puts a live API token in the path; Go's request logger, the Python access logger and Nginx's default `access_log /dev/stdout` all log it, and the key=value redactor cannot see it. Log the route template (`c.FullPath()`, Quart `url_rule.rule`), and add an Nginx `map $request_uri $loggable_uri` plus `log_format` that masks the segment after `/api/v1/system/tokens/`. Test with the log-redaction vectors plus one path vector.
- **Reading the SPA open-redirect `next` parameter unchecked.** Accept only a string starting with a single `/` and not `//` or `/\`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python token verification | A second hand-written HMAC/zlib verifier in production | `itsdangerous.URLSafeTimedSerializer.loads(..., max_age=...)` | It is the library whose format D-09 targets; one canonical verifier on the Python side; hand code only in Go |
| PBKDF2 in Go | A loop over HMAC | stdlib `crypto/pbkdf2` | Verified identical output, constant API, no dependency |
| Password hash strings on Python | Own formatter | `werkzeug.security.generate_password_hash(method="pbkdf2:sha256:600000")` / `check_password_hash` | Format owner |
| Constant-time compares | `==` on secrets | `hmac.Equal`, `subtle.ConstantTimeCompare`, `hmac.compare_digest` | Timing |
| OTP randomness | `math/rand` | `crypto/rand` with `rand.Int` over 10^6, zero-padded | Predictability |
| Mail delivery for tests | A fake mailer in test code | Mailpit container with its REST API | D-05 says verify for real |
| Log redaction regex | A bigger backtracking regex | Linear two-stage scan (section 9) | CR-02 |
| CSRF framework | A package | Origin check for cookie-authenticated unsafe requests, plus SameSite=Lax | Cookie auth is only the fallback path (R-35) |
| i18n runtime | Own message catalogue | i18next + react-i18next | Locked in CLAUDE.md |
| Forms and validation | Hand-rolled field state | react-hook-form + zod 3 | Locked in CLAUDE.md |
| Route-table enumeration | A hard-coded list of routes in tests | Real engine route tables (`gin.Engine.Routes()`, Quart `url_map.iter_rules()`) compared with the endpoint registry | Success criterion 2 says "enumerating the route tables" |

**Key insight:** the dangerous parts are not the crypto (small, now vector-tested) but the gaps around it: routes that exist in no table, tokens in URLs and logs, shared-IP rate limits, and reference authorization shortcuts.

## Runtime State Inventory

Not a rename or migration phase. Omitted. (One note: `user.language` stores a label by default in the Peewee model; see section 8.)

## Common Pitfalls

### Pitfall 1: Python writes scrypt hashes
**What goes wrong:** the superuser seeder or any Python path calls `generate_password_hash(pw)`; werkzeug 3.1.9 writes `scrypt:32768:8:1$...` and Go rejects it, so that user can never log in through Go.
**How to avoid:** one `hash_password()` in `common/security/passwords.py`, a unit test that every produced hash starts with `pbkdf2:sha256:`, and a cross-stack test where the Python-seeded superuser logs in through Go.
**Warning signs:** `scrypt:` appears in `user.password`.

### Pitfall 2: The 30-day wrapper expiry is not a 30-day session
**What goes wrong:** the inner UUID is stored unhashed and reused (D-10), so the wrapper timestamp is renewed on every login but the inner secret never rotates until logout or password change. A leaked wrapper stays valid up to 30 days after its signing, and the inner UUID in a database dump is a usable credential only together with the secret key (it must be wrapped to be accepted).
**How to avoid:** accept it as the documented design; make logout and password change/reset rewrite the row (D-08, AUTH-09); keep the secret out of Redis and out of the repo; consider storing no extra state. Record the trade-off in the decision row.

### Pitfall 3: Login token reuse race
**What goes wrong:** two first logins at once both see an empty or `INVALID_` token, each writes a new UUID, and one device holds a token that no longer matches.
**How to avoid:** conditional update `UPDATE user SET access_token=? WHERE id=? AND (access_token IS NULL OR access_token LIKE 'INVALID\_%' OR CHAR_LENGTH(access_token) < 32)`, then re-read the row and use whatever is stored. Integration test with parallel logins.

### Pitfall 4: Unknown-email timing and enumeration
**What goes wrong:** an unknown email returns immediately while a known one burns about 90 ms of PBKDF2, revealing which emails exist even though the message is generic (D-04).
**How to avoid:** on unknown email (and on disabled accounts before the password check) run a verification against a fixed dummy hash of the same cost, then return the generic error. Same for password reset (D-07): identical response body and similar latency whether or not mail is sent (send in a goroutine with bounded concurrency, never inline). Registration still reveals duplicate emails (unavoidable for sign-up UX); rate-limit it per IP.

### Pitfall 5: Valkey is `allkeys-lru` with a 128 MB cap
**What goes wrong:** OTP codes and rate-limit counters are eviction candidates; an evicted counter silently resets a lockout. Keys are tiny, so this only matters under memory pressure, but queue keys in later phases make pressure plausible [CITED: IN-04 in 01-REVIEW.md].
**How to avoid:** every key written here has a TTL; document it; do not store the signing secret or the superuser state in Redis. Consider `volatile-lru` as a Phase 4 item.

### Pitfall 6: PBKDF2 makes login a CPU-denial vector
**What goes wrong:** about 75 to 95 ms of CPU per attempt, in an `app` container capped at 768 MB and shared with Python and Nginx.
**How to avoid:** rate-limit before hashing (per email and per IP, section 6), cap concurrent hash operations with a small semaphore (for example number of CPUs), and cap password length.

### Pitfall 7: Peewee is synchronous inside async Quart
**What goes wrong:** token lookups on the Python gate block the event loop.
**How to avoid:** call the auth service through `asyncio.to_thread`, with a per-call `DB.connection_context()`; keep the gate's pre-database checks (header presence, token length, signature, max age) cheap so unauthenticated floods never reach MySQL.

### Pitfall 8: Public config must carry `register_enabled`
**What goes wrong:** D-01 requires the SPA to hide sign-up when registration is off, but `/api/v1/system/config` currently returns only engine, version, service [VERIFIED: internal/service/system.go]. Without a public flag the SPA cannot know.
**How to avoid:** add `register_enabled: bool` (and nothing else sensitive) to that public Go endpoint; the reference does the same with `registerEnabled` [CITED: ragflow system_api.py `get_config`].

### Pitfall 9: Cookie fallback re-introduces CSRF
**What goes wrong:** once `ragflow_auth` authenticates requests, a cross-site form post can ride the cookie.
**How to avoid:** cookie is `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000; Secure` when the request was TLS (`X-Forwarded-Proto: https` or `r.TLS != nil`); accepted by `jwt`-type routes only and never by `api`/`beta`; for non-GET/HEAD/OPTIONS requests that authenticated by cookie only (no Authorization header), require `Origin` (or `Referer`) to match the request host or the configured allow-list, else 403. Logout and password change clear it with `Max-Age=0`. The reference's cookie is deliberately not HttpOnly so JS can copy it (OAuth bootstrap); do not copy that.

### Pitfall 10: Docs mix `/v1/...` and `/api/v1/...`
**What goes wrong:** requirements write `/system/tokens` and `/tenants/<id>/users` without a prefix because the docs list Python route files mounted under a prefix; the SPA's `/` fallback would swallow unprefixed paths.
**How to avoid:** use the `/api/v1` prefix (the reference mounts these under `/api/v1` [CITED: ragflow router.go lines 279-285, 672-679]) and record the decision (Open Question 2).

### Pitfall 11: `check_secrets` will flag good test vectors if tightened carelessly
WR-23 tightening (unquoted assignments, token-named keys) must keep the `is_test_path` exemption for `test/fixtures/*.json` and the vector secrets must stay obviously fake and in test paths only. Production code reads the secret from configuration, never a literal.

## Code Examples

### Token verify, Go (sketch, structure only; clock and max age injected)
```go
// internal/common/token.go
// Source: reproduces itsdangerous 2.2.0 URLSafeTimedSerializer layout (verified vectors); reference: ragflow/internal/utility/token.go
func VerifyAccessToken(token, secret string, maxAge time.Duration, now time.Time) (string, error) {
    if len(token) == 0 || len(token) > 1024 { return "", ErrBadToken }
    i := strings.LastIndexByte(token, '.'); if i < 0 { return "", ErrBadToken }
    value, sig := token[:i], token[i+1:]
    if !hmac.Equal([]byte(sig), []byte(sign(value, secret))) { return "", ErrBadSignature }
    j := strings.LastIndexByte(value, '.'); if j < 0 { return "", ErrBadToken }
    payload, tsb64 := value[:j], value[j+1:]
    // decode timestamp (RawURLEncoding), age := now.Unix()-ts ; reject age > maxAge or age < 0
    // then: leading '.' => zlib inflate (cap output, e.g. io.LimitReader 4096) ; json.Unmarshal into string ; AUTH-08 checks by caller
}
func sign(value, secret string) string {
    k := sha1.Sum([]byte("itsdangerous" + "signer" + secret))
    m := hmac.New(sha1.New, k[:]); m.Write([]byte(value))
    return base64.RawURLEncoding.EncodeToString(m.Sum(nil))
}
```

### Password verify, Go (sketch)
```go
// Source: stdlib crypto/pbkdf2 (Go 1.24+); digest verified equal to hashlib.pbkdf2_hmac for the vectors above
k, err := pbkdf2.Key(sha256.New, password, []byte(salt), iterations, 32)
ok := subtle.ConstantTimeCompare([]byte(hex.EncodeToString(k)), []byte(storedHex)) == 1
```

### Linear redaction (CR-02), prototype run against the 12 shared vectors
Scratch implementation passed all 12 entries of `test/fixtures/log_redaction_vectors.json` and the new cases; see section 9 for the approach and timings.

### Mailpit read-back for tests (HTTP API)
`GET /api/v1/search?query=to:<address>&limit=1` returns matching messages newest first; `GET /api/v1/message/<ID>` returns the message including its text body; `DELETE /api/v1/messages` clears the mailbox before a test; `GET /api/v1/info` is a cheap readiness probe; the image also ships a `readyz` health command [CITED: mailpit swagger.json from github.com/axllent/mailpit (paths and methods), hub.docker.com image page for the health command]. Poll with the project's `wait_until` helper until the message for the unique recipient appears; extract the 6-digit code with `\b\d{6}\b` from the text body.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `golang.org/x/crypto/pbkdf2` | stdlib `crypto/pbkdf2` | Go 1.24 | No third-party dependency for PBKDF2 (host Go 1.25.5) |
| werkzeug default pbkdf2 | werkzeug default scrypt 32768:8:1 | werkzeug 3.0 | Python must request pbkdf2 explicitly |
| itsdangerous 1.x timestamp epoch (2011) | Unix epoch | itsdangerous 2.0 | Both stacks use Unix epoch |
| `minio/minio` image | `pgsty/minio` | Phase 1 decision | n/a here |

**Deprecated/outdated:** `docs/04-api` examples show `retcode/retmsg` and a JWT-looking access token; the project envelope is `{code,message,data}` (D-13) and the token is the itsdangerous-compatible wrapper, not a three-part JWT.

## Route ownership for every Phase 2 endpoint

Docs conflict, resolved as follows. Nginx location order is exact `=` first then `^~` prefixes, generated from `conf/routes.yaml` [VERIFIED: scripts/gen_routes.py, docker/nginx/ragflow.conf]. Every entry below must be added to `conf/routes.yaml` (and the endpoint registry) before it is implemented, per the established pattern.

| Method and path | Owner | Auth set | Roles | Note |
|-----------------|-------|----------|-------|------|
| `POST /api/v1/users` | Go | none | - | exact entry exists. Refuses with 403 envelope when `REGISTER_ENABLED=0` (D-01) |
| `POST /api/v1/auth/login` | Go | none | - | under existing `/api/v1/auth/` prefix (`auth: none`) |
| `POST /api/v1/auth/logout` | Go | **jwt** | any | prefix is `none`, so add an exact entry with `auth: jwt` (exact beats prefix). Reference: `authorized.Group("/api/v1").Group("/auth").POST("/logout")` [CITED: router.go 248-255]; AUTH-09 does not name the path |
| `POST /api/v1/auth/password/forgot/otp`, `.../otp/verify`, `POST .../password/reset` | Go | none | - | the reference also has `/forgot/captcha`; captcha is AUTH-25 (Phase 8), not built; D-06/D-07 replace it with rate limits |
| `GET /v1/user/info`, `POST /v1/user/setting`, `POST /v1/user/setting/password`, `GET /v1/user/tenant_info` | Go | jwt | any | under existing `/v1/user/` prefix. `set_tenant_info` is TEN-12, Phase 3 |
| `GET /v1/tenant/list` | Go | jwt | any | under existing `/v1/tenant/` prefix |
| `GET`, `POST /api/v1/system/tokens`; `DELETE /api/v1/system/tokens/{token}` | **Go** | jwt | any member for own tenant | **Conflict:** `docs/apikey llm.md` (user-released) and the reference's Go router say Go; `docs/04-api/system-api.md` lists the Python file; the Phase 1 comment in `routes.yaml` says Python catch-all. D-17 says Go owns user and tenant routes and tokens are generated with Go `crypto/rand` per the user-released doc. Follow Go. Add exact `/api/v1/system/tokens` and prefix `/api/v1/system/tokens/` entries (exact `=` locations beat the Python `/api/` prefix) |
| `GET /api/v1/tenants` (list, reference only) | Go | jwt | any | optional alias of `/v1/tenant/list`; skip unless the SPA needs it |
| `GET /api/v1/tenants/{tenant_id}/users` | Go | jwt | owner, admin, normal (any active member) | non-member gets 404 |
| `POST /api/v1/tenants/{tenant_id}/users` (invite by email, D-14) | Go | jwt | **owner only** (D-13) | target must be an existing account; duplicate/self/owner cases return conflict-style errors without revealing other tenants |
| `PATCH /api/v1/tenants/{tenant_id}` (accept; body optional `{"action":"decline"}`, D-15) | Go | jwt | caller must hold a pending invite | default action is accept to match the docs |
| `DELETE /api/v1/tenants/{tenant_id}/users` body `{user_id}` | Go | jwt | owner removes a member or withdraws a pending invite; a member removes self (leave); never the owner row (D-16) | |
| **new** `PATCH /api/v1/tenants/{tenant_id}/users/{user_id}` body `{role: admin\|normal}` | Go | jwt | owner only | TEN-11 has no documented endpoint; record as a decision. Cannot set `owner`, cannot target the owner row, cannot target a pending invite |
| `GET /api/v1/system/version` | Go | jwt | any | remove `public_until_phase` |
| `GET /api/v1/system/status` (+ `/system/status`) | Python | jwt | any | remove `public_until_phase` |
| Python catch-alls `/api/`, `/v1/` | Python | **api** | per route | currently `jwt`; upgrade to `api` so the later "JWT / API Key" routes accept API tokens; unknown paths return 401 via the gate |
| `/api/v1/mcp` (exact), `/api/v1/searchbots/` | Go | beta | - | Phase 8 builds the handlers; Phase 2 delivers `BetaAuthMiddleware` and the gate behaviour |

Query-string note (WR-20, deferred to "Phase 2, when `GET /api/v1/users?...` is first used"): no Phase 2 endpoint above is a Go exact path called with a query string. Still fix the Vite proxy key to `^path(\\?.*)?$` while touching `vite.config.ts`; it is a one-line change and a unit test over `buildProxy()`.

SPA routes (docs authoritative, `docs/02-frontend/routing.md`): `/login` (bare layout, covers sign-in and sign-up), `/home` (dashboard), `/user-setting/profile`; this phase adds `/user-setting/api` (UI-35) and `/user-setting/team` (UI-36) and a forgot-password route (UI-08). `/` redirects to `/home` when authenticated, else `/login`. The Phase 1 System status page moves behind the guard (it calls `/api/v1/system/status`, now authenticated).

## Schema impact

[VERIFIED: api/db/models/identity.py, chat.py, migrations list: 0001, 0002]

| Need | Existing structure | Migration? |
|------|--------------------|-----------|
| Superuser flag (D-03) | `user.is_superuser` BOOLEAN null default false | None |
| Access token, status, language, color scheme, avatar | `user.access_token`(255, indexed), `status` char(1), `language`, `color_schema`, `avatar` LONGTEXT | None |
| Tenant default model ids (AUTH-04) | `tenant.llm_id, embd_id, asr_id, img2txt_id, rerank_id` NOT NULL (empty string is a valid value), `tts_id, ocr_id` nullable, `parser_ids` NOT NULL | None; supply values from config |
| Roles | `user_tenant.role` varchar(32) | None. Store `owner`, `admin`, `normal`, and `invite` for a pending invitation (the reference's mechanism). `invite` is not a role: every permission check must treat it as no membership; add a test |
| Invitation state (D-15) | `user_tenant.status` is a 0/1 "wasted/valid" flag; `invited_by` NOT NULL | **None needed.** Pending = `role='invite', status='1'`. Accept: `role -> 'normal'`. Decline, withdraw, remove, leave: delete the row (hard delete keeps re-invite simple; no unique key on `(user_id, tenant_id)` exists, so the service must check before insert inside a transaction) |
| API tokens | `api_token` composite PK `(tenant_id, token)`, `beta`, `dialog_id`, `source` | None |
| Default tenant models rows (AUTH-04) | `tenant_llm` unique `(tenant_id, llm_factory, llm_name)` | None; rows only if a default factory is configured |
| Rate limits, OTP | Redis | None |

If the user prefers an explicit state column over `role='invite'`, that is migration `0003` (add `user_tenant.invitation_status`); not recommended: it diverges from the reference and the generated GORM entities, for no behavioural gain. `conf/schema.json` and `internal/entity` regeneration (`make gen`) are required only if a migration is added. Peewee remains the single schema owner.

## Mail (D-05, D-06)

- **Docs check:** `docs/` is silent on SMTP and on a mail catcher; the reference has SMTP settings and `send_invite_email`/reset-code mail [CITED: ragflow internal/utility/smtp.go, api/utils/web_utils]. Record as a decision: dev-only service, never started by the default profile list used for production.
- **Image:** `axllent/mailpit:v1.31.4`, 16.8 MB, not local; pull needs user approval and about 17 MB of disk (24 GB free now). Ports: SMTP 1025, HTTP UI/API 8025 inside the compose network; publish 8025 on `127.0.0.1` only so host-side tests can read mail (neither port is in use on this host now [VERIFIED: ss]). Add it to `docker-compose-base.yml` under `profiles: [mail]` and include `--profile mail` in `make up` for development; `MP_SMTP_AUTH_ACCEPT_ANY=1` is only needed if the sender authenticates. Memory limit about 64m in the dev overlay.
- **Settings** (`docker/.env.example` and `service_conf.yaml` `mail:` section): `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`none` | `starttls` | `tls`), `SMTP_USERNAME`, `SMTP_PASSWORD` (secret), `SMTP_FROM`. Defaults for the dev stack: `mailpit`, `1025`, `none`, empty, empty, `no-reply@devrag.local`. Refuse to send credentials over `none` (the reference does the same: `SMTPInsecureAuthError`), verify certificates for `starttls`/`tls`, set dial and send timeouts (about 5 s dial, 10 s total), and set `Date`, `Message-ID`, `From`, `To`, UTF-8 `Content-Type` headers. Sanitise the recipient (reject CR/LF) against header injection.
- **Library:** Go stdlib `net/smtp` (plus `crypto/tls` for `tls`); no package. Note that `smtp.PlainAuth` refuses plaintext to non-localhost hosts by design, so with `SMTP_SECURITY=none` and empty credentials simply skip auth.
- **Where it lives:** Go owns the routes, so OTP generation, storage, mail and verification live in the Go service layer (`service/otp.go`, `service/mail.go`). The `service` package may not import gin or `net/http/httputil` and `http.Client` is banned there; `net/smtp` is fine [VERIFIED: internal/layering_test.go].
- **OTP flow keys** (all with TTL): code hash `otp:{email}` (HMAC-SHA256 over a per-code random salt and the secret; store `salt:hash`), attempts `otp_attempts:{email}`, request cooldown/count keys, verified marker `otp_verified:{email}` (5-minute TTL after a successful verify, consumed by reset). Lowercase and trim the email before keying [CITED: reference otp.go key shapes]. 6 digits via `crypto/rand`, TTL 10 minutes, 5 wrong attempts invalidate the code (delete it, D-06), single use (delete on verify success), new request overwrites. The reference uses 4 uppercase letters, 5 minutes and a captcha; D-06 overrides.
- **Reset semantics:** reset requires the verified marker (or re-presents the code), sets the new hash, rewrites `access_token` to `INVALID_<hex>` (D-08), clears the cookie, deletes the marker. If SMTP fails for a real account, respond identically to success and log the failure (D-07), but keep the stored code so a retry within the cooldown works.

## Rate limits (Claude's discretion; all numbers are new decisions)

| Limit | Value | Mechanism |
|-------|-------|-----------|
| Login failures per normalised email | 5 in 15 minutes, then 15-minute lock | Redis counter with TTL, checked before hashing |
| Login attempts per client IP | 30 in 15 minutes | Redis counter |
| OTP requests per email | 1 per 60 seconds and 5 per hour | Redis |
| OTP requests per IP | 20 per hour | Redis |
| OTP verify wrong attempts | 5 per code (D-06) | Redis |
| Registration per IP | 10 per hour | Redis |
| Response | HTTP 429, envelope code 400 (no dedicated code, R-63 maps 429 to 400), `Retry-After` header, generic message | consistent with `api/apps/errors.py` |

Counters fail closed for OTP (if Redis is unavailable the request errors) and fail open with a loud log for login throttling only if the user prefers availability; recommend fail closed for both, since Redis is a hard dependency of the stack anyway. Use `INCR` then `EXPIRE` in one pipeline/script so a crash cannot leave a counter without TTL.

## Frontend

All against the Phase 1 UI contract (`01-UI-SPEC.md`): BareLayout for login, StandardLayout for the rest, no placeholder pages, copy rules, `data-testid` hooks, state conventions (loading skeleton, error state, empty state).

- **Routes registry** (`web/src/constants/routes.ts`): `auth: "required"` is recorded but unenforced today. Enforce it in `buildRoutes` by wrapping required entries in a `RequireAuth` layout route: no token -> `<Navigate to="/login?next=...">`; token present -> run session recovery. Public: `/login`, `/forgot-password`, `*` (not found stays public).
- **Session recovery (UI-07):** on boot, if `getAuthorization()` returns a token, fetch `GET /v1/user/info` through a `use-user-info-request` hook (TanStack Query); render a skeleton until it resolves; store the user (id, nickname, email, avatar, language, tenant id, role) in the Zustand user store (today it holds only `userId`). A 401 purges and redirects.
- **401 redirect (UI-04):** `purgeSession()` in `services/http.ts` currently clears storage, store and query cache and toasts. Add a registered navigate function (same pattern as `registerQueryClient`) that routes to `/login?next=<current path>`, so there is no hard reload. The Phase 1 rule "navigate only if a `/login` route exists" is satisfied now. Keep the existing `sentToken` guard so a stale 401 cannot purge a fresh login.
- **Login/register page (UI-06):** one `/login` page with sign-in and sign-up modes (docs: "User authentication & registration page"); sign-up hidden when `GET /api/v1/system/config` reports `register_enabled=false`; after register, log in (the register response carries no token per the docs' bodies) and land on `/home`. Client validation mirrors server (email format, nickname length, password >= 8, D-02). Generic login error string from the server is displayed as returned, never augmented. Do not put the password in the URL or the query cache.
- **Forgot password (UI-08, assumed mapping for AUTH-16..18):** three steps on one route (email, code, new password), copy that never confirms an account exists.
- **Settings:** `/user-setting/profile` (nickname, avatar, language, theme, password change; avatar: accept PNG/JPEG/WebP only, check magic bytes server-side, max 256 KB after client-side downscale to 256x256, store as a data URL in `user.avatar` LONGTEXT; no object storage until Phase 3), `/user-setting/api` (UI-35: a list with masked token, copy, reveal, create, delete via AlertDialog; because D-12 keeps full tokens listable, the list endpoint returns them and the UI masks by default), `/user-setting/team` (UI-36: members table, invite form for owners only, pending invitations with withdraw, role select, remove/leave; a "Pending invitations for you" card with accept/decline for invitees).
- **Home dashboard (UI-09), empty tenant:** real data only, no "coming soon" (UI-SPEC rule): greeting, workspace name, caller role, member count, number of API tokens, pending invitations count, and links to the three real settings pages. Dataset/chat tiles do not exist until their phases register routes.
- **Theme (UI-43):** the toggle and persistence already exist (`web/src/utils/theme.ts`, `components/theme-toggle.tsx`, key `devrag.theme`). Remaining work: apply on first paint (verify no flash), and on login sync with `user.color_schema` (map `Bright`/`Dark`; add `System` is not representable, so keep localStorage authoritative and write the choice to the profile as a best effort). No new package.
- **i18n (UI-42):** i18next 23 + react-i18next 14, initialised before `createRoot` render, resources bundled as JSON under `web/src/locales/{en,zh,es,fr,ja}.json`, `fallbackLng: "en"`, language order: `user.language` after login, then `localStorage` key `devrag.lang`, then `navigator.language`. All five locale files, with a vitest key-parity test so drift fails CI. English is the source; Chinese is the documented primary locale. Translation quality for es/fr/ja is unreviewed machine drafting and should be marked as such for the user (Open Question 6). Migrate `web/src/constants/copy.ts` into `en.json` in one plan unit rather than running two string systems; the Phase 1 tests that assert exact copy keep working against the `en` resources. Store `user.language` as the codes `en|zh|es|fr|ja` (the column help text says `English|Chinese`; accept legacy labels on read and map them), default `en`.
- **Forms:** react-hook-form with `zodResolver`, zod 3 schemas colocated per form, server error mapping to a form-level alert with `role="alert"`; labels via Radix Label; every input has a visible label, `autocomplete` attributes (`username`, `current-password`, `new-password`, `one-time-code`) so password managers work.
- **Tests:** vitest unit (guard redirects, open-redirect sanitiser, key parity, schemas), vitest live project for login through the real stack, existing `wait-until` helper.

## Open Phase 1 findings

| Finding | Fix | Plan-sized unit and test |
|---------|-----|--------------------------|
| **CR-02** quadratic/cubic redaction | Replace the two backtracking regexes in `common/log_utils.py` with a linear two-stage scan: (1) `KEYSEP = (?<![\w-])(?P<key>["']?[\w-]+["']?)(?P<sep>[ \t]*[=:][ \t]*)` finds each word run followed by a separator; (2) for a key containing a sensitive word, match the value with a **bounded** pattern anchored at that position (`{0,4096}` quantifiers, escaped-quote aware `"(?:[^"\\\n]\|\\.){0,4096}"`), consuming it so later matches inside it are skipped; `cookie`/`set-cookie` values consume to end of line; (3) URL userinfo `(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s:/@]*:[^\s@/]+(?=@)`, whose `\b` start was a second quadratic scan on `a-a-a-...` runs. Also truncate untrusted fields at the log site (path to 512 chars with a `[truncated]` marker) and cap `redact_text` input (for example 64 KiB) as defence in depth. Go's `regexp` is RE2 and linear, so the Go redactor needs no algorithm change. | Unit A (first task). Tests: (a) the 12 vectors in `test/fixtures/log_redaction_vectors.json` still pass; (b) new vectors for `redis://:pw@host`, `Authorization: ApiKey x`, `Cookie: a=1; session=SECRET; x=2`, escaped quote value, token-bearing path; (c) timing bound: inputs `"a"*100000`, `"token"*20000`, `"password="*12000`, `'password="'*10000`, `"a-"*50000`, `"cookie:"*14000`, `"a://"*25000` each under 0.25 s using `time.perf_counter`, in a unit test with a generous margin (not a fixed sleep); (d) a request-level test sending an 8 KB path through the app and asserting the response time bound. |
| WR-04 partial / WR-24 | Covered by the same rewrite (empty-user URL userinfo, `ApiKey`/`Api-Key`/`Negotiate`/`AWS4-HMAC-SHA256` schemes, cookie to end of line, escaped quotes). Mirror the new vectors in `internal/common/logger_test.go` | Unit A |
| WR-16 partial | Make `clean_room.sh` and `preflight.sh` resolve `COMPOSE_PROJECT_NAME` the same way (read `docker/.env`, then environment, then default) via one shared helper | Unit B (hardening bundle) |
| WR-19 partial | `scripts/render_conf.py` rejects U+0085, U+2028, U+2029 in values (add to the existing control-character rejection) with a test; relevant because Phase 2 adds more secret values | Unit B |
| WR-25 | Route-marker tests must exercise prefix and catch-all routes: the new generated 401 enumeration (below) subsumes this; delete the `public_until_phase` markers and `EXPECTED_MARKED` set per D-19 and assert the set is empty | Unit F (route gate) |
| WR-26 | The pool idle ping has no read timeout (not reproduced): set `read_timeout`/`write_timeout` on the PyMySQL connection used for ping, test with a blackholed port | Unit B |
| WR-06 (deferred, start of Phase 2) | Single-flight cached probe layer for `/system/healthz` and `/system/status`: one in-flight probe set shared by concurrent callers and a 2 to 5 second result cache; the status route is now authenticated, healthz stays public, so the public route is the exposed one | Unit B |
| WR-10 (deferred, first Go DAO consumer) | Go schema verify compares full column definitions against `conf/schema.json` (type, length, nullability, key); first Go DAO consumers land this phase, so do it before relying on the new DAOs; update R-86 | Unit C (Go foundation) |
| WR-20 | Vite proxy query-string fix as above | with frontend foundation |
| WR-23 | Tighten `check_secrets.py` (unquoted assignments, token-named keys) before credential handling lands, keeping the test-path exemption; add tests with the new `.env.example` keys and a deliberately bad Go literal | Unit B, before any task that adds secret-bearing config |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Go | Go auth, tests | yes | 1.25.5 linux/amd64 (`go.mod` is `go 1.25.0`; CLAUDE.md says 1.26.x, the host does not have it) | none needed; `crypto/pbkdf2` exists in 1.24+ |
| uv / Python | Python tests | yes | uv 0.9.18, `.venv` Python 3.13.11 | - |
| Node / npm | SPA | yes | v22.23.3 / 10.8.2 | - |
| Docker | compose stack | yes | 29.1.3 | - |
| itsdangerous, werkzeug, quart, valkey in `.venv` | Python gate | yes | 2.2.0, 3.1.9, 0.23.1, 6.1.1 | - |
| Local images | stack | yes | `devrag-app:local` (298 MB), `mysql:8.0.40`, `valkey/valkey:8`, `pgsty/minio:RELEASE.2026-03-25T00-00-00Z`, Elasticsearch 8.11.3 | `devrag-app:local` must be rebuilt to contain new code |
| Mailpit image | D-05 mail tests | **no** (not in `docker image ls`) | v1.31.4 on Docker Hub | needs user approval to pull (~17 MB); no equivalent already local |
| Free disk | build + pull | yes | 24 GB free on `/` (87% used) | B-03 notes the host figure is unstable |
| RAM | stack | marginal | 15.7 GB total, 4.4 GB available now (9.2 GB used by other programs) | B-14: gate needs 4 GB available; close other workloads before the exit gate |
| Host port 8080 | default web port | currently not listening (the other project's `compose-gateway-1` is exited) | - | devRag keeps `SVR_WEB_HTTP_PORT=8088` in `docker/.env` (R-87) regardless; 8025 and 1025 are free |
| Running containers | - | none running; the `devrag-stack` containers are exited | - | `make up` before live tests |

**Missing dependencies with no fallback:** none blocking research; the Mailpit pull and the frontend installs need user approval at checkpoints.
**Missing with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode=auto`, `-p no:anyio`, `filterwarnings=error`) via `run_tests.py`; Go stdlib `testing` + `httptest` with build tags `integration`, `e2e`; vitest 5.0.3 (`unit` and `live` projects) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`, `web/vitest.config.ts`, `Makefile` |
| Quick run command | `uv run python run_tests.py -m unit && go test -race ./internal/... && (cd web && npm run test -- --run)` |
| Full suite command | `scripts/wait_stack.sh && uv run python run_tests.py -m "integration or e2e" && go test -tags=integration,e2e ./... && (cd web && npm run test:live)` |
| Readiness rule | `scripts/wait_stack.sh` plus the per-language `wait_until` helper; `scripts/ci/check_no_sleep.py` forbids fixed sleeps in test trees. Mail and OTP reads poll Mailpit with `wait_until`, never `sleep` |

### Success criteria to verification

| Criterion | Verified by | Command / location |
|-----------|-------------|--------------------|
| SC1 register, atomic tenant+owner link, login, land on dashboard, refresh keeps session, guard redirect | Go integration test: register against MySQL then assert exactly one `user`, `tenant`, `user_tenant(role='owner')` row, and rollback by forcing a failure on the third insert (unique-key collision or injected failing statement in a savepoint-less transaction test) leaves zero rows; browser flow in the existing SPA browser test pattern (`test/testcases/test_spa_browser.py` style) or vitest live project: register, login, assert `/home`, reload, assert still on `/home`, clear storage and visit `/user-setting/profile`, assert redirect to `/login` | `go test -tags=integration ./internal/service/...`; `npm run test:live` |
| SC2 token from Go accepted by Python; logout 401 on both; every non-public route 401 | E2E: login via Go, call a Python-owned protected route (`GET /api/v1/system/status`) with the token, 200; call a Go-owned (`/v1/user/info`) 200; logout; both return 401. Enumeration: Go test builds the engine and iterates `engine.Routes()`; Python test iterates `app.url_map.iter_rules()`; each registered (method, path) must exist in the endpoint registry and answer 401 without credentials unless the registry marks it `none`; plus every family in `routes.yaml` is probed at `path`/`prefixprobe-<uuid>` (existing `load_probes`) and must answer 401 unless `none`; plus the reverse check that nothing registered is undeclared | `uv run python run_tests.py -m e2e -t route_enumeration`, `go test -tags=e2e ./internal/e2e/...` |
| SC3 change password, OTP reset, API token CRUD, API-token-only request resolves to owner tenant | E2E with Mailpit: request OTP, poll Mailpit for the code, verify, reset, old token 401 (D-08), login with new password; wrong code 5 times invalidates; expired code (use a short TTL config in the test environment, not a sleep: set `OTP_TTL` small via config for one test and poll until the key expires with `wait_until`); unknown email gives byte-identical response and sends nothing (assert Mailpit stays empty by polling a negative condition with a bounded wait helper, not a fixed sleep); token create/list/delete; call a `api`-type route (`/api/v1/system/status` if registered `api`, otherwise the test-registered route) with only the API token and assert principal tenant id | pytest e2e + Go e2e |
| SC4 invite, accept, role change, 403 outside matrix | Integration + E2E: owner invites B; B lists tenants, sees pending, accepts (row `normal`); owner changes B to `admin`; `normal`/`admin` attempting invite or role change gets 403; owner cannot remove or demote self; B can leave; decline and withdraw paths; accept by a non-invited user is 404 | Go integration + e2e |
| SC5 cross-tenant matrix from the route table | Generated from the endpoint registry: for every endpoint with `scope != none`, create tenants A and B through the real register endpoint, build A's resource through the declared fixture, call as B with A's id, and assert the response status, `code` and `message` equal those for a nonexistent id (generated random 32-hex), then assert A's resource is unchanged. Written once as a data-driven test (`test/testcases/test_cross_tenant_matrix.py` and Go twin) that later phases extend by adding registry rows | pytest e2e; Go e2e |

### Requirement groups to verification

| Group | Verified by |
|-------|-------------|
| AUTH-01..06 | Go service unit tests (validation, hashing), integration (transaction, rollback, default model rows when configured), E2E-01 and E2E-02 through Nginx |
| AUTH-07, 08, 12 | Shared vector files on both stacks; gate unit tests per resolution order, per credential type and per bad-token class (empty, whitespace, short, `INVALID_`) |
| AUTH-09, 10, 11 | Logout rewrite test (row becomes `INVALID_<hex>`, old token 401 on both servers); cookie accepted when no Authorization header; cookie-only POST without matching Origin is 403; cookie attributes asserted (`HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` when `X-Forwarded-Proto: https`) |
| AUTH-13..15 | Go handler/service tests; response-DTO test proving no `password` or hash leakage |
| AUTH-16..18 | E2E with Mailpit (above); Redis key TTL assertions |
| AUTH-19..22 | Token CRUD tests; list contains only own tenant's tokens; delete of another tenant's token is 404 |
| AUTH-23 | Go `httptest` engine with `router.WithExtraRoutes` registering a test route under `/api/v1/searchbots/`, real middleware, real MySQL; Python test blueprint under a beta-allowed policy entry. Not verifiable on the live stack until Phase 8 builds the routes: record in BLOCKERS as "proven with a test-registered route" |
| TEN-01, 02, 04..11 | Cross-tenant matrix, membership state-machine integration tests |
| UI-02, 04, 06, 07, 08, 09, 34..36, 42, 43 | vitest unit and live projects; locale key-parity test; theme persistence test (existing) |
| SEC-01 | Route enumeration (SC2) |
| SEC-09 | Vector file: expired by one second, future, tampered, wrong secret on both stacks |
| E2E-01, 02 | Marked `e2e`, run through Nginx on `SVR_WEB_HTTP_PORT` (8088 here), real MySQL/Valkey, no mocks |
| CR-02 | Timing-bound unit test (above) plus vectors |

### Sampling Rate
- **Per task commit:** the quick run command (no stack needed)
- **Per wave merge:** bring the stack up once, run the full suite command
- **Phase gate:** `scripts/clean_room.sh` green (down -v, up, full suite) per the Phase 1 exit rule; requires about 4 GB available RAM (B-14)

### Wave 0 Gaps
- [ ] `test/fixtures/access_token_vectors.json` and `password_vectors.json` (content in sections above), loaded by Go and Python tests
- [ ] `test/fixtures/go_issued_token.json` produced by a Go test (generated artifact, checked in, regenerated by `make gen` or a documented command)
- [ ] Endpoint registry (`endpoints:` section) and the generator extension; unit test that registry owners and auth sets agree with the family entries
- [ ] Two-user and two-tenant fixtures that register through the real endpoint (`test/helpers/` for Python, `internal/testutil/` for Go)
- [ ] Mailpit service (`mail` profile) and a Python/Go helper that reads it with `wait_until`
- [ ] vitest additions: `RequireAuth` harness, locale parity test, sanitiser tests

## Security Domain

### Applicable ASVS Categories (OWASP ASVS 4.x numbering) [ASSUMED: category names from training knowledge]

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | PBKDF2-HMAC-SHA256 600k, generic errors, rate limiting, OTP with attempt cap, constant-time compares, dummy hash for unknown users |
| V3 Session Management | yes | Single stored token rewritten on logout and password change; 30-day signed wrapper; HttpOnly SameSite cookie; Origin check for cookie auth |
| V4 Access Control | yes | Default-deny gate from the route table; role table; tenant-scoped queries; non-member gets not-found |
| V5 Input Validation | yes | Server-side email, nickname, password length, body size caps (Go binding validators; Python pydantic via quart-schema), avatar type and size validation |
| V6 Cryptography | yes | stdlib `crypto/*` only; `crypto/rand`; HMAC-SHA1 is dictated by the itsdangerous format (D-09, acceptable for a MAC; recorded) |
| V7 Error handling and logging | yes | Redaction (CR-02), no secrets in paths, generic 401/login messages |
| V14 Configuration | yes | `SECRET_KEY` required, length-checked, never in Redis or repo |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential stuffing / brute force | Spoofing | Per-email and per-IP Redis limits before hashing; 429 with Retry-After |
| Account enumeration (login, reset, timing) | Information disclosure | Same message and similar latency (dummy hash), identical reset response (D-04, D-07) |
| Token forgery or tampering | Spoofing | HMAC-SHA1 over `payload.ts` with a >= 32 char secret; constant-time compare; length cap before HMAC |
| Stale token reuse after logout or reset | Elevation | Row rewrite to `INVALID_<hex>`; every request re-reads the row |
| Cross-tenant data access (IDOR) | Information disclosure, Tampering | tenant_id filter in every DAO query; 404 for non-members; generated matrix |
| Privilege escalation through API tokens | Elevation | Management routes accept `jwt` only; API tokens cannot mint tokens or change roles |
| Self-demotion or owner removal via reference-style endpoints | Tampering | State-machine checks (`role='invite'` for accept/decline; owner row immutable) |
| CSRF via cookie fallback | Tampering | SameSite=Lax, HttpOnly, Origin check on cookie-only unsafe requests |
| Header injection through email | Tampering | Reject CR/LF; use fixed templates |
| Log leakage of tokens in URLs | Information disclosure | Route-template logging; Nginx masked `log_format` |
| ReDoS in the log redactor (CR-02) | Denial of service | Linear scan with bounded quantifiers; truncate untrusted fields |
| Unauthenticated login CPU exhaustion | Denial of service | Rate limit first; hash semaphore; password length cap |
| XSS stealing the `localStorage` token | Information disclosure | Accepted trade-off of R-35 default; strict CSP is not in scope (record), React escaping, DOMPurify only when raw HTML is introduced later |
| Open redirect after login | Spoofing | `next` must be a same-origin path |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 600,000 PBKDF2-SHA256 iterations matches current OWASP guidance | Pattern 2 | Weaker or stronger than needed; value is configurable and read from the stored string |
| A2 | Go `net/smtp` is frozen but supported | Standard Stack | If removed, switch to a maintained mailer; not expected in Go 1.25 |
| A3 | ASVS category names/numbers | Security Domain | Cosmetic |
| A4 | Mailpit REST paths and `readyz` behave as documented for v1.31.4 | Code Examples | Mail E2E helpers need adjusting; swagger.json from the `develop` branch was read, not the v1.31.4 tag |
| A5 | npm packages' age, download counts and source repos | Package Legitimacy Audit | slopcheck not run; user approves installs at a checkpoint anyway |
| A6 | Nginx request-line limits for CR-02 (Phase 1 left unconfirmed) | Open Phase 1 findings | Fix is algorithmic so it does not depend on the limit |
| A7 | `role='invite'` for pending invitations is acceptable under TEN-04's "three roles" | Schema impact | Alternative is a migration adding a state column |
| A8 | es/fr/ja translations drafted without a native-speaker review | Frontend | User-facing quality only |
| A9 | `/api/v1` prefix for tenant and token routes | Route ownership | Docs and requirements write unprefixed paths; SPA fallback would swallow them |

## Open Questions

1. **Cookie session literalness (AUTH-10, AUTH-11).** What we know: `docs/16-auth/sessions.md` describes a Redis session populated only by OAuth `login_user`, and the reference's `ragflow_auth` cookie is a non-HttpOnly OAuth bootstrap cookie. What is unclear: whether the user wants a literal Redis-backed `_user_id` session. Recommendation: one HttpOnly `ragflow_auth` cookie carrying the same signed token, resolved when no Authorization header is present, no Redis session, because the literal session needs a new package (`quart-session`) and duplicate invalidation, and the documented invariant (re-check `access_token` validity and user status) is preserved. Needs user confirmation as a deviation.
2. **Route prefix and owner for tokens and tenants.** Docs conflict (see table). Recommendation: Go owns `/api/v1/system/tokens*` and `/api/v1/tenants*`. Needs a recorded decision and `routes.yaml` entries.
3. **Default model configuration at registration (AUTH-04).** No provider is configured (B-09: no API key, no Ollama models). Recommendation: a `models.default_*` config section (`DEFAULT_CHAT_MODEL` etc. plus factory and base URL, all optional); registration writes `tenant.*_id` values from it (empty strings when unset) and inserts `tenant_llm` rows only when a factory is configured. E2E-02's "default models" are then empty until Phase 3 or a configured default; confirm this is acceptable.
4. **Pending-invitation storage** (A7). Recommendation: `role='invite'`, no migration.
5. **Mailpit pull approval** and whether production compose should include any mail service (recommendation: no, SMTP settings only).
6. **Locales:** ship all five (en, zh, es, fr, ja) with key parity enforced, or only en and zh now? Recommendation: all five; the user should review es/fr/ja.
7. **Frontend package approval** for the seven packages above.
8. **`itsdangerous` direct declaration** in `pyproject.toml` (transitive today).
9. **Max password length** (128) and the avatar limit (256 KB) are new numbers; confirm.
10. **Fail-closed rate limiting** when Redis is unavailable (recommended).

## Proposed DECISIONS rows (R-88 onward; statuses are `accepted (auto, not user-reviewed)` unless the user confirms)

| ID | Decision | Fit |
|----|----------|-----|
| R-88 | Token wire format finalised: salt `itsdangerous`, django-concat SHA-1 key, HMAC-SHA1, Unix-epoch minimal big-endian timestamp, compress-if-shorter, 30-day max age, 1,024-char length cap; vectors in `test/fixtures/access_token_vectors.json`; Go test strategy is verify-Python plus round-trip because Go's zlib bytes differ (resolves R-33; extends user-confirmed D-09, D-11) | docs/apikey llm.md |
| R-89 | Password hash `pbkdf2:sha256:600000` werkzeug format, Go stdlib `crypto/pbkdf2`, Python explicit method; plain password over TLS, no RSA; 8 to 128 characters (resolves R-34) | docs silent on scheme; reference differs |
| R-90 | Auth set semantics (`none|jwt|api|beta`), default deny, exact beats prefix, 401 envelope for every failure including beta; management routes `jwt`-only; per-endpoint registry beside `routes.yaml` (resolves R-40) | SEC-01 |
| R-91 | Cookie fallback: single HttpOnly `ragflow_auth` cookie, Origin check, no Redis session (amends AUTH-10 literal text; resolves R-35 cookie part) | needs user confirmation |
| R-92 | Tokens and tenants are Go-owned under `/api/v1`; new `PATCH /api/v1/tenants/{id}/users/{user_id}` for roles; decline via `PATCH /tenants/{id}` body; withdraw/remove/leave via `DELETE` | docs conflict |
| R-93 | Invitation state is `user_tenant.role='invite'`; non-member gets 404, member lacking role gets 403 | D-13..D-16 |
| R-94 | Rate limit numbers and 429 mapping; fail closed on Redis loss; trusted-proxy handling for client IP | D-04 |
| R-95 | Dev mail catcher `axllent/mailpit:v1.31.4` under profile `mail`; SMTP settings and `net/smtp` | D-05; docs silent |
| R-96 | `SECRET_KEY` from env, >= 32 chars, not stored in Redis; `init_env.sh` append mode | SEC-09 |
| R-97 | Log redaction rewritten as a linear scan with bounded quantifiers; untrusted log fields truncated; token-bearing paths logged as route templates and masked in Nginx (CR-02, WR-04, WR-24) | SEC-04 |
| R-98 | i18n: i18next 23 + react-i18next 14, five locale files with key parity test, no language-detector package; avatar stored as data URL under 256 KB | UI-42 |
| R-99 | Public `/api/v1/system/config` gains `register_enabled`; superuser seeded by a Python startup hook, idempotent, pbkdf2 hash | D-01, D-03, API-13 |

User-confirmed rows to update: the discuss-session decisions D-01 through D-16 (chosen in person) per the CONTEXT instruction, mapped onto R-33 (D-09..D-11), R-34 (hashing is Claude's discretion, so R-89 stays auto), R-35, R-36 (D-13), and new rows for D-01..D-08, D-10, D-12, D-14..D-16 numbered after R-99 or merged into R-88..R-99 with a "(user)" note. Add every user-confirmed number to the pinned set in `scripts/ci/check_decisions.py` with a dated comment.

## Suggested plan-sized units (dependency order)

1. **A: CR-02 and redaction** (linear scan, vectors, timing test) first; nothing else depends on it but it is an unauthenticated DoS.
2. **B: Hardening bundle** WR-16, WR-19, WR-26, WR-06, WR-23, `init_env.sh` append mode, `SECRET_KEY` and config sections (`security`, `mail`, `models`, `register_enabled`).
3. **C: Contract modules and vectors** Go `common/token.go`, `common/password.go`; Python `common/security/*`; fixture files; WR-10 full schema verification; Go DAO foundation.
4. **D: Route policy** endpoint registry, generator output for both stacks, default-deny gate on Go (`handler`) and Python (`api/apps`), `routes.yaml` edits (remove D-19 markers), enumeration tests (WR-25).
5. **E: Go identity**: register (transaction), login (reuse, dummy hash, rate limit), logout, user info/setting/password, tenant info/list, cookie, system config flag.
6. **F: Tokens and tenants**: API tokens CRUD, `api` and `beta` resolution, team endpoints and permission table, cross-tenant matrix fixtures.
7. **G: OTP and mail**: Mailpit service, mail sender, OTP routes, reset, E2E with Mailpit; superuser startup hook.
8. **H: Frontend foundation**: packages (checkpoint), i18n migration, guard, session recovery, 401 redirect, login/register, Vite proxy fix.
9. **I: Frontend settings and dashboard**: profile, API keys dialog, team, forgot password, home.
10. **J: Exit**: E2E-01/02, matrix, clean-room gate, BLOCKERS and DECISIONS updates.

## Project Constraints (from CLAUDE.md)

- `docs/` wins over `spec.md`, code, RAGFlow, judgment; do not add services, databases, queues or frameworks without checking `docs/` (Mailpit is a dev-only addition recorded as a decision; no other new service).
- Stack pins: Quart 0.20 line per docs (project actually pins 0.23.1), Peewee-owned schema, Gin, GORM, go-redis, Zustand 4, TanStack Query 5, Axios, Tailwind 3, shadcn, react-hook-form + zod 3 (not 4), i18next 23 / react-i18next 14, React 18. No FastAPI/SQLAlchemy/Celery, no Ant Design, no Tailwind 4, React 19, zod 4 or Zustand 5.
- No critical placeholders; every feature verified by realistic execution; no mocked stages; tests pass at phase end; broken tests only as documented blocked dependencies.
- Production quality: typed interfaces, config/env handling, input validation, structured errors and logging, transactions, timeouts, idempotency, health checks, no giant files.
- Decisions not in `docs/` must be recorded (what, why, how it fits): see the proposed rows.
- Use the smallest reasonable production-quality choice for unspecified items.
- GSD workflow: edits only through a GSD command; this research changed only the RESEARCH file.
- No project skills exist.

## Sources

### Primary (HIGH confidence)
- Installed `itsdangerous 2.2.0` source (`signer.py`, `timed.py`, `url_safe.py`, `serializer.py`) and executed vector generation and verification in `.venv` (Python 3.13.11)
- Installed `werkzeug 3.1.9` `security.py`; executed `generate_password_hash`, `check_password_hash`
- Go 1.25.5 executed: `crypto/pbkdf2`, `compress/zlib` comparisons
- `docs/apikey llm.md`, `docs/16-auth/{tokens,authentication,sessions,permissions,roles}.md`, `docs/20-security/{secrets,authentication-security,authorization-security}.md`, `docs/04-api/{authentication-api,user-api,tenant-api,system-api,endpoint-catalog}.md`, `docs/apis.md` (1-139), `docs/21-end-to-end-flows/{login,user-registration}.md`, `docs/02-frontend/{authentication,routing}.md`
- Repo: `conf/routes.yaml`, `scripts/gen_routes.py`, `api/apps/*`, `api/db/models/*`, `api/db/migrations/*`, `internal/{router,handler,service,dao,entity,server}`, `internal/layering_test.go`, `common/{log_utils,settings}.py`, `docker/*`, `web/src/*`, `web/package.json`, `pyproject.toml`, `uv.lock`, `go.mod`, `go.sum`
- Reference repo (read-only): `internal/utility/token.go`, `internal/utility/otp.go`, `internal/service/user.go`, `internal/handler/{auth,user}.go`, `internal/router/router.go`, `api/apps/__init__.py`, `api/apps/restful_apis/{tenant_api,system_api}.py`, `api/utils/crypt.py`, `common/settings.py`
- npm registry (`npm view`) for versions, peer dependencies and postinstall scripts

### Secondary (MEDIUM confidence)
- Docker Hub API (`axllent/mailpit` tags and sizes, fetched 2026-10-07); Mailpit swagger.json on GitHub `develop` branch (paths and methods)

### Tertiary (LOW confidence)
- Web search snippet for Mailpit healthcheck and `MP_SMTP_AUTH_ACCEPT_ANY`; OWASP and ASVS figures from training knowledge (A1, A3)

## Metadata

**Confidence breakdown:**
- Token and password contracts: HIGH, reproduced by execution; Go zlib divergence also executed
- Route ownership and endpoint behaviour: MEDIUM, docs conflict resolved by recorded recommendation
- Redaction fix: HIGH for the algorithm (prototype passed all vectors and timing); the final regex must still be re-tested in the repo
- Frontend: MEDIUM, versions from registry only; no install, no slopcheck
- Mail: MEDIUM, API paths read from the upstream swagger on the development branch

**Research date:** 2026-10-07
**Valid until:** 2026-11-06 for the contracts; re-check npm and Mailpit versions at install time
