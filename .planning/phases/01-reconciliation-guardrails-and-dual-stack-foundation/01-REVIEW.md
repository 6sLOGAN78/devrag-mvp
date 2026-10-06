---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
reviewed: 2026-10-06T19:01:14Z
depth: standard
review_type: re-review
diff_base: f81af84
files_reviewed: 44
files_reviewed_list:
  - .github/workflows/ci.yml
  - Dockerfile
  - api/apps/errors.py
  - api/db/database.py
  - api/db/migrations/runner.py
  - api/ragflow_server.py
  - common/log_utils.py
  - conf/routes.yaml
  - docker/.env.example
  - docker/docker-compose.yml
  - docker/entrypoint.sh
  - docker/healthcheck.sh
  - docker/prepare_runtime.sh
  - internal/common/logger.go
  - internal/common/logger_test.go
  - internal/router/router_test.go
  - internal/server/config.go
  - internal/server/config_redaction_test.go
  - run_tests.py
  - scripts/ci/check_decisions.py
  - scripts/clean_room.sh
  - scripts/preflight.sh
  - scripts/render_conf.py
  - scripts/wait_stack.sh
  - test/fixtures/log_redaction_vectors.json
  - test/integration/test_boot.py
  - test/integration/test_db_core.py
  - test/integration/test_migration_runner.py
  - test/testcases/_routes.py
  - test/testcases/test_dependency_outage.py
  - test/testcases/test_route_ownership.py
  - test/unit_test/test_ci_workflow.py
  - test/unit_test/test_clean_room_guard.py
  - test/unit_test/test_container_scripts.py
  - test/unit_test/test_db_pool.py
  - test/unit_test/test_error_status_mapping.py
  - test/unit_test/test_log_redaction.py
  - test/unit_test/test_preflight.py
  - test/unit_test/test_render_conf.py
  - test/unit_test/test_route_auth_markers.py
  - test/unit_test/test_run_tests.py
  - test/unit_test/test_startup_hooks.py
  - web/src/services/http.test.ts
  - web/src/services/http.ts
findings:
  critical: 1
  warning: 6
  info: 3
  total: 10
previous_findings_fixed: 17
previous_findings_open: 3
deferred_carried: 22
status: issues_found
---

# Phase 1: Code Review Report (re-review after gap closure 01-16..01-24)

**Reviewed:** 2026-10-06T19:01:14Z
**Depth:** standard
**Files Reviewed:** 44 (changed since `f81af84`)
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

This replaces the review of 2026-10-06T14:05:56Z. Scope is the 44 files changed since `f81af84`. Source files were read in full; new test files were read as their complete added content, and modified test files as their changed lines. `api/apps/middleware.py`, `conf/service_conf.yaml.template`, `docker/entrypoint_init.sh`, `test/helpers/wait.py` and the installed `playhouse/pool.py` / `peewee.py` were read as called code. `docs/apikey llm.md` was not opened. No Docker command was run, no server was started and no source file was changed.

Executed offline:

- `pytest -m unit test/unit_test`: 281 passed, 1 skipped.
- `go test ./internal/common/... ./internal/router/... ./internal/server/...`: all ok.
- `vitest run src/services/http.test.ts`: 24 passed.
- `scripts/ci/check_decisions.py`: OK on the repo (87 rows); a scratch copy with R-86 changed to `user-confirmed` was rejected (`R-86: must not be user-confirmed`).
- Scratchpad probes for redaction (Python and a copy of the Go expressions), `_is_read_only`, `render_conf.render`, request latency through the Quart test client, and `clean_room.sh` + `preflight.sh` copied into a throwaway checkout with a fake `docker` binary.

Result for the 20 findings that gap closure targeted: **17 fixed, 3 partially fixed, 0 not fixed**.

New: **1 blocker, 3 warnings, 3 info**. The blocker (CR-02) is not a regression: the defect existed at `f81af84` and was missed by the first review.

Not verified here: anything needing the live stack (integration/e2e tests, real MySQL pool behaviour, TLS mode, Nginx request-line limits), the GitHub workflow (B-06), and Go's YAML parser behaviour for the WR-19 residual.

## Status of previous findings

| ID | Status | Evidence |
|---|---|---|
| CR-01 | FIXED | `api/db/database.py:66-74`: the driver override lives in `_PyMySQLDatabase`, below `PooledDatabase` in the MRO; `RetryingPooledMySQLDatabase` has no `_connect` override, so `PooledDatabase._connect` (heap checkout, cap, stale check, `_in_use`) wraps the driver call. `_is_closed` (`:83-89`) pings with `reconnect=False`, so a dead idle connection is discarded, not revived. `test_db_pool.py:108-143` proves one physical connection over five cycles and `MaxConnectionsExceeded` at the cap. Live-MySQL equivalents exist in `test_db_core.py` (not run here). See WR-26 for a side effect of the ping. |
| WR-01 | FIXED | `database.py:97-114`: failed reconnects are caught inside `_reconnect`, increment the same `attempt`, and raise once `attempt >= max_retries`. Budget is bounded (delays 1, 2, 4, 8, 16 s at defaults); `test_db_pool.py:146-166` asserts both the recover and the exhaust path. |
| WR-02 | FIXED | `database.py:134`: a statement is retried only when `transaction_depth() == 0` and `_is_read_only(sql)`. `begin()` (`:139-148`) is retried, which is safe to replay. Writes propagate (`test_db_pool.py:187-195`). `WITH ...`, `(SELECT ...)`, `SET`, `CALL` are not classified read-only (conservative). Edge cases of first-keyword classification are in IN-19. |
| WR-03 | FIXED | `internal/common/logger.go:26`: optional quotes around the key and an optional `Bearer/Basic/Digest/Token` scheme in the value. Shared vectors in `test/fixtures/log_redaction_vectors.json` pass in both engines. Schemes outside that list still leak: WR-24. |
| WR-04 | PARTIAL | Fixed: `api[_-]?key`, `passwd`, `pwd` (`log_utils.py:14-15`, `logger.go:19,26`); list/tuple recursion (`log_utils.py:47-50`); Go non-primitive fields go through `redactComplex`/`redactAny` and an unserialisable value becomes `***unserialisable***`, never raw (`logger.go:57-120, 142-163`); `json:"-"` on both passwords (`config.go:23,32`). Open: the URL-userinfo rule requires a non-empty user, so `redis://:hunter2@redis:6379/0` is unchanged in both engines, and a password containing `@` keeps its tail (`amqp://user:p@ss@host/` becomes `user:***@ss@host/`). Confirmed by execution. See WR-04 below. |
| WR-05 | FIXED | `conf/routes.yaml:15-20` marks `/api/v1/system/version` with `public_until_phase: 2` and a note; R-84 records it. `test_route_auth_markers.py:17-40` pins the marked set. The accompanying "unmarked auth route must not answer 200" tests only bite for exact entries: WR-25. |
| WR-07 | FIXED | `api/ragflow_server.py:75-82`: hooks run in `before_serving`, on the serving loop. `test_startup_hooks.py` shows a task created by a hook is still alive while the app serves. |
| WR-08 | FIXED | `api/apps/errors.py:54-55`: unmapped 4xx gives `BAD_REQUEST`, 5xx gives `SERVER_ERROR`; 413 and 429 have explicit messages. |
| WR-09 | FIXED | `api/db/migrations/runner.py:100-110, 128`: version read/write run under `db.bind_ctx([SystemSettings])` for the passed database. `:57-69`: a same-column index with different uniqueness raises `MigrationError`. |
| WR-11 | FIXED | `docker/prepare_runtime.sh:15-16`: `mkdir -p` then a non-recursive `chown` of `LOG_DIR` only. Called from `entrypoint.sh:14` before the privilege drop (`setpriv`, `:16`, unchanged). No broad or recursive chown exists. Note: files already in the directory under a different UID are not re-owned (IN-21). |
| WR-12 | FIXED | `prepare_runtime.sh:18-24`: `NGINX_TLS=1` without both `server.crt` and `server.key` exits 1 before Nginx starts; `entrypoint.sh` runs under `set -e`, so the container stops. No HTTP fallback path remains. |
| WR-13 | FIXED | `docker/healthcheck.sh:22-28` probes Go and Python directly and requires 200; a 301 from port 80 is accepted only in TLS mode and only after both backends passed. `scripts/wait_stack.sh:34-42` uses the HTTPS port with `-k` in TLS mode. TLS mode itself was not run. |
| WR-14 | FIXED | `docker/docker-compose.yml:26` pins `GO_API_PORT: "9384"`; removed from `.env.example`. |
| WR-15 | FIXED | `scripts/clean_room.sh:23-35`: missing value, empty, `0`, `abc`, `-1`, `1.5` exit 2 before any Docker call (`test_clean_room_guard.py:96-101`). |
| WR-16 | PARTIAL | `clean_room.sh:64` runs a strict project guard before `stop`, and `preflight.sh:59-60` fails on a foreign working-dir label. The guard can check a different project name than the one that is torn down (confirmed by simulation). See WR-16 below. |
| WR-17 | FIXED | `run_tests.py:63-67`: exit 5 is a failure except in the serial second pass of `-p` or with `--allow-empty`. |
| WR-18 | FIXED (structure only) | `.github/workflows/ci.yml:10-28`: `contents: read`, `setup-go` from `go.mod`, Node 22, `npm ci` in `web/`. Never executed (B-06). |
| WR-19 | PARTIAL | `scripts/render_conf.py:53-60`: single quotes doubled in quoted positions, ASCII control characters rejected, quotes rejected in unquoted positions; output is validated and written through a 0600 `O_EXCL` temp file and `os.replace` (`:97-113`). Unicode line breaks are not rejected and still inject keys (confirmed). See WR-19 below. |
| WR-21 | FIXED | `web/src/services/http.ts:83-86, 144, 171`: purge only when the failing request carried a token and it still equals the stored one; otherwise the server message is shown. |
| WR-22 | FIXED | `http.ts:73-80, 121-130`: the header is attached only when `new URL(url, new URL(baseURL, origin)).origin` equals the page origin. Protocol-relative URLs, absolute URLs to other hosts, a foreign `baseURL`, backslash forms and userinfo forms (`https://localhost@evil.test/`) all resolve to a foreign origin under the same WHATWG parser the browser uses for the request, so no bypass was found. A parse failure returns `false`. |

Other requested checks:

- **`check_decisions.py`**: `CONFIRMED = {3, 17, 18, 48, 87}` (`:13`). Any other row marked `user-confirmed` still fails (`:63-64`), confirmed by execution. The hard-coded required range 53-73 is unchanged (deferred IN-18).
- **`test_dependency_outage.py:63-64`**: the new `wait_until(..., timeout=60)` raises `TimeoutError` on expiry and the original `assert service_health("app") == "healthy"` is kept. The assertion is not weakened; it only stops racing Docker's 10 s probe interval.
- **`clean_room.sh` base URLs** (`:40-44`): derived from `SVR_WEB_HTTP_PORT` in `docker/.env`, caller values win, paths quoted. The value is not validated (IN-21).

## Critical Issues

### CR-02: Log redaction regex is quadratic and runs on the unauthenticated request path, blocking the Python event loop

**Classification:** BLOCKER
**File:** `common/log_utils.py:20-24` (pattern), `common/log_utils.py:59-65, 98-101` (filter on every handler), `api/apps/middleware.py:30` (access log passes `request.path`)
**Issue:** `_PATTERN` starts with `["']?(?:[\w-]*(?:password|...)[\w-]*)`. On a run of word characters that contains no key, the regex engine scans to the end of the run from every start position, which is O(n^2). `redact_value` applies it to every string `extra`, and the access log emits `request.path` as an `extra` for every request, including 404s. `RedactingFilter` is attached per handler, so with stdout plus the log file the cost is paid twice, synchronously, inside `after_request` on the event loop.

Measured here:

| Input | Time |
|---|---|
| `redact_text("a" * 5000)` | 0.65 s |
| `redact_text("a" * 20000)` | 11.6 s |
| `redact_text("a" * 40000)` | 46.9 s |
| `GET /api/v1/` + 4000 x `a` through the Quart test client (two handlers) | 0.82 s wall, 404 |
| same with 8000 x `a` | 3.41 s wall, 404 |

The same shape existed at `f81af84` (1.54 s per pass at 8000 characters), so this is a pre-existing defect, not a regression. The Go redactor uses RE2 and is linear (40000 characters in 10 ms).

**Failure scenario:** an unauthenticated client sends `GET /api/v1/aaaa...` with a path just under Nginx's default 8 KB request-line limit. Each request holds the single Python event loop for about 3 s. A few requests per second make every Python-owned route unresponsive, `healthz` exceeds the 4 s healthcheck limit and the app container turns unhealthy. Any later log line containing a long hex or base64url string has the same effect. Whether a path of that length passes the Nginx and Hypercorn limits in the live stack was not tested.
**Fix:** drop the unbounded prefix (text before the keyword is outside the match and is kept anyway) and bound the suffix and the URL scheme. Checked in the scratchpad: all 12 shared vectors still pass, `redis://:pw@host` is also redacted, and 40000-character adversarial inputs take under 35 ms.
```python
_URL_USERINFO = re.compile(r"(?P<head>\b[a-z][a-z0-9+.-]{0,31}://[^\s:/@]*:)[^\s@/]+(?=@)", re.IGNORECASE)
_PATTERN = re.compile(
    rf"""(?P<key>(?:{_KEY_ALT})[\w-]{{0,64}}["']?)(?P<sep>\s*[=:]\s*)"""
    rf"""(?P<val>{_SCHEME}"[^"]*"|{_SCHEME}'[^']*'|{_SCHEME}[^\s,;&}}]+)""",
    re.IGNORECASE,
)
```
Also redact once (one filter on the logger, or mark the record as already redacted), truncate `path` in the access log, and add a timing regression test with a long word-character run.

## Warnings

### WR-04 (carried, partial): URL userinfo with an empty user or `@` in the password is not redacted

**Classification:** WARNING
**File:** `common/log_utils.py:17`; `internal/common/logger.go:29`
**Issue:** both expressions require `[^\s:/@]+` before the colon. `redis://:hunter2@redis:6379/0`, the usual Redis/Valkey URL form, passes through unchanged in both engines. For `amqp://user:p@ss@host/` only `p` is masked and `ss` remains.
**Fix:** allow an empty user (`[^\s:/@]*:`) and match the password up to the last `@` before the host (`[^\s/]+(?=@)` with a greedy match). Add both cases to `test/fixtures/log_redaction_vectors.json`.

### WR-16 (carried, partial): the project guard can check a different project than the one `down -v` removes

**Classification:** WARNING (data loss in another checkout's dev stack)
**File:** `scripts/clean_room.sh:11, 45, 64, 69`; `scripts/preflight.sh:22, 44-50`
**Issue:**
1. `clean_room.sh` takes `PROJECT` from the shell variable only, defaulting to `devrag-stack`. `preflight.sh` takes it from the shell variable, **then from `docker/.env`**. `clean_room.sh` does not pass its `PROJECT` to the guard. With `COMPOSE_PROJECT_NAME=myfork` in `docker/.env` and the shell variable unset, the guard inspects `myfork` while `stop` and `down -v` run with `-p devrag-stack`. Editing `docker/.env` is what the guard's own message suggests ("choose another COMPOSE_PROJECT_NAME"). Confirmed with a fake `docker` in a scratch checkout: the guard queried `label=com.docker.compose.project=myfork`, printed `preflight project check passed`, and the script then issued `compose -p devrag-stack ... stop` and `compose -p devrag-stack ... down -v` although the fake reported the `devrag-stack` containers as belonging to `/some/other/checkout/docker`.
2. The guard fails open: `docker info ... || return 0` (`:44`) and a failing `docker ps` (count 0, `:46-50`) both report OK in strict mode.
3. Only containers are inspected. If the other checkout ran `down` without `-v`, its `devrag-stack_*` volumes have no containers, the guard prints "no containers", and `down -v` deletes them.
**Fix:**
```bash
# clean_room.sh
step project-guard env PREFLIGHT_STRICT_PROJECT=1 COMPOSE_PROJECT_NAME="$PROJECT" scripts/preflight.sh --project-only
```
In strict mode make `check_project` fail when `docker info` or `docker ps` fails. Before `down -v`, refuse when volumes labelled `com.docker.compose.project=$PROJECT` exist while no container of this checkout does (or record ownership in a marker file under the repo). Add a unit test with `COMPOSE_PROJECT_NAME` set only in `docker/.env`.

### WR-19 (carried, partial): Unicode line breaks still inject YAML keys and silently alter secrets

**Classification:** WARNING
**File:** `scripts/render_conf.py:43-44, 53-60`
**Issue:** `_has_control_char` rejects only code points below 32 and 127. YAML also treats U+0085, U+2028 and U+2029 as line breaks. Confirmed with the real template: `MYSQL_PORT="3306\u2028  password: injected"` renders, passes the post-render `yaml.safe_load` check, and loads with `mysql.password == "injected"`. In a quoted position `MYSQL_PASSWORD="a\x85b"` loads as `"a b"`, so the stored secret differs from the supplied one with no error. Unquoted positions also accept ` #` (silent truncation) and `{a: 1}` (a mapping where an integer is expected). Go's YAML parser was not tested.
**Fix:**
```python
_LINE_BREAKS = {"\x85", "\u2028", "\u2029"}
def _has_control_char(value: str) -> bool:
    return any((ord(ch) < 32 and ch != "\t") or ord(ch) == 127 or ch in _LINE_BREAKS for ch in value)
```
and allow only `[A-Za-z0-9._-]+` in unquoted positions (every unquoted slot in the template is an integer).

### WR-24: Redaction leaks credentials for unlisted auth schemes, later cookies and escaped quotes (both engines)

**Classification:** WARNING
**File:** `common/log_utils.py:19-24`; `internal/common/logger.go:26`
**Issue:** confirmed by execution in Python and with a copy of the Go expressions:
- Only `Bearer|Basic|Digest|Token` are recognised. `Authorization: ApiKey <base64>` (the Elasticsearch scheme, and ES is the default engine) becomes `Authorization: *** <base64>`; the scheme word is masked and the credential is kept. Same for `Negotiate` and `AWS4-HMAC-SHA256 Credential=..., Signature=...`.
- `Cookie: theme=dark; sid=SECRET` becomes `Cookie: ***; sid=SECRET`; every cookie after the first survives.
- `{"password": "hun\"ter2tail"}` becomes `"***"ter2tail"}`: the value stops at the escaped quote.
- `X-Amz-Signature` / `X-Amz-Credential` in presigned MinIO URLs are not keys the pattern knows.
**Fix:** for `authorization`, `proxy-authorization`, `cookie` and `set-cookie` keys, mask to the end of the line instead of one token; make the quoted alternatives escape-aware (`"(?:[^"\\]|\\.)*"`); add `signature|credential` to the key list. Add these cases to the shared vector file.

### WR-25: The "unmarked auth route must not be public" tests do not cover prefix or catch-all routes

**Classification:** WARNING
**File:** `internal/router/router_test.go:264-284`; `test/testcases/test_route_ownership.py:38-45`; `test/unit_test/test_route_auth_markers.py:65-74`; `test/testcases/_routes.py:30-33`
**Issue:** R-84 states that tests fail if any other `auth != none` route answers 200 unauthenticated. That holds only for exact entries:
- the Go test skips every entry whose `match` is not `exact`;
- the Python and ingress tests probe prefix entries at a synthetic path (`<prefix>probe-<uuid>`), which is a 404 regardless of what is registered under the prefix;
- only `GET` is sent and only status 200 counts (201, 204, 206 pass).
**Failure scenario:** Phase 2 registers `GET /v1/user/info` in Go or `GET /api/v1/datasets` in Python without the auth middleware. Both sit under prefix entries declared `auth: jwt`. All three tests stay green.
**Fix:** enumerate registered routes (`engine.Routes()` in Go, `app.url_map.iter_rules()` in Quart), map each to its `routes.yaml` entry by longest match, call each registered method without a token, and fail on any 2xx unless the entry carries `public_until_phase`.

### WR-26: Idle-connection ping runs under the pool lock with no read timeout (introduced by the CR-01 fix)

**Classification:** WARNING (not reproduced against a live server)
**File:** `api/db/database.py:83-89, 151-166`
**Issue:** `PooledDatabase._connect` is `@locked` and calls `_is_closed` for each idle connection. The new `_is_closed` sends `COM_PING` and waits for the reply. `init_database` sets `connect_timeout=5` but no `read_timeout`/`write_timeout`, and PyMySQL uses a blocking socket after connect.
**Failure scenario:** MySQL becomes unreachable without closing the socket (paused container, dropped route). The first checkout blocks in `ping` until the kernel gives up on the connection, which can take minutes, while holding `_pool_lock`. Every other thread that needs a connection waits on the same lock, so the bounded retry budget never comes into play.
**Fix:** pass `read_timeout` and `write_timeout` in `init_database` (for example 30 s, configurable), and add a unit test whose fake `ping` blocks to show checkout fails within the timeout.

## Info

### IN-19: `_is_read_only` classifies by first keyword only

**Classification:** WARNING-tier not reached; informational
**File:** `api/db/database.py:49-56`
**Issue:** confirmed returns of `True` for statements that are not safe to replay or are session-dependent: `/*!50000 INSERT INTO t */ SELECT 1 FROM dual` (MySQL executable comment is stripped as noise), `SELECT 1 INTO OUTFILE ...`, `SELECT 1; DELETE FROM t` (only if `MULTI_STATEMENTS` is enabled; it is not by default), `SELECT GET_LOCK(...)`, `EXPLAIN ANALYZE DELETE ...` (whether MySQL 8.0 executes the DML was not verified). A replayed `SELECT LAST_INSERT_ID()` / `SELECT @var` runs on a new session and returns different data without error. Peewee emits none of these today.
**Fix:** do not strip `/*!` comments, reject statements containing `;` outside the final position, `INTO OUTFILE/DUMPFILE/@`, and `EXPLAIN ANALYZE`; document that session-state reads are not retry-safe.

### IN-20: Small behaviour notes on the fixes

**File:** `web/src/services/http.ts:83-86`; `internal/common/logger.go:83-97`; `run_tests.py:33-34, 63`
**Issue:** (a) a login attempt made while a stale token is still stored sends that token (same origin), so a wrong-password 401 purges and shows "session expired" rather than the credential error. (b) `redactAny` round-trips reflected values through JSON without `UseNumber`, so 64-bit integers above 2^53 inside `zap.Reflect`/`zap.Any` structs are logged with lost precision. (c) `run_tests.py -p -m "<expr selecting only serial tests>"` now always fails, because the first pass (`... and not serial`) collects nothing.
**Fix:** (a) let auth endpoints opt out with a per-request flag; (b) decode with `json.Decoder.UseNumber()`; (c) fail only when both passes return 5.

### IN-21: Script hardening notes

**File:** `scripts/clean_room.sh:40-44`; `docker/prepare_runtime.sh:16`; `docker/healthcheck.sh:24-25`
**Issue:** `WEB_PORT` is taken verbatim from `docker/.env` (quotes, trailing spaces or an inline comment produce a malformed base URL; this fails closed). The log-directory `chown` is deliberately non-recursive, so log files left by an earlier run under a different `APP_UID` stay unwritable and the servers exit. In TLS mode the healthcheck does not probe the 443 listener.
**Fix:** validate `WEB_PORT` against `^[0-9]+$`; chown existing `*.log` files in `LOG_DIR` (files only, no recursion); add a `curl -k https://127.0.0.1:443/` probe in TLS mode.

## Deferred (carried)

Recorded in `.planning/BLOCKERS.md` B-15; not re-reviewed as new and not counted in the open totals.

| ID | Title | Note |
|---|---|---|
| WR-06 | Public Python health routes open four fresh backend connections per request | Lands start of Phase 2 |
| WR-10 | Go schema verification compares type families only | Claim narrowed by R-86 |
| WR-20 | Vite dev proxy routes Go exact paths with a query string to Python | Dev server only |
| WR-23 | `check_secrets.py` misses unquoted assignments and token-named keys | Lands start of Phase 2 |
| IN-01 | `init.sql` hard-codes the database name | |
| IN-02 | Go and Python listen on `0.0.0.0` inside the app container | Relevant to CR-02: port 9380 is reachable from other containers without Nginx limits |
| IN-03 | Administrative accounts for MinIO and Elasticsearch | |
| IN-04 | Valkey `allkeys-lru` with queue and lock keys | |
| IN-05 | Passwords in process arguments of healthchecks | |
| IN-06 | Dead or unused items | `GO_API_PORT` removed from `.env.example`; the rest unchanged |
| IN-07 | Config errors escape as tracebacks; Go/Python accept different values | |
| IN-08 | Go dependency versions differ from the baseline without a DECISIONS row | |
| IN-09 | `dao.OpenDB` details | |
| IN-10 | `BaseModel` timestamps maintained only by `save()` | |
| IN-11 | CORS notes | |
| IN-12 | Nginx notes | |
| IN-13 | Preflight port list does not match published ports | `scripts/preflight.sh:23` unchanged |
| IN-14 | Frontend notes | |
| IN-15 | Version checks are permissive | |
| IN-16 | Image and init-container hardening | The `render_conf.py` part is fixed (0600 from creation); digests and root init job remain |
| IN-17 | `DatabaseLock` edge cases | `database.py:238-239` unchanged |
| IN-18 | Gate coverage notes | `check_decisions.py:40` still requires only R-53..R-73 |

---

_Reviewed: 2026-10-06T19:01:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
