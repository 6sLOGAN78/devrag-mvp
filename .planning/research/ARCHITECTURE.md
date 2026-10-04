# Architecture Research

**Domain:** Enterprise RAG platform (devRag) — implementation of the architecture prescribed by `docs/` (reverse-engineered RAGFlow specification)
**Researched:** 2026-10-05
**Confidence:** MEDIUM overall — HIGH on component boundaries and data-flow direction (many docs agree); MEDIUM/LOW on a set of specific contracts where the docs contradict themselves (ports, queue technology, response envelope, table names). Every such contradiction is listed in "Doc Ambiguities and Contradictions" with a proposed resolution that must be recorded as a Key Decision.

**Method:** Distilled from `docs/` only (the architecture is prescribed, not proposed). The reference checkout at `/home/logan78/desktop x/ragflow` was consulted read-only and only where the docs are silent or self-contradictory; each such use is marked "(ref repo)". `docs/apikey llm.md` was not opened.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. PRESENTATION                                                              │
│   React SPA (web/src)      ragflow-cli (Go)      HTTP / Python SDK clients   │
└───────────────┬──────────────────────┬───────────────────────┬───────────────┘
                │ REST + SSE           │ REST                  │ REST
┌───────────────▼──────────────────────▼───────────────────────▼───────────────┐
│ 2. INGRESS: Nginx reverse proxy (80/443) — static SPA + path-based routing    │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
   auth / user / tenant / system /                datasets / documents / chunks /
   searchbots / mcp                               chats / agents / search / models
┌───────────────▼───────────────┐              ┌───────────────▼───────────────┐
│ 3a. GO GIN SERVER (:9384)     │              │ 3b. PYTHON QUART SERVER (:9380)│
│ router → AuthMiddleware →     │              │ app → login_required →         │
│ handler → service → dao(GORM) │              │ restful_apis → services(Peewee)│
│ header: X-API-Source: go      │              │ + update_progress daemon thread│
└───────┬───────────────────────┘              └───┬───────────┬───────────┬───┘
        │                                          │           │           │
        │              ┌───────────────────────────▼──┐ ┌──────▼─────┐ ┌───▼──────────┐
        │              │ 4. CORE ENGINES (Python libs) │ │ Agent      │ │ LLM layer    │
        │              │ rag/nlp  (Dealer, tokenizer,  │ │ canvas     │ │ LLMBundle →  │
        │              │          query, rerank)       │ │ agent/     │ │ rag/llm      │
        │              │ rag/prompts (chunks_format,   │ │ component, │ │ drivers      │
        │              │          citations)           │ │ tools      │ │ (LiteLLM)    │
        │              └───────────────┬───────────────┘ └──────┬─────┘ └───▲──────────┘
        │                              │                        └───────────┘
        │   Redis Stream te.{prio}.common (XADD)                      ▲
        │              ┌───────────────▼────────────────────────────┐ │
        │              │ 5. TASK EXECUTOR WORKER(S) rag/svr          │─┘
        │              │ collect → lock → parser FACTORY (rag/app)   │
        │              │ → DeepDoc (deepdoc/) → tokenize → embed     │
        │              │ → DocStore.insert → set_progress → XACK     │
        │              └───────┬──────────────┬──────────────┬──────┘
┌───────▼──────────────────────▼──────────────▼──────────────▼──────────────────┐
│ 6. PERSISTENCE                                                                 │
│  MySQL 8 (metadata)   Redis 7 (sessions, queue,   MinIO/S3     DocStore        │
│                       locks, heartbeats, cache)   (blobs)      (ES / Infinity) │
└────────────────────────────────────────────────────────────────────────────────┘
```

Source: `docs/00-overview/high-level-architecture.md` (six layers), `docs/00-overview/architecture-diagram.md`, `docs/23-diagrams/architecture.mmd`, `docs/23-diagrams/deployment.mmd`, `docs/18-deployment/production-architecture.md`.

### Component Responsibilities

| # | Component | Responsibility | Talks to | Docs |
|---|-----------|----------------|----------|------|
| C1 | **React SPA** (`web/`) | Views, canvas editor, Zustand stores, React Query hooks, Axios client with Bearer injection, 401 redirect, SSE consumption | Nginx only (never a backend port directly in production) | `docs/02-frontend/frontend-architecture.md`, `directory-structure.md`, `api-client.md`, `frontend-data-flow.md` |
| C2 | **Nginx ingress** (`docker/nginx/`) | Serves SPA build, SSL termination, path-based proxy to Go or Python, SSE pass-through | C3, C4 | `docs/18-deployment/production-architecture.md` (Edge layer), `docs/22-code-tracing/frontend-to-backend.md` |
| C3 | **Go Gin API server** (`cmd/ragflow_server.go`, `internal/`) | Login, registration, password reset, user profile/settings, tenant info/list, system health/ping/config/version/language, search bots, MCP server endpoint; stamps `X-API-Source: go` | MySQL (GORM DAOs), Redis (go-redis); for search bots also DocStore + model providers | `docs/03-backend/backend-overview.md`, `api-layer.md`, `entry-points.md`, `docs/04-api/endpoint-catalog.md` §1, §5, `docs/apis.md` §1 |
| C4 | **Python Quart API server** (`api/`) | Dataset, document, chunk, chat, session, agent, search, model/provider and all remaining REST surface; SSE streaming; hosts `update_progress` daemon thread; loads plugins | MySQL (Peewee), Redis, MinIO, DocStore, LLM providers, C6–C11 in-process | `docs/03-backend/backend-architecture.md`, `entry-points.md` §2, `services.md` §1, `docs/04-api/endpoint-catalog.md` §2–4 |
| C5 | **Relational schema + service/DAO layer** (`api/db/`, `internal/dao/`, `internal/entity/`) | Single MySQL schema read by two ORMs; Handler → Service → DAO layering; connection pooling with retry; migrations | MySQL | `docs/08-database/database-overview.md`, `schema.md`, `entities.md`, `relationships.md`, `database-flow.md`, `migrations.md` |
| C6 | **Storage factory** (`rag/utils/storage_factory.py`, `internal/storage/`) | Pluggable blob store (`STORAGE_IMPL` = MINIO/S3/GCS/OSS/LOCAL); `put/get/rm/bucket_exists` | MinIO/S3 | `docs/09-storage/storage-overview.md`, `storage-flow.md` |
| C7 | **Redis adapter** (`rag/utils/redis_conn.py`) | Stream queue producer/consumer, `RedisDistributedLock`, session store, heartbeat hashes, LLM cache | Redis | `docs/10-cache-and-queues/redis.md`, `queues.md` |
| C8 | **LLM layer** (`rag/llm/`, `api/db/services/llm_service.py`) | `LLMBundle(tenant_id, type, name)` resolves tenant credentials → instantiates chat/embedding/rerank/CV/ASR/TTS driver; error-code mapping, retry, token accounting, Langfuse | MySQL (`tenant_llm`), external model APIs | `docs/11-llm/llm-architecture.md`, `provider-abstraction.md`, `docs/22-code-tracing/llm-call-chain.md` |
| C9 | **DocStore abstraction** (`common/doc_store/`, `rag/utils/*_conn.py`) | `DocStoreConnection` interface over vector + full-text engines; index create/delete, insert, update, delete, search with text/dense/fusion expressions | Elasticsearch / Infinity (others pluggable) | `docs/05-rag-pipeline/indexing.md`, `docs/03-backend/backend-architecture.md` pattern 4, `docs/17-integrations/vector-database-integrations.md` |
| C10 | **DeepDoc parsing engine** (`deepdoc/`) | Format parsers (PDF, DOCX, PPT, Excel, HTML, MD, TXT…) and vision models (layout recognition, OCR, table structure) | Local model files; called in-process by C11 | `docs/00-overview/why-ragflow-exists.md` §1, `docs/06-document-processing/*`, `docs/22-code-tracing/ingestion-call-chain.md` |
| C11 | **Ingestion worker** (`rag/svr/task_executor.py`, `rag/app/`) | Consume stream, lock task, fetch blob, run `FACTORY[parser_id].chunk()`, tokenize, embed in batches, bulk-insert (`BATCH_SIZE = 64`), report progress, ack; rate limiters | Redis, MySQL, MinIO, DocStore, C8, C10 | `docs/05-rag-pipeline/ingestion-pipeline.md`, `docs/06-document-processing/document-processing-workers.md`, `docs/10-cache-and-queues/workers.md`, `background-jobs.md`, `scheduling.md` |
| C12 | **Retrieval engine** (`rag/nlp/`) | `Dealer.search()` / `retrieval()`: query tokenization, BM25 expression, dense expression, fusion, deleted-chunk pruning, rerank, thresholding | C9, C8 (embedding + rerank) | `docs/07-retrieval/retrieval-flow.md`, `docs/22-code-tracing/retrieval-call-chain.md`, `docs/23-diagrams/retrieval.mmd` |
| C13 | **Chat subsystem** (`api/db/services/dialog_service.py`, `conversation_service.py`, `rag/prompts/`) | Assistant presets (`Dialog`), sessions (`Conversation`, `API4Conversation`), prompt compile, `chunks_format`, citation insertion, SSE generator, history persistence, OpenAI-compatible endpoint | C12, C8, MySQL | `docs/12-chat/chat-architecture.md`, `docs/22-code-tracing/chat-call-chain.md`, `docs/23-diagrams/chat.mmd` |
| C14 | **Agent / workflow engine** (`agent/`) | `Graph(dsl).run()` step-wise traversal; component registry (Begin, LLM, Retrieval, Categorize, Switch, Message, Iteration, Loop, Agent-with-tools…); tools (`agent/tools/`), MCP client, code sandbox; webhook trigger, replica snapshot, session persistence | C8, C12, MySQL, sandbox service | `docs/13-agents/agent-architecture.md`, `agent-overview.md`, `docs/14-workflows/workflow-engine.md`, `workflow-overview.md`, `docs/22-code-tracing/agent-call-chain.md`, `workflow-call-chain.md` |
| C15 | **CLI** (`cmd/ragflow-cli.go`, `internal/cli/`) | REPL + batch mode, user/admin scopes, VFS over REST | Public REST API only | `docs/15-cli/cli-overview.md` |
| C16 | **Admin servers** (Python `:9381`, Go `:9383`) | Service lifecycle, tenant administration, health | MySQL, Redis | `docs/18-deployment/services.md`, `production-architecture.md` |
| C17 | **Optional satellite services** | `sandbox-executor-manager` (`:9385`), `deepdoc` service (`:9390`), NATS (`:4222`, profile `ragflow-go`) | C14, C11 | `docs/18-deployment/docker-compose.md`, `services.md` |

**Hard boundary rules derived from the docs**

1. The SPA talks only to the ingress. Routing between engines is a proxy concern, not a client concern (`docs/22-code-tracing/frontend-to-backend.md` flowchart: `API Client → Nginx → Backend Routing Engine`).
2. The Go server touches only MySQL and Redis in every overview diagram (`docs/00-overview/architecture-diagram.md`, `high-level-architecture.md`). MinIO and the vector store are reached only from the Python stack and the worker. The documented exceptions are search bots (need retrieval) and the optional Go upload path (`docs/22-code-tracing/upload-call-chain.md` "Go Call Chain Equivalent").
3. The two servers never call each other over HTTP. Their only integration surfaces are the shared MySQL schema, the shared Redis instance, and the shared token/secret contract.
4. Workers never serve HTTP and are never called synchronously. The API enqueues; the worker reports back only by writing MySQL rows (`docs/23-diagrams/deployment.mmd`: worker → Redis, MinIO, vector store, MySQL).
5. Business code never names a concrete engine or provider: DocStore through `DocStoreConnection`, blobs through the storage factory, models through `LLMBundle`.

---

## Constraint Resolution (a)–(d)

### (a) Dual-stack backend: who owns what

**Route ownership as documented.** Three docs agree and form the contract: `docs/03-backend/api-layer.md` (Route & Auth Handler Matrix), `docs/04-api/endpoint-catalog.md` (per-route "Engine" column), `docs/apis.md` lines 1–145.

| Path | Engine | Auth | Source |
|------|--------|------|--------|
| `GET /health`, `GET /api/v1/system/{ping,config,version}`, `GET /api/v1/language` | Go | None | endpoint-catalog §1 |
| `POST /api/v1/auth/login`, `POST /api/v1/users`, `POST /api/v1/auth/password/forgot/otp`, `POST /api/v1/auth/password/reset` | Go | None | endpoint-catalog §1 |
| `GET /v1/user/info`, `POST /v1/user/setting`, `POST /v1/user/setting/password`, `GET /v1/user/tenant_info`, `GET /v1/tenant/list` | Go | JWT / session | endpoint-catalog §1 |
| `POST /api/v1/searchbots/ask`, `POST /api/v1/searchbots/retrieval_test`, `POST /api/v1/mcp` | Go | Beta auth | endpoint-catalog §5 |
| `/api/v1/datasets*`, `/api/v1/datasets/<id>/documents*`, `.../chunks` | Python | `login_required` (JWT / API key) | endpoint-catalog §2 |
| `POST /api/v1/documents/upload` | "Python / Go" | JWT / API key | endpoint-catalog §2 — see contradiction A3 |
| `/api/v1/agents*`, `POST /api/v1/agents/chat/completions` | Python | JWT / API key | endpoint-catalog §3 |
| `/api/v1/chats*`, `POST /api/v1/chat/completions` (SSE) | Python | JWT / API key | endpoint-catalog §4 |
| Everything else in `docs/04-api/` (search, models, provider, connector, langfuse, plugin, stats, bot, chat_channel, compilation_template, tenant, user, workflow) | Python — inferred: these files document `api/apps/restful_apis/*_api.py` handlers | `login_required` | `docs/04-api/*-api.md` |

Responsibility split in prose: Go = "user/tenant/auth/sync handlers" and Python = "heavy ML/agent execution" (`docs/03-backend/backend-architecture.md` pattern 1); Go "Serves user login, system config, search bots, MCP server endpoints, and document ingestion APIs", Python "Serves legacy RAG endpoints, agent canvas flows, chat completion streams (SSE), and deep document parsing endpoints" (`docs/04-api/api-overview.md`).

**How they share MySQL.** One schema, two ORMs: Peewee models in `api/db/db_models.py` and GORM DAOs in `internal/dao/` map the same tables (`docs/08-database/database-overview.md` mapping table). Both apply the same `tenant_id` + `status` filters (`docs/03-backend/authorization.md`). The docs name two schema-evolution mechanisms — Python `init_web_db()` creating tables at boot (`docs/03-backend/entry-points.md`) and the Go `--migrate` flag plus `internal/dao/migration.go` (`docs/08-database/migrations.md`) — and do not say which one is authoritative. See A8.

**How they share Redis.** Go uses it for cache and distributed locks (`docs/00-overview/technology-stack.md` §2); Python uses it for sessions (`SESSION_TYPE = "redis"`, `docs/16-auth/sessions.md`), the task stream, locks, heartbeats and LLM cache (`docs/10-cache-and-queues/redis.md`). Key namespaces must therefore be a shared constant set, defined once and mirrored in both languages.

**How they share identity.** Go issues the token at login; Python validates the same token on its routes via `Serializer(secret_key).loads(token)` → `access_token` → `UserService.query(access_token=...)`, rejecting empty, shorter-than-32, or `INVALID_`-prefixed values (`docs/03-backend/authentication.md`, `docs/16-auth/tokens.md`). The docs call this "JWT" but the code they quote is an itsdangerous serializer wrapping a UUID stored in `user.access_token`. Consequence: both engines must share one secret key and one token encoding. (Ref repo confirms the Go side re-implements itsdangerous signing in `internal/utility/token.go`, and that Go verifies werkzeug `scrypt:`/`pbkdf2:` password hashes in `internal/common/password.go`.) This is the highest-risk cross-language contract and needs a contract test in the phase that introduces it.

**How the proxy routes.** The docs state the mechanism only at the level "Nginx … path-based routing" (`docs/18-deployment/production-architecture.md`) and give one concrete route line: `Nginx -->|/api/v1/auth, /users, /sync| GinServer` and `Nginx -->|/api/v1/agents, /api/v1/chats, /api/v1/documents| QuartServer` (`docs/00-overview/architecture-diagram.md`). No docs file contains an actual location table. The plan below fills that gap from the endpoint catalog:

```
# Go (:9384) — explicit prefixes, listed first
/health
/api/v1/system/      /api/v1/language
/api/v1/auth/        /api/v1/users
/v1/user/            /v1/tenant/
/api/v1/searchbots/  /api/v1/mcp
# Python admin (:9381) / Go admin (:9383)
/api/v1/admin
# Python (:9380) — catch-all for the rest
/api/   /v1/
# SPA
/  → try_files $uri /index.html
```

The reference repo does this with an `API_PROXY_SCHEME` switch (`python` | `go` | `hybrid`) selecting one of three nginx configs, and the Vite dev server mirrors the same table (ref repo `docker/nginx/ragflow.conf.*`, `web/vite.config.ts`). Note that the ref repo's `hybrid` table differs from the docs (it sends `/api/v1/chat/completions` to Go and login to `/v1/user/login`); **docs win**, so the table above — not the ref repo's — is what to implement. Keep the "explicit Go prefixes + Python catch-all" shape, and keep the dev proxy and nginx config generated from one route list so they cannot drift.

**Plain statement of ambiguity.** The docs are consistent about *which engine owns the identity/system/searchbot/MCP routes versus the RAG/chat/agent routes*. They are contradictory about ports, about who handles upload, and about how much of the Python functionality must also exist in Go (see A1–A4). They are silent on the proxy route table.

### (b) Task/worker model for ingestion

| Aspect | Documented design | Source |
|--------|-------------------|--------|
| Queue technology | **Redis Streams**: producer `XADD` via `REDIS_CONN.queue_product()`, consumers `XREADGROUP` in group `SVR_CONSUMER_GROUP_NAME` (`ragflow_consumer_group`), `XACK` on completion | `docs/10-cache-and-queues/queues.md`, `redis.md`, `workers.md` |
| Queue names | `{SVR_QUEUE_NAME}.{priority}.{suffix}` → `te.1.common` (high), `te.0.common` (normal); consumers read high first | `docs/10-cache-and-queues/queues.md`, `docs/05-rag-pipeline/ingestion-pipeline.md` |
| Task creation | `TaskService.create_task()` splits a document into page-range tasks of `MAXIMUM_TASK_PAGE_NUMBER = 12`, one `task` row each | `docs/10-cache-and-queues/scheduling.md` |
| Trigger | `POST /api/v1/datasets/<id>/documents/parse` → set `document.run = "1"` → create tasks → enqueue | `docs/22-code-tracing/ingestion-call-chain.md` |
| Worker loop | `collect()`: drain own unacked messages first (`UNACKED_ITERATOR`), then read new; acquire `lock:task_{task_id}`; apply `task_limiter`, `chunk_limiter`, `embed_limiter`, `minio_limiter`, `kg_limiter` | `docs/05-rag-pipeline/ingestion-pipeline.md`, `docs/06-document-processing/document-processing-workers.md` |
| Pipeline | `FACTORY[parser_id]` → `chunk()` → `embd_mdl.encode()` → `DocStore.insert()` in batches of 64 | `docs/05-rag-pipeline/ingestion-pipeline.md` |
| Task types | `dataflow`, `raptor`, `graphrag`, `mindmap`, `memory`, … mapped to pipeline task types; KB-wide jobs use sentinel doc IDs | `docs/10-cache-and-queues/background-jobs.md` |
| Document states | `run`: `"0"` unstarted, `"1"` running, `"2"` cancelled, `"3"` finished, `"4"` failed. `status`: `"1"` active, `"0"` deleted. `progress`: 0.0–1.0, `-1.0` on failure | `docs/06-document-processing/document-lifecycle.md` |
| Task state | Carried by `task.progress` (float, indexed), `progress_msg`, `retry_count`, `begin_at`, `process_duration`, `chunk_ids`, `digest` — the `task` DDL has no status column | `docs/08-database/schema.md` §2 |
| Progress reporting | Worker calls `set_progress()` → writes task row. API server daemon thread `update_progress`, guarded by `RedisDistributedLock("update_progress")` so only one instance runs it, aggregates task rows into `document.progress` / `document.run`. UI shows a badge such as "RUNNING (0%)" from the documents list | `docs/05-rag-pipeline/ingestion-pipeline.md` step 6, `docs/03-backend/entry-points.md` §2.4, `docs/02-frontend/frontend-data-flow.md` |
| Liveness / recovery | Heartbeat in Redis hash (`WORKER_HEARTBEAT_TIMEOUT` = 120 s); crashed worker's pending messages are reclaimed by the next consumer | `docs/10-cache-and-queues/workers.md` |
| DB hygiene | Worker closes its DB connection before long vision inference | `docs/08-database/database-flow.md` |

The UI's mechanism for learning progress (polling the document list vs push) is not stated in the docs read; the SSE descriptions cover only chat and agent runs. Treat it as polling via React Query refetch, and record that as a decision.

Queue technology is contradicted elsewhere in the docs (Redis list, NATS JetStream) — see A5 for why Redis Streams is the resolution.

### (c) Doc-store abstraction

- **Interface:** "RAGFlow abstracts storage engines under a unified `DocStoreConnection` interface" (`docs/05-rag-pipeline/indexing.md`); "Vector database interactions pass through a unified DocStore interface … decoupling business logic from underlying search engines" (`docs/03-backend/backend-architecture.md` pattern 4).
- **Location:** adapters in `rag/utils/es_conn.py` and `rag/utils/infinity_conn.py` (`docs/05-rag-pipeline/indexing.md`, `docs/17-integrations/vector-database-integrations.md`); `common/` holds "Vector store adapters, constants, logging, settings" (`docs/00-overview/repository-map.md`). Go drivers at `internal/engine/elasticsearch/`, `internal/engine/infinity/` (`docs/05-rag-pipeline/indexing.md`).
- **Surface:** the docs name `insert` / `insert_chunks`, `search`, and `MatchDenseExpr(vector_column_name, query_vector, similarity)` (`docs/22-code-tracing/retrieval-call-chain.md`, `ingestion-call-chain.md`) but do not list the full interface. The ref repo's `common/doc_store/doc_store_base.py` supplies it: `db_type`, `health`, `create_idx`, `delete_idx`, `index_exist`, `search`, `get`, `insert`, `update`, `delete`, result accessors `get_total`, `get_doc_ids`, `get_fields`, `get_highlight`, `get_aggregation`, `sql`, plus expression types `MatchTextExpr`, `MatchDenseExpr`, `MatchSparseExpr`, `FusionExpr`, `OrderByExpr`. Adopt this surface; it is the smallest choice consistent with the documented call sites.
- **Chunk schema (engine-independent):** `id`, `doc_id`, `kb_id`, `content_ltks`, `title_tks` (boost 10×), `important_kwd` (30×), `question_tks` (20×), `position_int`, `q_{dim}_vec`, `available_int` (`docs/05-rag-pipeline/indexing.md`). The vector column name embeds the embedding dimension, so index creation depends on the dataset's embedding model.
- **Engine-specific behaviour leaks into retrieval and must be contained:** with Elasticsearch the Dealer recomputes kNN scores and reranks (`_knn_scores`, `rerank_with_knn`); with Infinity it uses the engine's normalized fused scores (`docs/07-retrieval/retrieval-flow.md` step 4). Keep that branch inside `rag/nlp/search.py` keyed on `db_type()`, not scattered in callers.
- **Selection:** a single env/config switch chooses the adapter at startup (ref repo: `DOC_ENGINE`, compose profile of the same name).

### (d) Tenant isolation boundaries

| Layer | Mechanism | Source |
|-------|-----------|--------|
| Identity → tenant | `user_tenant(user_id, tenant_id, role)` with roles `owner` / `admin` / `normal`; admin routes return 403 for `normal` | `docs/16-auth/multi-tenancy.md`, `docs/03-backend/authorization.md` |
| MySQL | "All database queries for datasets, documents, tasks, dialogues, and canvas workflows enforce tenant isolation via mandatory `tenant_id` filtering" — in Python services and Go DAOs alike | `docs/03-backend/authorization.md` |
| MySQL (transitive) | `document` has `kb_id` but no `tenant_id`; `task` has `doc_id` only. Isolation for documents, tasks and chunks is therefore enforced by resolving ownership through `knowledgebase.tenant_id` before any read/write | `docs/08-database/schema.md` vs `docs/16-auth/multi-tenancy.md` (A10) |
| DocStore | One index per tenant: `index_name(uid) = f"ragflow_{uid}"`; datasets separated inside it by `kb_id`; `Dealer.retrieval()` takes `tenant_ids` and `kb_ids` explicitly | `docs/05-rag-pipeline/indexing.md`, `docs/07-retrieval/retrieval-flow.md` |
| Object storage | Key prefix `{tenant_id}/{doc_id}` and `{tenant_id}/{doc_id}/{img_id}.png` in bucket `ragflow` | `docs/09-storage/storage-flow.md` |
| Model credentials | Per-tenant provider keys in `tenant_llm`; `LLMBundle(tenant_id, …)` resolves them; composite model id `model@instance@provider` | `docs/11-llm/llm-architecture.md` |
| API tokens | `APIToken` keyed by `tenant_id`; beta tokens resolve tenant for search bots / MCP | `docs/16-auth/tokens.md`, `docs/03-backend/middleware.md` |
| Sessions / chat | `Dialog.tenant_id`; completion handler calls `_ensure_owned_chat(chat_id)` first | `docs/12-chat/chat-architecture.md`, `docs/22-code-tracing/chat-call-chain.md` |
| Not isolated | Redis task streams, locks and worker pool are shared across tenants; the task payload carries the tenant | `docs/10-cache-and-queues/queues.md` |

Enforcement point: the service layer, never the handler. Every service method that reads tenant-owned data takes the tenant id as a required argument; a cross-tenant negative test accompanies every new resource type.

---

## Recommended Project Structure

`docs/00-overview/repository-map.md` specifies the top-level layout and `docs/02-frontend/directory-structure.md` specifies `web/src/`. Both are followed exactly. Sub-folders are taken from paths the docs cite; items marked `(ref)` are not named in the docs and come from the reference repo under the `docs/spec.md` "Folder Structure" rule.

```
devRag_@/
├── docs/                         # authoritative spec (existing)
├── .planning/                    # GSD planning (existing)
├── go.mod / go.sum               # Go module root
├── pyproject.toml / uv.lock      # Python project root
├── Dockerfile                    # main multi-stage image          (docs/18-deployment/deployment-overview.md)
├── Dockerfile_base
├── Dockerfile_deepdoc_oss        # optional deepdoc service image
├── build.sh                      # Go build script
├── run_tests.py                  # Python test runner              (docs/19-testing/test-architecture.md)
│
├── cmd/                          # Go entry points
│   ├── ragflow_server.go         # flags: --api --admin --ingestor --syncer --migrate
│   └── ragflow-cli.go
├── internal/                     # Go backend
│   ├── router/                   # router.go: public / beta / protected groups
│   ├── handler/                  # auth.go (AuthMiddleware, BetaAuthMiddleware), user.go, tenant.go,
│   │                             #   system.go, mcp_server.go, searchbot, document.go
│   ├── service/                  # tenant.go, user, model_service.go, document/, dataset/, chunk/
│   ├── dao/                      # GORM DAOs + migration.go
│   ├── entity/                   # GORM structs                    (docs/08-database/schema.md "Go struct: entity.Document")
│   ├── engine/                   # elasticsearch/, infinity/, redis/   — Go DocStore + cache drivers
│   ├── storage/                  # storage_factory.go, minio.go, s3.go, gcs.go, oss.go
│   ├── cli/                      # lexer, parser, commands, filesystem/ (VFS)
│   ├── mcp/                      # MCP connector
│   ├── common/                   # logger (zap), error codes, password, constants   (ref)
│   ├── utility/                  # token encode/decode shared-contract code         (ref)
│   ├── server/                   # config loading                                   (ref; cited in docs/23-diagrams/architecture.mmd)
│   ├── admin/                    # Go admin server (:9383)                          (ref)
│   ├── syncer/                   # background sync service (--syncer)
│   ├── ingestion/                # Go ingestion engine (--ingestor) — scope decision A4
│   └── agent/canvas/             # Go Eino DAG engine — scope decision A4
│
├── api/                          # Python Quart server
│   ├── ragflow_server.py         # entry: logger, init DB, plugins, daemon threads, app.run
│   ├── settings.py / constants.py / validation.py
│   ├── apps/
│   │   ├── __init__.py           # app factory, CORS, QuartSchema, session, _load_user, login_required, error handler
│   │   ├── restful_apis/         # one blueprint per resource: dataset_api, document_api, chunk_api, chat_api,
│   │   │                         #   agent_api, search_api, models_api, provider_api, tenant_api, user_api,
│   │   │                         #   system_api, bot_api, connector_api, mcp_api, plugin_api, langfuse_api,
│   │   │                         #   stats_api, openai_api, chat_channel_api, compilation_template*_api
│   │   └── services/             # cross-blueprint app services (canvas_replica_service.py)
│   ├── db/
│   │   ├── db_models.py          # split into a models package if it grows past ~500 lines per file (spec: "no giant files")
│   │   ├── services/             # user, knowledgebase, document, task, file, dialog, conversation, llm,
│   │   │                         #   tenant_llm, canvas, api, search, connector, mcp_server, langfuse …
│   │   ├── joint_services/       # tenant_model_service.py          (docs/22-code-tracing/llm-call-chain.md)
│   │   └── init_data.py          # seed LLM factories, superuser
│   ├── channels/                 # chat channel bridges (bootstrap.py)
│   └── utils/                    # api_utils.py (response envelope), validation helpers
│
├── common/                       # shared Python: used by api/, rag/, agent/, deepdoc/, worker
│   ├── settings.py               # config loading, get_svr_queue_name(), engine/storage selection
│   ├── constants.py              # enums: run status, task types, SVR_QUEUE_NAME, parser ids
│   ├── doc_store/                # doc_store_base.py (DocStoreConnection + expr types), es/infinity base + pools
│   ├── misc_utils.py             # thread_pool_exec
│   ├── token_utils.py            # token counting + usage sink
│   ├── llm_request_context.py
│   ├── mcp_tool_call_conn.py
│   └── log_utils.py, exceptions.py, crypto_utils.py, time_utils.py
│
├── rag/                          # core RAG engine (library; no HTTP)
│   ├── svr/                      # task_executor.py, task_executor_limiter.py   — worker entry point
│   ├── app/                      # domain chunkers = parser FACTORY: naive, book, paper, laws, manual, qa,
│   │                             #   table, presentation, picture, one, audio, email, resume, tag
│   ├── nlp/                      # search.py (Dealer, index_name), query.py (FulltextQueryer),
│   │                             #   rag_tokenizer.py, term_weight.py, synonym.py
│   ├── llm/                      # chat_model.py, embedding_model.py, rerank_model.py, cv_model.py,
│   │                             #   sequence2txt_model.py, tts_model.py, model_meta.py, __init__.py (registry)
│   ├── prompts/                  # generator.py (chunks_format, citation prompts) + templates
│   ├── utils/                    # es_conn.py, infinity_conn.py, redis_conn.py, storage_factory.py,
│   │                             #   minio_conn.py, s3_conn.py
│   ├── flow/                     # pipeline components for "dataflow" task type      (ref)
│   └── graphrag/                 # GraphRAG / RAPTOR background jobs                 (ref)
│
├── deepdoc/                      # document understanding (library; optional service)
│   ├── parser/                   # pdf_parser, docx_parser, excel_parser, ppt_parser, html_parser,
│   │                             #   markdown_parser, txt_parser, json_parser, figure_parser
│   └── vision/                   # layout_recognizer, ocr, table_structure_recognizer, recognizer, operators
│
├── agent/                        # canvas / agent engine (library; no HTTP)
│   ├── canvas.py                 # Graph: load DSL, run(), path/branch evaluation
│   ├── component/                # base.py + begin, llm, categorize, switch, message, iteration, loop,
│   │                             #   agent_with_tools, invoke, variable_* …  (registry in __init__.py)
│   ├── tools/                    # base.py + retrieval, exesql, code_exec, web search tools …
│   ├── plugin/                   # GlobalPluginManager
│   ├── sandbox/                  # sandbox client
│   └── templates/                # canvas templates
│
├── admin/                        # Python admin service (:9381) + admin UI hooks
├── conf/                         # service_conf.yaml, llm_factories.json, mapping.json (ES),
│                                 #   infinity_mapping.json, system_settings.json
├── docker/
│   ├── docker-compose.yml        # app containers; profiles cpu / gpu / deepdoc
│   ├── docker-compose-base.yml   # mysql, minio, redis, es01, infinity, (nats), (sandbox)
│   ├── .env                      # ports, passwords, DOC_ENGINE, COMPOSE_PROFILES
│   ├── service_conf.yaml.template
│   ├── init.sql
│   ├── entrypoint.sh / entrypoint_task_executor.sh
│   └── nginx/                    # nginx.conf, proxy.conf, route config(s)
├── helm/                         # Kubernetes chart (deployment docs mention Helm)
├── example/                      # SDK / HTTP examples
├── bin/                          # built Go binaries (git-ignored)
│
├── test/                         # Python tests
│   ├── unit_test/                # pure logic, no services
│   ├── integration/              # live MySQL / Redis / MinIO / DocStore
│   ├── testcases/                # HTTP API tests against a running stack
│   ├── playwright/               # browser e2e
│   └── fixtures/                 # sample documents
│   # Go tests live beside code as *_test.go with build tags integration / e2e  (docs/19-testing/test-architecture.md)
│
└── web/                          # React SPA
    ├── package.json, vite.config.ts, tailwind.config.js, tsconfig.json, index.html
    └── src/
        ├── app.tsx, routes.tsx, main.tsx
        ├── assets/  constants/  interfaces/  layouts/  locales/  utils/ (authorization-util.ts)
        ├── components/           # api-service, canvas, chunk-method-dialog, document-preview, llm-select,
        │                         #   llm-setting-items, markdown-content, similarity-slider, ui (shadcn)
        ├── hooks/                # auth-hooks, use-knowledge-request, use-document-request, use-chat-request,
        │                         #   use-send-message (SSE), use-agent-request + Zustand stores
        ├── services/             # low-level REST functions
        └── pages/                # login-next, datasets, dataset, next-chats, agent (canvas), user-setting, admin
```

### Structure Rationale

- **Top-level names are not free choices.** Every doc cross-reference is a path such as `rag/nlp/search.py` or `internal/handler/auth.go`. Keeping the names means each phase can read its docs section and land on the file to create. `docs/spec.md` requires following the documented structure where it is specified.
- **`common/` exists so the worker never imports `api/apps`.** Settings, constants, the DocStore base and Redis/storage clients are shared by three Python processes (API server, task executor, admin). Anything the worker needs must live in `common/`, `rag/`, `deepdoc/` or `api/db/` — never in the Quart app package.
- **`rag/`, `deepdoc/`, `agent/` are libraries with no HTTP.** This is what lets the same retrieval code serve chat, the search API and the agent Retrieval component (`docs/22-code-tracing/agent-call-chain.md` shows `Retrieval.run()` calling `Dealer.search()` directly).
- **`api/db/services/` is the only place that issues SQL from Python**; `internal/dao/` the only place from Go. Handlers do validation and envelope formatting only (`docs/03-backend/backend-architecture.md` pattern 2).
- **`conf/` holds engine mappings and the model-factory catalogue** as data, so adding a provider or changing the ES mapping is not a code change.
- **Deviation recorded:** the project/product name in identifiers (`ragflow_server`, index prefix `ragflow_`, bucket `ragflow`, compose network `ragflow`) is kept as documented. Renaming to `devrag_*` is a cosmetic decision for the user; if taken, it must be a single constant in `common/constants.py` and `internal/common/constants.go`, decided before any index or bucket is created.

---

## Architectural Patterns

### Pattern 1: Layered Handler → Service → DAO, twice

**What:** Identical layering in both languages; handlers own HTTP concerns, services own domain logic and tenant filtering, DAOs/models own SQL (`docs/03-backend/backend-architecture.md` pattern 2, `docs/23-diagrams/frontend-backend.mmd`).
**When:** Every endpoint.
**Trade-off:** Some boilerplate; in exchange the worker and agent engine can reuse services without the web framework.

```python
# api/apps/restful_apis/dataset_api.py
@manager.route("/datasets", methods=["GET"])
@login_required
async def list_datasets():
    args = ListDatasetsQuery.model_validate(request.args.to_dict())
    rows, total = KnowledgebaseService.list_for_tenant(g.user.tenant_id, args.page, args.page_size, args.keywords)
    return get_json_result(data={"items": rows, "total": total})
```

### Pattern 2: Enqueue-and-return, progress by row

**What:** HTTP handlers never parse documents. They write `document.run = "1"`, create page-range `task` rows, `XADD` each to `te.{priority}.common`, and return. Workers report by writing `task.progress`; a single lock-guarded thread rolls tasks up into the document row.
**When:** Parsing, and every other long job (RAPTOR, GraphRAG, mindmap).
**Trade-off:** Eventual consistency in the UI; requires idempotent task execution because a reclaimed message re-runs the task. Idempotency key is the task `digest` plus stored `chunk_ids` (`docs/08-database/schema.md` §2) — re-running must replace, not duplicate, that task's chunks.

### Pattern 3: Ports for every external engine

**What:** Three factories — `DocStoreConnection`, storage factory, `LLMBundle` — each chosen by config and each with a second real implementation (ES + Infinity; MinIO + local disk; LiteLLM + direct driver).
**When:** From the first line of code that touches a vector store, a blob, or a model.
**Trade-off:** The interface has to be designed before there is a second implementation. The docs remove most of that risk by specifying the call sites.

```python
# common/doc_store/doc_store_base.py
class DocStoreConnection(ABC):
    @abstractmethod
    def create_idx(self, index_name: str, dataset_id: str, vector_size: int, parser_id: str | None = None): ...
    @abstractmethod
    def insert(self, rows: list[dict], index_name: str, dataset_id: str | None = None) -> list[str]: ...
    @abstractmethod
    def search(self, select_fields, highlight_fields, condition, match_exprs, order_by,
               offset, limit, index_names, dataset_ids, **kw): ...
    @abstractmethod
    def delete(self, condition: dict, index_name: str, dataset_id: str) -> int: ...
```

### Pattern 4: Async I/O shell, thread pool for blocking compute

**What:** Quart handlers and the worker loop are `asyncio`; embedding, DocStore calls and vision inference are pushed through `thread_pool_exec` (`docs/10-cache-and-queues/async-processing.md`).
**When:** Any call into ONNX/tokenizer/DB-client code from an `async def`.
**Trade-off:** Peewee is synchronous — every service call from an async handler must go through the pool or it stalls SSE streams for all users.

### Pattern 5: SSE as an async generator with persistence at the tail

**What:** Completion handler yields a reference frame, then one `data:` frame per token delta, then persists the conversation and yields a terminal frame (`docs/22-code-tracing/chat-call-chain.md` steps 5–6, `docs/23-diagrams/chat.mmd`).
**When:** Chat completion, agent completion, workflow run.
**Trade-off:** Persistence happens after the client may have disconnected; wrap the tail in `finally` so history is saved on cancellation.

### Pattern 6: DSL-driven graph with a component registry

**What:** Canvas JSON (`components`, `history`, `retrieval`, `globals`, `path`) → `Graph` instantiates components by `component_name` from a registry → `run()` walks from `begin`, each component's `_run()` producing outputs that downstream nodes reference (`docs/14-workflows/workflow-engine.md`, `workflow-overview.md`).
**When:** Agents and workflows; also the frontend canvas serialises to the same DSL.
**Trade-off:** The DSL is a public contract between frontend, backend and stored rows — version it from day one.

---

## Data Flow

### Flow 1 — Ingestion: upload → parse → chunk → embed → index

```
SPA upload dialog
  │ POST /api/v1/documents/upload  (multipart: file, dataset_id; Bearer)
  ▼
Nginx ──► Quart document_api.upload_document()
  │        ├─ KnowledgebaseService.get_by_id(dataset_id)  + tenant ownership check
  │        ├─ xxhash checksum of stream
  │        ├─ FileService.save_file() ──► storage factory ──► MinIO  key {tenant_id}/{doc_id}
  │        └─ DocumentService.insert(run='0', progress=0.0) ──► MySQL document (+ file, file2document)
  ◄── 200 [{id, name, size, …}]
  │
  │ POST /api/v1/datasets/<id>/documents/parse {doc_ids}
  ▼
Quart document_api.parse_documents()
  ├─ DocumentService.update_by_id(run='1')                        ──► MySQL
  ├─ TaskService.create_task()  (12-page ranges)                  ──► MySQL task rows
  └─ REDIS_CONN.queue_product("te.{prio}.common", task)           ──► Redis XADD
  ◄── 200 (immediately)

Task executor (separate process, N replicas)
  collect(): XREADGROUP (own pending first) ──► acquire lock:task_{id}
  ├─ storage.get({tenant_id}/{doc_id})                            ◄── MinIO
  ├─ FACTORY[parser_id].chunk()
  │     └─ deepdoc parser: layout recognition + OCR + table structure  → blocks, positions, images
  ├─ tokenize: content_ltks, title_tks, important_kwd, question_tks
  ├─ LLMBundle(tenant, EMBEDDING, kb.embd_id).encode(batch)       ──► model provider
  ├─ DocStore.create_idx(ragflow_{tenant_id}, kb_id, dim) if missing
  ├─ DocStore.insert(batch of 64)                                 ──► ES / Infinity
  ├─ set_progress(task, 0.0…1.0 | -1, msg)                        ──► MySQL task
  └─ XACK

API server thread update_progress (holds RedisDistributedLock)
  └─ aggregate task rows ──► document.progress, document.run ('3' finished / '4' failed),
                              chunk_num, token_num

SPA: document list refetch ──► badge RUNNING(n%) → FINISHED
```

Direction is strictly one-way from API to worker through Redis, and one-way from worker to API through MySQL. Sources: `docs/22-code-tracing/upload-call-chain.md`, `ingestion-call-chain.md`, `docs/05-rag-pipeline/ingestion-pipeline.md`, `docs/23-diagrams/ingestion.mmd`, `docs/03-backend/business-logic.md` §1.

### Flow 2 — Question answering: question → retrieve → rerank → prompt → stream

```
SPA chat input
  │ POST /api/v1/chat/completions {session_id, message, stream:true}   (fetch-based SSE)
  ▼
Nginx (buffering off) ──► Quart chat_api.session_completion()
  ├─ login_required → g.user
  ├─ _ensure_owned_chat(chat_id) → Dialog (kb_ids, llm_id, prompt_config)        ◄── MySQL
  ├─ load Conversation.message history                                            ◄── MySQL
  ├─ Dealer.retrieval(question, embd_mdl, tenant_ids, kb_ids, page, page_size,
  │                   similarity_threshold, vector_similarity_weight, top, rerank_mdl)
  │     ├─ rag_tokenizer.tokenize(question) → FulltextQueryer → MatchTextExpr (BM25 on content_ltks…)
  │     ├─ LLMBundle.encode_queries(question) → MatchDenseExpr on q_{dim}_vec     ──► embedding provider
  │     ├─ DocStore.search(index ragflow_{tenant_id}, kb_ids, [text, dense, fusion])  ──► ES / Infinity
  │     ├─ _prune_deleted_chunks()
  │     ├─ rerank: rerank_by_model() | ES: rerank_with_knn() | Infinity: engine scores
  │     └─ threshold + stable sort → top-K chunks
  ├─ chunks_format(chunks) → context with citation markers                (rag/prompts/generator.py)
  ├─ build messages: system prompt + context + trimmed history + question
  └─ stream():
        yield  reference frame (chunks + doc aggs)                               ──► SSE
        async for delta in LLMBundle.chat_streamly(system, history, gen_conf):   ──► chat provider
            yield data: {…, "data": {"answer": delta}}                           ──► SSE
        insert citations into final answer
        ConversationService.save (messages + reference), token usage sink         ──► MySQL
        yield terminal frame                                                       ──► SSE
SPA: use-send-message appends deltas → markdown-content re-render → citations drawer
```

Sources: `docs/22-code-tracing/chat-call-chain.md`, `retrieval-call-chain.md`, `docs/07-retrieval/retrieval-flow.md`, `docs/23-diagrams/rag-pipeline.mmd`, `chat.mmd`, `docs/02-frontend/frontend-data-flow.md` §2.

### Flow 3 — Authentication across engines

```
SPA login ─► Nginx ─► Go  POST /api/v1/auth/login
                        ├─ UserDAO: SELECT user WHERE email AND status=1
                        ├─ verify password hash
                        ├─ write user.access_token (UUID) ─► MySQL
                        └─ return signed token (serializer(secret).dumps(access_token))
SPA stores token (localStorage) → Authorization: Bearer on every request
   ├─► Go routes:     AuthMiddleware → c.Set("user")
   └─► Python routes: login_required → _load_user → Serializer(secret).loads → UserService.query(access_token)
Logout: access_token := "INVALID_<hex>"  → both engines reject afterwards
401 anywhere → SPA clears token → redirect /login-next
```

Sources: `docs/04-api/api-call-flow.md` §1, `docs/03-backend/authentication.md`, `middleware.md`, `docs/02-frontend/api-client.md`.

### Flow 4 — Agent / workflow run

```
SPA canvas (xyflow) ─ save DSL ─► POST/PUT /api/v1/agents ─► MySQL user_canvas.dsl
Run: POST /api/v1/agents/chat/completions  |  POST /v1/agent/<id>/webhook
  ▼ Quart agent_api
  ├─ access check + load DSL        ├─ (webhook) validate_webhook_security, commit runtime replica snapshot
  ├─ Graph(dsl, tenant_id).run(stream=True)
  │     begin → component._run() → resolve downstream → …
  │        Retrieval ─► Dealer (Flow 2 retrieval half)
  │        LLM / Agent ─► LLMBundle; Agent loops tools up to max_rounds (indexed tool names)
  │        tools ─► agent/tools/*, MCP servers, sandbox-executor-manager
  │     emits SSE events: workflow_started, node_started, message, done
  └─ persist session (logs, node states, token counts) ─► MySQL
```

Sources: `docs/22-code-tracing/agent-call-chain.md`, `workflow-call-chain.md`, `docs/23-diagrams/workflows.mmd`, `agents.mmd`, `docs/13-agents/agent-architecture.md`, `docs/14-workflows/workflow-overview.md`.

### State Management (frontend)

```
Server state:  React Query hooks in hooks/use-*-request.ts ──► services/* ──► Axios (interceptors)
Global state:  Zustand stores (useUserSettingStore, useAgentStore, useChatStore)
Local state:   useState / useReducer
Streaming:     use-send-message (fetchEventSource) ──► appends to message state
```

Source: `docs/02-frontend/frontend-architecture.md` §3.

---

## Build Order

Dependency graph (an arrow means "must exist first"):

```
Compose infra ─► Config + schema ─► Go auth ──┬─► Python auth middleware ─► every Python route
                                              └─► SPA shell + login
Storage factory ─► Upload
LLM layer (embedding) ─┬─► Ingestion worker ─► Chunks in DocStore ─► Retrieval ─► Chat ─► Agents
DocStore adapter ──────┘                                              ▲
Redis adapter (streams + locks) ─► Ingestion worker                   │
LLM layer (rerank, chat) ─────────────────────────────────────────────┘
Retrieval + LLM (Python proven) ─► Go search bots / MCP
Whole REST surface ─► CLI
```

Seven stages. Each ends runnable and testable; the frontend is built alongside the backend slice it exposes rather than as a final stage, because `docs/spec.md` requires each phase to end in a working state and "frontend and backend communicate correctly".

| Stage | Build | Depends on | Ends in this runnable state |
|-------|-------|-----------|-----------------------------|
| **1. Foundation & dual-stack skeleton** | Repo skeleton per tree above; `docker-compose-base.yml` (MySQL, Redis, MinIO, one DocStore engine); `conf/service_conf.yaml` + env loading in `common/settings.py` and Go config; full MySQL schema + migration owner (A8); Quart app factory with envelope, error handler, structured logging; Gin engine with zap logger and `X-API-Source: go`; health/ping/version on both; Nginx route table; SPA scaffold (Vite, Tailwind, shadcn, router, Axios client) | — | `docker compose up` → `/health` (Go) and Python system health respond through Nginx with the right engine; schema migrates from empty; unit + integration test harness for both languages runs in CI |
| **2. Identity, tenancy, authorization** | Go: register, login, password reset, user info/settings, tenant info/list, `AuthMiddleware`. Python: `_load_user` / `login_required` (JWT, API token, beta token, session fallback), `APIToken` CRUD, role checks. Shared token + password-hash contract with cross-language contract tests. SPA: login/register, auth interceptor, 401 redirect, layout, user settings | 1 | Register → login via Go → same token accepted by a Python protected route; logout invalidates on both; cross-tenant access returns 403/empty; SPA login works end to end |
| **3. Model layer, datasets, storage, upload** | `rag/llm` drivers (chat, embedding, rerank) + `LLMBundle` + tenant provider/model config APIs + `llm_factories.json` seed; `KnowledgebaseService` + dataset API with parser/retrieval config; storage factory (MinIO + local); file + document services, upload endpoint, document list/delete. SPA: model settings, dataset list/create/configure, upload dialog, document table | 2 | With a real provider key or local Ollama: `LLMBundle.encode()` and `.chat()` succeed for a tenant; create dataset, upload a PDF, blob present in MinIO under `{tenant_id}/{doc_id}`, row shows `run='0'` |
| **4. Ingestion pipeline** | Redis adapter (streams, consumer group, distributed lock); `TaskService.create_task` page splitting; parse/cancel endpoints; task executor (collect, limiters, heartbeat, ack/reclaim, retries); DocStore interface + first adapter + mappings; tokenizer; `rag/app` chunkers (start `naive`, then the rest); `deepdoc` parsers + vision; `update_progress` thread; chunk list/create/update/enable APIs. SPA: parse trigger, progress badges, chunk viewer, chunk-method dialog | 3 (embedding, storage, documents) | Upload → parse → worker log shows task done → `document.run='3'`, `progress=1.0`, chunk count > 0; chunks visible in UI; killing a worker mid-task results in reclaim and no duplicate chunks; failure path sets `progress=-1` with message |
| **5. Retrieval and chat (Core Value)** | `FulltextQueryer`, `Dealer.search/retrieval/rerank`, filters, retrieval-test and search APIs; `Dialog`/`Conversation` services; prompt construction, context window trimming, `chunks_format`, citation insertion; SSE completion; OpenAI-compatible endpoint; token usage accounting. SPA: retrieval test page, chat assistants, sessions, streaming chat with citations drawer | 4 (indexed chunks), 3 (chat + rerank models) | Ask a question about the uploaded document and receive a streamed, cited answer in the UI. This is PROJECT.md's Core Value; nothing later may be started until it passes with no mocked stage |
| **6. Agents and workflows** | `agent/canvas.py` Graph + DSL versioning; component registry and components; tools (retrieval, exesql, code exec, web search), MCP client, sandbox integration; agent CRUD, completion SSE, webhook, replica snapshot, session persistence; canvas templates. SPA: xyflow canvas, node config drawers, run/debug log | 5 (Retrieval component reuses Dealer; LLM component reuses LLMBundle) | Build Begin → Retrieval → LLM → Message in the canvas, run it, see node events and final streamed answer; webhook trigger returns outputs; session row persisted |
| **7. Go surface completion, CLI, integrations, deployment hardening** | Go search bots + MCP server (needs Go DocStore driver + model resolution, or the documented "retrieval bridging"); `ragflow-cli` (lexer, parser, user/admin modes, VFS); admin servers; remaining REST surface (connector, bot, chat_channel, langfuse, plugin, stats, compilation templates); second DocStore adapter; additional storage back-ends; background job types (RAPTOR, GraphRAG, mindmap); Dockerfiles, compose profiles, entrypoints, Helm; all `docs/21-end-to-end-flows/` as automated e2e | 5 for search bots; whole API for CLI | `docker compose --profile … up` from a clean machine brings up the full stack; CLI can log in, list datasets, upload and search; every documented e2e flow passes |

**Ordering rationale**

- Schema before both servers because two ORMs bind to it; changing it later is a two-language change.
- Go auth before any Python route because Python cannot be exercised without a token Go issued (or else a throwaway Python login would be written and discarded).
- LLM layer before ingestion because embedding is a mandatory ingestion step and fixes the vector dimension of the index.
- DocStore lands in stage 4 with its first writer, and gets its first reader in stage 5; the interface must nevertheless be written in stage 4 with `search` included, so stage 5 does not reshape it.
- Go search bots and MCP are last among the Go routes although the docs assign them to Go, because they need retrieval and model access from Go — the two things the Go stack otherwise never touches.
- If the roadmap wants fewer than seven phases, merge 6 into 7's predecessor rather than merging 4 and 5: the ingestion/retrieval split is the natural verification boundary.

**Research flags for phases**

| Stage | Needs deeper research | Why |
|-------|----------------------|-----|
| 2 | Yes | Cross-language token and password-hash compatibility; exact Go middleware behaviour is described in two sentences in the docs |
| 4 | Yes | DeepDoc model acquisition and runtime (ONNX weights, CPU performance), tokenizer choice, ES mapping details, Redis Streams reclaim semantics |
| 5 | Moderate | ES vs Infinity scoring branches, citation insertion algorithm |
| 6 | Yes | DSL schema, component I/O variable resolution, sandbox service |
| 7 | Yes | How Go search bots obtain retrieval (native drivers vs bridge); scope of Go parity engines (A4) |
| 1, 3 | No | Standard patterns, well specified |

---

## Doc Ambiguities and Contradictions

Per `docs/spec.md`, deviation is permitted only on "a genuine contradiction or an implementation blocker" and must be documented. Each item below needs a Key Decision entry. "Proposed" is the recommendation; none has been confirmed by the user.

| # | Topic | What the docs say | Proposed resolution |
|---|-------|-------------------|---------------------|
| A1 | **Ports** | Both engines on `:9380` (`docs/00-overview/high-level-architecture.md`, `docs/02-frontend/frontend-architecture.md`). Go `9380` / Python `9381` (`docs/apis.md`). Python `9380`, Python admin `9381`, MCP `9382`, Go admin `9383`, Go `9384` (`docs/18-deployment/services.md`, `networking.md`, `production-architecture.md`) | Use the `18-deployment` assignment: three files agree, it is the only one that is physically possible, and it is the section that owns ports |
| A2 | **Proxy route table** | Never specified beyond "path-based routing" and one diagram edge label. `docs/00-overview/architecture-diagram.md` mentions `/sync` and `/users` routes for Go that appear in no catalog | Derive from `docs/04-api/endpoint-catalog.md`: explicit Go prefixes, Python catch-all (table in section a). Treat `/sync` as the Go syncer's internal concern, not a public route, until a doc defines it |
| A3 | **Who handles upload and parse** | Catalog: upload is "Python / Go", handler `document_api.upload_info`. `docs/02-frontend/frontend-data-flow.md`: upload **and** parse go to the Go server. `docs/03-backend/backend-data-flow.md`: upload to Go, parse to Python. `docs/22-code-tracing/upload-call-chain.md`: Python is the main chain; Go "equivalent" is at a different path `/api/v1/datasets/:id/documents/upload`. `docs/apis.md`: Python, "Go also proxies/streams this to MinIO" | Python owns both (majority, and it keeps MinIO off the Go stack as every overview diagram shows). Go upload at the dataset-scoped path is an optional parity item for stage 7 |
| A4 | **Extent of Go parity** | Docs describe Go counterparts for nearly everything: chat (`internal/handler/chat.go`), OpenAI chat, canvas (Eino DAG "dual engine"), model service, DocStore drivers, ingestion engine (`--ingestor`), storage. The endpoint catalog nevertheless assigns each route to exactly one engine | Route ownership per the catalog is the delivered contract. Whether the Go Eino canvas engine, Go ingestion engine and Go chat handlers are in scope is a **scope question for the user**, not something to settle silently: building them roughly doubles stages 4–6. Recommendation: defer and document as not-yet-implemented parity; do not present as complete |
| A5 | **Queue technology** | Redis Streams, `te.{0,1}.common`, XADD/XREADGROUP/XACK (`docs/10-cache-and-queues/queues.md`, `workers.md`, `redis.md`, `docs/05-rag-pipeline/ingestion-pipeline.md`). Redis **list** `ragflow_TASK_EXE_QUEUE`, RPUSH/LPOP (`docs/21-end-to-end-flows/document-processing.md`, `docs/22-code-tracing/ingestion-call-chain.md`, `docs/23-diagrams/ingestion.mmd`, `architecture.mmd`, `docs/99-glossary/important-terms.md`). **NATS JetStream** (`docs/18-deployment/production-architecture.md`, `deployment-overview.md`) | Redis Streams with the `te.*` names: it is what the dedicated queue section specifies in detail, and it is the only variant with ack/reclaim semantics, which the retry and idempotency requirements need. NATS is in compose profile `ragflow-go` only (`docs/18-deployment/docker-compose.md`) — treat as optional transport for the Go ingestor (A4). Ref repo agrees with Streams |
| A6 | **Response envelope** | `{retcode, retmsg, data}` (`docs/04-api/api-overview.md`, `docs/02-frontend/api-client.md`, `docs/03-backend/middleware.md`). `{code, message, data}` (`docs/21-end-to-end-flows/*`, `docs/22-code-tracing/*`, `docs/11-llm/llm-request-flow.md`, `docs/23-diagrams/chat.mmd`) | Docs split roughly evenly, so the ref repo breaks the tie: `{"code", "message", "data"}` (ref `api/utils/api_utils.py`). Define it once in each language and in one TS interface. Needs user confirmation because `04-api` is the nominal owner of this contract |
| A7 | **Chat completion path and SSE framing** | Path `/api/v1/chat/completions` (catalog, `apis.md`, frontend flow) vs `/v1/session/completion` (`docs/22-code-tracing/chat-call-chain.md`, `chat.mmd`). `docs/05-rag-pipeline/complete-rag-flow.md` uses the agent completion path for a plain query. Terminal frame `data: [DONE]` (frontend flow) vs `data: true` (`chat.mmd`). Delta frame `{"answer": …}` vs `{"code":0,"data":{"answer": …}}` | Path: `/api/v1/chat/completions` (catalog). Frames: enveloped `data: {"code":0,"data":{"answer","reference"}}`, terminal `data: {"code":0,"data":true}`; emit `[DONE]` only on the OpenAI-compatible endpoint |
| A8 | **Schema owner** | Python `init_web_db()` creates tables at boot; Go has `--migrate` and `internal/dao/migration.go`; `docker/init.sql` "initializes database schema" (`docs/18-deployment/services.md`) | One owner. Recommend Python models + migrator as the source of truth (`docs/08-database/entities.md` is generated from `api/db/db_models.py`), run as an explicit one-shot migrate step before either server starts; Go structs map the result and a contract test compares them to the live schema. `init.sql` only creates the database and user |
| A9 | **Table and column names** | Chat: `dialog` / `conversation` / `api_4_conversation` (`docs/12-chat/chat-architecture.md`, `entities.md`) vs `chat_dialog` / `chat_session` (`docs/21-*`, `docs/22-*`, `chat.mmd`). Canvas: `UserCanvas` (`entities.md`) vs `canvas` (`database.mmd`, agent call chain). `agent_session`, `canvas_replica`, `tenant_token_usage` appear in flows but not in `entities.md`. KB embedding column `embd_id` (`schema.md`) vs `emb_id` (`database.mmd`). `schema.md` gives DDL for only 3 of ~40 entities | Follow `docs/08-database/` (`entities.md`, `schema.md`) for names; for the three tables absent from `entities.md`, map `agent_session` → `API4Conversation`, `canvas_replica` → `UserCanvasVersion`, and decide token-usage storage in stage 5. Column-level DDL for the other entities must be taken from the ref repo's `db_models.py` — flag for stage 1 research |
| A10 | **Tenant scoping of documents and tasks** | "Every database entity (`Knowledgebase`, `Document`, `Task`, …) references a `tenant_id`" (`docs/16-auth/multi-tenancy.md`) vs DDL where `document` and `task` have none (`docs/08-database/schema.md`). `relationships.md` draws `Tenant ||--|{ User` directly while `multi-tenancy.md` uses the `user_tenant` join. Code samples use `current_user.tenant_id`, which is not a `user` column | Follow the DDL; enforce document/task isolation transitively through `knowledgebase.tenant_id`. Membership through `user_tenant`; resolve "current tenant" in auth middleware and attach it to the request context |
| A11 | **Document/task state vocabulary** | `run` codes `"0"`–`"4"` (`document-lifecycle.md`); responses and traces say `status: "SUCCESS"` / `"FINISHED"` / `UNSTART`; `database.mmd` gives `TASK.status`, the DDL has none; lifecycle diagram adds `UPLOADED`, `PARSED`, `INDEXED` states that have no stored representation | `document.run` char codes are the stored state; `document.status` is the soft-delete flag; task state is derived from `progress`. Diagram-only states are progress messages, not enum values |
| A12 | **Default DocStore engine** | "Infinity Connection (Default Vector DB)" (`docs/05-rag-pipeline/indexing.md`); most diagrams write "Elasticsearch / Infinity" with ES first; the engine list itself varies by file (Qdrant/Milvus/PGVector in overview, ClickHouse/SereneDB/OceanBase in deployment). Ref repo env default is `elasticsearch` | Owned by STACK research. Architecturally: build the interface plus one adapter in stage 4, the second in stage 7; only ES and Infinity have documented adapters, so the others are out of scope unless the user asks |
| A13 | **Object storage key scheme** | Bucket `ragflow`, key `{tenant_id}/{doc_id}` (`docs/09-storage/storage-flow.md`); `document.location` is described elsewhere as the lookup key (`FileService.get_file(doc.location)`) | Follow `storage-flow.md`; store the object key in `document.location` |
| A14 | **Python framework naming** | "Quart (ASGI)" in most files; "Python Flask API server", "Gunicorn or standard WSGI runner" in `docs/18-deployment/production-architecture.md`, `docker.md`, `docs/05-rag-pipeline/rag-overview.md` | Quart. The Flask mentions are stale wording |
| A15 | **DeepDoc placement** | In-process library called by the worker (all call chains) vs a separate `deepdoc` container on `:9390` under an optional profile (`docs/18-deployment/docker-compose.md`); `docs/00-overview/architecture-diagram.md` draws DeepDoc under the Quart server | In-process in the worker by default; the separate service is an optional profile for stage 7 |
| A16 | **Password hashing** | "PBKDF2 / Bcrypt" (`docs/03-backend/authentication.md`, `docs/04-api/api-call-flow.md`); quoted code uses werkzeug `check_password_hash` | One format readable by both languages. Ref repo uses werkzeug-format hashes (scrypt / pbkdf2) verified natively in Go; adopt that. Confirm in stage 2 research |
| A17 | **Foreign content in `docs/apis.md`** | From roughly line 145 onward the file is an unrelated guide to building a metered API-key/billing platform (PostgreSQL, Stripe, credits, usage ledger). It introduces a database and services found nowhere else in `docs/` | Treat lines 1–145 as spec and the remainder as non-normative. **Needs user confirmation**: if the billing/credits system is intended scope, it is a new subsystem with a different database and must be planned explicitly |
| A18 | **Progress delivery to the UI** | Not specified (see section b) | Polling via React Query refetch interval while any row is running |
| A19 | **`docs/apikey llm.md`** | Not read (off-limits) | May contain per-tenant model/API-key requirements that affect C8; user to review |

---

## Scaling Considerations

| Scale | Architecture adjustments |
|-------|--------------------------|
| Single node, evaluation | One app container running Nginx + Go + Python + N task executors, as documented (`docs/18-deployment/services.md` §1); one DocStore node |
| Team / department | Separate worker container(s) (`docs/23-diagrams/deployment.mmd` already draws the worker as its own container); raise executor count; GPU profile for DeepDoc |
| Multi-node | Stateless Go and Python replicas behind the load balancer; `update_progress` stays single-runner via its Redis lock; workers scale horizontally on the consumer group; Helm chart |

### Scaling Priorities

1. **First bottleneck — ingestion throughput.** CPU-bound layout/OCR. Fixed by more workers (page-range task splitting already parallelises a single large PDF) and the limiter settings, not by API changes.
2. **Second bottleneck — event-loop stalls in the Quart server.** Synchronous Peewee, embedding and DocStore calls must go through the thread pool or concurrent SSE streams freeze.
3. **Third — embedding/rerank provider rate limits.** `embed_limiter` and `LLMErrorCode` retry classification are the levers.

---

## Anti-Patterns

### Anti-Pattern 1: Letting the frontend choose the engine
**What people do:** Give the SPA two base URLs (Go, Python).
**Why it's wrong:** Leaks deployment topology into the client and breaks the documented single-ingress model.
**Do this instead:** One origin; route in Nginx and mirror the same table in the Vite dev proxy.

### Anti-Pattern 2: A second, convenient login in Python
**What people do:** Add a Python login endpoint to unblock early Python work.
**Why it's wrong:** Creates two token issuers and hides cross-language incompatibility until late.
**Do this instead:** Build Go auth first; prove the shared-token contract with a test in stage 2.

### Anti-Pattern 3: Parsing inside the request
**What people do:** Parse small files synchronously in the upload handler "for now".
**Why it's wrong:** Bypasses task rows, progress, retries and the worker; has to be rewritten.
**Do this instead:** Always enqueue, even for a one-page text file.

### Anti-Pattern 4: Engine-specific calls outside the adapter
**What people do:** Build an Elasticsearch query dict in `dialog_service` or a component.
**Why it's wrong:** The second engine becomes a rewrite; violates `docs/03-backend/backend-architecture.md` pattern 4.
**Do this instead:** Only expression objects cross the `DocStoreConnection` boundary.

### Anti-Pattern 5: Worker importing the web app
**What people do:** `from api.apps import …` in the task executor to reuse a helper.
**Why it's wrong:** Pulls Quart, sessions and blueprints into a process with no HTTP; slow start and circular imports.
**Do this instead:** Shared code lives in `common/`, `rag/`, or `api/db/services/`.

### Anti-Pattern 6: Tenant filter in the handler
**What people do:** Fetch by id in the service, compare tenant in the handler.
**Why it's wrong:** The worker, agent components and Go DAOs reuse services without the handler.
**Do this instead:** Tenant id is a required service/DAO argument.

### Anti-Pattern 7: Schema defined twice
**What people do:** Let Peewee `create_tables` and GORM `AutoMigrate` both run.
**Why it's wrong:** Column type and default drift between the two ORMs' ideas of the table.
**Do this instead:** One migration owner (A8), contract test on the other side.

### Anti-Pattern 8: Presenting a parity stub as done
**What people do:** Add `internal/agent/canvas/` with empty functions because the docs mention it.
**Why it's wrong:** `docs/spec.md` forbids placeholder implementations presented as complete.
**Do this instead:** Leave it out and record it as a documented, undelivered parity item until scheduled (A4).

---

## Integration Points

### External Services

| Service | Integration pattern | Notes |
|---------|---------------------|-------|
| LLM / embedding / rerank providers | `LLMBundle` → `rag/llm` drivers → LiteLLM or direct SDK; per-tenant keys | Filter generation params to the allowed set; map errors to `LLMErrorCode` with retryable flag (`docs/11-llm/provider-abstraction.md`) |
| Elasticsearch / Infinity | `DocStoreConnection` adapter, one index per tenant | Vector column name depends on embedding dimension |
| MinIO / S3 | Storage factory, `STORAGE_IMPL` | `bucket_exists` → create on first write (`docs/09-storage/storage-flow.md`) |
| Redis | Single adapter: streams, locks, sessions, heartbeats, cache | Shared by both engines and the worker; one key-name registry |
| MySQL | Peewee pooled with retry (5 retries, backoff) and GORM | `@DB.connection_context()` on every service call; workers close connections before long inference |
| Sandbox executor manager | HTTP from code-exec tool (`:9385`) | Optional compose profile; needs Docker socket |
| MCP servers (as client) | `common/mcp_tool_call_conn.py` over SSE/stdio | Tools discovered at agent init |
| Langfuse | Observation hooks inside `LLMBundle` | Per-tenant config (`TenantLangfuse`) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| SPA ↔ backends | REST + SSE via Nginx only | Bearer token; envelope; 401 → logout |
| Go server ↔ Python server | None directly; shared MySQL, Redis, secret key | Token and password-hash formats are the contract |
| Python API ↔ worker | Redis stream (API → worker), MySQL rows (worker → API) | No RPC; idempotent tasks |
| API / worker ↔ DocStore | `DocStoreConnection` | Expression objects only |
| API / worker ↔ blobs | Storage factory | Keys `{tenant_id}/{doc_id}` |
| Chat / agent ↔ retrieval | In-process call to `Dealer` | Same code path for chat, search API and Retrieval component |
| Anything ↔ models | `LLMBundle` | Never instantiate a driver directly |
| Agent engine ↔ API | `agent_api` constructs `Graph`; engine yields events | Engine has no HTTP dependency |
| CLI ↔ system | Public REST API | No direct DB access |

---

## Sources

Primary (authoritative, HIGH): `docs/spec.md`; `docs/00-overview/*`; `docs/02-frontend/{directory-structure,frontend-architecture,frontend-data-flow,api-client}.md`; `docs/03-backend/*`; `docs/04-api/{api-overview,api-call-flow,endpoint-catalog}.md`; `docs/apis.md` (lines 1–145); `docs/05-rag-pipeline/{complete-rag-flow,ingestion-pipeline,indexing}.md`; `docs/06-document-processing/{document-lifecycle,document-processing-workers}.md`; `docs/07-retrieval/retrieval-flow.md`; `docs/08-database/{database-overview,schema,entities,relationships,database-flow,migrations}.md`; `docs/09-storage/{storage-overview,storage-flow}.md`; `docs/10-cache-and-queues/*`; `docs/11-llm/{llm-architecture,provider-abstraction}.md`; `docs/12-chat/chat-architecture.md`; `docs/13-agents/{agent-architecture,agent-overview}.md`; `docs/14-workflows/{workflow-engine,workflow-overview}.md`; `docs/15-cli/cli-overview.md`; `docs/16-auth/{multi-tenancy,sessions,tokens}.md`; `docs/17-integrations/vector-database-integrations.md`; `docs/18-deployment/{services,production-architecture,networking,docker-compose,deployment-overview}.md`; `docs/19-testing/test-architecture.md`; `docs/22-code-tracing/*`; `docs/23-diagrams/*.mmd`.

Secondary (reference repo, used only where docs are silent or tied; MEDIUM): `/home/logan78/desktop x/ragflow` — top-level layout; `docker/nginx/ragflow.conf.{python,golang,hybrid}`; `docker/entrypoint.sh` (`API_PROXY_SCHEME`); `web/vite.config.ts` (dev proxy); `common/doc_store/doc_store_base.py` (interface surface); `common/settings.py` (`DOC_ENGINE`, queue names); `api/utils/api_utils.py` (envelope); `internal/utility/token.go`, `internal/common/password.go` (cross-language auth contract); directory listings of `api/`, `rag/`, `deepdoc/`, `agent/`, `internal/`, `test/`.

Not consulted: `docs/apikey llm.md` (off-limits). Not read in full: `docs/01-*` (absent), `docs/20-security/*`, `docs/21-end-to-end-flows/*` (searched, not read end to end), `docs/24-learning/*`, most per-resource files in `docs/04-api/`. No web sources were needed; the architecture is prescribed.

---
*Architecture research for: devRag enterprise RAG platform*
*Researched: 2026-10-05*
