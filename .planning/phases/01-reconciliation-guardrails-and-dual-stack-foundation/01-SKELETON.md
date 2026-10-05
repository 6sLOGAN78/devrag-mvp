# Walking Skeleton — devRag

**Phase:** 1
**Generated:** 2026-10-05

## Capability Proven End-to-End

A developer runs the documented local command (`make init-env && make up`, wrapped by `scripts/clean_room.sh`) and opens `http://127.0.0.1:8080/`: the SPA "System status" page, served by Nginx, shows live health of the Go API and the Python API (database, Redis, storage, doc store), each card naming the answering engine from the `X-API-Source` header. Clicking "Refresh status" re-queries both servers through the same ingress. The schema version that the one-shot `init` job wrote to MySQL (`system_settings.schema.version`) is read back by Go at `/api/v1/system/version`.

This touches every layer once: scaffold, Nginx routing, one real DB write (init migration), one real DB read (Go version route and both health probes), one real UI interaction (Refresh status), and a dev deployment (Docker Compose).

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Frontend | React 18.3 + TypeScript + Vite 7 + React Router 7 + TanStack Query + Axios + Zustand + Tailwind 3.4 + shadcn/ui (new-york, hand-written `components.json`) | docs/00-overview/technology-stack.md, D-19; UI contract in 01-UI-SPEC.md |
| Python server | Quart on Hypercorn, quart-schema (OpenAPI), quart-cors, Peewee 3.x + PyMySQL, Python 3.13 via uv | D-15, D-16, D-10 |
| Go server | Gin, GORM (verify-only, AutoMigrate never called), zap, viper, go-redis; `go 1.25.0` | D-01, D-10, R-57 |
| Data layer | MySQL 8.0.40 (`MYSQL_IMAGE`), Valkey 8, MinIO (pgsty), Elasticsearch 8.11.3 | D-03, D-17, D-18, D-20 |
| Schema ownership | Peewee models + versioned migrations run by a one-shot `init` service before either server; `conf/schema.json` exported from Peewee generates the GORM entities; Go `--migrate` only verifies | D-10, D-11, D-12 |
| Ingress and ownership | One Nginx; `conf/routes.yaml` is the single route list and generates the Nginx config and the Vite proxy file; exact-match (`=`) and `^~` locations only; Go owns explicit routes, Python is the catch-all; no Go-to-Python proxying | D-04..D-09, R-53 |
| Response contract | `{code, message, data}` defined once in Python, once in Go, once as a TS interface; real HTTP status mirrors the error class; unhandled errors use the same envelope | D-13, R-63 |
| Auth | Not built. Routes carry an `auth` marker in `routes.yaml`; Phase 2 enforces it | Phase boundary |
| Deployment target | Docker Compose project `devrag-stack`, network `ragflow`, one app image (Nginx + Go + Python under tini) plus infra services; ingress on host port 8080 | D-24, R-59 |
| Config and secrets | `docker/.env.example` (empty secrets) -> `scripts/init_env.sh` generates ignored `docker/.env` -> `conf/service_conf.yaml.template` rendered by `scripts/render_conf.py`; compose uses `${VAR:?}` | D-28, SEC-04, R-61 |
| Directory layout | docs/00-overview/repository-map.md and docs/02-frontend/directory-structure.md: `api/ common/ cmd/ internal/ web/ conf/ docker/ scripts/ test/` | D-23 |
| Test harnesses | pytest via `run_tests.py`; `go test` with tiers `integration`, `e2e`, `manual`, `cgo`; vitest with `unit` and `live` projects; one `wait_until` per language, no fixed sleeps | D-30, TEST-01..04, TEST-10 |
| Guardrails | `make ci` runs `scripts/ci/check_*` (decisions, placeholders, pickle, no-sleep, secrets, generated-files); each gate has known-bad fixtures | D-25, D-26, D-27 |

## Stack Touched in Phase 1

- [x] Project scaffold (uv/pyproject, go.mod, web/package.json, Makefile, lint and test runners)
- [x] Routing: Nginx generated from `conf/routes.yaml`; `/health`, `/api/v1/system/*`, `/api/v1/language` to Go; `/system/*` and the `/api/`, `/v1/` catch-all to Python
- [x] Database: one real write (init migration records `schema.version`) and real reads (Go version route, health probes, Python status)
- [x] UI: "Refresh status" button wired through the real HTTP client to both servers
- [x] Deployment: `docker compose` project `devrag-stack` brought up from empty volumes by `scripts/clean_room.sh`

## Out of Scope (Deferred to Later Slices)

- Login, registration, tokens, tenants, roles, auth guard (Phase 2). `/system/status` is public until then and is flagged in `routes.yaml`.
- Model providers, datasets, upload, object-storage keys (Phase 3).
- Parsing, chunking, embedding, task executor, Redis Streams consumers (Phase 4).
- Retrieval, chat, SSE endpoints (Phase 5; the Nginx SSE-safe directives exist now, no SSE route does).
- Deep parsing, agents, canvas, sandbox, admin servers, ingestor/syncer, CLI, Infinity adapter, billing (Phases 6-8; D-02 only requires not foreclosing billing).
- i18n, theming beyond light/dark/system, feature navigation. The shell shows only routes that exist.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering the decisions above:

- Phase 2: a user registers, logs in through Go, and the same token works on Python; tenants are isolated.
- Phase 3: a tenant connects a real model provider, creates a dataset with a real index, and uploads documents.
- Phase 4: an uploaded document becomes searchable chunks through a reliable background worker.
- Phase 5: a question about an uploaded document yields a streamed, cited answer (Core Value gate).
- Phase 6: deep parsing and the remaining chunkers.
- Phase 7: agents and workflows on a canvas.
- Phase 8: Go surface completion, CLI, integrations, billing, Infinity, production image.
