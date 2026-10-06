---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
reviewed: 2026-10-06T14:05:56Z
depth: standard
files_reviewed: 156
files_reviewed_list:
  - .dockerignore
  - .github/workflows/ci.yml
  - .gitignore
  - .python-version
  - Dockerfile
  - Makefile
  - api/__init__.py
  - api/apps/__init__.py
  - api/apps/errors.py
  - api/apps/middleware.py
  - api/apps/restful_apis/__init__.py
  - api/apps/restful_apis/system_api.py
  - api/db/__init__.py
  - api/db/database.py
  - api/db/db_models.py
  - api/db/init_db.py
  - api/db/migrations/0001_system_settings.py
  - api/db/migrations/0002_baseline_schema.py
  - api/db/migrations/__init__.py
  - api/db/migrations/runner.py
  - api/db/models/__init__.py
  - api/db/models/base.py
  - api/db/models/canvas.py
  - api/db/models/chat.py
  - api/db/models/files.py
  - api/db/models/identity.py
  - api/db/models/integrations.py
  - api/db/models/knowledge.py
  - api/db/models/llm.py
  - api/db/models/system.py
  - api/db/services/__init__.py
  - api/db/services/system_service.py
  - api/ragflow_server.py
  - api/utils/__init__.py
  - api/utils/api_utils.py
  - api/utils/validation.py
  - cmd/log.go
  - cmd/migrate.go
  - cmd/modes.go
  - cmd/ragflow_server.go
  - common/__init__.py
  - common/bootstrap/__init__.py
  - common/bootstrap/ensure_bucket.py
  - common/constants.py
  - common/health/__init__.py
  - common/health/probes.py
  - common/log_utils.py
  - common/settings.py
  - conf/routes.yaml
  - conf/service_conf.yaml.template
  - docker/.env.example
  - docker/docker-compose-base.yml
  - docker/docker-compose.dev.yml
  - docker/docker-compose.tls.yml
  - docker/docker-compose.yml
  - docker/entrypoint.sh
  - docker/entrypoint_init.sh
  - docker/healthcheck.sh
  - docker/init.sql
  - docker/nginx/nginx.conf
  - docker/nginx/proxy.conf
  - docker/nginx/ragflow.conf
  - docker/nginx/ragflow.https.conf
  - go.mod
  - internal/common/constants.go
  - internal/common/error_code.go
  - internal/common/logger.go
  - internal/common/response.go
  - internal/dao/db.go
  - internal/dao/redis.go
  - internal/dao/settings.go
  - internal/dao/transaction.go
  - internal/dao/verify.go
  - internal/handler/system.go
  - internal/router/middleware.go
  - internal/router/router.go
  - internal/server/config.go
  - internal/service/system.go
  - internal/testutil/cgo_probe.go
  - internal/testutil/scratch.go
  - internal/testutil/wait.go
  - pyproject.toml
  - run_tests.py
  - scripts/ci/__init__.py
  - scripts/ci/_walk.py
  - scripts/ci/check_decisions.py
  - scripts/ci/check_generated.py
  - scripts/ci/check_go_toolchain.sh
  - scripts/ci/check_no_sleep.py
  - scripts/ci/check_pickle.py
  - scripts/ci/check_placeholders.py
  - scripts/ci/check_secrets.py
  - scripts/ci/run_all.py
  - scripts/clean_room.sh
  - scripts/export_schema.py
  - scripts/gen_go_entities.py
  - scripts/gen_routes.py
  - scripts/gen_selfsigned.sh
  - scripts/init_env.sh
  - scripts/preflight.sh
  - scripts/record_memory.py
  - scripts/render_conf.py
  - scripts/wait_stack.sh
  - web/components.json
  - web/index.html
  - web/package.json
  - web/postcss.config.js
  - web/scripts/check-chunks.mjs
  - web/src/app.tsx
  - web/src/components/app-sidebar.tsx
  - web/src/components/empty-state.tsx
  - web/src/components/error-state.tsx
  - web/src/components/page-header.tsx
  - web/src/components/route-skeleton.tsx
  - web/src/components/skip-link.tsx
  - web/src/components/theme-toggle.tsx
  - web/src/components/ui/badge.tsx
  - web/src/components/ui/button.tsx
  - web/src/components/ui/card.tsx
  - web/src/components/ui/dropdown-menu.tsx
  - web/src/components/ui/separator.tsx
  - web/src/components/ui/sheet.tsx
  - web/src/components/ui/skeleton.tsx
  - web/src/components/ui/sonner.tsx
  - web/src/components/ui/tooltip.tsx
  - web/src/constants/api-paths.ts
  - web/src/constants/copy.ts
  - web/src/constants/retcode.ts
  - web/src/constants/routes.ts
  - web/src/hooks/use-system-status-request.ts
  - web/src/index.css
  - web/src/interfaces/envelope.ts
  - web/src/interfaces/health.ts
  - web/src/layouts/bare-layout.tsx
  - web/src/layouts/full-bleed-layout.tsx
  - web/src/layouts/standard-layout.tsx
  - web/src/lib/utils.ts
  - web/src/lib/with-lazy-route.tsx
  - web/src/main.tsx
  - web/src/pages/not-found/index.tsx
  - web/src/pages/route-error/index.tsx
  - web/src/pages/system-status/index.tsx
  - web/src/routes.tsx
  - web/src/services/http.ts
  - web/src/services/notify.ts
  - web/src/services/system-service.ts
  - web/src/stores/user-store.ts
  - web/src/test/setup.ts
  - web/src/test/wait-until.ts
  - web/src/utils/authorization.ts
  - web/src/utils/theme.ts
  - web/tailwind.config.ts
  - web/tsconfig.json
  - web/tsconfig.node.json
  - web/vite.config.ts
  - web/vitest.config.ts
findings:
  critical: 1
  warning: 23
  info: 18
  total: 42
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-06T14:05:56Z
**Depth:** standard
**Files Reviewed:** 156
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

All 156 listed files were read. No Docker command was run, no server was started and no source file was changed. Two things were executed locally, both offline: a probe script in the session scratchpad that drives `RetryingPooledMySQLDatabase` with a fake `pymysql.connect` and exercises the redaction regexes, and a two-line bash check of the `for run in $(seq ...)` behaviour. `docs/apikey llm.md` was not opened. Recorded decisions (R-xx) and BLOCKERS entries were not re-reported unless the recorded behaviour is unsafe (WR-02 is the one such case).

Assessment by focus area:

- **Database pool / retry / lock:** one blocker. The retrying pool does not pool (CR-01, confirmed by execution). The retry loop also abandons on the first failed reconnect (WR-01) and can double-apply standalone writes (WR-02). `DatabaseLock` itself is sound: dedicated connection, parameterised `GET_LOCK`, release checked.
- **SQL / command injection:** none found. Python SQL is parameterised; `db_default` rejects quotes and backslashes; Go uses bound parameters; test-only DDL goes through an identifier whitelist; all subprocess calls are list-form.
- **Secrets and log redaction:** no hard-coded secrets found. The Go redactor fails on bearer tokens and JSON-quoted keys (WR-03, confirmed), and both redactors have structural gaps (WR-04).
- **Envelope consistency:** key set, order, 404/405/500/503 bodies and `X-API-Source` agree between Go and Python. One Python-side class mismatch (WR-08).
- **CORS:** allow-list only, `*` rejected at config time on both sides, no credentials header. Minor notes only (IN-11).
- **Nginx routing / SSE:** Go exact and prefix locations versus Python catch-alls match `conf/routes.yaml`; proxy settings are SSE-safe (buffering off, HTTP/1.1, 3600 s timeouts, gzip excludes `text/event-stream`). Defects are in TLS mode and port wiring (WR-12, WR-13, WR-14).
- **`clean_room.sh` Docker guard:** the guard holds. `-p "$PROJECT"` is always explicit, the name is checked before Docker is invoked, the only destructive call is `down -v` on that project, no prune/rmi exists, and paths are quoted for the space in the repo path. Two weaknesses around it: a zero-run false pass (WR-15) and a same-name project from another checkout (WR-16).
- **Dockerfile / entrypoint:** no secrets baked into the image; `.dockerignore` excludes env files, keys and `docs/`. Log-directory ownership and TLS fail-open are defects (WR-11, WR-12).
- **Frontend HTTP client:** token is read only through `utils/authorization.ts`; the 401 purge clears token, store and query cache. The purge is unconditional and the header is attached to any destination (WR-21, WR-22).

## Critical Issues

### CR-01: `RetryingPooledMySQLDatabase._connect` overrides the pool checkout, so nothing is pooled, closed or capped

**File:** `api/db/database.py:57-59`
**Issue:** The MRO is `RetryingPooledMySQLDatabase -> PooledMySQLDatabase -> PooledDatabase -> MySQLDatabase`. `PooledDatabase._connect` is the method that takes a connection from the idle heap, enforces `max_connections`, applies `stale_timeout` and registers the connection in `_in_use`. The subclass overrides `_connect` and calls `pymysql.connect` directly without `super()`, so that logic never runs. On `close()`, `PooledDatabase._close` finds the key absent from `_in_use` and does nothing: the connection is neither returned to the pool nor closed.

Confirmed by execution with a fake driver (`max_connections=1`): three `connect()`/`close()` cycles created three connections, `close()` was never called on any of them, the idle pool stayed empty, and a second concurrent `connect()` from another thread succeeded instead of raising `MaxConnectionsExceeded`.

**Failure scenario:** every `connection_context()` opens a new TCP + auth handshake and drops the socket without `COM_QUIT` (it is only reclaimed by `__del__`). `mysql.max_connections` and `mysql.stale_timeout` in `service_conf.yaml` are inert. Under concurrent load in later phases the process can open connections without bound until MySQL returns "Too many connections" (the dev override caps the server at 200). DATA-03 ("pooled") is not delivered.
**Fix:** keep the `database=` keyword fix but place it below `PooledDatabase` in the MRO so the pool still wraps it:
```python
class _PyMySQLDatabase(peewee.MySQLDatabase):
    def _connect(self) -> Any:
        # peewee passes the deprecated ``db=`` keyword; PyMySQL 1.2 warns about it.
        return pymysql.connect(database=self.database, autocommit=True, **self.connect_params)


class RetryingPooledMySQLDatabase(PooledDatabase, _PyMySQLDatabase):
    ...  # no _connect override here
```
Add a unit test that asserts one physical connection across N connect/close cycles and `MaxConnectionsExceeded` at the cap.

## Warnings

### WR-01: Retry loop gives up on the first failed reconnect

**File:** `api/db/database.py:67-73, 85-108`
**Issue:** `_backoff` calls `self.connect(reuse_if_open=True)` from inside the `except` block of `execute_sql`/`begin`. If that reconnect fails (MySQL still restarting: error 2003), the exception propagates straight out. 2003 is also not in `LOST_CONNECTION_CODES`. `max_retries=5` with exponential backoff is therefore only reachable when the server is already back after the first 1 s sleep.
**Failure scenario:** MySQL restarts for 5 s. A statement fails with 2013, sleeps 1 s, reconnect raises `OperationalError(2003)`, and the request fails after one attempt despite a nominal 31 s retry budget.
**Fix:** catch connect failures inside the loop and count them as attempts:
```python
def _backoff(...):
    ...
    time.sleep(delay)
    try:
        self.connect(reuse_if_open=True)
    except (peewee.OperationalError, peewee.InterfaceError) as exc:
        logger.warning("reconnect failed: %s", exc)  # next loop iteration fails fast and retries
```
and treat 2002/2003 as retryable when `was_open` is false because of a prior backoff.

### WR-02: Standalone writes are retried after "lost connection during query" and can be applied twice

**File:** `api/db/database.py:85-96`
**Issue:** R-74 records that standalone statements are retried. With `autocommit=True`, error 2013 can arrive after the server has executed and committed the statement. The retry then re-executes it. This is the unsafe part of a recorded decision.
**Failure scenario:** `UPDATE tenant_llm SET used_tokens = used_tokens + N` is committed, the reply is lost, the retry adds N again. For an `INSERT` with a client-generated primary key the retry raises `IntegrityError` for a row that was in fact written, so the caller reports failure for a successful write.
**Fix:** retry only when the failure is known to precede execution (2006 on send, or a failed ping before sending), or restrict automatic retry to `SELECT`; let writes propagate and be retried by idempotent callers.

### WR-03: Go redactor leaks bearer tokens and misses JSON-quoted keys

**File:** `internal/common/logger.go:19, 33-35`
**Issue:** `fragmentPattern` takes the value as `[^\s,;&]+`, which stops at the space after an auth scheme, and requires `=`/`:` immediately after the key, which a closing quote prevents. Checked with the same expression: `Authorization: Bearer eyJ...` becomes `Authorization=*** eyJ...` (token intact); `{"password":"hunter2"}` and `{"access_token": "abc123"}` are unchanged. The Python redactor handles both, so the two engines diverge.
**Failure scenario:** Phase 2 logs an upstream error string or a request dump containing an `Authorization` header or a JSON body; the token or password reaches `ragflow_go.log` and stdout.
**Fix:**
```go
var fragmentPattern = regexp.MustCompile(`(?i)(["']?[\w-]*(?:password|passwd|pwd|secret|api[_-]?key|token|authorization|cookie)[\w-]*["']?)(\s*[=:]\s*)((?:(?:Bearer|Basic|Digest|Token)\s+)?(?:"[^"]*"|'[^']*'|[^\s,;&}]+))`)
// replace with "${1}${2}***"
```
Add shared Go/Python redaction test vectors, as already done for RetCode.

### WR-04: Redaction coverage gaps in both engines (structured fields, key list)

**File:** `common/log_utils.py:14-22, 40-47`; `internal/common/logger.go:17, 57-76`; `internal/server/config.go:20-34`
**Issue:**
1. The key list has `api_key`/`apikey` but not `api-key`, so `x-api-key: sk-123` passes through unredacted in both engines (confirmed for Python by execution). `pwd=` and `passwd:` are also not matched, and URL userinfo (`mysql://app:hunter2@mysql:3306/db`) is not redacted (confirmed).
2. Python `redact_value` recurses into dicts but not lists or tuples: `extra={"items": [{"password": "hunter2"}]}` is emitted verbatim (confirmed).
3. Go `redactFields` only rewrites `StringType` and `ErrorType` fields. `zap.Any`, `zap.Reflect`, `zap.Stringer`, `zap.Strings` and `zap.ByteString` bypass redaction. `MySQLConfig.Password` and `RedisConfig.Password` have no `json:"-"` tag, so `zap.Any("cfg", cfg)` would serialise both passwords.
**Fix:** extend the key alternation (`api[_-]?key`, `passwd`, `pwd`), add a `://user:pass@` rule, recurse into lists/tuples in `redact_value`, tag the Go password fields `json:"-"`, and in `redactFields` render non-primitive field types through a redacting encoder (or reject them) instead of passing them through.

### WR-05: `/api/v1/system/version` is declared `auth: jwt` but served without authentication

**File:** `conf/routes.yaml:15`; `internal/router/router.go:43`
**Issue:** The route table marks the version route `jwt` with no `public_until_phase`. The Go router registers it with no auth middleware, and nothing in `api/`, `internal/`, `cmd/` or `web/src` reads the `auth` field. R-55 records the temporary public exposure of `/system/status` only. The response discloses the application version and schema version to any caller.
**Fix:** either add `public_until_phase: 2` plus a DECISIONS row (as was done for status), or return 401 from Go until the auth middleware exists. Add a test that fails when a route with `auth != none` and no `public_until_phase` answers 200 without a token.

### WR-06: Public Python health routes fan out to four fresh backend connections per request

**File:** `common/health/probes.py:30-39, 79-93`; `api/apps/restful_apis/system_api.py:69-70`
**Issue:** Each unauthenticated GET to any of the four health paths starts four worker threads and opens a new MySQL connection (full auth handshake), a Valkey connection, a MinIO request and an ES client. `asyncio.timeout` cancels the await but not the thread, which keeps running until its own socket timeouts (up to about 4 s for MySQL: 2 s connect + 2 s read). There is no caching, single-flight or rate limit. The Go side reuses a 10-connection pool and does not have this problem.
**Failure scenario:** a modest request flood on `/system/status` saturates the default executor (at most `min(32, cpu+4)` threads), so legitimate probes time out and report `down`, and drives MySQL connection churn toward `max_connections`.
**Fix:** cache the last probe result for 1-2 s behind an `asyncio.Lock` (single-flight), and probe the database through the application pool once CR-01 is fixed.

### WR-07: Startup hooks run on a throwaway event loop

**File:** `api/ragflow_server.py:84, 116`
**Issue:** `boot()` runs hooks with `asyncio.run(_run_hooks())`, which creates and closes a loop; `main()` then serves on a second loop from `asyncio.run(_serve(...))`. B-08 names `register_startup_hook` as the extension point for the Phase 4 background daemons.
**Failure scenario:** a hook that calls `asyncio.create_task(update_progress())` or creates an async client has its task cancelled and its resources bound to a closed loop before the server starts. The daemon silently never runs.
**Fix:** run hooks on the serving loop, for example `app.before_serving(_run_hooks)` or `await _run_hooks()` at the top of `_serve`, keeping the `boot.step` log order.

### WR-08: Unmapped 4xx statuses carry envelope code 500

**File:** `api/apps/errors.py:49-50`
**Issue:** `_CODE_FOR_STATUS.get(status, RetCode.SERVER_ERROR)` gives code 500 for any HTTP status outside the six mapped ones. A 413 from `MAX_CONTENT_LENGTH`, 415, 408 or 429 returns HTTP 4xx with `{"code": 500, "message": "request failed"}`, contradicting R-63 (status mirrors the envelope error class).
**Failure scenario:** an oversized upload shows the user "Request failed / Code 500", and any client branching on `code >= 500` treats a client error as a server fault and retries.
**Fix:** `code = _CODE_FOR_STATUS.get(status, RetCode.SERVER_ERROR if status >= 500 else RetCode.BAD_REQUEST)`, and add explicit entries/messages for 413 and 429.

### WR-09: Migration runner ignores its `db` argument for version reads/writes; index helper ignores uniqueness

**File:** `api/db/migrations/runner.py:55-60, 91-93, 96-115`
**Issue:**
1. `run_migrations(db=...)` uses `db` for the connection context, `ensure_system_settings` and `module.upgrade`, but `current_version()` and `upsert_setting()` go through `SystemSettings`, which is bound to the global `DB`. Passing any database other than `DB` applies DDL on one database and records the version on another.
2. `add_index_if_missing` matches on column tuple only. An existing non-unique index on the same columns satisfies a request for a unique one, so the constraint is silently never created.
**Fix:** wrap the version read/write in `with db.bind_ctx([SystemSettings]):` (or drop the parameter), and compare `i.unique == unique` in the index check, raising when a same-column index with different uniqueness exists.

### WR-10: Go schema verification compares type families only

**File:** `internal/dao/verify.go:111-132, 190`; `cmd/migrate.go:17-18`
**Issue:** The verifier reads only `data_type` and compares coarse families (string/int/float/time). It does not compare length, nullability, primary key, defaults or indexes, although `conf/schema.json` carries all of them. The comment "exits non-zero on any drift" overstates it.
**Failure scenario:** `document.name` narrowed from `varchar(255)` to `varchar(32)`, `task.to_page` changed from `int` to `bigint` (Go maps `int32`, scan overflow), or a nullable column made `NOT NULL` (Go maps a pointer) all pass `--migrate` and the init gate.
**Fix:** select `column_type`, `is_nullable`, `column_key` as well and compare against `schema.json` (the generator's own input) rather than the reflected struct; or narrow the comment and R-06 wording to what is checked.

### WR-11: Entrypoint does not make `LOG_DIR` writable for the dropped UID

**File:** `docker/entrypoint.sh:13-14`; `Dockerfile:48-49`; `docker/docker-compose.yml:65`
**Issue:** The entrypoint chowns `SERVICE_CONF` but only `mkdir -p`s `LOG_DIR` as root. Go and Python then run as `APP_UID:APP_GID` and both open a log file there at boot; neither tolerates failure (`OpenFile` error returns from `runAPI`; `RotatingFileHandler` raises outside the `BootError` handling).
**Failure scenario:** `docker compose up` without `scripts/preflight.sh` (which is what pre-creates `ragflow-logs/` as the host user), or a host user whose UID is not 1000 while `.env` keeps `APP_UID=1000`: the bind-mount directory is root-owned or foreign-owned, both servers exit, and the container restart-loops. The image's own `/ragflow/logs` is root-owned too.
**Fix:** `mkdir -p "$LOG_DIR" && chown "$APP_UID:$APP_GID" "$LOG_DIR"` in the entrypoint, and have `init_env.sh` write `APP_UID=$(id -u)` / `APP_GID=$(id -g)`.

### WR-12: `NGINX_TLS=1` silently falls back to plain HTTP when certificates are missing

**File:** `docker/entrypoint.sh:16-18`
**Issue:** The HTTPS config is installed only if `NGINX_TLS=1` and both files exist. Otherwise the HTTP config stays in place with no message.
**Failure scenario:** the mounted `certs/` directory exists but holds differently named files (or is empty). The operator requested TLS; the stack serves credentials and tokens in clear text on port 80 and reports healthy.
**Fix:**
```bash
if [ "${NGINX_TLS:-0}" = "1" ]; then
  [ -f /etc/nginx/certs/server.crt ] && [ -f /etc/nginx/certs/server.key ] \
    || { echo "entrypoint: NGINX_TLS=1 but certificate or key is missing" >&2; exit 1; }
  cp /etc/nginx/ragflow.https.conf /etc/nginx/conf.d/ragflow.conf
fi
```

### WR-13: Health checks are meaningless in TLS mode

**File:** `docker/healthcheck.sh:4-5`; `scripts/gen_routes.py:98` (emits `docker/nginx/ragflow.https.conf:5`); `scripts/wait_stack.sh:69, 75`
**Issue:** In the HTTPS config, port 80 answers every path with `301`. `curl -f` only fails on status >= 400, so both healthcheck probes succeed without reaching Go or Python. Conversely `wait_stack.sh` requires a literal `200` on port 80 and can never succeed.
**Failure scenario:** with the TLS override, the container is `healthy` while either backend is hung; `make up` then times out in `wait_stack.sh` after 300 s against a working stack.
**Fix:** probe the backends directly in the healthcheck (`http://127.0.0.1:9384/health`, `http://127.0.0.1:9380/api/v1/system/healthz`) or use `curl -fsS -o /dev/null -w '%{http_code}'` and require `200`; make `wait_stack.sh` use `https://...:${SVR_WEB_HTTPS_PORT}` with `-k` when `NGINX_TLS=1`.

### WR-14: `GO_API_PORT` is configurable but Nginx is hard-wired to 9384

**File:** `docker/docker-compose.yml:25`; `docker/.env.example:78`; `docker/nginx/ragflow.conf:7` (all Go locations)
**Issue:** Compose passes `GO_API_PORT` from `.env` into the container and the template renders it into `go_api.http_port`, while the generated Nginx config proxies to the fixed port from `conf/routes.yaml`. The compose comment says in-network ports are fixed, and the others are, but this one is not.
**Failure scenario:** an operator sets `GO_API_PORT=9399`. Go listens on 9399, every Go-owned route returns 502, the healthcheck fails and the container is marked unhealthy.
**Fix:** pin `GO_API_PORT: "9384"` in `x-app-env` like `SVR_HTTP_PORT`, and remove it from `.env.example`.

### WR-15: `clean_room.sh` reports success when zero runs execute

**File:** `scripts/clean_room.sh:22, 44, 75`
**Issue:** `--runs` is not validated. A failing command substitution in a `for` word list does not trigger `set -e`. Confirmed: with `RUNS=abc`, `seq` prints an error, the loop body is skipped, and the script prints `clean-room: abc run(s) passed` and exits 0. `--runs 0` behaves the same.
**Failure scenario:** the phase-exit gate is invoked with a typo or an empty variable (`--runs "$N"`), nothing is rebuilt or tested, and the gate is green.
**Fix:**
```bash
case "$RUNS" in ''|*[!0-9]*|0) echo "--runs must be a positive integer" >&2; exit 2 ;; esac
```

### WR-16: A same-named compose project from another checkout is only a warning before `down -v`

**File:** `scripts/preflight.sh:103-104`; `scripts/clean_room.sh:49-51`
**Issue:** The guard is by project name. Preflight already detects containers of project `devrag-stack` whose `working_dir` label is not this checkout, but only prints `WARNING` and leaves `FAILED=0`. `clean_room.sh` runs `stop` before preflight and `down -v` right after it.
**Failure scenario:** a second clone of the repo (or a worktree) has its own `devrag-stack` stack with data. Running the gate from this checkout stops its containers and deletes its named volumes. This is the B-05 class of harm with a matching name.
**Fix:** make the collision a hard `fail` in preflight when invoked from `clean_room.sh` (e.g. `PREFLIGHT_STRICT_PROJECT=1`), and move that check ahead of the `stop` step.

### WR-17: `run_tests.py` treats "no tests collected" as success in every mode

**File:** `run_tests.py:59-61`
**Issue:** Exit code 5 is ignored for all commands, not just the serial second pass it was written for.
**Failure scenario:** `clean_room.sh` runs `run_tests.py -m integration`; a marker typo, a moved `testpaths` entry or a collection-time skip yields zero tests and the step prints `PASS integration`.
**Fix:** tolerate 5 only for the second (serial) command in parallel mode, or add `--allow-empty` and pass it explicitly from the one `e2e and serial` step.

### WR-18: CI workflow cannot pass as written

**File:** `.github/workflows/ci.yml:13-17`
**Issue:** `make test-unit` runs `go test -race ./internal/...` and `cd web && npm run test`, but the job has no `actions/setup-go`, no `actions/setup-node` and no `npm ci`. `vitest` is not installed, and the runner's default Go may be older than `go 1.25.0`, which the `check_go_toolchain.sh` gate rejects. B-06 records that the workflow is unverified; this is a concrete defect in it rather than an environment limitation.
**Fix:** add `actions/setup-go` with `go-version-file: go.mod`, `actions/setup-node` with `node-version: 22`, and `npm ci` in `web/` before `make test-unit`; set `permissions: contents: read`.

### WR-19: `render_conf.py` substitutes values into YAML without escaping

**File:** `scripts/render_conf.py:36-38`; `conf/service_conf.yaml.template:12, 20, 24, 30`
**Issue:** Values are pasted between single quotes verbatim. Generated secrets are hex and safe, but operator-supplied values are not.
**Failure scenario:** a password containing `'` produces invalid YAML and both servers fail with "not valid YAML"; a password containing `''` is silently read as one quote, so authentication fails with no hint. A value with a quote followed by a newline can inject keys.
**Fix:** escape for the single-quoted context (`value.replace("'", "''")`) and reject control characters, or render by loading the template as data and emitting with `yaml.safe_dump`.

### WR-20: Vite dev proxy routes Go exact paths with a query string to Python

**File:** `web/vite.config.ts:15`
**Issue:** Exact routes become the regex `^<path>$`, and Vite tests it against `req.url`, which includes the query string (`doesProxyContextMatchUrl` in the installed Vite). `/api/v1/users?page=1` fails the anchor and falls through to the `/api/` prefix, which targets Python. Nginx location matching ignores the query, so dev and production disagree. The path is also not regex-escaped.
**Failure scenario:** in Phase 2, `GET /api/v1/users?...` or `/api/v1/mcp?...` works behind Nginx and returns a Python 404 under `npm run dev`.
**Fix:** `const key = route.match === "exact" ? `^${escapeRegExp(route.path)}(\\?.*)?$` : route.path;`

### WR-21: 401 purge is unconditional

**File:** `web/src/services/http.ts:70-79, 121, 148`
**Issue:** Any 401 status or code 401 runs `purgeSession()`: it ignores `silent`, does not check that a token existed, and does not check that the failing request carried the current token. It also suppresses the server's own message.
**Failure scenario:** (a) a wrong-password login answers 401 and the user sees "Session expired" instead of the credential error; (b) a slow request sent with an old token returns 401 after the user has logged in again, and the fresh token, user store and query cache are wiped.
**Fix:** record the token used in the request interceptor (`config.metadata`), and purge only when that token is non-null and still equals `getAuthorization()`; otherwise fall through to `toastFor`.

### WR-22: Bearer token is attached regardless of destination origin

**File:** `web/src/services/http.ts:103-107`
**Issue:** The request interceptor sets `Authorization` on every request made through `http`. Axios lets a caller pass an absolute `url` that overrides `baseURL`.
**Failure scenario:** a later feature fetches a presigned MinIO URL, an avatar URL or a user-supplied endpoint through `request()`; the access token is sent to that host.
**Fix:** attach the header only for same-origin or relative URLs (`new URL(config.url, location.origin).origin === location.origin`).

### WR-23: `check_secrets.py` misses unquoted assignments and token-named keys

**File:** `scripts/ci/check_secrets.py:23-24, 56`
**Issue:** `LITERAL_ASSIGN` requires a quoted value and only matches keys containing `password|passwd|secret|api_?key`. Unquoted YAML or env-style lines (`password: hunter2`, `REDIS_PASSWORD=abc123`) and keys such as `token`, `access_key` or `Authorization` pass. Every file under a directory named `test`/`tests` skips the literal check entirely.
**Failure scenario:** a compose override or YAML fixture with a real credential is committed and the gate prints `secrets OK`.
**Fix:** add an unquoted form for `.yml/.yaml/.env`-style files (`^\s*[\w.-]*(password|secret|token|api[_-]?key)[\w.-]*\s*[:=]\s*[^\s$<{%'"#][^\s#]*`), add `token|access_key|authorization` to the key list, and keep an allow-comment for intentional fixtures.

## Info

### IN-01: `init.sql` hard-codes the database name

**File:** `docker/init.sql:2`
**Issue:** Creates `rag_flow` regardless of `MYSQL_DBNAME`; with a different name it leaves a stray empty database.
**Fix:** drop the file (the image already creates `MYSQL_DATABASE` with the server charset flags) or generate it from the variable.

### IN-02: Go and Python listen on `0.0.0.0` inside the app container

**File:** `conf/service_conf.yaml.template:4, 7`
**Issue:** Nginx is in the same container and proxies to `127.0.0.1`, but both APIs are reachable from any container on the `ragflow` network, bypassing Nginx route ownership (including the Python `/api/v1/language` duplicate).
**Fix:** set `RAGFLOW_HOST` and `GO_API_HOST` to `127.0.0.1` in `x-app-env`.

### IN-03: Application uses administrative accounts for MinIO and Elasticsearch

**File:** `docker/docker-compose-base.yml:59-60`; `conf/service_conf.yaml.template:23-24, 29-30`
**Issue:** The app authenticates as the MinIO root user and the ES `elastic` superuser; R-61 covers least privilege for MySQL only.
**Fix:** create a scoped MinIO user/policy and an ES role in the init job in a later phase; record the interim choice in DECISIONS.

### IN-04: Valkey uses `allkeys-lru` while it will hold the task queue and locks

**File:** `docker/docker-compose-base.yml:39`
**Issue:** Under memory pressure (128 MB cap) stream and lock keys are eligible for eviction. This matches the reference compose file, so it is noted rather than raised.
**Fix:** use `noeviction` or `volatile-lru` once Streams and locks land (Phase 4), with TTLs on cache keys.

### IN-05: Passwords appear in process arguments of healthchecks and the Valkey command (unverified exposure)

**File:** `docker/docker-compose-base.yml:30, 39, 50, 93`
**Issue:** `valkey-server --requirepass "$REDIS_PASSWORD"`, `valkey-cli -a`, `mysqladmin -p"..."` and `curl -u elastic:...` put secrets in argv. Whether each tool scrubs its argv was not verified.
**Fix:** use `REDISCLI_AUTH`, `MYSQL_PWD` or a defaults file, and a curl config read from stdin.

### IN-06: Dead or unused items

**File:** `docker/.env.example:23-24`; `cmd/modes.go:56`; `api/apps/errors.py:16, 24`; `pyproject.toml:18`; `web/src/constants/copy.ts:11`
**Issue:** `GO_HTTP_PORT` and `EXPOSE_MYSQL_PORT` are not referenced by the compose files; `selectMode`'s `out` parameter is unused; the `400` entries of `_CODE_FOR_STATUS`/`_MESSAGE_FOR_STATUS` are unreachable because the `BadRequest` handler always wins; `httpx` is a runtime dependency used only under `test/`; `copy.nav.closeMenu` is unused while `sheet.tsx:42` hard-codes "Close".
**Fix:** remove them, move `httpx` to the dev group.

### IN-07: Some config errors escape as raw tracebacks, and Go/Python accept different values

**File:** `common/settings.py:137`; `common/log_utils.py:87`; `internal/common/logger.go:90-98`; `internal/server/config.go:103`
**Issue:** `int(rd.get("db", 0))` raises `ValueError`/`TypeError` instead of `ConfigError`; an unknown `logging.level` raises `ValueError` from `setLevel`. Go silently reads a non-numeric `redis.db` as 0. `LOG_LEVEL=CRITICAL` is valid for Python and rejected by Go from the same shared file.
**Fix:** validate both through `_get(..., int)` and an explicit level set shared by both engines.

### IN-08: Go dependency versions differ from the CLAUDE.md baseline without a DECISIONS row (unverified whether recorded elsewhere)

**File:** `go.mod:7-13`
**Issue:** gorm 1.31.2 / driver 1.6.0 (baseline 1.25.7 / 1.5.2, "keep ref pins unless a bug forces a bump"), viper 1.21.0 (1.18.2), go-redis 9.22.0 (9.18.0), zap 1.28.0 (1.27.1). R-81 covers module path and Go version only. Plan summaries were not checked.
**Fix:** add a row equivalent to R-69/R-70 for the Go set.

### IN-09: `dao.OpenDB` details

**File:** `internal/dao/db.go:22, 40-41, 60-63, 86-88`
**Issue:** The `Ping` error is returned raw while the open error goes through `sanitize`, so the stated "no host/user in errors" rule is applied inconsistently; `sanitize` also discards the MySQL error number, leaving operators with only a type name. The 2 s `readTimeout`/`writeTimeout` is baked into the shared pool DSN and will abort any later query that runs longer.
**Fix:** sanitise consistently but keep the numeric code; rely on context deadlines per call instead of a DSN-wide 2 s I/O timeout.

### IN-10: `BaseModel` timestamps are maintained only by `save()`

**File:** `api/db/models/base.py:59-66`
**Issue:** `Model.insert()`, `insert_many()` and `update().execute()` leave `create_*`/`update_*` unset; `upsert_setting` already has to set them by hand.
**Fix:** override `insert`/`update` classmethods as the reference does, before services are written.

### IN-11: CORS notes

**File:** `internal/router/middleware.go:57-62`; `api/apps/middleware.py:17-19`; `internal/server/config.go:104-108`
**Issue:** Go adds `Vary: Origin` only for allowed origins, so a shared cache can serve a response without CORS headers to an allowed origin. Configured origins are compared verbatim in both engines; an entry with a trailing slash or different case never matches and nothing warns.
**Fix:** always set `Vary: Origin` when an allow-list is configured; normalise and validate entries (scheme + host + optional port, no path) at load time.

### IN-12: Nginx notes

**File:** `docker/nginx/ragflow.conf:91-95`; `docker/nginx/ragflow.https.conf:5, 13`; `scripts/gen_routes.py:70-88, 98`
**Issue:** `/assets/` and all proxied API responses carry no `X-Content-Type-Options`; no CSP is set (and `web/index.html:7-15` uses an inline script); the HTTPS server sets no HSTS; `/api` and `/v1` without a trailing slash fall through to the SPA and return `index.html` with 200; the port-80 redirect uses `$host`, which drops the published port (8443).
**Fix:** move the security headers to `server` scope with `always`, add HSTS on 443, add `location = /api { return 404; }` style guards, and redirect with an explicit port variable.

### IN-13: Preflight port list does not match the published ports

**File:** `scripts/preflight.sh:23`
**Issue:** Checks 9380-9384, which compose does not publish, and omits `SVR_WEB_HTTPS_PORT` (8443), which it does.
**Fix:** derive the list from the compose `ports:` entries.

### IN-14: Frontend notes

**File:** `web/src/app.tsx:11-15`; `web/src/services/system-service.ts:11-12`; `web/src/utils/authorization.ts:4-6`
**Issue:** `registerQueryClient` is a side effect inside a `useState` initialiser, which StrictMode double-invokes in development (which instance ends up registered was not verified). `fetchHealth` validates the shape on the 503 path but not on the 200 path, so a non-envelope 200 body would crash `DependencyRows`. `localStorage` access is unguarded and throws when storage is blocked, rejecting every request.
**Fix:** create the client at module scope; run `isHealthData` on success too; wrap storage access in try/catch.

### IN-15: Version checks are permissive

**File:** `cmd/migrate.go:53-56`; `api/ragflow_server.py:59`; `api/db/migrations/runner.py:91-93`
**Issue:** Go `--migrate` prints `schema OK ... schema.version=unset` and exits 0 when no version row exists. Python boot only requires `version >= 1`, not the latest known migration, and a stored version newer than the code is accepted silently. A non-numeric stored value is read as 0 and re-runs every migration.
**Fix:** fail on unset in Go; compare against the highest discovered migration in Python and refuse to boot on mismatch.

### IN-16: Image and init-container hardening

**File:** `Dockerfile:5, 12, 20`; `docker/entrypoint_init.sh:8-11`; `scripts/render_conf.py:61-62`
**Issue:** Base images are referenced by mutable tag; the one-shot init job (migrations, bucket, Go verify) runs entirely as root; `render_conf.py` writes the secret-bearing file and only then chmods it to 0600.
**Fix:** pin digests, drop privileges in the init entrypoint with the same `setpriv` helper, and create the file with `os.open(..., 0o600)`.

### IN-17: `DatabaseLock` edge cases

**File:** `api/db/database.py:181-199`
**Issue:** `__exit__` calls `release()`, which raises on a dead lock connection and replaces any in-flight exception from the guarded block. Loss of the lock connection mid-migration is not detected (`holds_lock()` is never called by the runner).
**Fix:** in `__exit__`, log and suppress release errors when an exception is already propagating; check `holds_lock()` before each migration.

### IN-18: Gate coverage notes

**File:** `scripts/ci/check_decisions.py:39`; `scripts/ci/check_pickle.py:22, 78-81`; `scripts/ci/check_go_toolchain.sh:29-43`
**Issue:** The required R-range is hard-coded to 53-73, so R-74 to R-82 could be deleted without failing the gate. The pickle gate does not scan `scripts/` (one file of which ships in the image), does not flag `yaml.load`/`unsafe_load`, and only catches `allow_pickle=True` as a literal. The toolchain gate does not assert `GOTOOLCHAIN=local`.
**Fix:** derive the range from the highest ID present, add `scripts` to `TARGETS`, flag any non-`False` `allow_pickle`, and check `go env GOTOOLCHAIN`.

---

_Reviewed: 2026-10-06T14:05:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
