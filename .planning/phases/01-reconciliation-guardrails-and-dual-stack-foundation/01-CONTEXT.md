# Phase 1: Reconciliation, Guardrails and Dual-Stack Foundation - Context

**Gathered:** 2026-10-05
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers three things and nothing else:

1. **Reconciliation** — `.planning/DECISIONS.md` recording a resolution and status for every row of the research register (R-01..R-52 in `.planning/research/SUMMARY.md`), plus the `.planning/BLOCKERS.md` convention.
2. **Guardrails** — CI gates that fail on placeholders/fakes in production trees and on pickle loads of untrusted data; `.gitignore` covering `docs/apikey llm.md` and `.env*`; a host preflight script.
3. **Dual-stack foundation** — repo skeleton; Docker Compose bringing MySQL, Valkey, MinIO and Elasticsearch to healthy; one shared schema created from empty by a single migration owner; Go Gin and Python Quart servers both answering health/system routes through one Nginx ingress with one response envelope; SPA shell loading through Nginx; pytest, `go test` and frontend component harnesses running green against the live stack.

Requirements: DEPLOY-02..04, DEPLOY-11..16, DATA-01..06, DATA-08, API-01..13, SYS-01..07, UI-01, UI-03, SEC-04..05, SEC-10, TEST-01..04, TEST-10.

Not in this phase: any auth, user, tenant, dataset, upload, model, or pipeline behaviour (Phases 2+). Auth middleware is wired only as far as API-01..13 require; login itself is Phase 2.

</domain>

<decisions>
## Implementation Decisions

All decisions below were auto-selected (`--auto`: recommended option) from the research register unless marked **USER-CONFIRMED**. Auto-selected rows are recorded in `DECISIONS.md` with status `accepted (auto, not user-reviewed)` so the user can audit and overturn them.

### Scope decisions (USER-CONFIRMED 2026-10-05)
- **D-01 (R-03):** Go Gin builds only the routes the endpoint catalogue assigns it (health/system, auth, user, tenant, search bots, MCP, CLI). Python owns every RAG/ML pipeline. Go mirror engines are v2 and are never stubbed.
- **D-02 (R-48):** Billing from `docs/apis.md` (BILL-01..10) is in v1, scheduled in Phase 8. Phase 1 does nothing for it except not foreclose it.
- **D-03 (R-17/R-18):** Elasticsearch is the default doc store for compose and tests; Infinity is the second adapter (Phase 8). All other engines are v2.

### Ports, routing and server ownership
- **D-04 (R-01):** Ports follow `docs/18-deployment`: Python API 9380, Python admin 9381, MCP 9382, Go admin 9383, Go API 9384; sandbox 9385 and deepdoc 9390 reserved.
- **D-05 (R-02):** Route ownership is derived from `docs/04-api/endpoint-catalog.md`: explicit Go prefixes (`/health`, `/api/v1/system/`, `/api/v1/language`, `/api/v1/auth/`, `/api/v1/users`, `/v1/user/`, `/v1/tenant/`, `/api/v1/searchbots/`, `/api/v1/mcp`); Python is the catch-all. One route list is the single source; the Nginx config and the Vite dev proxy are both generated from it.
- **D-06 (R-04):** No Go-to-Python proxying. A Go handler that only forwards to Python is treated as drift. How Go search bots reach retrieval is a Phase 8 research question.
- **D-07 (R-05):** Python owns upload, parse trigger and public chatbot routes (relevant here only for the route table).
- **D-08 (R-29):** Go serves `/health` and `/api/v1/system/ping`; Python serves `/system/healthz` and `/system/status`. Health reports each dependency (database, Redis, storage, doc store), not just liveness. Every response carries `X-API-Source`.
- **D-09 (R-25):** `endpoint-catalog.md` plus `apis.md` lines 1–139 are the canonical paths. Legacy aliases are not served.

### Schema and data layer
- **D-10 (R-06):** One schema writer: Peewee models own DDL and migrations, run as a one-shot init step before either server starts. GORM maps the result with AutoMigrate off; Go `--migrate` only verifies.
- **D-11 (R-31):** Table and column names follow `docs/08-database/`.
- **D-12 (R-20):** Follow the documented DDL; tenant isolation is transitive through `knowledgebase.tenant_id` and `user_tenant`. No `tenant_id` column is invented on `document`/`task`.

### API contract
- **D-13 (R-24):** Response envelope is `{code, message, data}`, defined once per language and once as a TS interface. Unhandled errors use the same envelope. This contradicts `04-api/api-overview.md` (`retcode/retmsg`) and is recorded as a deviation with rationale.
- **D-14 (R-32):** CORS is a configurable allow-list defaulting to same-origin behind the proxy; never wildcard with credentials.
- **D-15 (R-45):** Python server is Quart on Hypercorn; Flask/Gunicorn mentions in docs are treated as stale.

### Stack and versions
- **D-16 (R-41):** Python 3.13 via `uv` (`requires-python = ">=3.13,<3.14"`). Deviation from the docs' "3.10 slim" base image, recorded.
- **D-17 (R-42):** MySQL image is parameterised as `MYSQL_IMAGE`, defaulting to the documented `mysql:8.0.40`. Moving to 8.4 LTS needs user approval.
- **D-18 (R-43):** `valkey/valkey:8` for the Redis role; restrict to core commands so Redis 7 also works.
- **D-19 (R-46):** Frontend: Vite only, shadcn/ui only (no `antd`), TanStack Query wrapped in `use-*-request` hooks, Zustand, React Router 7, TailwindCSS.
- **D-20 (STACK):** Pin `litellm==1.84.0` exactly; use `pgsty/minio` rather than `minio/minio`. Versions come from the reference repo's lockfiles and must be re-verified against registries during phase research.
- **D-21 (R-44):** No torch and no PyMuPDF in base dependencies (onnxruntime + pdfplumber/pypdfium2 later). Phase 1 only needs the dependency policy recorded.

### Naming and layout
- **D-22 (R-09):** Keep documented identifiers (`ragflow_server`, index prefix `ragflow_`, bucket `ragflow`, compose network `ragflow`), each defined as one constant per language so a later rename is a one-line change.
- **D-23:** Repository layout follows `docs/00-overview/repository-map.md` and `docs/02-frontend/directory-structure.md` exactly, as expanded in `.planning/research/ARCHITECTURE.md` "Recommended Project Structure".
- **D-24 (R-07):** Container topology: one app image (Nginx + Go + Python) plus infrastructure services; a standalone task-executor container arrives in Phase 4.

### Guardrails
- **D-25:** CI gate fails any build that introduces placeholder/fake/mock implementations under production source trees (test trees exempt), and any `pickle.load(s)` on data crossing a trust boundary (R-38: deliberate deviation from the docs' numpy whitelist).
- **D-26 (R-49):** `docs/apikey llm.md` stays unread and uncommitted until the user reviews it. `.gitignore` excludes it and `.env*`. Never run `git add docs/` or `git add -A`.
- **D-27:** Anything that cannot be implemented or verified is written to `.planning/BLOCKERS.md`, never faked.
- **D-28 (R-37):** Secrets come from env only; structured logging redacts them. (Encryption of provider keys is Phase 3.)

### Host budget and tests
- **D-29:** A preflight script checks free disk, `vm.max_map_count` and RAM and prints an actionable message per failure. The dev compose override caps memory (Elasticsearch heap in particular) to fit a ~5 GB free-RAM host with no GPU.
- **D-30:** Tests assert against the live stack and wait on health/readiness conditions, never fixed sleeps (the prior attempt's flaky-test failure mode).
- **D-31 (R-50):** Real model source for later phases: Ollama in the dev/test compose with one small chat and one small embedding model, unless the user supplies an OpenAI-compatible key. Phase 1 records the decision only.

### Claude's Discretion
- Exact migration tooling for Peewee, the CI runner, the linter/formatter choices, logging library configuration, and the internal structure of the preflight script.
- Wording and visual design of the SPA shell (subject to `/gsd:ui-phase` if run).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Rules and decisions
- `docs/spec.md` — implementation rules and priority order (`docs/` wins)
- `.planning/PROJECT.md` — constraints and key decisions
- `.planning/REQUIREMENTS.md` — requirement text for the IDs listed above
- `.planning/research/SUMMARY.md` — decision register R-01..R-52, host blockers, user-confirmed decisions
- `.planning/research/ARCHITECTURE.md` — component boundaries, recommended project structure, build order
- `.planning/research/STACK.md` — version pins and open stack decisions
- `.planning/research/PITFALLS.md` — pitfalls 1–4, 10–13, 17–18 apply to this phase

### Architecture and backend
- `docs/00-overview/high-level-architecture.md`, `technology-stack.md`, `repository-map.md`, `architecture-diagram.md`
- `docs/03-backend/` (all) — entry points, middleware, API layer, backend architecture
- `docs/04-api/api-overview.md`, `docs/04-api/endpoint-catalog.md`, `docs/04-api/system-api.md`, `docs/04-api/api-call-flow.md`
- `docs/apis.md` lines 1–139 only (canonical routes)

### Data and infrastructure
- `docs/08-database/` (all) — schema, entities, relationships, indexes, migrations, transactions
- `docs/09-storage/storage-overview.md`, `docs/10-cache-and-queues/redis.md`
- `docs/18-deployment/` (all) — services, docker-compose, environment variables, networking, volumes
- `docs/17-integrations/vector-database-integrations.md`

### Frontend, testing, security
- `docs/02-frontend/directory-structure.md`, `frontend-architecture.md`, `routing.md`, `api-client.md`
- `docs/19-testing/` (all)
- `docs/20-security/secrets.md`, `file-security.md`, `api-security.md`

### Reference implementation (read-only, lower priority than docs)
- `/home/logan78/desktop x/ragflow` — `docker/`, `conf/`, `api/apps/__init__.py`, `internal/router/router.go`, `web/vite.config.ts`. Doc links to `file:///home/logan78/Desktop/ragflow/...` map here.

### Off-limits
- `docs/apikey llm.md` — do not read, stage, or commit.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None. The repository contains only `docs/`, `.planning/`, `CLAUDE.md` and `.gitignore`. This is a greenfield phase.

### Established Patterns
- None in-repo. Patterns come from `docs/` first, then the RAGFlow reference checkout.

### Integration Points
- Everything later phases build on is created here: the route list, the envelope, the schema owner, config loading, the compose base, and the three test harnesses.

### Environment facts
- Project path contains a space and `@` (`/home/logan78/desktop x/devRag_@`): every script, compose file and Makefile must quote paths.
- Host: ~5.8 GB free disk, `vm.max_map_count=65530`, ~5 GB free RAM, no GPU, Node 22 present. Disk and `vm.max_map_count` need user action before the compose stack can reach healthy.
- `docs/` is currently untracked in git (commit was blocked pending the user's review for credentials).

</code_context>

<specifics>
## Specific Ideas

- Generate Nginx config and Vite dev proxy from one route-ownership list, and have tests assert which engine answered via `X-API-Source`.
- `DECISIONS.md` must distinguish three statuses: `user-confirmed`, `accepted (auto, not user-reviewed)`, and `open` — so nothing auto-selected is presented as the user's choice.
- Exit gate from research: clean-room `docker compose down -v && docker compose up` reaches healthy from documented instructions.

</specifics>

<deferred>
## Deferred Ideas

- MySQL 8.4 LTS upgrade — needs user approval (R-42).
- Renaming identifiers to `devrag_*` — user preference, one-constant change (R-09).
- NATS JetStream queue and `ragflow-go` profile (ING-20, DEPLOY-09) — confirm or move to v2 before Phase 8.
- Splitting Phase 8 (117 requirements) into smaller phases.
- `[P]`-flagged thin-spec features (R-51) — need user confirmation and per-phase research.

</deferred>

---

*Phase: 1-Reconciliation, Guardrails and Dual-Stack Foundation*
*Context gathered: 2026-10-05*
