# Phase 1: Reconciliation, Guardrails and Dual-Stack Foundation - Research

**Researched:** 2026-10-05
**Domain:** Spec reconciliation, CI guardrails, Docker Compose infrastructure, dual-stack (Go Gin + Python Quart) skeleton on one MySQL schema behind one Nginx ingress, React SPA shell, three test harnesses
**Confidence:** MEDIUM-HIGH (host facts and registry versions verified this session; schema columns beyond three tables come from the reference repo; resource figures for not-yet-built images are estimates)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

All decisions below were auto-selected (`--auto`: recommended option) from the research register unless marked **USER-CONFIRMED**. Auto-selected rows are recorded in `DECISIONS.md` with status `accepted (auto, not user-reviewed)` so the user can audit and overturn them.

#### Scope decisions (USER-CONFIRMED 2026-10-05)
- **D-01 (R-03):** Go Gin builds only the routes the endpoint catalogue assigns it (health/system, auth, user, tenant, search bots, MCP, CLI). Python owns every RAG/ML pipeline. Go mirror engines are v2 and are never stubbed.
- **D-02 (R-48):** Billing from `docs/apis.md` (BILL-01..10) is in v1, scheduled in Phase 8. Phase 1 does nothing for it except not foreclose it.
- **D-03 (R-17/R-18):** Elasticsearch is the default doc store for compose and tests; Infinity is the second adapter (Phase 8). All other engines are v2.

#### Ports, routing and server ownership
- **D-04 (R-01):** Ports follow `docs/18-deployment`: Python API 9380, Python admin 9381, MCP 9382, Go admin 9383, Go API 9384; sandbox 9385 and deepdoc 9390 reserved.
- **D-05 (R-02):** Route ownership is derived from `docs/04-api/endpoint-catalog.md`: explicit Go prefixes (`/health`, `/api/v1/system/`, `/api/v1/language`, `/api/v1/auth/`, `/api/v1/users`, `/v1/user/`, `/v1/tenant/`, `/api/v1/searchbots/`, `/api/v1/mcp`); Python is the catch-all. One route list is the single source; the Nginx config and the Vite dev proxy are both generated from it.
- **D-06 (R-04):** No Go-to-Python proxying. A Go handler that only forwards to Python is treated as drift. How Go search bots reach retrieval is a Phase 8 research question.
- **D-07 (R-05):** Python owns upload, parse trigger and public chatbot routes (relevant here only for the route table).
- **D-08 (R-29):** Go serves `/health` and `/api/v1/system/ping`; Python serves `/system/healthz` and `/system/status`. Health reports each dependency (database, Redis, storage, doc store), not just liveness. Every response carries `X-API-Source`.
- **D-09 (R-25):** `endpoint-catalog.md` plus `apis.md` lines 1-139 are the canonical paths. Legacy aliases are not served.

#### Schema and data layer
- **D-10 (R-06):** One schema writer: Peewee models own DDL and migrations, run as a one-shot init step before either server starts. GORM maps the result with AutoMigrate off; Go `--migrate` only verifies.
- **D-11 (R-31):** Table and column names follow `docs/08-database/`.
- **D-12 (R-20):** Follow the documented DDL; tenant isolation is transitive through `knowledgebase.tenant_id` and `user_tenant`. No `tenant_id` column is invented on `document`/`task`.

#### API contract
- **D-13 (R-24):** Response envelope is `{code, message, data}`, defined once per language and once as a TS interface. Unhandled errors use the same envelope. This contradicts `04-api/api-overview.md` (`retcode/retmsg`) and is recorded as a deviation with rationale.
- **D-14 (R-32):** CORS is a configurable allow-list defaulting to same-origin behind the proxy; never wildcard with credentials.
- **D-15 (R-45):** Python server is Quart on Hypercorn; Flask/Gunicorn mentions in docs are treated as stale.

#### Stack and versions
- **D-16 (R-41):** Python 3.13 via `uv` (`requires-python = ">=3.13,<3.14"`). Deviation from the docs' "3.10 slim" base image, recorded.
- **D-17 (R-42):** MySQL image is parameterised as `MYSQL_IMAGE`, defaulting to the documented `mysql:8.0.40`. Moving to 8.4 LTS needs user approval.
- **D-18 (R-43):** `valkey/valkey:8` for the Redis role; restrict to core commands so Redis 7 also works.
- **D-19 (R-46):** Frontend: Vite only, shadcn/ui only (no `antd`), TanStack Query wrapped in `use-*-request` hooks, Zustand, React Router 7, TailwindCSS.
- **D-20 (STACK):** Pin `litellm==1.84.0` exactly; use `pgsty/minio` rather than `minio/minio`. Versions come from the reference repo's lockfiles and must be re-verified against registries during phase research.
- **D-21 (R-44):** No torch and no PyMuPDF in base dependencies (onnxruntime + pdfplumber/pypdfium2 later). Phase 1 only needs the dependency policy recorded.

#### Naming and layout
- **D-22 (R-09):** Keep documented identifiers (`ragflow_server`, index prefix `ragflow_`, bucket `ragflow`, compose network `ragflow`), each defined as one constant per language so a later rename is a one-line change.
- **D-23:** Repository layout follows `docs/00-overview/repository-map.md` and `docs/02-frontend/directory-structure.md` exactly, as expanded in `.planning/research/ARCHITECTURE.md` "Recommended Project Structure".
- **D-24 (R-07):** Container topology: one app image (Nginx + Go + Python) plus infrastructure services; a standalone task-executor container arrives in Phase 4.

#### Guardrails
- **D-25:** CI gate fails any build that introduces placeholder/fake/mock implementations under production source trees (test trees exempt), and any `pickle.load(s)` on data crossing a trust boundary (R-38: deliberate deviation from the docs' numpy whitelist).
- **D-26 (R-49):** `docs/apikey llm.md` stays unread and uncommitted until the user reviews it. `.gitignore` excludes it and `.env*`. Never run `git add docs/` or `git add -A`.
- **D-27:** Anything that cannot be implemented or verified is written to `.planning/BLOCKERS.md`, never faked.
- **D-28 (R-37):** Secrets come from env only; structured logging redacts them. (Encryption of provider keys is Phase 3.)

#### Host budget and tests
- **D-29:** A preflight script checks free disk, `vm.max_map_count` and RAM and prints an actionable message per failure. The dev compose override caps memory (Elasticsearch heap in particular) to fit a ~5 GB free-RAM host with no GPU.
- **D-30:** Tests assert against the live stack and wait on health/readiness conditions, never fixed sleeps (the prior attempt's flaky-test failure mode).
- **D-31 (R-50):** Real model source for later phases: Ollama in the dev/test compose with one small chat and one small embedding model, unless the user supplies an OpenAI-compatible key. Phase 1 records the decision only.

### Claude's Discretion
- Exact migration tooling for Peewee, the CI runner, the linter/formatter choices, logging library configuration, and the internal structure of the preflight script.
- Wording and visual design of the SPA shell (subject to `/gsd:ui-phase` if run).

### Deferred Ideas (OUT OF SCOPE)
- MySQL 8.4 LTS upgrade - needs user approval (R-42).
- Renaming identifiers to `devrag_*` - user preference, one-constant change (R-09).
- NATS JetStream queue and `ragflow-go` profile (ING-20, DEPLOY-09) - confirm or move to v2 before Phase 8.
- Splitting Phase 8 (117 requirements) into smaller phases.
- `[P]`-flagged thin-spec features (R-51) - need user confirmation and per-phase research.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-02 | Base compose: MySQL, Valkey, MinIO, health checks, named volumes | Compose design, healthcheck table (Pitfalls 3-5), all four infra images already local |
| DEPLOY-03 | App compose with `cpu` profile; app waits for MySQL healthy | `depends_on: service_healthy` + one-shot `init` (Pattern 2) |
| DEPLOY-04 | Profiles `elasticsearch`, `infinity` | Both tags exist on Docker Hub; Infinity only needs to parse in Phase 1 (never pulled) |
| DEPLOY-11 | `.env`-driven config covering the documented variable catalog | `.env.example` + automated catalog-coverage test against `docs/18-deployment/environment-variables.md` |
| DEPLOY-12 | Nginx: SPA, API prefixes, TLS, SSE-safe buffering | Generated config, `=`/`^~` locations only, reference `proxy.conf` directives |
| DEPLOY-13 | One bridge network with aliases; only documented ports exposed | Network `ragflow`; host ports remapped (80 and 6379 are taken on this host) |
| DEPLOY-14 | Container healthcheck on app health every 10 s | Combined Go+Python probe (Open Question 4) |
| DEPLOY-15 | MySQL initialised from `init.sql` on first boot | `/docker-entrypoint-initdb.d/` (true first-boot semantics); DDL stays with Peewee |
| DEPLOY-16 | Logs bind-mounted to host | `./ragflow-logs`; UID mapping pitfall |
| DATA-01 | Schema for the 38 documented entities | Schema section: 3 tables have DDL in docs, 35 are names only; reference `db_models.py` supplies columns |
| DATA-02 | Documented secondary indexes | 7 documented indexes; verify via `information_schema.statistics` by column coverage |
| DATA-03 | Pooled connections with retry/backoff (5 retries) | Reference `RetryingPooledMySQLDatabase`; live test with `KILL CONNECTION` |
| DATA-04 | Multi-step mutations in transactions | `DB.atomic()` / GORM `Transaction`; live rollback test |
| DATA-05 | Migrations; Go `--migrate` flag | Versioned idempotent runner under `DatabaseLock`; Go `--migrate` = verify-only |
| DATA-06 | One schema, Peewee models + GORM structs | Generate GORM structs from a Peewee-exported `schema.json`; CI drift check |
| DATA-08 | DB-backed lock (`DatabaseLock`) | MySQL `GET_LOCK`; session-scoped pitfall |
| API-01..13 | Dual servers, routing, envelope, versioning, X-API-Source, layering, validation, OpenAPI, error envelope, request logging, CORS, Go run modes, Python boot | Route list + generators, envelope kit, Quart/Gin patterns; API-12/13 only partly buildable now (see Requirement Coverage Caveats) |
| SYS-01..07 | `/health`, ping, config, version, language, status, healthz | Route-collision analysis: exact-match locations required; Python status probes with hard timeouts |
| UI-01, UI-03 | Lazy routes + layouts; HTTP client unwraps envelope | Vite 7 / React 18 / Router 7 / Axios; vitest against live ingress |
| SEC-04 | Secrets from env, never logged | `.env.example` with empty secrets, `${VAR:?}`, redaction filter/zap wrapper, ruff `S105/S106` |
| SEC-05 | Restricted unpickler | Deviation per R-38: ban pickle on untrusted data; exact `(module,name)` allow-list only if a helper must exist |
| SEC-10 | Injection prevention | Parameterised queries only; ruff `S608/S602/S605`; schema validation; probe test |
| TEST-01..04, TEST-10 | pytest `run_tests.py`, Python API tests vs live stack, `go test -race`, Go build-tag tiers, frontend component tests | Validation Architecture section |
</phase_requirements>

## Summary

Phase 1 is almost entirely "decide once, generate everywhere, then prove it against a live stack". The load-bearing risks are not library choices but five concrete collisions that the research register did not catch and that this session found by reading `docs/04-api/*`, the reference repo, and the host. (1) The documented Go prefixes `/api/v1/system/` and `/api/v1/mcp` would swallow Python routes the docs also list (`/api/v1/system/tokens`, `/api/v1/system/stats`, `/api/v1/system/status`, `/api/v1/system/healthz`, `/api/v1/mcp/servers`), so the generated Nginx table must use exact-match locations for those Go routes. (2) The requirement text gives Python's probes as `/system/healthz` and `/system/status`, but every doc and the reference mount them under `/api/v1`; this needs a recorded decision (Open Question 1). (3) The reference's Elasticsearch disk watermarks (5gb/3gb/2gb free) were already tripped on this host on 2026-09-27 at 3.1 GB free; with 5.5 GB free the dev override must lower them or ES will refuse shards. (4) Host ports 80 and 6379 are already in use, and a stopped compose project named `devrag` from the prior attempt exists, so the compose project name and published ports must be chosen explicitly. (5) Go on this host is 1.25.5, not 1.26.4; `go.mod` must say `go 1.25.0` or `GOTOOLCHAIN=auto` will try to download a toolchain.

The infrastructure fits the host. All four infrastructure images (`mysql:8.0.40`, `valkey/valkey:8`, `pgsty/minio:RELEASE.2026-03-25T00-00-00Z`, `docker.elastic.co/elasticsearch/elasticsearch:8.11.3`) and `nginx:alpine` (1.31.6) are already in the local Docker store, so no infrastructure pull is needed provided the compose file references the ES image by its `docker.elastic.co/...` name (the Docker Hub `elasticsearch:8.11.3` name would trigger a ~0.7 GB pull). New disk is dominated by builder images and the app image, estimated at about 1.8 GB total against 5.5 GB free. The max_map_count blocker is softer than STATE.md states: ES 8.11.3 with `discovery.type=single-node` started on this very host at 65530 and logged only a WARN, so preflight should fail by default (as the roadmap requires) but offer an explicit, recorded override.

Verification is the other half. Every success criterion has a live check: DECISIONS.md completeness is a script, the CI gates are verified by feeding them known-bad fixtures, schema/`--migrate` is verified by running the init job from an empty volume, route ownership is verified by asserting `X-API-Source` through Nginx plus route-table enumeration on both servers, and the three harnesses wait on readiness (`wait_until`) rather than sleeping.

**Primary recommendation:** Build in this order: (1) DECISIONS.md/BLOCKERS.md/.gitignore/preflight/CI gate scripts with self-tests; (2) `conf/routes.yaml` plus generators for Nginx and the Vite proxy; (3) compose base + dev override + one-shot `init` image; (4) Peewee schema package with exported `schema.json`, generated GORM structs, Go `--migrate` verify; (5) envelope kit and both servers' system routes; (6) SPA shell; (7) the three harnesses and the clean-room `down -v && up` exit gate with measured memory recorded.

## Project Constraints (from CLAUDE.md)

- `docs/` always wins over `spec.md`, existing code, RAGFlow and general judgment, in that order; deviate only on a genuine contradiction or blocker and record it.
- Do not introduce a new service, database, queue, framework or abstraction layer without checking it against `docs/`.
- No critical placeholders; every feature verified by realistic execution, not static inspection.
- Backend quality bar: typed interfaces, config/env handling, input validation, structured errors and logging, migrations, transactions, retries, timeouts, health checks; no giant files.
- Each phase ends in a working state with passing tests; a broken test is acceptable only if documented as a blocked dependency.
- Any decision not covered by `docs/` must be recorded (what, why, how it fits). Unspecified choices take the smallest reasonable production-quality option, using RAGFlow as supporting evidence.
- GSD workflow: repo edits happen through a GSD command (`/gsd-execute-phase` for planned work).
- Hard rules from the orchestrator: never read, stage or commit `docs/apikey llm.md`; never run `git add docs/`, `git add -A` or `git add .`; quote the path `/home/logan78/desktop x/devRag_@`.
- No project skills exist (`.claude/skills/`, `.agents/skills/` absent). CONVENTIONS.md and ARCHITECTURE.md sections of CLAUDE.md are empty placeholders.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Route ownership table (single source) | Build-time config (`conf/routes.yaml`) | Nginx, Vite dev proxy, both servers' route tests | One list generates the ingress and dev proxy and is asserted against both servers |
| Ingress, TLS, SSE-safe proxying, SPA static serving | Nginx (CDN/Static + ingress) | - | Docs place path routing and TLS in Nginx; SPA is static files |
| `/health`, `/api/v1/system/{ping,config,version}`, `/api/v1/language` | Go API (9384) | - | Endpoint catalogue assigns them to Go |
| `/system/healthz`, `/system/status` | Python API (9380) | - | Python probes MinIO and doc store directly; Phase 3 later puts the doc-store port behind `status` |
| Response envelope, error mapping, `X-API-Source`, request logging, CORS | Each API server | Shared TS interface | Defined once per language; contract-tested for byte equality |
| Schema DDL and migrations | Python one-shot `init` job (Peewee) | MySQL | One writer (D-10) |
| Schema mapping and verification | Go (GORM, `--migrate` verify-only) | CI contract test | Go never alters the schema |
| Distributed/DB lock | Database (`GET_LOCK`) via Python | Redis lock (Phase 4) | DATA-08 |
| Dependency health probing | Both servers, each for what it touches | - | Go: MySQL + Redis; Python: MySQL, Redis, MinIO, ES |
| Secrets and config loading | Env -> `service_conf.yaml.template` -> process | - | SEC-04; no secret in git |
| Placeholder/pickle/no-sleep guardrails | CI scripts (`scripts/ci/`) | ruff rules | Run identically locally and in any CI |
| SPA shell, lazy routes, HTTP client, notifications | Browser | Nginx (static) | UI-01/03 |
| Host preflight | Developer host script | CI | Disk, `vm.max_map_count`, RAM |

## Standard Stack

### Core (Phase 1 installs)

All "Latest" values were read from the PyPI JSON API, npm registry and `proxy.golang.org` on 2026-10-05 [VERIFIED: registry queries this session]. "Reference pin" is the version in `/home/logan78/desktop x/ragflow` lockfiles. Package names originate from `docs/00-overview/technology-stack.md` or the reference lockfiles (see Package Legitimacy Audit).

#### Python (`pyproject.toml`, Python 3.13 via uv)
| Library | Recommended | Latest verified | Reference pin | Purpose |
|---------|-------------|-----------------|---------------|---------|
| quart | 0.23.1 | 0.23.1 (2026-08-29, needs Python >=3.13) | 0.20.0 (transitive) | ASGI app. STACK.md's "0.20.0 is latest" is stale |
| hypercorn | 0.18.0 | 0.18.0 | 0.18.0 | ASGI server |
| quart-schema | 0.25.0 | 0.25.0 (requires `quart>=0.19`) | 0.23.0 | Request validation + OpenAPI (API-07/08) |
| quart-cors | 0.8.0 | 0.8.0 | 0.8.0 | CORS (API-11) |
| pydantic | 2.13.5 | 2.13.5 | 2.12.5 | Typed models |
| peewee | **3.19.0, constrain `<4`** | 4.5.2 exists | `>=3.17.1,<4.0.0`, locked 3.19.0 | ORM, `playhouse.pool`, `playhouse.migrate`. 3.19.0 is the last 3.x (2026-01-07); 4.0.0 landed 2026-02-20 and its break set was not verified, so stay on 3.x [ASSUMED re. 4.x incompatibility] |
| PyMySQL | 1.2.3 (fallback 1.1.2) | 1.2.3 | 1.1.2 | MySQL driver. `caching_sha2_password`/`sha256_password` need `PyMySQL[rsa]` [CITED: pypi.org/project/PyMySQL], so keep the documented `mysql_native_password` server flag |
| valkey (client) | 6.1.1 | 6.1.1 | 6.0.2 | Redis protocol client (`redis` 8.1.0 also acceptable) |
| minio (client) | 7.2.20 | 7.2.20 | 7.2.4 | Bucket ensure + health |
| elasticsearch (client) | `>=8.19,<9` (8.19.3) | 9.5.1 exists | dsl 8.12.0 | Health probe only in Phase 1. A 9.x client against an 8.11 server is wrong; keep 8.x [ASSUMED from ES client/server compatibility policy] |
| PyYAML | 6.0.3 | 6.0.3 | - | `service_conf.yaml` loading and route list |
| httpx | 0.28.1 | 0.28.1 | - | Test HTTP client against the ingress |

Dev/test: pytest 9.1.1, pytest-asyncio 1.4.0, pytest-xdist 3.8.0, pytest-cov 7.1.0, ruff (host 0.14.5; latest 0.16.10), optionally pytest-timeout 2.4.0 [all VERIFIED: PyPI]. Reference uses `asyncio_mode = "auto"`, `--strict-markers`, and `filterwarnings=["error", ...]` in `[tool.pytest.ini_options]`; copy the shape.

Logging: stdlib `logging` with a JSON formatter and a redaction filter. No new dependency (structlog 26.1.0 exists but adds nothing required).

Fallback rule: if quart 0.23.1 + quart-schema 0.25.0 misbehave, drop to the reference combination (quart 0.20.0, quart-schema 0.23.0, PyMySQL 1.1.2), which is known to work together.

#### Go (`go.mod`, `go 1.25.0`)
| Module | Recommended | Latest verified | Reference pin |
|--------|-------------|-----------------|---------------|
| github.com/gin-gonic/gin | v1.12.0 (its go.mod says `go 1.25.0`) | v1.12.0 (2026-02-28) | v1.12.0 |
| gorm.io/gorm | v1.31.2 | v1.31.2 (2026-06-22) | v1.25.7 |
| gorm.io/driver/mysql | v1.6.0 | v1.6.0 | v1.5.2 |
| go.uber.org/zap | v1.28.0 | v1.28.0 | v1.27.1 |
| github.com/spf13/viper | v1.21.0 | v1.21.0 | v1.18.2 |
| github.com/redis/go-redis/v9 | v9.22.0 | v9.22.0 | v9.18.0 |
| github.com/minio/minio-go/v7 | v7.3.0 | v7.3.0 | v7.0.99 |
| github.com/stretchr/testify | v1.12.1 (optional) | v1.12.1 | - |

The reference's `go 1.26.4` must NOT be copied: host Go is 1.25.5 and `GOTOOLCHAIN=auto`, so a higher directive triggers a toolchain download. If an exact older module is needed to avoid a regression, fall back to the reference pin. Do not add `go-sqlmock` or `miniredis` (mocks conflict with D-30). Elasticsearch Go client is not needed in Phase 1.

#### Frontend (`web/package.json`, Node 22.23.3, npm 10.8.2, no pnpm)
| Package | Recommended | Latest verified | Why not latest |
|---------|-------------|-----------------|----------------|
| vite | 7.3.6 | 8.3.2 | STACK pins 7; vitest 5 peers `^6.4 || ^7 || ^8` so 7 is fine |
| @vitejs/plugin-react | 5.2.0 | 6.1.1 | 5.x peers include Vite 7 |
| react / react-dom | 18.3.1 | 19.3.0 | Docs say React 18 |
| typescript | 5.9.3 | 7.0.2 | STACK pin; 6.x and 7.x exist |
| react-router | 7.18.4 | 8.4.0 | D-19 says Router 7 |
| zustand | 5.0.15 (STACK said 4.5.7) | 5.0.15 | Greenfield; pick latest unless a plugin needs 4 |
| @tanstack/react-query | 5.104.1 | 5.104.1 | - |
| axios | 1.20.0 | 1.20.0 | Docs name an Axios client |
| tailwindcss | 3.4.19 (`v3-lts` dist-tag) | 4.3.3 | STACK: stay on v3 |
| tailwindcss-animate | 1.0.7 | 1.0.7 | v3-era animation plugin |
| tailwind-merge | 2.6.1 | 3.7.0 | 3.x targets Tailwind v4; STACK pin is 2.6.1 |
| class-variance-authority, clsx, lucide-react | 0.7.1, 2.1.1, 1.52.0 | same | shadcn deps |
| shadcn (CLI) | 4.21.1 | 4.21.1 | Docs state existing Tailwind v3 + React 18 projects keep working and new components stay v3/React 18 [CITED: ui.shadcn.com/docs/tailwind-v4] |
| sonner | 2.0.8 | 2.0.8 | Notification host for UI-03 (shadcn's current toast component) [ASSUMED it is the shadcn default; verify when adding] |
| vitest | 5.0.3 (fallback 4.1.11) | 5.0.3 | Needs Node `^22.12` (OK) |
| jsdom | 30.1.2 | 30.1.2 | Needs Node `^22.22.2` (host 22.23.3 OK) |
| @testing-library/react, jest-dom, user-event | 16.3.3, 7.0.1, 14.6.7 | same | Documented RTL |
| openapi-typescript | 7.13.0 (dev) | 7.13.0 | Generates TS types from the Python OpenAPI (Pitfall 17); peers `typescript ^5.x` |
| @playwright/test | optional | 1.63.0 | Host has `/usr/bin/google-chrome` and a Playwright chromium cache; use `channel: 'chrome'` to avoid a download |

**Installation:**
```bash
# Python (uv owns the interpreter; never use /usr/bin/python3 = 3.10.12)
uv python pin 3.13 && uv sync
# Go
go mod tidy
# Frontend
cd web && npm ci
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled versioned Peewee migration runner | peewee-migrate | Extra dependency not named in docs; docs name `playhouse.migrate` + `DatabaseMigrator` |
| stdlib logging JSON formatter | structlog | No capability gain in Phase 1 |
| GORM structs generated from `schema.json` | Hand-written structs | 38 hand-written structs duplicate the schema (Anti-Pattern 7) |
| `redis` Python client | `valkey` client | Docs name Valkey; both speak the protocol |
| Playwright browser smoke | vitest-only | Playwright can use system Chrome; defer unless time allows |

## Package Legitimacy Audit

slopcheck was NOT run: the orchestrator forbids installing anything, so the protocol's graceful-degradation path applies. Substitutes performed: every name below was confirmed to exist on its own ecosystem's registry (PyPI JSON, npm registry, `proxy.golang.org`) this session, and all npm packages were checked for `postinstall`/`install` scripts (none found for the frontend set listed). Every name originates from `docs/00-overview/technology-stack.md`, the reference lockfiles, or is a standard test tool named in `docs/19-testing/`.

| Package | Registry | Source of the name | slopcheck | Disposition |
|---------|----------|--------------------|-----------|-------------|
| quart, hypercorn, quart-schema, quart-cors, peewee, PyMySQL, pydantic, PyYAML, valkey, minio, elasticsearch, pytest, pytest-asyncio, pytest-xdist, pytest-cov, httpx, ruff | PyPI | docs / reference `pyproject.toml` / `uv.lock` | not run | `[ASSUMED]` per protocol; exist on PyPI |
| gin, gorm, gorm mysql driver, zap, viper, go-redis, minio-go, testify | Go proxy | docs / reference `go.mod` | not run | `[ASSUMED]` per protocol; exist on proxy.golang.org |
| react, react-dom, vite, @vitejs/plugin-react, react-router, zustand, @tanstack/react-query, axios, tailwindcss, tailwindcss-animate, tailwind-merge, class-variance-authority, clsx, lucide-react, shadcn, vitest, jsdom, @testing-library/*, typescript | npm | docs / reference `package.json` | not run | `[ASSUMED]` per protocol; exist; no install scripts |
| sonner, openapi-typescript, @playwright/test | npm | shadcn default toast; Pitfall 17 recommendation; Playwright | not run | `[ASSUMED]`; not named in `docs/`; recorded as additions in DECISIONS.md |

**Packages removed due to slopcheck [SLOP]:** none (not run).
**Packages flagged [SUS]:** none identified; planner should add one `checkpoint:human-verify` that reviews the three lockfiles (`uv.lock`, `go.sum`, `package-lock.json`) once, rather than one checkpoint per package.

## Architecture Patterns

### System Architecture Diagram

```
 developer / test runner / browser
          |  http://127.0.0.1:${SVR_WEB_HTTP_PORT}  (8080 on this host; 80 is taken)
          v
 +-------------------------------- app container (one image, tini PID 1) -------------+
 |  Nginx :80  (config GENERATED from conf/routes.yaml)                                |
 |    = /health, = /api/v1/system/{ping,config,version}, = /api/v1/language  ---+     |
 |    ^~ /api/v1/auth/, = /api/v1/users, ^~ /v1/user/, ^~ /v1/tenant/,           |     |
 |    ^~ /api/v1/searchbots/, = /api/v1/mcp                                      v     |
 |                                                                       Go Gin :9384  |
 |    ^~ /api/v1/admin (later)  --> :9381/:9383                          (X-API-Source: go)
 |    = /system/healthz, = /system/status (Open Question 1)  --+                |     |
 |    ^~ /api/ , ^~ /v1/   (catch-all)  ------------------------+--> Quart/Hypercorn  |
 |    /  -> static SPA, try_files -> /index.html                       :9380           |
 |                                                                (X-API-Source: python)
 +------------------------------------+--------------------------------+---------------+
                                      | MySQL (shared schema)          | probes
          +---------------------------+-----------+-----------+--------+---------+
          v                           v           v           v                  v
     mysql :3306                valkey :6379   minio :9000   es01 :9200   (infinity profile: off)
     (healthy)                  (healthy)      (healthy)     (healthy)

 one-shot `init` service (same app image, runs BEFORE the app, exits 0):
   wait deps -> GET_LOCK -> Peewee migrate (38 tables) -> Go `--migrate` VERIFY
   -> ensure MinIO bucket `ragflow` -> export schema version -> exit

 build/CI side:  conf/routes.yaml --gen--> docker/nginx/*.conf, web proxy json
                 Peewee models --export--> conf/schema.json --gen--> internal/entity/*.go
                 scripts/ci/*  (placeholder gate, pickle gate, no-sleep gate, decisions check, drift checks)
```

### Recommended Project Structure

Follow `.planning/research/ARCHITECTURE.md` "Recommended Project Structure" (D-23). Phase 1 creates only the skeleton below; empty future directories get no placeholder files (a `.gitkeep` is acceptable, a stub module is not).

```
conf/
  routes.yaml                 # single route-ownership source (owner, match type, paths, auth, notes)
  schema.json                 # exported from Peewee; input to Go struct generator (committed, drift-checked)
  service_conf.yaml.template  # envsubst template, `${VAR:-default}`; secrets have NO default
docker/
  docker-compose.yml          # app + init (profile cpu); includes base
  docker-compose-base.yml     # mysql, redis(valkey), minio, es01, infinity (profile) , network ragflow
  docker-compose.dev.yml      # memory caps, ES watermarks, host port remaps, 127.0.0.1 binds
  .env.example                # catalog of variables; secrets empty
  init.sql                    # CREATE DATABASE only
  nginx/                      # nginx.conf, proxy.conf, ragflow.conf (generated), ragflow.https.conf (generated)
  entrypoint.sh, entrypoint_init.sh
scripts/
  preflight.sh                # disk / vm.max_map_count / RAM / ports / compose project collision
  gen_routes.py               # routes.yaml -> nginx + vite proxy json
  gen_go_entities.py          # schema.json -> internal/entity/*.go
  ci/                         # check_placeholders.py, check_pickle.py, check_no_sleep.py, check_decisions.py, ...
  wait_stack.sh               # readiness polling for compose, no sleeps
api/                          # Quart: apps/__init__.py (factory), apps/restful_apis/system_api.py, db/models/ (package), db/migrations/, utils/api_utils.py
common/                       # settings.py, constants.py (RetCode + identifiers), log_utils.py, health/ probes
cmd/ragflow_server.go         # flags --api --admin --ingestor --syncer --migrate
internal/                     # router/, handler/system.go, service/, dao/ (GORM, verify), entity/ (generated), common/ (envelope, constants, logger), server/ (config)
web/                          # Vite app; src/{app.tsx,routes.tsx,main.tsx,services/,hooks/,utils/,layouts/,components/ui/,constants/,interfaces/}
test/                         # unit_test/, integration/, testcases/ (HTTP vs live stack), helpers/wait.py
.planning/DECISIONS.md, BLOCKERS.md
```

Split `db_models.py`: the reference file is 1886 lines. CLAUDE.md forbids giant files, so create `api/db/models/` (one module per domain: identity, llm, knowledge, files, chat, canvas, integrations, system) and keep `api/db/db_models.py` as a thin re-export because docs cite that path.

### Pattern 1: One route list, generated ingress, enumerated servers
**What:** `conf/routes.yaml` entries carry `owner: go|python`, `match: exact|prefix`, path(s), `auth: none|jwt|beta|api` and optional `direct_only_duplicate: true`. A generator emits Nginx `location = ...` / `location ^~ ...` blocks (no regex locations, so no first-match ordering hazards) and a JSON file the Vite proxy imports (no YAML dependency in Node). Two tests enumerate the real route tables (`engine.Routes()` in Gin, `app.url_map.iter_rules()` in Quart) and assert every registered route belongs to its owner, with the single documented exception for diagnostics.
**When to use:** always; this is the answer to Pitfall 2 and D-05.
**Required refinement of D-05 (collision evidence):**
- Go gets `= /health`, `= /api/v1/system/ping`, `= /api/v1/system/config`, `= /api/v1/system/version`, `= /api/v1/language` (exact), not the `/api/v1/system/` prefix, because Python documents `/api/v1/system/tokens`, `/api/v1/system/stats`, `/api/v1/system/status`, `/api/v1/system/healthz` [CITED: docs/04-api/system-api.md, stats-api.md; reference `api/apps/restful_apis/system_api.py`].
- Go gets `= /api/v1/mcp` (exact), not the prefix, because Python documents `/api/v1/mcp/servers` [CITED: docs/04-api/mcp-api.md].
- Go gets `= /api/v1/users` (exact) for registration; Python's `user-api.md` also lists `/auth/login` and `/users` (stale duplicates of Go's routes, R-30). Python must NOT register them.
- Prefix matches are safe for `/api/v1/auth/`, `/v1/user/`, `/v1/tenant/`, `/api/v1/searchbots/` (no Python route documented under them).
- Python is the catch-all for `/api/` and `/v1/`.
**Example (shape only):**
```yaml
# conf/routes.yaml
routes:
  - {owner: go,     match: exact,  path: /health,                 auth: none}
  - {owner: go,     match: exact,  path: /api/v1/system/ping,     auth: none}
  - {owner: go,     match: exact,  path: /api/v1/language,        auth: none, python_diagnostic_duplicate: true}
  - {owner: go,     match: prefix, path: /api/v1/auth/,           auth: none}
  - {owner: go,     match: exact,  path: /api/v1/mcp,             auth: beta}
  - {owner: python, match: exact,  path: /api/v1/system/healthz,  auth: none, also: [/system/healthz]}
  - {owner: python, match: prefix, path: /api/,                   auth: jwt, catch_all: true}
```

### Pattern 2: One-shot `init` before either server
**What:** A compose service using the app image (`restart: "no"`) that waits for MySQL, takes `GET_LOCK('init_database_tables', 60)`, runs the versioned Peewee migrations, runs `ragflow_server --migrate` (verify-only), ensures the MinIO bucket, then exits 0. The app service uses `depends_on: init: condition: service_completed_successfully`, and `init` itself `depends_on` mysql/redis/minio/es01 with `service_healthy`.
**Why:** Removes the race of two servers creating schema (Pitfall 2/18), makes DEPLOY-03 and criterion 3 directly testable (`docker compose run --rm init` from an empty volume).
**Note:** `docker compose up --wait` handling of exited-0 one-shot services varies by Compose version [ASSUMED]; prefer `scripts/wait_stack.sh` polling `docker compose ps --format json` plus the app health URL. Host has Compose v5.0.0.

### Pattern 3: Envelope kit, defined once per language
**What:** `{"code": int, "message": str, "data": any}`. Python: `api/utils/api_utils.py` (`json_result`, `error_result`) plus `app.errorhandler(Exception)`, `HTTPException`, and quart-schema's `RequestSchemaValidationError`. Go: `internal/common/response.go`, custom `gin.CustomRecovery`, `engine.NoRoute`, `engine.NoMethod` (Gin's defaults return plain text, which would violate API-03/API-09). TS: `interface Envelope<T> { code: number; message: string; data: T }`. Reuse the reference `RetCode` numbering (0, 100-111, 400, 401, 403, 404, 409, 500) [VERIFIED: reference `common/constants.py`, `internal/common/error_code.go`]; add a parity test that parses the Python enum, Go constants and TS enum and compares numeric values.
**HTTP status:** set the real HTTP status (400/401/403/404/405/409/500/503) as well as the envelope code; the client treats either as an error. (Recorded deviation: the reference often returns HTTP 200 with a non-zero code.)
**Test of an unhandled error:** the factories accept extra blueprints/routes (Quart `create_app(...)`, Gin `NewEngine(...)`); the test tree registers a route that raises/panics and asserts the envelope in-process. Against the live stack use real failures (unknown route -> 404, wrong method -> 405, malformed JSON -> 400, and a serial test that stops a dependency to see 503).

### Pattern 4: Dependency probes with hard timeouts
**What:** Python `/api/v1/system/status` and `/healthz` run MySQL `SELECT 1`, Valkey `PING`, MinIO bucket check, ES `_cluster/health` concurrently (`asyncio.gather` over `asyncio.to_thread`) with a 2 s per-probe cap and `max_retries=0` on the ES client, returning `{name: {status, elapsed_ms}}` only (no hostnames or error strings, since Phase 1 serves `/system/status` unauthenticated; the reference wraps it in `login_required`, but login is Phase 2). Go `/health` probes MySQL and Redis with `context.WithTimeout` and goroutines. Overall HTTP 200 only if all are ok, else 503 with the same envelope.
**Why:** Peewee and the ES/MinIO clients are synchronous; a down dependency must not stall the event loop or hang the compose healthcheck.

### Pattern 5: Peewee pool with retry, DB lock
**What:** Copy the documented `RetryingPooledMySQLDatabase` shape: override `execute_sql` and `begin`, retry on MySQL errors 2006/2013 and `InterfaceError`, 5 retries, `delay * 2**attempt` [VERIFIED: reference `api/db/db_models.py` lines 259-318; docs/08-database/transactions.md]. `DatabaseLock` uses `SELECT GET_LOCK(name, timeout)` / `RELEASE_LOCK` [VERIFIED: reference lines 561-620]. `GET_LOCK` is session-scoped: hold one dedicated connection for the lock's lifetime and release on that same connection.

### Pattern 6: Versioned idempotent migrations (discretion)
**What:** `api/db/migrations/NNNN_name.py` modules; `0001_baseline` creates all 38 tables (`create_table(safe=True)`); later steps use `playhouse.migrate` helpers that first check `DB.get_columns`/`get_indexes` (the reference `alter_db_add_column` pattern). Applied versions are recorded in a documented table: store `schema.version` in `system_settings` rather than inventing a 39th table [ASSUMED acceptable; record as a deviation either way]. Whole run under `DatabaseLock`.

### Anti-Patterns to Avoid
- **Regex Nginx locations** (the reference's hybrid file): first-match ordering makes ownership depend on line order. Use `=` and `^~` only.
- **Prefix Go locations for `/api/v1/system/` and `/api/v1/mcp`**: silently routes documented Python endpoints to Go (404 envelope from the wrong engine).
- **Go `--migrate` that calls AutoMigrate**: breaks D-10. It must compare GORM-parsed schema to `information_schema` and exit non-zero on drift.
- **Compose project named `devrag`**: collides with the stopped prior-attempt project (see Pitfall 6).
- **`/` health checks that only prove the port is open** (the documented ES `curl http://localhost:9200` returns 401 and still exits 0).
- **A `sleep` anywhere** in compose entrypoints, scripts or tests.
- **A mock/fake importable from production packages.** Fakes live under `test/` only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request validation + OpenAPI | Custom validators / hand-written OpenAPI | quart-schema 0.25.0 (`QuartSchema(app)`, `validate_request`) | Docs name it (API-07/08) |
| Pool + connection-loss retry | New pool | `playhouse.pool.PooledMySQLDatabase` subclass per docs | Docs give the exact pattern |
| Schema migration ops | Raw `ALTER TABLE` strings | `playhouse.migrate.MySQLMigrator` | Docs name `DatabaseMigrator`; parameterised |
| Go config | Custom env parser | viper | Docs name it |
| Go logging | Custom logger | zap (+ lumberjack for rotation) | Docs name it |
| Python/JS/Go injection checks | Regex over source | ruff `S301/S403/S608/S602/S605` (Python); `database/sql`/GORM placeholders (Go) | ruff rules exist locally [VERIFIED: `ruff rule S301`...] |
| Security header/CORS logic | Hand-written CORS | quart-cors; `gin-contrib/cors` (v1.7.9 exists) or small allow-list middleware | D-14 allow-list |
| Container init ordering | `sleep N` | compose healthchecks + `service_completed_successfully` | Pitfall 18 |
| Nginx/Vite route parity | Two hand-edited tables | `scripts/gen_routes.py` from `conf/routes.yaml` | D-05 |
| GORM struct maintenance | 38 hand-written structs | generator from Peewee-exported `schema.json` | DATA-06 |
| Readiness waiting | `sleep` loops | one `wait_until(predicate, timeout, interval)` per language | D-30 |

**Key insight:** this phase's failure mode is drift between duplicated definitions (routes, envelope, schema, identifiers). Every duplicated definition needs a generator or a parity test, and every guardrail needs a self-test with a known-bad fixture proving it fails.

## The Minimal Full Schema (what docs specify vs. what Phase 1 must create)

**What `docs/08-database/` actually specifies** [VERIFIED: read all 8 files]:
- Full `CREATE TABLE` DDL for exactly **3 tables**: `document`, `task`, `knowledgebase` (`schema.md`).
- A 7-row index table (`indexes.md`): `document.kb_id`, `document.parser_id`, `document.status`, `task.doc_id`, `task.progress`, `knowledgebase.tenant_id`, `file.parent_id`. The DDL for the three tables names `idx_doc_kb_id`, `idx_doc_parser_id`, `idx_doc_status`, `idx_task_doc_id`, `idx_task_progress`, `idx_kb_tenant_id`, `idx_kb_name`. `idx_kb_name` is not in the index table (docs inconsistency); `file.parent_id` has no DDL.
- Names only (`entities.md`) for the remaining **35 entities**, which with the 3 above make **38 tables**: User, Tenant, UserTenant, InvitationCode, LLMFactories, LLM, TenantLLM, TenantLangfuse, Knowledgebase, Document, File, File2Document, FileCommit, FileCommitItem, Task, Dialog, Conversation, APIToken, API4Conversation, UserCanvas, CanvasTemplate, UserCanvasVersion, MCPServer, CompilationTemplate, CompilationTemplateGroup, Search, PipelineOperationLog, Connector, Connector2Kb, ChatChannel, SyncLogs, Memory, SystemSettings, TenantModelProvider, TenantModelInstance, TenantModel, TenantModelGroup, TenantModelGroupMapping. DATA-01 lists 34 names with `TenantModel*` standing for the five model-provider tables, so 38 matches.
- Relationship text: tenant -> knowledgebase -> document -> task, file <-> document via `file2document`. No foreign-key constraints are specified, and the reference uses none (varchar(32) ids, no FKs) [VERIFIED: reference models].
- Mapping `Peewee model <-> Go DAO`: `internal/dao/migration.go` and `db_models.py` `migrate_db()` define the post-baseline alterations.

**Gaps and contradictions to record (new register rows):**
- The documented `knowledgebase` DDL omits columns every later phase needs and the reference defines: `created_by`, `permission`, `doc_num`, `token_num`, `chunk_num`, `similarity_threshold`, `vector_similarity_weight`, `pipeline_id`, `pagerank`, `tenant_embd_id`, and about 18 task-tracking columns [VERIFIED: reference `Knowledgebase`, lines 837-891]. Documented `document` DDL has `create_time`/`update_time` but not `create_date`/`update_date`, which the reference `DataBaseModel` adds to every table.
- **Rule for Phase 1:** columns the docs specify are created with exactly the documented name, type, nullability and default; every other column comes from the reference model for that table and is listed in DECISIONS.md as "supplemental from reference (R-31)". Do not invent columns the reference lacks. Do not copy reference columns that belong to out-of-scope features if they are Go-only entities (`ingestion_task`, `skill_*`, `license`, `evaluation`, billing `_ee` tables exist only in the reference Go entities, not in the docs entity list).
- Documented types are narrower than the reference in places (docs `parser_config longtext NOT NULL`; reference `JSONField` stored as LONGTEXT). Use LONGTEXT-backed JSON fields; GORM maps them to `string` or a JSON scanner type.
- Documented `run varchar(1) DEFAULT '0'`, `status varchar(1) DEFAULT '1'`, id `varchar(32)`, `kb_id varchar(256)`: keep as documented (R-14).
- Reference index strategy puts `index=True` on most columns (`knowledgebase` has about 35). Recommendation: create the 7 documented indexes (by column coverage) plus the reference's `index=True` flags as written, because later query paths depend on them and the 64-index MySQL cap is not at risk. Test by `information_schema.statistics` column coverage, not by index name (Peewee auto-names `document_kb_id`; naming to `idx_doc_kb_id` via `ModelIndex(... name=)` is [ASSUMED] possible and optional).
- `user.email` unique index is added by the reference Go migration, not in the Peewee model; Phase 2 concern, but include the unique constraint at baseline to avoid a later data migration [ASSUMED acceptable].

**What Phase 1 must create:** all 38 tables from empty via the Peewee baseline; the 7 documented indexes; `schema.json` export; 38 generated GORM entity files with `AutoMigrate` unused; Go `--migrate` verification of table/column presence and types; no seed data (LLM factories and superuser are Phase 2/3).

## Host Budget (measured where marked)

| Resource | Measured / Verified | Phase 1 need | Verdict |
|----------|--------------------|--------------|---------|
| Disk (`/` = Docker root = project dir, one partition) | 5.5 GB free, 97% used [VERIFIED: `df`] | Images already local: mysql 826 MB, valkey 176 MB, pgsty/minio 223 MB, ES 2.19 GB, nginx:alpine 94 MB [VERIFIED: `docker images`]. New: golang:1.25-alpine (64 MB compressed, about 280 MB on disk), node:22-alpine (61 MB, about 165 MB), python:3.13-slim (46 MB, about 125 MB), app image about 350-450 MB, build cache, host `node_modules` about 300 MB, host `.venv` about 150 MB, MySQL volume about 200 MB, ES volume about 50 MB [sizes of new items are `[ASSUMED]` estimates; compressed sizes VERIFIED via Docker Hub API] | About 1.8 GB new; fits with about 3.7 GB headroom. Phase 3+ (Ollama models, ONNX) will not fit without user action |
| Reclaimable by user (needs consent) | Docker reports 5.4 GB reclaimable images; Go module cache 5.2 GB; npm cache 4.2 GB; uv cache 798 MB [VERIFIED: `docker system df`, `du`] | - | Candidate user actions; never prune automatically |
| RAM | 15.6 GB total, 5.2 GB available at probe time [VERIFIED: `free -m`] | Proposed `mem_limit`: es01 2g (`-Xms1g -Xmx1g`), mysql 640m, minio 256m, valkey 160m (`maxmemory 128mb`), app 768m, init 256m transient. Limits sum about 3.8 GB; expected RSS about 2.3-2.9 GB [`ASSUMED` typical RSS; must be measured with `docker stats` at the exit gate and recorded] | Fits, tight. Prior ES run here used `-Xms1g -Xmx1g` and started in about 9 s [VERIFIED: old container logs] |
| MySQL tuning for dev | Docs: `--max_connections=1000` etc. | dev override: `--innodb-buffer-pool-size=128M --performance-schema=OFF --max_connections=200` (documented values kept in the base file) | [ASSUMED] saves a few hundred MB |
| `vm.max_map_count` | 65530 [VERIFIED] | ES recommends 262144 | ES 8.11.3 single-node started at 65530 with only a WARN on this host (2026-09-27) [VERIFIED: `docker logs ragflow-es01`]; docs confirm single-node evades bootstrap checks [CITED: elastic.co bootstrap-checks]. Preflight fails by default; provide `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` that records the override; add an early empirical task |
| **ES disk watermarks** | Reference sets `low=5gb, high=3gb, flood_stage=2gb` free; on this host ES logged "low disk watermark [5gb] exceeded ... free: 3.1gb" and "high disk watermark [3gb] exceeded" [VERIFIED: old container logs]. Defaults are 85/90/95% used [CITED: elastic.co modules-cluster]; disk is 97% used | Dev override must set absolute byte watermarks well below the headroom, e.g. `low=1gb high=750mb flood_stage=500mb`, or `cluster.routing.allocation.disk.threshold_enabled=false` for dev only [CITED: threshold_enabled exists, default true] | **Mandatory** or ES goes read-only and Phase 3 index creation fails |
| GPU | none | not needed in Phase 1 | `gpu` profile is later, record in BLOCKERS.md |
| Ollama | Binary at `/usr/local/bin/ollama`; server not running; `~/.ollama` is 20 KB (no models) [VERIFIED] | Phase 3 | Correct STATE.md's "no Ollama": binary exists, no models; a compose-contained Ollama is still the D-31 plan |

## Common Pitfalls

### Pitfall 1: Nginx prefix swallows Python routes
**What goes wrong:** `/api/v1/system/tokens` or `/api/v1/mcp/servers` is answered by Go with a 404 envelope.
**Why:** D-05 lists prefixes; docs also list Python routes under the same prefixes.
**How to avoid:** exact matches for the Go system and MCP routes (Pattern 1). Add a routing test that requests every Python-documented path and asserts `X-API-Source: python`.
**Warning signs:** an `X-API-Source: go` header on an agent/dataset/system-token path.

### Pitfall 2: The ES image name decides whether a 0.7 GB pull happens
**What goes wrong:** `image: elasticsearch:${STACK_VERSION}` (the documented form) is not the local tag; Compose pulls on a 5.5 GB disk.
**How to avoid:** use `docker.elastic.co/elasticsearch/elasticsearch:${STACK_VERSION}`, which is present locally [VERIFIED: `docker images`]; keep the tag pin 8.11.3. Record as a deviation (same content, official registry name).

### Pitfall 3: Healthchecks that cannot fail or cannot run
**What goes wrong / evidence:** the prior attempt's `minio/minio:2023-11-20` curl healthcheck failed with `exec: ... not found` (no curl) [VERIFIED: old container health logs]; its Valkey healthcheck failed with `NOAUTH` (password not passed); the documented ES check `curl http://localhost:9200` returns 401 with security on yet exits 0.
**How to avoid (verified in this session by running short `--network none` containers):** `pgsty/minio:RELEASE.2026-03-25...` has `curl` and `mc`, so the documented `curl -f http://localhost:9000/minio/health/live` works [VERIFIED]. `valkey/valkey:8` (v8.1.10) has `valkey-cli` and `redis-cli` but no curl [VERIFIED]; use `valkey-cli -a "$$REDIS_PASSWORD" ping | grep PONG` via `CMD-SHELL`. ES image has curl [VERIFIED]; use `curl -fsS -u elastic:$$ELASTIC_PASSWORD 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5s'`. MySQL: ping over TCP (`mysqladmin ping -h 127.0.0.1 -uroot -p"$$MYSQL_ROOT_PASSWORD"`) so the entrypoint's temporary skip-networking server does not report healthy before the real server starts [ASSUMED standard pattern]. Use `$$VAR` so the password is not inlined in the compose file; it remains visible in `docker inspect` env (inherent, note in SEC doc).

### Pitfall 4: Published host ports collide
**Evidence:** host listens on 80, 6379 (loopback), 5432, 27017, 9009 [VERIFIED: `ss -ltn`]. 3306, 9000, 9001, 9200, 9380-9384 and 8080 are free.
**How to avoid:** `.env.example` sets `SVR_WEB_HTTP_PORT=8080`, `REDIS_PORT=6380` (or unpublished), and dev override binds published ports to `127.0.0.1`. Preflight checks every published port and prints the owner via `ss -ltnp`.

### Pitfall 5: Compose project name collision
**Evidence:** stopped containers and network `devrag_ragflow-network` belong to compose project `devrag` from the earlier attempt in `/home/logan78/desktop x/devRAG`; project `docker` holds `docker_mysql_data`, `docker_esdata01`, etc. [VERIFIED: `docker ps -a`, `docker volume ls`].
**How to avoid:** set top-level `name:` explicitly to something unique (for example `devrag-at`); never run `down -v` under a name that matches an old project; preflight warns if the chosen project name already has resources. Do not remove old volumes or images without user consent. The `@` and space in the path also break unquoted bind mounts and scripts; run a CI step that executes the scripts from a path containing a space (the repo path itself already does).

### Pitfall 6: MySQL `GET_LOCK` is session-scoped; Peewee runs in a thread pool
Using `DB.execute_sql` for lock/unlock may hit different pooled connections, so release fails ("not established by this thread"). Hold a single dedicated connection around the migration body.

### Pitfall 7: Python MySQL auth plugin
Dropping `--default-authentication-plugin=mysql_native_password` (deprecated in 8.0, removed in 8.4) makes PyMySQL need `PyMySQL[rsa]` for `caching_sha2_password` on non-TLS links. Keep the documented flag on 8.0.40; the 8.4 upgrade decision (R-42, deferred) must include this.

### Pitfall 8: The placeholder gate fires on legitimate code
`placeholder` is an HTML/JSX attribute; "mock"/"fake" occur in legitimate names. A naive grep gate trains people to bypass it. Use AST/token-aware checks (see Validation Architecture), require an inline `gate-ok: <reason>` for exceptions, and give the gate self-tests with known-bad and known-good fixtures.

### Pitfall 9: `go.mod` toolchain drift
Reference says `go 1.26.4`; host is 1.25.5 with `GOTOOLCHAIN=auto`. Use `go 1.25.0` (Gin 1.12.0 requires 1.25.0) and make CI fail if `go.mod` requires a newer toolchain than `go version`.

### Pitfall 10: ES client defaults hang health endpoints
Default ES client timeout is 10 s with retries; a stopped ES makes `/system/status` hang past the compose healthcheck timeout. Set `request_timeout=2`, `max_retries=0` for probes and run probes concurrently.

### Pitfall 11: Bind-mounted logs owned by root
`./ragflow-logs` created by Docker is root-owned; a non-root app user cannot write. Run the app with `user: "${UID:-1000}:${GID:-1000}"` or create the directory in preflight with correct ownership.

### Pitfall 12: `.gitignore` `.env*` swallows `.env.example`
`.env*` also ignores the file DEPLOY-11 needs committed. Add `!.env.example` (and `!docker/.env.example`). Also add `*.pem`, `*.key`, `ragflow-logs/`, `node_modules/`, `.venv/`, `bin/`, `web/dist/`. Current `.gitignore` has only `docs/apikey llm.md` and `.env` [VERIFIED].

### Pitfall 13: Vite dev proxy does not reproduce Nginx streaming/`^~` semantics
Generate both from the list; the SSE-safe directives (`proxy_buffering off`, `proxy_http_version 1.1`, `Connection ""`, 3600 s timeouts, no `text/event-stream` in `gzip_types`) go into `proxy.conf` now even though no SSE route exists yet [CITED: reference `docker/nginx/proxy.conf`; PITFALLS 10].

### Pitfall 14: GET_LOCK-guarded init plus Compose `restart: unless-stopped`
Do not give the `init` service a restart policy; a failing migration must fail the stack loudly.

## Code Examples

### Reference retry pool shape (documented pattern, copy and adapt)
```python
# Source: /home/logan78/desktop x/ragflow/api/db/db_models.py lines 259-318 (reference);
#         docs/08-database/transactions.md
class RetryingPooledMySQLDatabase(PooledMySQLDatabase):
    def __init__(self, *args, **kwargs):
        self.max_retries = kwargs.pop("max_retries", 5)
        self.retry_delay = kwargs.pop("retry_delay", 1)
        super().__init__(*args, **kwargs)

    def execute_sql(self, sql, params=None, commit=True):
        for attempt in range(self.max_retries + 1):
            try:
                return super().execute_sql(sql, params, commit)
            except (OperationalError, InterfaceError) as e:
                lost = (e.args and e.args[0] in (2006, 2013)) or isinstance(e, InterfaceError)
                if lost and attempt < self.max_retries:
                    self._handle_connection_loss()
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise
```
(`time.sleep` here is backoff in production code, not a test sleep; the no-sleep gate applies to test trees only.)

### Nginx generated shape
```nginx
# Generated by scripts/gen_routes.py from conf/routes.yaml - do not edit
location = /health                  { proxy_pass http://127.0.0.1:9384; include proxy.conf; }
location = /api/v1/system/ping      { proxy_pass http://127.0.0.1:9384; include proxy.conf; }
location = /api/v1/mcp              { proxy_pass http://127.0.0.1:9384; include proxy.conf; }
location ^~ /api/v1/auth/           { proxy_pass http://127.0.0.1:9384; include proxy.conf; }
location = /api/v1/system/healthz   { proxy_pass http://127.0.0.1:9380; include proxy.conf; }
location ^~ /api/                   { proxy_pass http://127.0.0.1:9380; include proxy.conf; }
location ^~ /v1/                    { proxy_pass http://127.0.0.1:9380; include proxy.conf; }
location /                          { root /ragflow/web/dist; try_files $uri $uri/ /index.html; }
```
Longest-prefix and `=`/`^~` precedence is what makes this order-independent [ASSUMED standard Nginx semantics; add a test that requests each documented path and asserts the answering engine].

### Compose dev override (sketch)
```yaml
# docker/docker-compose.dev.yml
services:
  es01:
    mem_limit: 2g
    environment:
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
      - cluster.routing.allocation.disk.watermark.low=1gb
      - cluster.routing.allocation.disk.watermark.high=750mb
      - cluster.routing.allocation.disk.watermark.flood_stage=500mb
  mysql:
    mem_limit: 640m
    command: >-
      --innodb-buffer-pool-size=128M --performance-schema=OFF --max_connections=200
      --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
      --default-authentication-plugin=mysql_native_password
```

### Go: Gin with envelope-safe defaults
```go
// Source: Gin docs pattern (CustomRecovery, NoRoute, NoMethod); envelope per D-13
engine := gin.New()
engine.HandleMethodNotAllowed = true
engine.Use(sourceHeader("go"), requestLogger(log), gin.CustomRecovery(func(c *gin.Context, _ any) {
    common.Fail(c, http.StatusInternalServerError, common.CodeExceptionError, "internal error")
}))
engine.NoRoute(func(c *gin.Context)  { common.Fail(c, 404, common.CodeNotFound, "not found") })
engine.NoMethod(func(c *gin.Context) { common.Fail(c, 405, common.CodeBadRequest, "method not allowed") })
```

### Python: Quart error mapping
```python
# Source: Quart/quart-schema documented hooks; envelope per D-13
@app.errorhandler(HTTPException)
async def _http(e):  return error_result(e.code, e.description), e.code
@app.errorhandler(RequestSchemaValidationError)
async def _val(e):   return error_result(RetCode.ARGUMENT_ERROR, "invalid request"), 400
@app.errorhandler(Exception)
async def _any(e):   log.exception("unhandled"); return error_result(RetCode.EXCEPTION_ERROR, "internal error"), 500
@app.after_request
async def _src(resp): resp.headers["X-API-Source"] = "python"; return resp
```
(`Quart`, `quart-schema` calls are from training and the reference; verify exact import names against the installed versions at implementation [ASSUMED].)

### Readiness wait (Python)
```python
def wait_until(predicate, timeout=60.0, interval=0.5, describe=lambda: ""):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last: return last
        time.sleep(interval)       # lives in test/helpers/, the one allowed polling site
    raise TimeoutError(f"condition not met in {timeout}s; last={last!r} {describe()}")
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Quart 0.20.0 (STACK.md "latest") | Quart 0.23.1 (needs Python >=3.13) | Consistent with D-16; fall back to reference pins if regressions |
| Peewee 3.x only | Peewee 4.5.2 exists | Stay `<4` until a compatibility check is done |
| `minio/minio` image | `pgsty/minio` (archived upstream) | Already decided (D-20); image has curl and mc |
| React 19 / Tailwind 4 defaults in `shadcn init` | Existing React 18 + Tailwind 3 projects keep working | Use v3-compatible components; do not run `init` expecting v4 |
| MySQL 8.0 | EOL 2026-04-30 per STACK/SUMMARY | Pin stays (D-17); upgrade needs approval |
| `elasticsearch` Docker Hub name | `docker.elastic.co/...` registry name | Matches the local image |

**Deprecated/outdated:** Flask/Gunicorn wording in `18-deployment/docker.md` (stale per D-15); `--default-authentication-plugin` (deprecated but valid on 8.0.40); the reference `go 1.26.4`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Peewee 4.x is not a drop-in for the documented 3.x patterns | Standard Stack | Low: staying on 3.19.0 is safe either way |
| A2 | `elasticsearch` Python client 9.x does not work against an 8.11 server | Standard Stack | Low: pinning 8.x is safe either way |
| A3 | `sonner` is the current shadcn toast component | Standard Stack | Low: swap component |
| A4 | New-image and volume sizes (builder images, app image, MySQL/ES volumes) | Host Budget | Medium: disk headroom shrinks; recheck with `docker system df` after first build |
| A5 | Typical RSS of the stack is 2.3-2.9 GB | Host Budget | Medium: measure with `docker stats` at the exit gate; adjust limits |
| A6 | `docker compose up --wait` behaviour with exited-0 one-shot services varies by version | Pattern 2 | Low: polling script is the primary path |
| A7 | MySQL TCP-based `mysqladmin ping` avoids the init-phase temp server | Pitfall 3 | Low: only affects readiness timing |
| A8 | Nginx `=`/`^~` precedence makes the generated table order-independent | Code Examples | Low: covered by routing test |
| A9 | `ModelIndex(name=)` can give Peewee indexes the documented `idx_*` names | Schema | Low: test by column coverage instead |
| A10 | Storing `schema.version` in `system_settings` is an acceptable use of a documented table | Pattern 6 | Low: record as deviation |
| A11 | Baseline `user.email` unique index avoids a later data migration | Schema | Low-Medium: confirm in Phase 2 research |
| A12 | MySQL perf tuning (`performance-schema=OFF`, 128 MB buffer pool) saves a few hundred MB | Host Budget | Low |
| A13 | `numpy.f2py.diagnose.run_command` is gone in numpy `main` (the file now contains a `run()` diagnostic), so the documented PoC may not reproduce on current numpy | Security | Medium: the regression test must use a gadget present in the pinned numpy, chosen at implementation time |
| A14 | Quart/quart-schema exact hook names and import paths | Code Examples | Low: verify against installed versions |
| A15 | Running the app as the unprivileged host UID fixes log permissions | Pitfall 11 | Low |

## Open Questions

1. **`/system/healthz` and `/system/status`: literal or `/api/v1`-prefixed?**
   - What we know: SYS-06/07, ROADMAP criterion 4 and D-08 write `/system/healthz` and `/system/status`. `docs/04-api/system-api.md` lists them blueprint-relative; the reference mounts them at `/api/v1/system/healthz|status`; API-04 says versioned routes. A Nginx route sending literal `/system/*` would not exist in the reference (its Python location is `^/(v1|api)`).
   - What's unclear: whether a verifier tests the literal path.
   - Recommendation: serve the canonical `/api/v1/system/{healthz,status}` AND the literal `/system/{healthz,status}` as one route-list entry (`also:`), record it as an explicit deviation from D-09's "no aliases" because it is the requirement's own text, and let plan-check confirm. Cheapest to reverse: delete the `also` line.

2. **`/system/status` is public in Phase 1.**
   - What we know: the reference wraps it in `login_required`; login is Phase 2; criterion 4 requires it to report live state.
   - Recommendation: public in Phase 1, minimal payload (status + elapsed only), flagged `auth: jwt` in `routes.yaml` with a `public_until_phase: 2` marker so Phase 2 flips it and its route-enumeration 401 test then covers it.

3. **App container healthcheck target (DEPLOY-14).**
   - Recommendation: one script probing Go `/health` and Python `/api/v1/system/healthz` (both must be 200) every 10 s; Nginx itself is covered because the probe goes through `127.0.0.1:80/health` and `/api/v1/system/healthz`.

4. **MySQL account.** The reference connects as `root`. Recommendation: create an application user via `MYSQL_USER`/`MYSQL_PASSWORD`/`MYSQL_DATABASE` entrypoint variables (least privilege), keep `init.sql` for charset/database settings (DEPLOY-15). Record as a deviation from `service_conf.yaml`.

5. **API-12 and API-13 are only partly buildable now.**
   - API-12: `--api` and `--migrate` are real; `--admin` (Phase 8), `--ingestor` and `--syncer` (v2 mirrors per D-01) must not be stubbed. Recommend: the flags parse, and an unbuilt mode exits non-zero with a message naming its phase and the BLOCKERS.md entry. The placeholder gate must be configured so this deliberate refusal is not flagged and not worded "not implemented".
   - API-13: logger, DB init verification and boot hooks exist; superuser init needs the user model and hashing (Phase 2); plugin load (Phase 7); `update_progress` daemon (Phase 4). Record the split in the traceability notes.

6. **SEC-05 wording vs R-38.** REQUIREMENTS says "whitelisted modules (`numpy`, `rag_flow`)". Recommendation per D-25: no pickle on untrusted data at all; if any helper is kept, allow-list exact `(module, name)` pairs and ship a regression test with a gadget that exists in the pinned numpy. Phase 1 deliverable is the CI gate plus that regression test.

7. **CI runner.** The repo has no remote and no `.github/`. Recommendation: all gates are plain scripts under `scripts/ci/` invoked by a `Makefile` target (`make ci`), plus a committed `.github/workflows/ci.yml` that calls the same target; the workflow cannot be executed on this host (no remote, no `act`) so record it in BLOCKERS.md as "authored, unverified here".

8. **Default `.env` secrets.** Docs list default passwords (`infini_rag_flow`). SEC-04 forbids hard-coded secrets. Recommendation: `.env.example` has secret variables empty; `scripts/init_env.sh` generates random values into an ignored `.env`; compose uses `${VAR:?message}` to fail fast. Record as a deviation (docs defaults are example values).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | compose stack | yes (user in `docker` group, socket `srw-rw---- root:docker`) | 29.1.3 | - |
| Docker Compose | compose stack | yes | v5.0.0 (`docker compose`; no `docker-compose`) | - |
| Go | Go server, tests | yes, `/usr/local/go/bin/go` | 1.25.5 (STACK.md's 1.26.4 is wrong) | `go.mod go 1.25.0` |
| gcc | `go test -race`, cgo tier | yes | present | - |
| Python | pytest, tools | system 3.10.12 (do not use); uv-managed 3.13.11, 3.12.12, 3.14.2 installed | 3.13.11 via uv | - |
| uv | Python env | yes | 0.9.18 (latest 0.12.23) | - |
| Node / npm | SPA, vitest | yes | 22.23.3 / 10.8.2 | - |
| pnpm | not required | no | - | use npm |
| make | `make ci` | yes | 4.3 | scripts directly |
| git | repo | yes | 2.34.1 | - |
| curl, jq | scripts | yes | curl 7.81.0, jq present | - |
| ruff | Python lint gates | yes | 0.14.5 | pin in dev deps |
| redis-cli (host) | debugging only | yes | - | `docker exec` |
| nginx (host) | not required (runs in container; `nginx -t` via `nginx:alpine`) | no | image has 1.31.6 | `docker run --rm nginx:alpine nginx -t` |
| shellcheck, hadolint, golangci-lint, mysql client, act | optional lint | no | - | skip; do not install |
| google-chrome / Playwright chromium cache | optional browser smoke | yes | `/usr/bin/google-chrome`, chromium-1243 cache | vitest-only |
| Ollama | Phase 3 | binary yes, server not running, no models | - | compose-contained Ollama (D-31) |
| GPU | `gpu` profile | no | - | record in BLOCKERS.md |
| Images (local) | compose | mysql:8.0.40, valkey/valkey:8 (8.1.10), pgsty/minio:RELEASE.2026-03-25T00-00-00Z, docker.elastic.co/elasticsearch/elasticsearch:8.11.3, nginx:alpine (1.31.6) | all present | - |
| Images (registry, not pulled) | builds | golang:1.25-alpine, node:22-alpine, python:3.13-slim(-bookworm), nginx:1.31-alpine tags exist; `infiniflow/infinity:v0.7.2-x64-v3` and `v0.7.3-x64-v3` exist (about 322 MB compressed) | verified via Docker Hub API | - |
| Network | registries | yes (Docker Hub, PyPI, npm, Go proxy reachable) | - | - |

**Free disk 5.5 GB, free RAM about 5.2 GB, `vm.max_map_count` 65530** (see Host Budget).
**Host ports in use:** 80, 631, 5432 (loopback), 6379 (loopback), 9009, 27017, plus a few ephemeral ports. Free and needed: 3306, 8080, 9000, 9001, 9200, 9380-9384.
**Missing with no fallback:** none.
**Missing with fallback:** pnpm (npm), shellcheck/hadolint (skip), host nginx (container `nginx -t`).
**User actions still open:** free disk beyond Phase 1 headroom; optionally `sudo sysctl -w vm.max_map_count=262144` and persist it (soft blocker, see Host Budget); real model source for Phase 3.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json`.

### Test Framework
| Property | Value |
|----------|-------|
| Python | pytest 9.1.1 + pytest-asyncio 1.4.0 + pytest-xdist 3.8.0 + pytest-cov 7.1.0 + httpx 0.28.1, run via `run_tests.py` (flags `-p/--parallel`, `-t/--test`, `-m/--markers`, `-i/--ignore`, coverage) per `docs/19-testing/test-architecture.md`; config in `pyproject.toml [tool.pytest.ini_options]` (`--strict-markers`, markers `unit`, `integration`, `e2e`, `smoke`) |
| Go | stdlib `testing` + `httptest` (+ testify optional); `go test -race ./internal/...`; tiers by build tag: default unit, `integration`, `e2e`, `manual`, and the built-in `cgo` constraint (satisfied by `CGO_ENABLED=1`, not passed via `-tags`) |
| Frontend | vitest 5.0.3 + jsdom 30.1.2 + @testing-library/react 16.3.3, `npm run test` in `web/` |
| Shell/CI gates | plain Python scripts under `scripts/ci/` with their own pytest self-tests (known-bad fixtures must fail the gate) |
| Config files | `pyproject.toml`, `go.mod` (+ build tags in files), `web/vitest.config.ts`, `scripts/ci/tests/` |
| Quick run | `uv run python run_tests.py -m unit` ; `go test -race ./internal/...` ; `cd web && npm run test -- --run` |
| Full suite (needs live stack) | `scripts/wait_stack.sh && uv run python run_tests.py -m "integration or e2e" && go test -tags=integration,e2e ./... && cd web && npm run test:live` |

### Readiness, not sleeps
- `scripts/wait_stack.sh`: polls `docker compose ps --format json` until every long-running service reports `healthy` and `init` has exited 0, then polls `GET /health` and `GET /api/v1/system/healthz` through the ingress; prints the last observed state on timeout. Bounded by a total timeout, interval about 2 s.
- One `wait_until(predicate, timeout, interval)` helper per language (`test/helpers/wait.py`, `internal/testutil/wait.go`, `web/src/test/wait-until.ts`); these are the only places a poll delay may live.
- CI gate `check_no_sleep.py` fails on `time.sleep`, `asyncio.sleep`, `time.Sleep`, `setTimeout`-based waits under test trees, except the three helper files (named allow-list).
- ES near-real-time is not exercised in Phase 1 (no indexing), but the helper contract is fixed here.
- Isolation: each test that writes data creates its own rows with unique ids and removes them; no shared mutable fixture. Destructive tests (stop a dependency, `KILL CONNECTION`) are marked `serial` and excluded from `-p`.

### Phase Success Criteria -> Verification
| # | Criterion | How verified against the live stack | Automated command |
|---|-----------|------------------------------------|-------------------|
| 1a | DECISIONS.md has a resolution and status for R-01..R-52 | `check_decisions.py` parses `.planning/research/SUMMARY.md` for R-IDs and `.planning/DECISIONS.md`; asserts each id appears once with a status in {`user-confirmed`, `accepted (auto, not user-reviewed)`, `open`}; asserts R-03, R-17, R-18, R-48 are `user-confirmed` | `uv run python scripts/ci/check_decisions.py` |
| 1b | BLOCKERS.md exists; `.gitignore` excludes `docs/apikey llm.md` and `.env*` | pytest: `git check-ignore -q "docs/apikey llm.md" .env .env.local`; `git check-ignore -q docker/.env.example` must FAIL (example stays tracked) | `uv run pytest test/unit_test/test_repo_hygiene.py` |
| 1c | CI gates fail on placeholder/fake in production tree and on untrusted pickle | Run each gate against a temporary tree containing a known-bad file (exit != 0) and a known-good file (exit 0); ruff `S301/S403` fixture for pickle | `uv run pytest scripts/ci/tests` |
| 2a | Preflight reports disk, `vm.max_map_count`, RAM, ports with actionable messages | Run `scripts/preflight.sh` with thresholds overridden by env (e.g. `PREFLIGHT_MIN_DISK_GB=9999`) and assert non-zero exit and message text for each check; assert success path with real thresholds | `uv run pytest test/unit_test/test_preflight.py` |
| 2b | `docker compose down -v && up` reaches healthy inside the recorded memory budget | Exit-gate script: down -v, up -d, `wait_stack.sh`, then `docker stats --no-stream` -> assert each container under its `mem_limit` and total under the recorded budget; write measured figures to DECISIONS.md | `scripts/clean_room.sh` (manual gate, minutes) |
| 3 | Schema from empty by one owner; Go `--migrate` verify passes | `docker compose run --rm init` on a fresh volume; assert 38 tables in `information_schema.tables`, the 7 documented indexes by column coverage, `schema.version` set; then run Go `--migrate` and assert exit 0; negative test: drop a column in a scratch database and assert `--migrate` exits non-zero | `uv run pytest -m integration test/integration/test_schema.py` ; `go test -tags=integration ./internal/dao -run Migrate` |
| 4a | Go answers `/health`, `/api/v1/system/ping`, `/api/v1/language` with `X-API-Source: go` | httpx/Go HTTP against the ingress, assert header and body | `uv run pytest -m e2e test/testcases/test_routing.py` |
| 4b | Python answers `/system/healthz`; `/system/status` reports DB/Redis/storage/docstore | assert `X-API-Source: python`, four named checks `ok`; serial test stops one dependency container and asserts 503 envelope then restores | same file, `-m "e2e and serial"` |
| 4c | Language route names the engine | ingress `/api/v1/language` -> `go`; direct `127.0.0.1:9380/api/v1/language` -> `python` | same |
| 4d | One envelope everywhere, including unhandled errors | live: 404/405/400 on both families; in-process: panic/raise route on both app factories | `test_envelope.py`, `go test ./internal/router -run Envelope` |
| 4e | Routing table honoured | for every `routes.yaml` entry, request via ingress and assert `X-API-Source`; enumerate `app.url_map` and `engine.Routes()` and assert owners; regenerate Nginx/Vite files and `git diff --exit-code` | `test_route_ownership.py`, `scripts/ci/check_generated_clean.sh` |
| 5a | SPA shell loads through Nginx with lazy routes | integration: `GET /` returns HTML; every `<script src>`/`<link href>` in it returns 200 with correct content type; a deep link (`/datasets`) returns `index.html`; the route table build emits more than one JS chunk | `cd web && npm run test:live -- spa-shell` |
| 5b | HTTP client surfaces non-zero envelope code as error notification | vitest + jsdom against the ingress: request `/api/v1/does-not-exist` (real 404 envelope from Python), assert the sonner toast text and the thrown error carries `code`; unit tier for success unwrapping and 401 token purge | `npm run test:live -- http-client` |
| 5c | Three harnesses green against the live stack | the full-suite command above | CI gate / `make test-live` |

### Requirement -> Test Map (Phase 1)
| Req | Behaviour | Type | Command | Exists |
|-----|-----------|------|---------|--------|
| DEPLOY-02/03/04 | compose parses with each profile; base services healthy; `--profile infinity config` valid (never pulled) | integration | `docker compose -f ... config -q` + `wait_stack.sh` | Wave 0 |
| DEPLOY-11 | every variable in `18-deployment/environment-variables.md` appears in `.env.example` | unit | `pytest test/unit_test/test_env_catalog.py` | Wave 0 |
| DEPLOY-12 | `nginx -t` passes in `nginx:alpine`; response headers show no buffering for proxied paths; TLS variant serves HTTPS with a generated self-signed cert (`curl -k`) | integration | `pytest -m integration test/integration/test_nginx.py` | Wave 0 |
| DEPLOY-13 | only documented ports published; single network `ragflow` with aliases | integration | `docker compose config` parse + `docker port` assertions | Wave 0 |
| DEPLOY-14 | container reports healthy within 10 s interval | e2e | `docker inspect --format '{{.State.Health.Status}}'` via wait | Wave 0 |
| DEPLOY-15 | database exists with utf8mb4 after first boot | integration | SQL check | Wave 0 |
| DEPLOY-16 | log files appear in `./ragflow-logs` with expected names and are readable by the host user | e2e | file existence poll with `wait_until` | Wave 0 |
| DATA-01/02/05/06 | see criterion 3; plus Peewee `schema.json` vs GORM parsed schema unit contract (no DB) | integration + unit | as above | Wave 0 |
| DATA-03 | `KILL CONNECTION <id>` then query succeeds after retry | integration (serial) | `pytest -m "integration and serial" test_retry.py` | Wave 0 |
| DATA-04 | exception inside `DB.atomic()` rolls back both writes; same for GORM `Transaction` | integration | pytest + go test `-tags=integration` | Wave 0 |
| DATA-08 | two sessions contend on `GET_LOCK`; second times out; release on same connection | integration | pytest | Wave 0 |
| API-01..05, API-09..11 | routing, envelope, versioned prefixes, `X-API-Source`, error envelope, request log line (method, path, status, duration) captured from the log file/stdout, CORS allow-list (allowed origin echoed, disallowed not, never `*` with credentials) | e2e | `test_routing.py`, `test_envelope.py`, `test_cors.py`, `test_request_log.py` | Wave 0 |
| API-06 | layering: handler modules import only services, services only DAO (import-linter style check or AST test) | unit | `pytest test_layering.py`; Go `go vet` + small package-import test | Wave 0 |
| API-07 | schema-validated body rejected before service runs (test-only route in test tree; SQLi probe string returns 400) | unit | in-process app tests | Wave 0 |
| API-08 | `GET /api/v1/openapi.json` valid OpenAPI 3 and lists the system routes; TS types generate and compile | e2e + frontend | `pytest`, `npm run gen:api && npm run typecheck` | Wave 0 |
| API-12 | each Go flag parses; `--migrate` works; unbuilt modes exit non-zero with the documented message | unit | `go test ./cmd/...` | Wave 0 |
| API-13 | boot order logged: logger -> DB verify -> hooks -> serve | integration | pytest reading logs | Wave 0 |
| SYS-01..07 | each route's status, body shape and engine; status reports four dependencies | e2e | `test_system_routes.py` | Wave 0 |
| UI-01 | route table is lazy (`React.lazy`), layout wrappers render; build output has multiple chunks | unit + integration | vitest + `vite build` assertion | Wave 0 |
| UI-03 | token injection, envelope unwrap, error toast, 401 purge | unit + live | vitest | Wave 0 |
| SEC-04 | no secret literal in repo (scan for known default `infini_rag_flow` outside docs/examples), logs redact `password/api_key/authorization`, `${VAR:?}` makes compose fail when a secret is unset | unit + integration | `pytest test_secrets.py` | Wave 0 |
| SEC-05 | gate rejects `pickle.loads`; allow-list helper (if present) rejects `os.system` and a gadget present in pinned numpy | unit | `pytest scripts/ci/tests test/unit_test/test_unpickle.py` | Wave 0 |
| SEC-10 | ruff `S608/S602/S605` clean; probe strings (`' OR 1=1 --`, `; rm -rf`) on any validated field return 400 and never reach SQL | unit | `ruff check --select S` + pytest | Wave 0 |
| TEST-01..04, TEST-10 | the harnesses themselves: `run_tests.py -p` works; `go test -race` runs with CGO; each Go tier tag compiles and runs at least one real test (the `cgo` tier is thin in Phase 1: a build-constraint file proving the tier mechanism, with the first real cgo test arriving with native parsers); `npm run test` runs | meta | CI | Wave 0 |

### Sampling Rate
- **Per task commit:** the quick-run commands above (seconds, no stack).
- **Per wave merge:** bring the stack up once, run the full suite.
- **Phase gate:** `scripts/clean_room.sh` (down -v, up, full suite, measured memory recorded), run three times in a row to catch flakes (PITFALLS 13), then `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `pyproject.toml` with pytest config, markers, ruff rules (`S301,S403,S608,S602,S605,S307,S102,FIX001,FIX002`), uv lock
- [ ] `run_tests.py` runner per docs flags
- [ ] `test/helpers/wait.py`, `internal/testutil/wait.go`, `web/src/test/wait-until.ts`
- [ ] `scripts/ci/` gates with fixture-based self-tests; `check_generated_clean.sh`
- [ ] `scripts/wait_stack.sh`, `scripts/preflight.sh`, `scripts/clean_room.sh`
- [ ] one test file per Go tier tag; `web/vitest.config.ts` with a `live` project
- [ ] Framework installs: `uv sync`, `go mod tidy`, `npm ci`

## Security Domain

`security_enforcement` is not set to false in `.planning/config.json`, so it is enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (Phase 2); Phase 1 only wires middleware seams and marks routes `public` | route list `auth` field, default-deny enumeration test arrives in Phase 2 |
| V3 Session Management | No (Phase 2) | - |
| V4 Access Control | Minimal: dependency detail not exposed on a public status route | minimal payload |
| V5 Input Validation | Yes | quart-schema + pydantic; Gin `binding` tags; parameterised SQL only |
| V6 Cryptography | No new crypto; no hand-rolled secrets handling | env-supplied secrets; provider-key encryption is Phase 3 |
| V7 Error handling / logging | Yes | one envelope; no stack traces to clients; redacting log filter / zap wrapper |
| V10 Malicious code / V14 Config | Yes | no pickle on untrusted data, no `shell=True`, secrets from env, pinned versions, `.gitignore` for credentials |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unsafe deserialization (documented numpy-whitelist unpickler reproduces a known bypass) | Tampering / EoP | Ban pickle on untrusted data; ruff `S301/S403`; exact-pair allow-list only if unavoidable; regression test with a gadget valid in the pinned numpy |
| SQL injection | Tampering | Peewee/GORM parameters; ruff `S608`; no f-string SQL |
| Command injection | EoP | ruff `S602/S605`; no `shell=True`; Go `exec.Command` without `sh -c` of user data |
| Secret leakage in git/logs/inspect | Info disclosure | `.gitignore` (`docs/apikey llm.md`, `.env*` with `!.env.example`, `*.pem`); empty secret defaults; `${VAR:?}`; redaction; note healthcheck env visibility in `docker inspect` |
| Wildcard CORS with credentials | Spoofing | configurable allow-list, default same-origin (D-14); test asserts no `*` |
| Info disclosure via public status route | Info disclosure | status+elapsed only, no hosts or exception strings; auth added in Phase 2 |
| Exposed infrastructure ports | Info disclosure | publish MySQL/Valkey/MinIO/ES only on `127.0.0.1` in dev; document ports |
| Exposed Docker socket | EoP | not mounted in Phase 1 (sandbox is later) |
| Supply chain (litellm malicious releases 1.82.7/1.82.8 per STACK.md) | Tampering | exact pin `litellm==1.84.0` when added in Phase 3; lockfile review checkpoint now |

## Requirement Coverage Caveats

- **API-12:** `--admin`, `--ingestor`, `--syncer` have no documented component to run yet (admin Phase 8; ingestor/syncer are Go mirror engines deferred to v2 under D-01). Phase 1 delivers real `--api`/`--migrate` and honest non-zero refusals for the rest, recorded in BLOCKERS.md; this is "complete with blocker" for that sub-clause, not "complete".
- **API-13:** superuser init (Phase 2), plugin load (Phase 7) and background daemons (Phase 4+) cannot exist yet. Same treatment.
- **SEC-05:** satisfied by deviation (R-38), not by the literal requirement text.
- **DEPLOY-12 TLS:** verifiable only with a self-signed certificate generated by a script into an ignored directory; real certificate handling is Phase 8.
- **DEPLOY-14 and TEST-04 `cgo`:** thin in Phase 1 as described.

## Suggested Register Additions (for DECISIONS.md, proposed R-53..)

| ID | Topic | Resolution | Status |
|----|-------|------------|--------|
| R-53 | Go prefix collisions with Python-documented routes | Exact-match Go locations for `/api/v1/system/*`, `/api/v1/mcp`, `/api/v1/users` | accepted (auto, not user-reviewed) |
| R-54 | Literal `/system/*` probe paths vs `/api/v1/system/*` | Serve both from one entry (Open Question 1) | open |
| R-55 | Public `/system/status` until Phase 2 | Minimal payload, auth in Phase 2 | accepted (auto) |
| R-56 | ES image reference and dev watermarks | `docker.elastic.co/elasticsearch/elasticsearch:8.11.3`; absolute low watermarks in dev override | accepted (auto) |
| R-57 | Go toolchain | `go 1.25.0` (host 1.25.5), not the reference's 1.26.4 | accepted (auto) |
| R-58 | Peewee major | `<4`; PyMySQL auth plugin stays `mysql_native_password` on 8.0.40 | accepted (auto) |
| R-59 | Compose project name and host ports | Unique `name:`; ingress 8080, Redis 6380 (80 and 6379 occupied) | accepted (auto) |
| R-60 | Schema column sourcing | Documented columns exact; all others from reference model per table; no invented columns | accepted (auto) |
| R-61 | MySQL app user and `.env` secret generation | Least-privilege user; empty secret defaults generated by script | accepted (auto) |
| R-62 | `vm.max_map_count` as warning-with-override | Fail by default; explicit recorded override | accepted (auto) |
| R-63 | HTTP status mirrors error class in addition to envelope code | Deviation from reference's HTTP-200 errors | accepted (auto) |

## Sources

### Primary (HIGH confidence)
- `docs/08-database/*` (all 8 files), `docs/18-deployment/*`, `docs/04-api/{system-api,endpoint-catalog,api-overview,mcp-api,user-api,tenant-api,stats-api}.md`, `docs/03-backend/{entry-points,middleware}.md`, `docs/19-testing/*`, `docs/20-security/{file-security,secrets,api-security}.md`, `docs/02-frontend/{api-client,routing,directory-structure}.md`, `docs/apis.md` lines 1-139, `docs/spec.md`
- `.planning/{PROJECT,REQUIREMENTS,STATE,ROADMAP}.md`, `.planning/research/{SUMMARY,ARCHITECTURE,PITFALLS,STACK}.md`, `01-CONTEXT.md`
- Reference repo (read-only): `api/db/db_models.py`, `internal/dao/migration.go`, `internal/router/router.go`, `docker/docker-compose-base.yml`, `docker/nginx/*`, `docker/service_conf.yaml.template`, `go.mod`, `pyproject.toml`, `uv.lock`, `common/constants.py`, `internal/common/error_code.go`, `SECURITY.md`
- Host probes this session: `docker --version`, `docker compose version`, `docker images`, `docker system df`, `docker ps -a`, `docker logs ragflow-es01`, old container health logs, short `--network none` containers to list tools in `pgsty/minio`, `valkey/valkey:8`, ES and nginx images, `ss -ltn`, `df`, `free`, `sysctl`
- Registry queries: PyPI JSON API, npm registry, `proxy.golang.org`, Docker Hub tags API (2026-10-05)
- elastic.co: modules-cluster (watermark defaults, `threshold_enabled`), bootstrap-checks (single-node evades checks)
- ui.shadcn.com/docs/tailwind-v4 (Tailwind v3 + React 18 remain supported)
- pypi.org/project/PyMySQL (`PyMySQL[rsa]` for sha2 auth)

### Secondary (MEDIUM confidence)
- numpy `main` `f2py/diagnose.py` fetched from GitHub raw (shows `run()` only; the documented `run_command` is not in that file)

### Tertiary (LOW confidence)
- Resource estimates for images not yet built and RSS of the running stack (marked `[ASSUMED]`)
- Context7 was not available; Quart, quart-schema, Gin and Compose API details are from training plus the reference and must be re-checked against installed versions

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM-HIGH. Versions read from registries today; compatibility between newest Quart/quart-schema/GORM and the reference patterns is untested (fallback pins given).
- Architecture: HIGH for route collisions and init ordering (derived from docs and the reference); MEDIUM for Compose `--wait` behaviour.
- Schema: HIGH for what the docs do and do not specify; MEDIUM for supplemental columns (reference-derived).
- Host budget: HIGH for measured values; MEDIUM-LOW for estimates of unbuilt images and runtime RSS.
- Pitfalls: HIGH where backed by prior-run evidence on this host.

**Research date:** 2026-10-05
**Valid until:** 2026-11-04 for pins (registries move weekly; re-run `npm view`/`pip index`/`go list -m` at lock time); host facts are valid until the user frees disk or changes sysctl.
