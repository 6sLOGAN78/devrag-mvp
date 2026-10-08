# BLOCKERS

Convention (D-27): anything that cannot be implemented or verified in this environment is recorded here. It is never faked, stubbed or silently skipped.

Each entry has: ID `B-NN`, Title, Status (`open` | `mitigated` | `closed`), Affects (requirement IDs or phase), Evidence, Needed from user, Workaround in repo.

## B-01 `docs/apikey llm.md` unreviewed and uncommitted
- Status: closed
- Affects: R-49, Phase 3+ (LLM layer)
- Evidence: file is off-limits to agents and may contain credential material; it is neither read nor relied on.
- Needed from user: review the file and say which parts, if any, are requirements.
- Workaround in repo: listed in `.gitignore`; `docs/` is never staged wholesale.
- Closed 2026-10-07: the user reviewed the file, confirmed it holds no credentials and released it for reading and publishing. A scan of all 228 files under `docs/` found no key-shaped strings other than truncated illustrative examples in `docs/apis.md`. `docs/` is now tracked and pushed. Follow-up for planning (not a blocker): the file's token-format and usage-tracking content was not available to Phase 1 research; see R-49.

## B-02 `vm.max_map_count` is 65530
- Status: open
- Affects: DEPLOY (Elasticsearch), Phase 1 preflight
- Evidence: Elasticsearch wants 262144; changing it needs sudo, which agents do not use. Single-node ES started at 65530 with a WARN.
- Needed from user: `sudo sysctl -w vm.max_map_count=262144` if desired.
- Workaround in repo: preflight fails by default; `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` records an override.
- Update 2026-10-06 (plan 01-15): still 65530. The phase-exit gate ran with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` on all three runs (recorded in `ragflow-logs/preflight-overrides.log`); Elasticsearch reached healthy each time.
- Update 2026-10-08 (plan 02-26): still 65530 (measured). The Phase 2 exit gate ran with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` on all three runs; the override was recorded each time in `ragflow-logs/preflight-overrides.log`; Elasticsearch reached healthy each time (35, 37 and 44 s).

## B-03 Disk space
- Status: open
- Affects: phase-exit gate (plan 01-15), Phase 3+ downloads
- Evidence: 4.2 GB free on / as measured at revision time (an earlier estimate of 5.5 GB was wrong). After .venv, node_modules, Go module cache and the image build only about 1.5 to 2 GB is expected to remain. The three clean-room runs in plan 01-15 MAY REQUIRE THE USER TO FREE DISK, and Phase 3+ model and ONNX downloads will not fit.
- Needed from user: freeing disk is the user's action; no plan frees it.
- Workaround in repo: `PREFLIGHT_ALLOW_LOW_DISK=1` is a recorded override. Nothing is pruned or deleted automatically.
- Update 2026-10-06 (plan 01-15): free space on / changed several times during the phase for reasons outside this project (4.2 GB, then about 23 GB, then 4.6 GB, then about 9 GB). Measured 9 GB free before the gate and 9G after each of the three clean-room runs; the disk override was NOT used. This project accounts for roughly 1.5 GB of working files plus about 1.7 GB of Docker images. Still open: free space on this host is not stable, and Phase 3+ model downloads need headroom that is not guaranteed.

## B-04 No GPU
- Status: open
- Affects: DEPLOY-06
- Evidence: host has no NVIDIA GPU; the `gpu` compose profile cannot be verified.
- Needed from user: a GPU host for verification.
- Workaround in repo: profile authored but unverified.

## B-05 Earlier compose projects present
- Status: mitigated
- Affects: Phase 1 deployment
- Evidence: stopped compose project `devrag` and project `docker` volumes from earlier attempts exist.
- Needed from user: decide whether to remove them; they are not ours to delete.
- Workaround in repo: do not remove; the new project name is `devrag-stack`.
- Update 2026-10-06 (plan 01-15): after three `down -v` cycles of `devrag-stack`, the 16 non-`devrag-stack` containers and 13 non-`devrag-stack` volumes matched a snapshot taken before the gate (diff empty); project `devrag` still has 6 containers.

## B-06 CI workflow not runnable here
- Status: closed
- Affects: TEST (CI)
- Evidence: no git remote, so `.github/workflows/ci.yml` cannot execute.
- Needed from user: push to a remote with Actions enabled.
- Workaround in repo: workflow authored; it calls the same `make ci` target that runs locally.
- Update 2026-10-07 (plan 01-23): `ci.yml` now sets up Go from `go.mod`, Node 22 and runs `npm ci`, with `contents: read` permissions. It has still never run on GitHub; status stays open.
- Closed 2026-10-07: pushed to `6sLOGAN78/devrag-mvp` (user asked for `master` to be replaced; old history kept at branch `archive/mvp-master`, commit `3fe760d`). Workflow run 37517324018 on commit `184e262` passed (job `guardrails`, 1m52s). Follow-up, not blocking: the pinned action versions target the deprecated Node 20 runtime, and `ubuntu-latest` changes to Ubuntu 26 from 2026-10-19.

## B-07 Go run modes
- Status: open
- Affects: API-12, Phase 8 and v2
- Evidence: `--admin` (Phase 8), `--ingestor` and `--syncer` (v2 mirrors per D-01) are not built.
- Needed from user: none unless scope changes.
- Workaround in repo: these modes refuse with non-zero exit naming this entry. API-12 complete with blocker.

## B-08 Python boot items
- Status: open
- Affects: API-13 (plugin load, background daemons)
- Evidence: the superuser init part is delivered by plan 02-19 (2026-10-07): `ensure_superuser` startup hook, idempotent and race-safe seed, one transaction for user, tenant and owner row, pbkdf2 hash, nothing created unless SUPERUSER_EMAIL and SUPERUSER_PASSWORD are both set. Observed live: 9 integration tests on MySQL, and the cross-stack e2e (seeded superuser logs in through Go, token accepted by Python). Still absent: plugin load (Phase 7) and background daemons (Phase 4).
- Needed from user: none.
- Workaround in repo: boot logger, DB verify (no DDL), the superuser hook, hooks and serve are real and tested in order. The two missing items are deliberately not stubbed: `register_startup_hook` is the extension point for them. API-13 complete with blocker.

## B-09 Real model source for Phase 3+
- Status: open
- Affects: R-50, D-31, Core Value verification
- Evidence: no API key is configured; host `ollama` binary exists with no models pulled.
- Needed from user: an OpenAI-compatible key, or approval to pull one small chat and one small embedding model.
- Workaround in repo: Ollama service in compose with one small chat and one small embedding model unless a key is supplied.

## B-10 TLS only verified with a self-signed certificate
- Status: open
- Affects: DEPLOY-12 (Phase 8)
- Evidence: no real certificate or domain available.
- Needed from user: real certificate for production.
- Workaround in repo: self-signed certificate under ignored `docker/nginx/certs/`.

## B-11 `cgo` Go test tier is a mechanism proof only
- Status: open
- Affects: TEST-04
- Evidence: no native parsers exist yet to exercise cgo.
- Needed from user: none.
- Workaround in repo: tier runs a minimal cgo proof; real coverage lands with native parsers.

## B-12 MySQL 8.4 LTS upgrade needs approval
- Status: open
- Affects: R-42, D-17
- Evidence: `mysql:8.0.40` has had no security patches since 2026-04-30; docs pin it.
- Needed from user: approval to move to `mysql:8.4`, after which auth-plugin behaviour with PyMySQL and go-sql-driver must be verified.
- Workaround in repo: image is parameterised as `MYSQL_IMAGE`, default is the docs pin.

## B-13 numpy-whitelist gadget regression test skipped (numpy not installed)
- Status: open
- Affects: SEC-05 (R-38), plan 01-03
- Evidence: `test/unit_test/test_unpickle.py::test_numpy_allow_list_unpickler_is_bypassable` skips because numpy is not in the user-approved Phase 1 package set, so the gadget demonstration has never run here. The gate and production-tree tests do run.
- Needed from user: none; the test activates once numpy is installed by a later plan (DeepDoc).
- Workaround in repo: `check_pickle.py` rejects all unpickling in production trees regardless.

## B-14 Phase-exit gate needs 4 GB of available RAM
- Status: open
- Affects: `scripts/clean_room.sh` / `scripts/preflight.sh` on this host
- Evidence: 2026-10-06, with the stack stopped only 2763 MB was available (other programs held about 10.7 GB of 15.7 GB) against `PREFLIGHT_MIN_RAM_MB=4096`. The user freed memory; the gate then ran with 5.2 to 6.9 GB available. The threshold was not lowered.
- Needed from user: close other workloads before running the gate on this machine.
- Workaround in repo: none applied; `PREFLIGHT_MIN_RAM_MB` exists but was left at its default.
- Update 2026-10-07 (plan 01-24): gap-closure gate ran with 6513 to 7246 MB available before start (stack stopped); threshold unchanged at 4096 MB; no user action was needed this time.

## B-15 Deferred Phase 1 review findings
- Status: mitigated
- Affects: Phase 2 planning (health probes, Go schema verification, dev proxy, secret scanning)
- Evidence: `01-REVIEW.md` findings not fixed by gap plans 01-16..01-24. Every other warning (WR-01..05, WR-07..09, WR-11..19, WR-21, WR-22) and CR-01 was fixed and covered by tests.

| Finding | Reason deferred | Lands |
|---|---|---|
| WR-06 health routes open four fresh backend connections per request | Needs a single-flight cached probe layer on the application pool; no Phase 1 must-have fails | Closed by plan 02-02 (single-flight cached probes, pool read/write timeouts); confirmed by the plan 02-26 gate (dependency-outage tests in the e2e serial tier passed in all three runs) |
| WR-10 Go schema verify compares type families only | Needs a full comparison against `conf/schema.json`; the claim is narrowed by R-86 meanwhile | Closed by plan 02-07 (full column, primary-key and index comparison; a live scratch-database test detects three same-family drifts and the real schema verifies clean, 38 tables); `--migrate` verification is also exercised by the Go integration tier of the plan 02-26 gate |
| WR-20 Vite dev proxy misses Go exact paths that carry a query string | Dev server only; no Phase 1 Go exact route is called with a query string; production Nginx is correct | Fixed by plan 02-27 (exact keys are now `^escaped-path(\?.*)?$`, built in `web/src/lib/vite-proxy.ts`; `web/src/vite-proxy.test.ts` covers every generated exact route and failed 13 of 16 on the old keys). Not re-verified against a running dev server (none started), so the closure rests on the unit test only. The generated route JSON is unchanged, so the drift gate is unaffected. Closed by plan 02-26 on that evidence |
| WR-23 `check_secrets` blind spots | Tightening needs false-positive triage across env examples and fixtures; no real secret is committed | Closed by plan 02-02 (unquoted, Go `:=` and token-named secrets now detected); `check_secrets` is part of `make ci` and passed 7/7 after the plan 02-26 gate |
| IN-01..IN-18 | Informational; out of scope for gap closure | Rolling backlog |

Also this phase: WR-16, WR-19, WR-26 (plan 02-02) and CR-02, WR-04, WR-24 (plan 02-01) are closed by their plans; WR-25 is subsumed by plans 02-10 and 02-14 (default-deny gate and route enumeration). CR-02, WR-04, WR-16, WR-19, WR-24, WR-25 and WR-26 are recorded closed by plan 02-26 against the evidence in those SUMMARY files and the green gate.

- Update 2026-10-08 (plan 02-26): WR-06, WR-10, WR-20 and WR-23 are closed (rows above); every WR finding and both CR findings of `01-REVIEW.md` are now closed. Only the informational items IN-01..IN-18 remain, as a rolling backlog with no owner action.
- Needed from user: nothing.
- Workaround in repo: none.

## B-16 Host port 8080 taken by another project
- Status: mitigated
- Affects: dev stack and exit gate on this host
- Evidence: 2026-10-07, container `compose-gateway-1` (compose project `compose`, not ours, untouched) published 8080; preflight failed on the port before any teardown.
- Needed from user: none; the user chose to move devRag to another port.
- Workaround in repo: `SVR_WEB_HTTP_PORT=8088` in the git-ignored `docker/.env` (R-87); `clean_room.sh` now derives `E2E_BASE_URL`, `MANUAL_BASE_URL` and `LIVE_BASE_URL` from that value.

## B-17 Per-IP rate limits are effectively global behind Docker's port proxy
- Status: open
- Affects: AUTH-01, AUTH-05, AUTH-16 (registration, login and OTP rate limits), production deployment
- Evidence: found in plan 02-09 (2026-10-07). Go takes the client address from `X-Real-IP`, which Nginx sets to `$remote_addr` and Go trusts only from a loopback peer (R-114). With the app container's port published through Docker, Nginx sees the Docker gateway address for every external client, so all clients share one per-IP bucket: the per-IP limits (registration 10/hour, login 30 per 15 min, OTP 20/hour by default) apply to everyone combined, and one abusive client can exhaust them for all. Per-email limits are unaffected. A second observation from the same plan: the per-email login lock also rejects the correct password until the window ends.
- Needed from user: a decision on how the real client address reaches the container in production (for example host networking, a trusted upstream proxy with `real_ip_header` and a configured trusted range, or accepting global limits and sizing them accordingly), and whether the correct password should bypass the per-email lock.
- Workaround in repo: none. Limits are configurable (R-112); the dev stack raises the per-IP values so the test suites can run.
- Backend review addition (WR-02, 2026-10-08, behaviour NOT changed, still waiting for the user): the per-account failure lock (5 failures per 15 minutes, R-94) answers 429 even for the correct password, so anyone who knows an email can keep that person locked out of login with five wrong guesses per window from a single IP (the same holds for the password change, key `pwchange:user:<id>`). Since fix CR-01 the lock is keyed on the account, so no spelling of the address escapes or multiplies it. Options for the user: (a) keep it (simple, strongest against password guessing, but a targeted denial of service); (b) block on (account, client IP) and keep a much higher account-only threshold that only raises an alert or a challenge, which needs a working per-IP signal and therefore the B-17 answer first, because behind the Docker proxy every client shares one IP and (b) degrades to (a); (c) progressive delay instead of a hard refusal; (d) let the correct password through while the lock is on (stops the lockout, but every guess then still has to be checked, so the lock no longer limits guessing speed). Recommendation: decide B-17's client-address question first, then choose (b); until then (a) stays and the dev numbers are unchanged. A related residual of the same kind: five wrong codes destroy a victim's current reset code (D-06), a recovery denial of service; a per-IP limiter on the verify step would bound it and needs the same per-IP signal.

## B-18 Interface languages es, fr and ja are not shipped (UI-42)
- Status: open
- Affects: UI-42 (partly delivered; left unticked in REQUIREMENTS.md)
- Evidence: Phase 2 ships en and zh with a test that both locale files hold the same keys (plans 02-11, 02-27; R-98, D-23). Spanish, French and Japanese are deferred because nobody here can review them.
- Needed from user: reviewers or an approved source for es, fr and ja copy; then a planner adds a locale file per language (the parity test already covers any language listed).
- Workaround in repo: the language switch offers en and zh only; an unsupported browser language falls back to en.

## B-19 Beta token proven on a test-registered route only (AUTH-23)
- Status: open
- Affects: AUTH-23 (recorded complete with blocker), Phase 8 (bot, search-bot and MCP routes)
- Evidence: the beta credential is resolved by both gates per route policy and tested on routes registered by the tests (Go `httptest` and live through Nginx under `/api/v1/searchbots/`; Python test blueprint). The real handlers do not exist yet.
- Needed from user: none. The Phase 8 planner must add a live check of the beta token on each real route.
- Workaround in repo: none needed; the middleware is not stubbed, only its consumers are absent.

## B-20 Manual-only verifications (real SMTP delivery, Chinese text review)
- Status: open
- Affects: AUTH-16..18 (real SMTP), UI-42 (zh copy), `02-VALIDATION.md` Manual-Only table
- Evidence: the reset flow is proven end to end against the local mail catcher (Mailpit) over SMTP, three times in the gate. No real SMTP account exists here. The Chinese strings in `web/src/locales/zh.json` were written by the agent and have not been read by a Chinese reader.
- Needed from user: (1) set the SMTP variables in `docker/.env` to a real server, request a reset for your own address and confirm the email arrives; (2) read the Chinese interface (login, profile, API tokens, team, forgot password) and correct `zh.json`.
- Workaround in repo: none; both items stay open until a person does them.

## B-21 API tokens are stored in plaintext (BILL-01)
- Status: open
- Affects: AUTH-19..22 storage, BILL-01 (Phase 8, hash-plus-prefix API keys)
- Evidence: the documented `api_token` table holds the token itself and the gate looks it up by exact match (D-12, plan 02-20, T-02-97 accepted). The token page masks values and the logs never carry them (plan 02-25), but a database read exposes every live token.
- Needed from user: none now; Phase 8 BILL-01 replaces storage with a hash plus a visible prefix.
- Workaround in repo: exact BINARY matching, owner-only management, per-tenant cap and a creation rate limit.

## B-22 Tenant filtering and permission enforcement cover only the routes that exist (TEN-01, TEN-05)
- Status: open
- Affects: TEN-01, TEN-05 (left unticked), Phases 3, 7 and 8
- Evidence: the only tenant-owned routes in Phase 2 are API tokens and memberships. The cross-tenant matrix (plan 02-25) covers all 8 implemented tenant-scoped registry rows with no exclusion of a row, and a new tenant-scoped row without a fixture fails the test. The permission table lists 10 areas but only team administration has routes to enforce; the other nine are enforced as their routes land.
- Needed from user: none. Each later plan that adds a tenant-owned route must add its matrix fixture and enforce its permission area, and the phase verifier should tick TEN-01 and TEN-05 only after the last such route (datasets and documents in Phase 3, agents in Phase 7, bots and MCP in Phase 8). If you prefer, tell the planner to move the two requirements to the phase that owns the final route.
- Workaround in repo: matrix guard test and the generated permission table with its oracle test.

## B-23 A 405 on a known path logs the raw path
- Status: open
- Affects: SEC-01 hygiene, log secrecy (R-127)
- Evidence: Quart and Gin have no route template for a request whose method does not match, so the access log records the raw path. Only the token family and token-shaped values are masked on that path; any future route with a secret in its path would be logged raw on a wrong-method call.
- Needed from user: none. Later phases must not put secrets in path segments, or must extend the masking rule with a test.
- Workaround in repo: Nginx, Go and Python mask the token family and token-shaped segments on every spelling.

## B-24 Old log files may hold raw token paths
- Status: open
- Affects: local log hygiene, `ragflow-logs/` (git-ignored)
- Evidence: before the plan 02-25 fixes, Nginx, Go and Python logged the raw path of `DELETE /api/v1/system/tokens/<token>`, and the matrix tests wrote real (test) tokens into it. `ragflow-logs/ragflow_go.log` and `ragflow-logs/ragflow_server.log` were not rewritten and may still hold such lines; Nginx writes to the container's stdout, which `down -v` discards at the start of each gate run.
- Needed from user: delete or rotate the old files under `ragflow-logs/` if the machine is shared; they are not committed. The tokens were created by tests on throwaway accounts.
- Workaround in repo: none (no agent deletes user files).

## B-25 Leftover test accounts
- Status: mitigated
- Affects: local database content, dev stack
- Evidence: plans 02-16, 02-19, 02-21 and 02-25 recorded `webauth-`, `webprofile-`, `http-`, `status-` and `user-` rows left in MySQL by live suites (the web helper `registerLiveAccount` does not clean up its `http-` and `status-` accounts). The Phase 2 gate runs `down -v` at the start of every run, so those older rows are gone from the dev database. The last gate run (run 3) ended without removing volumes, so a few rows from that run may exist; the stack is stopped and they were not inspected.
- Needed from user: none; the next `scripts/clean_room.sh` or `down -v` removes them. A later plan should make the live helper delete its accounts.
- Workaround in repo: test emails use the reserved `@example.test` domain.

## B-26 `npm audit` findings are untouched
- Status: open
- Affects: `web/` dependency tree (D-20 package set and the Tailwind v3 pin)
- Evidence: `npm audit` on 2026-10-08 reports 8 findings (5 high, 3 moderate, 0 critical): tailwindcss and tailwindcss-animate (direct) and braces, chokidar, fast-glob, micromatch, postcss-nested, postcss-selector-parser (transitive). npm reports no fix available for tailwindcss, tailwindcss-animate, braces, chokidar, micromatch and postcss-selector-parser, and Tailwind is pinned to v3 by the project stack. Nothing was upgraded or overridden in Phase 2.
- Needed from user: a decision on whether to accept the risk for build-time tooling, or approve a Tailwind or package override in a later phase.
- Workaround in repo: none.

## B-27 Local stack secrets appeared in a session transcript (plan 02-19)
- Status: open
- Affects: local development secrets only
- Evidence: during plan 02-19 a subagent printed the contents of the git-ignored `conf/service_conf.yaml` (rendered from `docker/.env`: database, cache, object-storage and signing secrets) into its session output. Nothing was committed and no file was written; the values are for the local dev stack only.
- Needed from user: if that transcript is kept or shared, rotate the secrets by regenerating `docker/.env` (`scripts/init_env.sh --force`, which replaces every generated secret) and rebuilding the stack with `down -v`, which also discards the local data and every local session.
- Workaround in repo: none; `check_secrets` guards committed files only.

## B-28 Python auth lookup threads are bounded but not cancelled on a database stall (WR-07 residual)
- Status: open (low)
- Affects: Python engine under a MySQL stall
- Evidence: fixed by R-133 (dedicated 16-thread pool, reproduced and tested offline). Not load-tested against a real stalled MySQL: a lookup that has started keeps its worker thread until the driver's 30 s read timeout, so for that window at most 16 authenticated requests are in the database at once and later ones time out at 5 s with the fail-closed 503. The read timeout was not lowered because the same pooled connections serve other queries.
- Needed from user: none. A later phase that adds a per-statement `MAX_EXECUTION_TIME` or a separate short-timeout pool for auth can lift the limit; revisit with real load figures.
- Workaround in repo: R-133.

## B-29 Review items deferred after the Phase 2 backend review (IN-03, IN-04, IN-06, IN-09 parts)
- Status: open (info)
- Affects: deployment and hardening, no Phase 2 requirement
- Evidence: see the Fix status table in 02-REVIEW-backend.md. IN-03 (registration and invites reveal whether an email exists) is already accepted in R-107. IN-04 (HTTPS redirect drops the port, no HSTS) needs a configured public URL and a TLS deployment decision. IN-06 (SMTP defaults point at the dev sidecar and `none` security is allowed for non-loopback relays) needs an operator-facing production profile. IN-09 leftovers: the PBKDF2 slot wait has no context (HashPassword and VerifyPassword have no ctx parameter and many callers), `scripts/clean_room.sh` exports MYSQL_ROOT_PASSWORD to every step (pinned by R-128 and its guard test), and the reset verify step has no per-IP limiter (needs the B-17 per-IP signal).
- Needed from user: B-17 answer for the per-IP items; a production deployment profile for IN-04 and IN-06.
- Workaround in repo: none needed for the Phase 2 gate.


## B-30 Review items deferred after the Phase 2 frontend review (IN-F01, IN-F02, IN-F10, IN-F13 parts)
- Status: open (info)
- Affects: SPA hardening, no Phase 2 requirement
- Evidence: see the Fix status table in 02-REVIEW-frontend.md. IN-F01: `DELETE /api/v1/system/tokens/{token}` puts a live API token in the URL path; `docs/04-api/system-api.md` mandates it and R-127 and R-131 mask it in server logs, so the residual exposure is browser devtools and any intermediary or future client telemetry that records full URLs. IN-F02: the access token lives in `localStorage` as `docs/02-frontend/api-client.md` requires, and `web/index.html` ships no Content-Security-Policy, so an XSS would exfiltrate the session; no XSS sink exists today. The copied API token also stays on the clipboard. IN-F10: `web/tsconfig.json` adds Node types to the whole `src` tree; splitting them into a tooling tsconfig touches the `tsc -b` build graph and was left alone. IN-F13 (part): the hidden avatar file input is not `aria-hidden` because an existing test asserts it has an accessible name, and `aria-hidden` removes the name; the language and colour fields mirrored into the user store are kept because tests assert them.
- Needed from user: a decision on a strict CSP at the Nginx layer (script-src self, no inline scripts beyond the hashed theme bootstrap) in a hardening phase; whether the avatar-input test may be changed to match an `aria-hidden` input.
- Workaround in repo: no `dangerouslySetInnerHTML`, no raw HTML rendering, strict avatar data-URL regex; client telemetry that records URLs must not be added without redacting `/system/tokens/`.
