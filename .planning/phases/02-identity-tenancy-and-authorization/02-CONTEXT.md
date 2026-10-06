# Phase 2: Identity, Tenancy and Authorization - Context

**Gathered:** 2026-10-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can create an account, log in through either server, recover their session on refresh, manage their profile, password and API tokens, and work inside their own tenant with roles and invitations. No user can see or change another tenant's data, and every non-public route on both servers rejects unauthenticated requests.

Requirements: AUTH-01..23, TEN-01, TEN-02, TEN-04..11, UI-02, UI-04, UI-06..09, UI-34..36, UI-42, UI-43, SEC-01, SEC-09, E2E-01, E2E-02.

Also in this phase, before feature work (carried from Phase 1, see `01-VERIFICATION.md` and BLOCKERS B-15): fix the unauthenticated CPU denial-of-service in the Python log redactor (CR-02) and the open hardening items (WR-16 partial, WR-19 partial, WR-04 partial / WR-24, WR-25, WR-26); address the deferred findings WR-06, WR-10, WR-20, WR-23 at the points B-15 names.

Not in this phase: datasets, documents, models, chat (Phases 3+); the admin service and Go `--admin` mode (Phase 8); OAuth/SSO login; billing-style hashed API keys (Phase 8).

</domain>

<decisions>
## Implementation Decisions

Every decision below marked **(user)** was chosen by the user in the discuss session on 2026-10-07. The planner must update the matching rows in `.planning/DECISIONS.md` to `user-confirmed` and add their numbers to the pinned set in `scripts/ci/check_decisions.py` with a dated comment (as was done for R-49 and R-87).

### Sign-up and login
- **D-01 (user):** Self-registration is open by default and controlled by a config switch (RAGFlow's `REGISTER_ENABLED`); when off, `POST /api/v1/users` refuses with a clear envelope error and the SPA hides the sign-up form.
- **D-02 (user):** Password rule is minimum 8 characters, length only, no composition rule. The same rule applies at registration, password change and password reset, enforced on the server and mirrored in the SPA.
- **D-03 (user):** A first superuser is created by a one-shot init from an email and password set in `docker/.env`. If either is unset, nothing is created. No default credential ships in the repository. This delivers the superuser part of API-13 that Phase 1 left open (BLOCKERS B-08).
- **D-04 (user):** Failed login returns one generic message ("Email or password is incorrect") for both unknown email and wrong password. Repeated failures are rate-limited.

### Password reset
- **D-05 (user):** The reset code is sent by email through configurable SMTP settings. The dev compose stack includes a local mail-catcher so the whole flow is verified for real; production points at the user's SMTP server. The mail-catcher is a new dev-only service: check it against `docs/` and record it as a decision.
- **D-06 (user):** The reset code is 6 digits, expires after 10 minutes, is invalid after 5 wrong attempts, is single use, and a new request replaces the previous code. Stored in Redis.
- **D-07 (user):** A reset request for an email with no account gets the same response as a real one and sends nothing.
- **D-08 (user):** A successful password reset or password change invalidates the stored access token, signing the user out on every device.

### Sessions and tokens
- **D-09 (user):** The login token follows RAGFlow's format as documented in `docs/apikey llm.md`: a UUID access token stored on the user row, wrapped in an itsdangerous-`URLSafeTimedSerializer`-compatible payload (zlib, timestamp, HMAC-SHA1) that Go creates and Python verifies with its standard library. Not a standard JWT. Go and Python share test vectors. Resolves R-33.
- **D-10 (user):** One stored token per user, shared across devices: a second login reuses the current valid token; logout on any device rewrites it to `INVALID_<hex>` and signs out all devices.
- **D-11 (user):** The signed wrapper is rejected after 30 days, forcing a fresh login. The docs claim an expiry check without a value, so 30 days is a new recorded decision. Supports SEC-09.
- **D-12 (user):** API tokens are generated, stored and listed as documented (`ragflow-` plus 32 random bytes, URL-safe base64; beta token is a 32-character hyphen-stripped UUID). Moving to hash-plus-prefix, shown once, is deferred to the billing phase (BILL-01) to avoid doing it twice.

### Team invites and roles
- **D-13 (user):** Only the owner may invite members, following `docs/16-auth/permissions.md` over `authorization.md`. Resolves R-36.
- **D-14 (user):** Invitations target existing accounts only, by email, as the documented API implies. No sign-up-by-invite email.
- **D-15 (user):** An invited person can accept or decline; the owner can withdraw a pending invitation. Decline and withdraw are small additions to the documented accept-only flow, to be recorded as decisions.
- **D-16 (user):** The owner can remove a member and a member can leave a tenant. The owner cannot leave or be removed.

### Carried from Phase 1 (locked)
- **D-17:** Go owns register, login, password and user/tenant routes; Python verifies the same token; neither server proxies to the other (Phase 1 D-01, D-05, D-06).
- **D-18:** Envelope `{code, message, data}`; Peewee owns the schema; Go verifies only; routes come from `conf/routes.yaml`; no mocks or fixed sleeps; the web port on this host is 8088 (R-87).
- **D-19:** `/api/v1/system/status` and `/api/v1/system/version` carry `public_until_phase: 2` and must become authenticated in this phase; the marker tests then need the routes removed from the public set (R-55, R-84).

### Claude's Discretion
- Password hashing scheme and parameters, provided hashes are salted, verifiable in both Go and Python with shared test vectors, and never unsalted SHA-256 (R-34). Research must settle the exact scheme from `docs/16-auth/authentication.md` and the reference.
- Client token storage (R-35): the recorded default is a Bearer header from `localStorage`, with the documented cookie and Redis session only as the fallback path and CSRF protection if a cookie is ever used for auth.
- Rate-limit numbers for login and OTP requests, avatar handling in the profile, the mail-catcher image, i18n library wiring and which locales ship first (UI-42 lists zh, en, es, fr, ja), theme persistence, and the home dashboard content for a tenant with no data yet.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth, tokens and tenancy (authoritative)
- `docs/apikey llm.md` — token formats: Go-issued itsdangerous-compatible access token, `ragflow-` API token, beta token and its restricted endpoints, provider balance endpoint, `used_tokens` tracking. Released by the user on 2026-10-07; Phase 1 research never saw it.
- `docs/16-auth/authentication.md`, `tokens.md`, `sessions.md` — auth resolution order, token validation rules, logout, session fallback
- `docs/16-auth/authorization.md`, `permissions.md`, `roles.md`, `multi-tenancy.md` — roles, the 10-area permission matrix, tenant scoping
- `docs/03-backend/authentication.md`, `authorization.md`, `middleware.md`
- `docs/20-security/authentication-security.md`, `authorization-security.md`, `api-security.md`, `secrets.md`, `attack-surface.md`

### API surface
- `docs/04-api/authentication-api.md`, `user-api.md`, `tenant-api.md`, `system-api.md`, `endpoint-catalog.md`
- `docs/apis.md` lines 1–139 (canonical routes; the remainder is the billing material scoped to Phase 8)
- `docs/21-end-to-end-flows/user-registration.md`, `login.md` — acceptance flows E2E-01, E2E-02
- `docs/22-code-tracing/frontend-to-backend.md`

### Frontend
- `docs/02-frontend/authentication.md`, `pages.md`, `routing.md`, `state-management.md`, `api-client.md`, `components.md`
- `.planning/phases/01-reconciliation-guardrails-and-dual-stack-foundation/01-UI-SPEC.md` — design tokens, layouts, state conventions, copy rules that Phase 2 screens inherit

### Project records
- `.planning/DECISIONS.md` — R-33, R-34, R-35, R-36, R-40 (open, resolved here), R-20, R-49, R-55, R-83, R-84, R-85, R-86, R-87
- `.planning/BLOCKERS.md` — B-07, B-08, B-15
- `.planning/phases/01-reconciliation-guardrails-and-dual-stack-foundation/01-VERIFICATION.md` and `01-REVIEW.md` — CR-02 and the open hardening items to fix first
- `docs/spec.md`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `./CLAUDE.md`

### Reference implementation (read-only, lower priority than docs)
- `/home/logan78/desktop x/ragflow` — `internal/utility/token.go`, `internal/service/api_token.go`, `internal/handler/auth.go`, `api/apps/__init__.py`, `api/db/services/user_service.py`, `web/src/pages/login`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/db/models/` — 38 Peewee models including `user`, `tenant`, `user_tenant`, `api_token`; generated GORM entities in `internal/entity/`
- `api/db/database.py` — pooled, retrying database, `transaction()`, `DatabaseLock`
- `api/apps/` — Quart factory, envelope, error mapping, validation, request log middleware; `internal/router`, `internal/handler`, `internal/service`, `internal/dao` — Gin layering with the same envelope
- `conf/routes.yaml` + `scripts/gen_routes.py` — single route list with `auth` and `public_until_phase` markers; Nginx and Vite proxy generated from it
- `web/src/services/http.ts` — Axios client with same-origin token injection, envelope unwrap, 401 purge of the token actually sent; `web/src/routes`, three layouts, `EmptyState`, `ErrorState`, `PageHeader`, sonner toasts, user store
- Test harnesses: `run_tests.py`, Go build-tag tiers, vitest unit and live projects, `scripts/clean_room.sh` exit gate

### Established Patterns
- Tests are written first and the pre-fix failure is recorded; shared cross-language vector files live under `test/fixtures/`
- Every route is declared in `conf/routes.yaml` before it is implemented; ownership and auth-marker tests enforce it
- Decisions go to `.planning/DECISIONS.md` with a truthful status; unbuildable items go to `.planning/BLOCKERS.md`

### Integration Points
- Auth middleware on both servers replaces the Phase 1 public markers; the route-enumeration 401 test and the cross-tenant test matrix are generated from the route table and extended by every later phase
- The dev compose stack gains a mail-catcher service; `docker/.env.example` gains SMTP, superuser and registration-switch variables

</code_context>

<specifics>
## Specific Ideas

- The user wants RAGFlow's token format as documented rather than a modernised one: wire compatibility with RAGFlow clients over a newer signature primitive.
- Account-enumeration resistance is a consistent choice: generic login error and identical reset response for unknown emails.
- No default credential anywhere: the superuser exists only if the user sets its email and password.

</specifics>

<deferred>
## Deferred Ideas

- Hash-plus-prefix API keys shown once — billing phase (BILL-01, Phase 8)
- Inviting people who have no account yet by email
- Independent per-device sessions with separate logout
- OAuth / SSO login and the Go `--admin` service — Phase 8
- Password composition rules beyond length

</deferred>

---

*Phase: 2-Identity, Tenancy and Authorization*
*Context gathered: 2026-10-07*
