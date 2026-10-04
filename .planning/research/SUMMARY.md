# Project Research Summary

**Project:** devRag
**Domain:** Enterprise multi-tenant RAG platform — a complete implementation of the reverse-engineered RAGFlow specification in `docs/` (dual-stack Go Gin + Python Quart, React SPA, DeepDoc parsing, hybrid retrieval, cited streaming chat, agent/workflow canvas)
**Researched:** 2026-10-05
**Confidence:** MEDIUM

Detail lives in [STACK.md](./STACK.md), [FEATURES.md](./FEATURES.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [PITFALLS.md](./PITFALLS.md). This file integrates them and is the input to roadmap creation.

## Executive Summary

devRag is not a product to be designed; it is a prescribed architecture to be implemented. `docs/` describes six layers (SPA, Nginx ingress, two API servers, Python RAG/agent/DeepDoc libraries, a Redis-Streams task executor, and MySQL / Redis / MinIO / doc-store persistence) and roughly 525 documented feature rows across 28 categories, all of which are v1 because the project has no MVP cut. The research agrees on the shape: Go owns identity, tenant, system, search-bot, MCP, CLI and admin routes; Python owns datasets, documents, chat, agents and all ML; the two never call each other and integrate only through one MySQL schema, one Redis, and one shared token/secret contract. Three ports sit behind every engine (`DocStoreConnection`, the storage factory, `LLMBundle`), and ingestion is strictly enqueue-and-return with progress reported by database row.

The recommended approach is: reconcile first, then build one thin, entirely real vertical slice to a cited answer, then widen. The docs contradict themselves in load-bearing places (ports, queue technology, response envelope, SSE framing, chunk IDs, citation markers, default engine, schema owner, extent of Go parity), and the previous attempt died from exactly the two failure modes this implies: silently "resolving" the spec differently in each phase, and building breadth for eight parts without ever producing an answer. So the roadmap must open with a reconciliation and guardrails stage that writes every contradiction into a decision register, then follow ARCHITECTURE.md's seven-stage dependency order, holding stages 3 to 5 to the narrowest path that reaches PROJECT.md's Core Value (upload a text-layer PDF, `naive` chunk, embed, index in Elasticsearch, hybrid retrieve, stream a cited answer through Nginx) before any breadth work starts.

The main risks are, in order: (1) the host cannot currently run the documented stack (6.0 GB free disk, about 5 to 6 GB free RAM, `vm.max_map_count` too low for Elasticsearch, no GPU, no LLM key) and several of these need user action that agents cannot perform; (2) agents shipping fakes as done because no real model is reachable, which directly violates the Core Value; (3) dual-stack drift (two ORMs, two auth implementations, duplicated routes); (4) cross-tenant leaks, since isolation is by convention and child entities carry no `tenant_id`; (5) an unresolved scope question about how much of the Python engine must also exist in Go, which roughly doubles stages 4 to 6 if answered "all of it". Every resolution proposed in this document is a recommendation from research. None has been confirmed by the user.

## Key Findings

### Recommended Stack

Follow the documented stack exactly, pinned to the reference repo's lockfiles (RAGFlow 0.26.4, commit `6677f14`) as a known mutually compatible baseline. Pins are "start here", not "latest": they were not individually re-verified against registries. See [STACK.md](./STACK.md) for the full tables and install commands.

**Core technologies:**
- **Frontend:** React 18.3 + TypeScript 5.9 + Vite 7 + React Router 7 + Zustand 4 + TanStack Query 5 + Axios + Tailwind 3.4 + shadcn/ui + `@xyflow/react` 12 — all named in `docs/`; stay on these majors (no React 19, Tailwind 4, zod 4, Zustand 5).
- **Python engine:** Python 3.13 via `uv`, Quart 0.20 + Hypercorn + quart-schema (OpenAPI), Peewee 3.19 + PyMySQL, itsdangerous (token signing), LiteLLM pinned exactly to `1.84.0` (1.82.7/1.82.8 were malicious releases), openai / ollama SDKs, tiktoken.
- **Go engine:** Go 1.22+ (host has a newer toolchain), Gin 1.12, GORM 1.25.7, Zap, go-redis v9, Viper, minio-go, go-elasticsearch v8, `peterh/liner` for the CLI.
- **Infrastructure:** MySQL `8.0.40` (docs pin; EOL since 2026-04-30), `valkey/valkey:8`, `pgsty/minio` (upstream `minio/minio` is no longer published), Elasticsearch `8.11.3` as the default doc engine with Infinity `0.7.x` as the second adapter, Nginx.
- **ML runtime:** `onnxruntime` CPU + OpenCV headless + `numpy<2` + xgboost, with ONNX models from `InfiniFlow/deepdoc` fetched at build/bootstrap time. No PyTorch, PaddleOCR, ultralytics, transformers, or PyMuPDF (AGPL) in base dependencies; local embeddings go through Ollama or TEI out of process.
- **Testing:** pytest 9 + pytest-asyncio, `go test` with build-tag tiers, Vitest + Testing Library, Playwright for end-to-end flows.

**Do not use:** FastAPI/Flask/Django, SQLAlchemy/Alembic, Celery/Kafka/RabbitMQ, LangChain/LlamaIndex as pipeline core, UmiJS, Ant Design, Redux, native `EventSource` (cannot send POST bodies or `Authorization`), Pinecone/Weaviate/Chroma.

### Expected Features

"Table stakes" here means "explicitly documented in `docs/`". All of it is v1; ordering is build order, not scope. See [FEATURES.md](./FEATURES.md) for stable `CATEGORY-NN` IDs intended to be lifted into REQUIREMENTS.md.

**Must have (Core Value path, tier T1):**
- Foundation: DEPLOY-02/03/04, DATA-01..05, API-01..11, SYS-01..07
- Identity and tenancy: AUTH-01..23, TEN-01..13, UI-01..08
- Model configuration: LLM-01..09, LLM-14..28, UI-37 (dataset creation needs an embedding dimension)
- Upload to cited answer: KB-01..09, STOR-01/02, DOC-01..16, ING-01..16, PARSE-01..03 and 09..13, CHUNK-01/02/16..19, IDX-01..10, RETR-01..19, CHAT-01..23, UI-10..25, E2E-01..09 and E2E-12

**Must have (documented breadth, tiers T2/T3, after the Core Value gate):**
- Deep parsing: layout analysis, OCR, table structure (PARSE-04..08, 18..25), the other 13 chunkers, LLM enrichment and RAPTOR (CHUNK-03..15, 20..27)
- Workflow engine and agents: FLOW-01..36, AGT-01..38, UI-27..32, E2E-10/11
- Go-owned surface: CLI-01..17, ADMIN-01..07, SRCH-06/07, MCP-01..03
- Integrations: more storage and engine adapters, provider breadth, Langfuse, search apps, channels, connectors, templates
- SEC-01..10 and TEST-01..11 land with the features they cover, never as a final phase

**Pending user confirmation (v1.x):**
- `[P]`-flagged rows named in docs with no behavioural description (OAuth/OIDC login, captcha, custom RBAC GRANT/REVOKE, invitation codes, file manager, 11 extra background task types, GraphRAG filter keys, ASR/TTS/OCR model types, pages `files`/`skills`/`memory`, Helm, rate limiting, and others)
- Go mirrors of Python engines (PARSE-26, CHUNK-28, IDX-15, RETR-23, LLM-35, AGT-39, FLOW-37, ING-19/20)

**Defer (v2+):**
- Everything undocumented: full GraphRAG, evaluation harness, agent memory product, skills marketplace, connector catalogue, crawler, SAML/SCIM, audit log, Prometheus/OTel
- BILL-01..10, the metered-billing content pasted into `docs/apis.md` (pending user decision)

**Anti-features (forbidden by `docs/spec.md`):** mocked or placeholder stages presented as complete, silently skipping hard features, simplifying the documented architecture, adding undocumented services, copying RAGFlow source or cloning its look, declaring completion from static inspection.

### Architecture Approach

A single-ingress, dual-engine system with library-style cores. The SPA talks only to Nginx; Nginx routes explicit Go prefixes to `:9384` and everything else under `/api/` and `/v1/` to Python on `:9380`. `rag/`, `deepdoc/` and `agent/` are libraries with no HTTP so the same retrieval code serves chat, the search API and the agent Retrieval node. Top-level directory names are not free choices: the docs cross-reference paths such as `rag/nlp/search.py` and `internal/handler/auth.go`. See [ARCHITECTURE.md](./ARCHITECTURE.md).

**Major components:**
1. **React SPA (`web/`)** — views, canvas, typed API client, fetch-based SSE reader
2. **Nginx ingress** — static SPA, path routing, SSE-safe proxying (buffering off, long read timeout)
3. **Go Gin server (`cmd/`, `internal/`)** — auth, user, tenant, system, search bots, MCP, admin, CLI binary; touches only MySQL and Redis except for search bots
4. **Python Quart server (`api/`)** — datasets, documents, chunks, chat, agents, models; SSE; `update_progress` daemon
5. **Task executor (`rag/svr/`)** — Redis Streams consumer: lock, fetch blob, parse, chunk, embed, bulk index, progress, ack
6. **Ports:** `DocStoreConnection` (ES / Infinity), storage factory (MinIO / S3 / local), `LLMBundle` (per-tenant credentials, LiteLLM + direct drivers)
7. **Retrieval (`rag/nlp/` Dealer), chat (`dialog_service`, `rag/prompts/`), agent/workflow engine (`agent/` Graph + component registry)**

**Hard boundary rules:** SPA to ingress only; Go and Python never call each other over HTTP; workers never serve HTTP and report back only via MySQL rows; business code never names a concrete engine or provider; tenant ID is a required service/DAO argument, never a handler-level check.

### Critical Pitfalls

Nineteen pitfalls are documented in [PITFALLS.md](./PITFALLS.md). The ones that shape the roadmap:

1. **Spec drift** — agents fill thin docs with generic-RAG priors, or each resolves a contradiction differently. Prevent with a decision register written before the dependent phase, per-phase "docs read" lists and conformance tables, and CI tests pinning documented constants (`MAXIMUM_TASK_PAGE_NUMBER = 12`, `BATCH_SIZE = 64`, `te.1.common` / `te.0.common`, `q_{dim}_vec`, `ragflow_{tenant_id}`, field boosts, `topk = 1024`).
2. **Mocked functionality passing as done** — no key and no GPU make a `FakeEmbedder` the path of least resistance. Prevent by making real execution possible without secrets (a local model path), keeping fakes under `tests/` only, a CI grep gate on production trees, behavioural tests a fake cannot pass, and a `BLOCKERS.md` convention.
3. **Dual-stack ownership confusion** — one owner per route, one owner per table's DDL, a cross-stack contract suite (token issued by Go accepted by Python; identical envelope; identical tenant scoping), `X-API-Source` asserted in tests. The documented "JWT" is an itsdangerous-signed wrapper around a DB-stored `access_token`; a stock Go JWT library will reject it.
4. **Tenant isolation leaks** — `document` and `task` have no `tenant_id`; retrieval takes `kb_ids` from the request body; Redis cache keys are not tenant-namespaced. Prevent structurally (tenant-scoped service base, DocStore adapter builds the index name itself) and with a cross-tenant test matrix generated from the route table, extended as an exit criterion by every resource phase.
5. **Ingestion worker unreliability** — Redis Streams are at-least-once and the documented lock (`SET NX EX 60` + unconditional `DEL`) is unsafe. Prevent with delete-then-upsert per page range, owner-token locks, ack only after terminal state is persisted, `retry_count` cap of 3, a pending-entry reaper, and kill-the-worker / poison-message / re-parse idempotency tests.
6. **Host and heavy-ML limits** — see "Host/environment blockers" below.
7. **Position and citation loss** — positions must survive five transformations from PDF points to `position_int`; define one `ParsedBlock` and one `Chunk` type at the parser/chunker boundary before any second parser or chunker is written, and round-trip test on a PDF longer than 12 pages.
8. **Two documented security defects to deviate from on purpose** — the `RestrictedUnpickler` module-level `numpy` whitelist reproduces a known RCE, and a literal reading of `secrets.md` yields unsalted SHA-256 passwords.

## Host/environment blockers

Measured on this machine on 2026-10-05. Items marked "user action" cannot be fixed by agents and must be raised before the infrastructure stage starts.

| Blocker | Measured | Requirement | Consequence | Mitigation | Owner |
|---|---|---|---|---|---|
| **Disk** | 6.0 GB free, 97% used | Tens of GB for images (ES, MySQL, MinIO, app image with ONNX models), volumes, and optionally Ollama models | `docker compose up` or the first image build fails with `no space left on device` | Free space before stage 1. Record a per-image and per-volume budget in `DECISIONS.md`. Pruning Docker images/volumes may delete user data and needs consent | **User action** |
| **RAM** | 15 GB total; about 5 to 6 GB available (STACK measured ~6 GB, PITFALLS ~5 GB) | Docs set `MEM_LIMIT=8g` per engine container | ES is OOM-killed (`Exited (137)`) or the stack does not fit beside a desktop session | Dev/test compose override: single-node ES with `ES_JAVA_OPTS=-Xms1g -Xmx1g` and a 2 GB container limit, reduced MySQL buffer pool, one task-executor worker, `mem_limit` per service sized to the budget | Agents (stage 1); user may need to close other workloads |
| **`vm.max_map_count`** | 65530 | 262144 or higher for Elasticsearch | ES refuses to start or goes red | `sudo sysctl -w vm.max_map_count=262144` and persist it; compose preflight script checks it and prints an actionable error | **User action** (needs sudo) |
| **No GPU** | `nvidia-smi` absent | `gpu` compose profile; fast OCR/DLA and cross-encoder rerank | DEPLOY-06 cannot be verified here; OCR of long scans takes minutes; reranking 1024 candidates on CPU delays first token by tens of seconds | `onnxruntime` CPU only; configurable rerank candidate cap recorded as a decision if it differs from 1024; 2 to 3 page fixtures; record `gpu` profile as "built, unverified on this host" in `BLOCKERS.md` | Agents; residual blocker documented |
| **No LLM key and no Ollama** | No API keys configured in the session; a local Ollama install was not confirmed by any research file | A real chat model and a real embedding model for every stage from 3 onward | The Core Value ("no mocked stages") cannot be verified; strongest pressure toward shipping fakes | Either the user supplies an OpenAI-compatible key, or Ollama is added to the dev/test compose with one small chat model and one small embedding model (names and dimensions recorded in `DECISIONS.md`). Ollama models add several GB to the disk requirement | **User action** (choose and provide) |
| System Python | 3.10.12 | Python 3.13 recommended (3.10 is EOL this month) | Lockfile resolved for 3.13 will not install on system Python | `uv python install 3.13`; never use the system interpreter | Agents |
| Go toolchain | Reported as 1.26.4 (STACK) and 1.25.5 (PITFALLS) | Docs floor 1.22+ | None expected; the two research files disagree on the installed version | Verify with `go version` in stage 1 and pin `go.mod` accordingly | Agents |
| Project path | `/home/logan78/desktop x/devRag_@` (space and `@`) | — | Unquoted paths break scripts, bind mounts and test runners; `@` leaks into the default compose project name | Quote every path; set `name:` explicitly in compose; CI check that runs scripts from a path containing a space | Agents |
| Offline model provisioning | DeepDoc models download from Hugging Face at runtime in the reference | Workers must run with the network disabled in tests | First parse hangs; concurrent workers race the download | Fetch `InfiniFlow/deepdoc` (pinned revision, checksum) plus `cl100k_base` and `nltk_data` in a build/init step into a named volume; fail fast if absent. Licence and current file layout of that repo are unverified | Agents (stage 4 research) |
| Image availability | Not checked | `pgsty/minio:RELEASE.2026-03-25...`, `valkey/valkey:8`, `infiniflow/infinity:v0.7.x-x64-v3`, `infiniflow/sandbox-executor-manager` | A documented tag may not exist or pull | Verify each tag pulls before pinning; never substitute silently | Agents (stage 1) |

Host facts that are not blockers: 16 cores; AVX2 present (so the `x64-v3` Infinity image runs here, though not on every CI runner); Docker 29.1.3 with Compose v2 `include:` and `profiles:` support; Node 22.

## Doc contradictions & open decisions

One de-duplicated register merged from STACK.md (D1 to D12), FEATURES.md (C-1 to C-27 and "Needs User Decision"), ARCHITECTURE.md (A1 to A19) and PITFALLS.md (Pitfall 1 table and others). This is the seed for `.planning/DECISIONS.md` in stage 0.

**Status of every row: proposed, not user-confirmed.** The "Sign-off" column says whether the user should confirm before the dependent stage is planned ("Yes"), or whether the resolution follows from the `docs/spec.md` priority rule or is a documented tightening and only needs recording ("Record"). "Record" rows are still unconfirmed proposals. Where the four research files disagreed with each other, the row says so.

### Topology and ownership

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-01 | Server ports | Both engines on `:9380` (overview diagrams); Go `9380` / Python `9381` (`apis.md`); Python `9380`, Python admin `9381`, MCP `9382`, Go admin `9383`, Go `9384` (`18-deployment`) | Use the `18-deployment` assignment, plus sandbox `9385` and deepdoc `9390`. It is the only physically possible variant and three files agree. Proposed, not user-confirmed | Record | C-1, A1, Pitfall 1 |
| R-02 | Route ownership and proxy table | Docs give no location table, only "path-based routing". The reference ships three modes and defaults to Python-only; its hybrid table differs from the docs (sends chat completions to Go) | Derive from `04-api/endpoint-catalog.md`: explicit Go prefixes (`/health`, `/api/v1/system/`, `/api/v1/language`, `/api/v1/auth/`, `/api/v1/users`, `/v1/user/`, `/v1/tenant/`, `/api/v1/searchbots/`, `/api/v1/mcp`), Python catch-all. Docs win over the reference. Generate Nginx config and the Vite dev proxy from one route list. Proposed, not user-confirmed | Yes | A2, STACK (a), Pitfall 2 |
| R-03 | Extent of Go parity | Docs describe Go counterparts of parsers, chunkers, doc-store drivers, retrieval, model service, Eino canvas, ingestor, chat handlers, yet the catalogue assigns each route to one engine | Go builds what the catalogue assigns it. Go mirrors of Python engines are deferred and recorded as undelivered parity items, never stubbed. This is the largest scope question in the project: answering "build all mirrors" roughly doubles stages 4 to 6. Proposed, not user-confirmed | **Yes** | C-20, A4, Pitfall 2 |
| R-04 | How Go reaches Python-owned capability | CLI docs call `:9384/v1/dataset/list` (a Python route); search bots and MCP are Go-owned but need retrieval. **Researchers disagree:** STACK D11 proposes that Go reverse-proxies unmatched paths to Python; ARCHITECTURE rule 3 says the servers never call each other; PITFALLS flags a proxy-only Go handler as a drift warning sign | No Go-to-Python proxying. The CLI targets canonical routes through the ingress. How Go search bots obtain retrieval (native Go doc-store driver vs a documented bridge) is decided by stage 7 research. Proposed, not user-confirmed | **Yes** | D11, C-24, A-rule 3, Pitfall 2 |
| R-05 | Upload, parse trigger, public chatbot owner | Upload is "Python / Go"; one doc sends upload and parse to Go; `upload.md` auto-enqueues on upload while the end-to-end flow leaves the document UNSTART until Parse is clicked; chatbot route is Go in one file, Python in another | Python owns upload, parse and chatbot completions. Upload does not enqueue; parsing is an explicit step. A Go upload at the dataset-scoped path is optional parity in stage 7. Proposed, not user-confirmed | Record | C-8, A3 |
| R-06 | Schema and migration owner | Python `init_web_db()`, Go `--migrate` + `migration.go`, and `docker/init.sql` all claim to create schema | One writer: Peewee models own DDL and migrations, run as a one-shot step before either server starts. GORM maps the result with AutoMigrate off; `--migrate` only verifies. `init.sql` creates the database and grants only. CI contract test diffs the two definitions. This narrows the documented meaning of Go `--migrate`. Proposed, not user-confirmed | Yes | D1, A8, Pitfall 2 |
| R-07 | Container topology | Docs and reference run Nginx + Go + Python + executors in one app container; scaling docs draw a separate worker container | No research file made a recommendation. Default to the documented single app container plus a standalone task-executor container (DEPLOY-17); if split further, Nginx upstreams use service names. Decide in stage 1. Proposed, not user-confirmed | Record | Pitfall 18, DEPLOY-17 |
| R-08 | DeepDoc placement | In-process library called by the worker (all call chains) vs separate `deepdoc` container on `:9390`; the security docs want native parsing isolated | In-process in the worker by default; honour `DEEPDOC_URL` and ship the `deepdoc` profile later. Parsing never runs in the API process. Proposed, not user-confirmed | Record | A15, SEC-08, PARSE-24 |
| R-09 | Identifier naming | Docs use `ragflow_server`, index prefix `ragflow_`, bucket `ragflow`, compose network `ragflow` | Keep as documented. If the user prefers `devrag_*`, it must be one constant per language, decided before any index or bucket is created. Proposed, not user-confirmed | Yes | ARCHITECTURE structure rationale |

### Queue, ingestion and state

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-10 | Task queue technology | Redis Streams `te.{priority}.common` with consumer groups; Redis list `ragflow_TASK_EXE_QUEUE`; NATS JetStream | Redis Streams, the only variant with ack/reclaim semantics and the one specified in detail. Put the queue behind an interface; NATS only if the Go ingestor is ever built (R-03). Proposed, not user-confirmed | Record | D2, C-2, A5, Pitfall 1 |
| R-11 | Chunk ID scheme | Docs: `doc_id + "_" + chunk_order`. Reference: `xxhash64(content + doc_id)`. The docs scheme is underdetermined for parallel 12-page sub-tasks; the hash collapses identical chunks | Docs scheme by the priority rule, with ordering made deterministic per page range; exact construction settled in stage 4 research. Whichever is chosen, a task deletes its prior chunks for `(doc_id, from_page, to_page)` then upserts. Proposed, not user-confirmed | Yes | Pitfall 1, Pitfall 6, IDX-07 |
| R-12 | Redis distributed lock | Documented as `SET NX EX 60` with unconditional `DEL` on release, which lets a slow task delete another worker's lock | Tighten: owner token, compare-and-delete release, TTL renewal while the task runs. Proposed, not user-confirmed | Record | Pitfall 6 |
| R-13 | Embedding batch size | Docs `BATCH_SIZE = 64`; reference default 16 | 64 per docs, configurable per provider to respect provider limits. Proposed, not user-confirmed | Record | Pitfall 7 |
| R-14 | Document and task state vocabulary | `run` codes `0` to `4` vs glossary `3 = FAIL` vs string states in flows; diagrams show a `task.status` column the DDL lacks | `document.run` char codes per `06` (`3` finished, `4` failed); `document.status` is the soft-delete flag; task state derives from `progress` (`-1` failed). Diagram-only states are progress messages. Proposed, not user-confirmed | Record | C-4, A11 |
| R-15 | Dedup hash | `xxh64` vs "xxhash/md5" | `xxh64`. Proposed, not user-confirmed | Record | C-9 |
| R-16 | Progress delivery to the UI | Not specified | Polling: one list endpoint refetch with backoff while any row is running. Proposed, not user-confirmed | Record | A18 |

### Storage, index and retrieval

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-17 | Default doc engine | `indexing.md` calls Infinity the default; deployment env vars and the reference default to Elasticsearch | Elasticsearch 8.11.3 for compose default and integration tests; Infinity as the second adapter behind the same interface. Note the trade-off: ES needs more RAM than this host comfortably has (see blockers). Resolves the pending Key Decision in PROJECT.md. Proposed, not user-confirmed | Yes | STACK (b), C-17, A12, Pitfall 1 |
| R-18 | Engines beyond ES and Infinity | Docs list 8+ engines and the list differs per file; the reference has no Qdrant, Milvus or PGVector adapter at all | Order: ES, Infinity, then OpenSearch. Qdrant / Milvus / PGVector / OceanBase / Tantivy / ClickHouse / SereneDB / SeekDB need their own research and an explicit "is this in scope for complete" answer. Proposed, not user-confirmed | **Yes** | D8, C-17, A12 |
| R-19 | Index naming and vector-level isolation | `ragflow_{tenant_id}` vs `ragflow_{kb_id}` vs "index chunks with `tenant_id` fields" | One index per tenant, datasets separated by `kb_id` filter. The adapter takes `tenant_id` and builds the index name itself; callers never pass one. Proposed, not user-confirmed | Record | C-3, Pitfall 1, ARCHITECTURE (d) |
| R-20 | Tenant scoping of documents and tasks | "Every entity references `tenant_id`" vs DDL where `document` and `task` have none; samples use `current_user.tenant_id`, which is not a user column, and resolve API tokens as if tenant ID were user ID | Follow the DDL. Enforce isolation transitively through `knowledgebase.tenant_id`; membership through `user_tenant`; resolve current tenant in auth middleware. Do not copy the tenant-equals-owner assumption. Proposed, not user-confirmed | Record | A10, Pitfall 5 |
| R-21 | Object storage layout | Bucket `ragflow` with key `{tenant_id}/{doc_id}` (`09`); bucket `ragflow-{tenant_id}` (`17`); "randomized UUID object names" (`20`). **Researchers disagree:** ARCHITECTURE proposes `{tenant_id}/{doc_id}`; PITFALLS proposes `{kb_id}/{uuid}` | Bucket `ragflow`, key `{tenant_id}/{doc_id}`, stored in `document.location`. The key contains only generated IDs, so no user-supplied filename enters it, which is what the security doc is protecting. Azure Blob remains `[P]`. Proposed, not user-confirmed | Yes | C-18, A13, Pitfall 15 |
| R-22 | Queries across datasets with different embedding models | Query column is derived from query-vector length; a mismatch yields silent zero vector recall | Always embed the query with the dataset's model; reject a multi-dataset query whose datasets use different `embd_id`s with a clear error; lock `embd_id` once a dataset has chunks. Proposed, not user-confirmed | Record | Pitfall 7 |
| R-23 | Fusion method and weight direction | Weighted sum and RRF (`k = 60`) both documented without saying when each applies; `vector_similarity_weight = 0.3` vs `rerank_by_model(tkweight=0.3, vtweight=0.7)` | Weighted sum is the implemented path for the default engine, RRF an option. Keep each documented default in its own function, name functions after the documented ones, and add a golden test that fails if the weights are swapped. Proposed, not user-confirmed | Record | C-23, Pitfall 1, Pitfall 8 |

### API contract and streaming

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-24 | Response envelope keys | `{retcode, retmsg, data}` (`04-api/api-overview.md`, `02`, `03`) vs `{code, message, data}` (`21`, `22`, `11`, diagrams) | `{code, message, data}`. Docs split evenly, so the reference breaks the tie. Defined once per language and in one TS interface. `04-api` nominally owns this contract and says the opposite. Proposed, not user-confirmed | Yes | D12, C-7, A6 |
| R-25 | Path prefixes and legacy aliases | Completion, session, dataset and login routes each appear under two to four paths (`/api/v1/...`, `/v1/...`, `/v1/api/...`); CLI docs use paths absent from the catalogue | `04-api/endpoint-catalog.md` plus `apis.md` lines 1 to 139 are canonical. Legacy aliases are not served unless the user asks. The CLI calls canonical routes. Proposed, not user-confirmed | Record | D12, C-5, C-24, A7 |
| R-26 | Chat SSE framing | Terminator `data: [DONE]` (`12`, `04`) vs `data: {"code":0,"data":true}` (`21`, diagram); reference payload on the final frame (`12`) vs the first frame (`21`, call chain); delta vs cumulative `answer` not stated. **Researchers disagree:** ARCHITECTURE proposes the enveloped `true` terminator with reference first; FEATURES and PITFALLS follow `12-chat/streaming.md` | Follow `12-chat/streaming.md`, the section that owns the protocol: enveloped frames, `reference` on the final frame, `data: [DONE]` terminator. Delta-vs-cumulative resolved in stage 5 research by reading `12-chat/complete-chat-flow.md` and `21-end-to-end-flows/chat-streaming.md` in full. One shared frame encoder per stack; client tolerant of either reference timing. Proposed, not user-confirmed | Yes | C-6, A7, Pitfall 10 |
| R-27 | Citation marker | `##N$$` (`12`, `21`, glossary) vs `[ID:n]` (reference prompt, `05`, `11`) vs `[1]` | `##N$$` in stored answers. Prompt, post-processor, stored message and frontend parser must agree; indices refer to the frozen retrieved list for that turn. Proposed, not user-confirmed | Record | C-6, Pitfall 1, Pitfall 9 |
| R-28 | Workflow SSE event names | `workflow_started` / `node_started` / `node_finished` / `message` / `workflow_finished` (`14`) vs `component_start` / `node_start` (`21`) | Follow `14`, which has payload schemas. Proposed, not user-confirmed | Record | C-14 |
| R-29 | Health endpoint | `/health`, `/api/v1/system/ping`, `/system/healthz`, `/v1/system/health`, `/v1/admin/health` | Serve `/health` (Go) and `/system/healthz` (Python); point the compose check at one; health reports each dependency, not just liveness. Proposed, not user-confirmed | Record | C-21, Pitfall 18 |
| R-30 | Reliability of per-resource API docs | Thirteen `04-api/*-api.md` files pair routes with wrong handler names and omit CRUD verbs; no logout endpoint is documented anywhere | Treat those files as evidence that a route exists; confirm verb, body and semantics against the reference during each phase's research. Define a logout route in stage 2 and record it. Proposed, not user-confirmed | Record | C-13 |
| R-31 | Table and column names | `dialog` / `conversation` / `api_4_conversation` vs `chat_dialog` / `chat_session`; `UserCanvas` vs `canvas`; `embd_id` vs `emb_id`; `agent_session`, `canvas_replica`, `tenant_token_usage` appear in flows only; full DDL exists for 3 of about 40 entities | Follow `08-database/`. Map `agent_session` to `API4Conversation` and `canvas_replica` to `UserCanvasVersion`; decide token-usage storage in stage 5. Column-level DDL for the other entities comes from the reference `db_models.py`. Proposed, not user-confirmed | Record | C-7, A9 |
| R-32 | CORS policy | `allow_origin="*"` (`03`) vs whitelisted origins (`20`) | Configurable allow-list defaulting to same-origin behind the proxy; never wildcard with credentials. Proposed, not user-confirmed | Record | C-25, Pitfall 16 |

### Auth and security

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-33 | Access-token format | Docs say "signed JWT" but quote an itsdangerous serializer wrapping a UUID `access_token` stored on the user row; one doc claims expiry checks the snippet does not show | The stored-`access_token` model: Go issues at login, both engines verify by decoding then looking up the row, logout rewrites it to `INVALID_<hex>`. One encoding implemented in both languages with shared test vectors. Expiry semantics must be specified in stage 2. Proposed, not user-confirmed | Record | D7, C-11, ARCHITECTURE (a), Pitfall 16 |
| R-34 | Password hashing | "PBKDF2 / Bcrypt"; werkzeug `check_password_hash`; `secrets.md` says "SHA256 / AES" | Werkzeug-format hashes (scrypt / pbkdf2) verified natively in Go, as the reference does. Never unsalted SHA-256. Confirm against `docs/16-auth/authentication.md` in stage 2 research. Proposed, not user-confirmed | Record | D7, C-10, A16, Pitfall 11 |
| R-35 | Client token storage | `localStorage` key (`02`) vs signed `ragflow_auth` cookie (`21`, glossary) | Bearer header from `localStorage`; cookie only for the documented session fallback, with CSRF protection if used. Proposed, not user-confirmed | Record | C-12 |
| R-36 | Who may invite members | Owner and admin (`authorization.md`) vs owner only (`permissions.md` matrix) | Follow the matrix: owner only. Proposed, not user-confirmed | Record | C-22 |
| R-37 | Provider key storage | Docs require encryption at rest and masking; the reference stores `tenant_llm.api_key` in plaintext | Docs win: AES-GCM with an env-supplied key, ciphertext + nonce + key version, one test vector shared by Go and Python; single masking serializer; empty or masked value on update means "unchanged"; log redaction. The algorithm is a choice the docs leave open. Proposed, not user-confirmed | Record | Pitfall 1, Pitfall 11, SEC-02/03 |
| R-38 | Restricted unpickler | `file-security.md` presents a module-level `numpy` whitelist as the mitigation while naming `numpy.f2py.diagnose.run_command` as the exploit; the reference `SECURITY.md` confirms the bypass | Deliberate deviation from the docs: no pickle on any data crossing a trust boundary; if the helper must exist, whitelist exact `(module, name)` pairs and keep the documented PoC as a regression test. Proposed, not user-confirmed | Yes | Pitfall 15, SEC-05 |
| R-39 | Sandbox executor | 512 MB (`13`) vs 256m (`18`, `20`); Docker/Wasm with Python/SQL vs Docker with Python/Node.js; docs reference an `infiniflow/sandbox-executor-manager` image of unverified availability that mounts the Docker socket | Docker, Python + Node.js, 256m and 10 s defaults, configurable. Build our own manager under `agent/sandbox/` rather than depend on the third-party image. The Code node is not shippable without it; if it cannot be completed it is a recorded blocker, never a host `exec`. Proposed, not user-confirmed | Yes | D9, C-15, Pitfall 14 |
| R-40 | Auth snippet transcription | The documented `_load_user()` crashes on a missing header, tries every scheme on the same string, and shows no expiry | Treat as a behavioural description. Write an auth contract (schemes per route group, parsing rules, error codes, expiry, logout); default-deny route registration; route-enumeration 401 test on both stacks. Proposed, not user-confirmed | Record | Pitfall 16 |

### Stack, versions and scope

| ID | Topic | Conflict | Proposed resolution (proposed, not user-confirmed) | Sign-off | Merged from |
|---|---|---|---|---|---|
| R-41 | Python version | Docs: "3.10+" and a "Python 3.10 slim" base image. Reference: 3.13 only. 3.10 reaches end of life this month | Python 3.13 via `uv`, `requires-python = ">=3.13,<3.14"`. A deviation from the `docker.md` base-image line. Proposed, not user-confirmed | Yes | D3 |
| R-42 | MySQL version | Docs pin `mysql:8.0.40`, which has had no security patches since 2026-04-30 | Parameterise as `MYSQL_IMAGE`, default to the docs pin. Ask the user to approve `mysql:8.4` LTS; if approved, verify auth-plugin behaviour with PyMySQL and go-sql-driver (untested). Proposed, not user-confirmed | Yes | D4 |
| R-43 | Redis 7 vs Valkey 8 | `technology-stack.md` and PROJECT.md say Redis 7; deployment docs say `valkey/valkey:8` | `valkey/valkey:8` (most specific doc, wire-compatible). Restrict to core commands so either works. Proposed, not user-confirmed | Record | D5 |
| R-44 | ML runtime and PDF library | "PyTorch / PaddleOCR / YOLOv8 / Transformers / HanLP" vs "ONNX"; "PyMuPDF fitz / pdfium" | `onnxruntime` + `InfiniFlow/deepdoc` models; pdfplumber + pypdfium2. No torch and no PyMuPDF (AGPL) in base dependencies. This reads the docs' PyTorch line as model lineage rather than a runtime requirement, which is an interpretation. Proposed, not user-confirmed | Yes | D6, STACK (c), Pitfall 12 |
| R-45 | Python framework wording | Quart ASGI nearly everywhere vs "Flask + Gunicorn/WSGI" in three files | Quart + Hypercorn; the Flask mentions are stale. Proposed, not user-confirmed | Record | C-16, A14, Pitfall 1 |
| R-46 | Frontend stack details | "Vite/UmiJS"; "shadcn/ui + Ant Design"; "React Query" vs "custom hooks" | Vite only, shadcn/ui only (no `antd`), TanStack Query wrapped in `use-*-request` hooks. PROJECT.md already records Vite + shadcn. Proposed, not user-confirmed | Record | D10, C-26, Pitfall 1 |
| R-47 | Chunker and node catalogues | "14 chunkers" vs 7 to 10 in other lists; 20 nodes in `14-workflows/nodes.md` with Code, Image Generate, Keyword Extract, Rewrite and Parallel named elsewhere | Build the 14 chunkers and the 20 catalogued nodes plus Code. Unimplemented `parser_id`s are rejected explicitly, never aliased to a generic chunker. The remaining nodes are `[P]`. Proposed, not user-confirmed | Record | C-19 |
| R-48 | Foreign content in `docs/apis.md` | From about line 140 the file is an unrelated Q&A on a metered API-key billing platform (PostgreSQL, Stripe, Kafka, credits ledger) that no other doc references | Treat lines 1 to 139 as specification and the remainder as non-normative; BILL-01..10 stay out of v1. If billing is intended scope it is a new subsystem and must be planned explicitly. Proposed, not user-confirmed | **Yes** | C-27, A17, FEATURES "Needs User Decision" |
| R-49 | `docs/apikey llm.md` | Not read by any researcher or by this synthesis (off-limits, possible credential material). It may contain per-tenant model or API-key requirements affecting the LLM layer | User reviews it. Until then it is neither committed nor relied on; add it and `.env*` to `.gitignore` in stage 0 and never run `git add docs/` wholesale. Proposed, not user-confirmed | **Yes** | A19, Pitfall 11, PROJECT.md |
| R-50 | Real model for verification | Core Value forbids mocked stages; no key is configured | Add Ollama (a documented provider) to the dev/test compose with one small chat and one small embedding model, or use a user-supplied OpenAI-compatible key. Integration tier uses a scripted OpenAI-compatible stub in the test harness only; a separately marked tier uses the real local models. Proposed, not user-confirmed | **Yes** | STACK variants, Pitfall 4, Pitfall 13 |
| R-51 | `[P]`-flagged features | Dozens of rows are named in docs with no behavioural description | Schedule as v1.x pending user confirmation; each needs phase research against the reference before it can be specified. Not silently dropped: listed in REQUIREMENTS.md with that status. Proposed, not user-confirmed | Yes | FEATURES "Add After Validation" |
| R-52 | Rerank candidate window on CPU | Docs default `top = 1024`; cross-encoder over 1024 candidates on CPU takes far too long on this host | Keep 1024 as the documented default constant; add a configurable cap for the rerank model call and record the dev value after timing it. Proposed, not user-confirmed | Record | Pitfall 8, Performance traps |

**Sign-off summary:** 20 rows need user confirmation (R-02, 03, 04, 06, 09, 11, 17, 18, 21, 24, 26, 38, 39, 41, 42, 44, 48, 49, 50, 51), in addition to the three user actions in the blockers table (disk, `vm.max_map_count`, model access). The six in bold (R-03, R-04, R-18, R-48, R-49, R-50) change scope or unblock the Core Value and should be asked first.

## Implications for Roadmap

The structure is fixed by two findings that all four research files support: reconcile and install guardrails before any code, then follow ARCHITECTURE.md's seven-stage dependency order while holding stages 3 to 5 to a thin, real vertical slice. Breadth comes only after a cited answer exists.

### Stage 0: Spec reconciliation and guardrails
**Rationale:** The prior attempt failed on drift and on fakes. Every later plan depends on decisions that are currently unresolved, and the host cannot yet run the stack.
**Delivers:** `.planning/DECISIONS.md` seeded from the register above with user answers to the "Yes" rows; `.planning/BLOCKERS.md` convention; `.gitignore` covering `docs/apikey llm.md` and `.env*`; host budget (disk, RAM) and preflight requirements; the tiered requirement list (T1 Core Value path, T2 documented end-to-end flows, T3 everything else); the endpoint checklist counted from `endpoint-catalog.md` and `apis.md`; CI gates (placeholder grep on production trees, no-`sleep` in tests, pickle ban); test conventions (`wait_until` helper, per-test tenant fixture, unit / integration / e2e tiers).
**Addresses:** No feature rows; it is the precondition for all of them.
**Avoids:** Pitfalls 1, 3, 4, 11 (off-limits file), 12 (budget), 13.
**Exit gate:** No "Yes" row that a stage 1 to 3 plan depends on is unresolved; disk and `vm.max_map_count` fixed by the user; a real model source chosen.

### Stage 1: Foundation and dual-stack skeleton
**Rationale:** Two ORMs bind to one schema; changing it later is a two-language change. Proxy configuration determines whether streaming ever works.
**Delivers:** Repo skeleton per the documented tree; compose base (MySQL, Valkey, MinIO, Elasticsearch) with health-gated ordering, a one-shot init job, reduced dev limits and a preflight script; config loading in both languages; full schema with one migration owner; Quart app factory and Gin engine with the shared envelope, error handling, structured logging with redaction, `X-API-Source`; health endpoints on both; Nginx route table with SSE-safe `proxy.conf`; OpenAPI generation; SPA scaffold with generated client types.
**Addresses:** DEPLOY-02/03/04/12/13, DATA-01..06, API-01..13, SYS-01..07, UI-01/03.
**Avoids:** Pitfalls 2 (DDL owner), 10 (proxy), 17 (contract), 18 (compose ordering).
**Exit gate:** Clean-room `down -v && up` from documented instructions reaches healthy; both engines answer through Nginx and tests assert which one answered; schema migrates from empty; both test harnesses run.

### Stage 2: Identity, tenancy, authorization
**Rationale:** Python cannot be exercised without a token Go issued; a temporary Python login would hide the cross-language contract until late.
**Delivers:** Go register / login / password reset / user and tenant routes; Python `login_required` with JWT, API token, beta token and session fallback; API-token CRUD; role checks; the shared token and password-hash contract with cross-language test vectors; tenant-scoped service base and GORM scope; the cross-tenant test-matrix generator and route-enumeration 401 test; SPA login, register, auth interceptor, settings.
**Addresses:** AUTH-01..23, TEN-01..13, UI-02, UI-04..08, UI-34..36, E2E-01/02.
**Avoids:** Pitfalls 2, 5, 16.
**Exit gate:** Register and log in via Go; the same token is accepted by a Python route; logout invalidates on both; cross-tenant access is indistinguishable from not-found.

### Stage 3: Model layer, datasets, storage, upload
**Rationale:** Embedding is a mandatory ingestion step and fixes the index's vector dimension, so the LLM layer precedes ingestion. Dataset creation validates the embedding model.
**Delivers (thin first):** `LLMBundle` with chat and embedding drivers for one real provider plus the conformance suite; tenant provider/model config APIs with encrypted, masked keys and test-connection on save; dataset CRUD with parser and retrieval config; storage factory with MinIO and local drivers; upload pipeline (streamed, size-limited at every hop, extension and magic-byte checks); document list/delete; matching SPA pages.
**Addresses:** LLM-01..05, LLM-14..28, KB-01..09, STOR-01/02/06/08/11, DOC-01..08, DOC-14..16, UI-10..12, UI-37, E2E-03/04, SEC-02/03/06.
**Avoids:** Pitfalls 11, 15, 19.
**Exit gate:** With a real key or local Ollama, `encode()` and `chat()` succeed for a tenant; a PDF uploads, its blob is in MinIO under the decided key, and the row shows `run='0'`.

### Stage 4: Ingestion pipeline
**Rationale:** Retrieval cannot be verified by realistic execution until real chunks exist. The DocStore interface is written here with `search` included so stage 5 does not reshape it.
**Delivers (thin first):** Redis adapter (streams, consumer group, token-based lock); task creation with page splitting; parse and cancel endpoints; task executor with limiters, heartbeat, ack-after-persist, retry cap, reaper; `DocStoreConnection` plus the Elasticsearch adapter with dynamic `q_{dim}_vec` mapping; tokenizer; shared `ParsedBlock` and `Chunk` types; text-layer PDF, DOCX, XLSX, PPTX, HTML and TXT parsers; the `naive` chunker; `update_progress`; chunk list/create APIs; SPA parse trigger, progress badges, chunk viewer.
**Addresses:** ING-01..16, PARSE-01..03, PARSE-09..13, CHUNK-01/02/16..19, IDX-01..09, DOC-09..13, UI-13..17, E2E-05/06.
**Avoids:** Pitfalls 6, 7, 9 (position tracking), 12 (model provisioning).
**Exit gate:** Upload, parse, `run='3'`, `progress=1.0`, chunks visible with correct positions on a PDF longer than 12 pages; killing a worker mid-task leads to reclaim with no duplicate chunks; a poison file fails terminally after 3 retries; re-parse leaves an identical chunk count.

### Stage 5: Retrieval and chat — the Core Value gate
**Rationale:** This is PROJECT.md's Core Value. Nothing in the breadth list may start until it passes with no mocked stage.
**Delivers:** `FulltextQueryer`, `Dealer` search / retrieval / rerank, filters, the retrieval-test API; assistants and sessions; prompt construction, token-budgeted context, citation insertion against a frozen reference list; SSE completion with in-band errors, cancellation and exactly-once persistence; token accounting; SPA retrieval-test page and streaming chat with citation drawer and PDF highlight.
**Addresses:** RETR-01..19, CHAT-01..23, LLM-09 (one rerank driver), KB-18, UI-18, UI-20..25, E2E-07/08/09/12.
**Avoids:** Pitfalls 8, 9, 10.
**Exit gate:** A question about an uploaded document yields a streamed, cited answer in the UI, verified through Nginx by a Playwright run; first frame arrives before the last; the cited chunk contains the fact; golden fusion tests and a labelled recall fixture pass.

### Breadth pass after the gate: deep parsing and remaining chunkers
**Rationale:** ARCHITECTURE.md lists DeepDoc vision and "the rest" of the chunkers inside stage 4, while FEATURES.md and PITFALLS.md both place them after the Core Value. This synthesis keeps the seven stage numbers and resolves the difference by scheduling the vision stack and the other 13 chunkers as a widening of stage 4 that runs after the stage 5 gate. The roadmapper may make it its own phase. It is the single largest research risk and must not sit on the critical path.
**Delivers:** Layout analysis, OCR fallback, table structure recognition with provisioned ONNX models; figure extraction and captioning; remaining chunkers each with a fixture and expected boundaries; LLM enrichment (keywords, questions, tags, metadata), RAPTOR; the `deepdoc` service profile.
**Addresses:** PARSE-04..08, PARSE-14..25, CHUNK-03..15, CHUNK-20..27, LLM-10, DEPLOY-08, SEC-08.
**Avoids:** Pitfalls 9, 12, 15 (parser guards).

### Stage 6: Agents and workflows
**Rationale:** The Retrieval node reuses the Dealer and the LLM node reuses `LLMBundle`, so this follows stage 5. The DSL is a public contract between frontend, backend and stored rows.
**Delivers:** Versioned DSL schema with golden fixtures first; `Graph` engine run headlessly before any canvas UI; nodes in tiers (Begin / LLM / Retrieval / Message, then Switch / Categorize / variables, then Loop / Iteration with guards, then tools / Invoke / AgentWithTools, then sandboxed Code, then Fillup / Browser / generators); agent CRUD, completion SSE, webhook, replica snapshot, session persistence; MCP client; sandbox service with its security tests; SPA canvas, node drawers, run log.
**Addresses:** FLOW-01..36, AGT-01..38, MCP-03, DEPLOY-07, SEC-07, TEST-06/07/09, UI-27..32, E2E-10/11.
**Avoids:** Pitfall 14 (and SSRF / prompt-injection rows of the security table).
**Exit gate:** Begin, Retrieval, LLM, Message built in the canvas runs with node events and a streamed answer; palette and engine registry are in parity; the loop guard triggers; outbound nodes cannot reach compose-internal services.

### Stage 7: Go surface completion, CLI, integrations, deployment hardening
**Rationale:** Search bots and MCP are Go-owned but need retrieval and model access from Go, the two things the Go stack otherwise never touches; the CLI needs the whole REST surface to exist.
**Delivers:** Go search bots and MCP server; `ragflow-cli` (lexer, parser, user and admin modes, VFS); admin servers; remaining REST surface (search apps, connectors, channels, Langfuse, plugins, stats, templates); Infinity adapter then OpenSearch; additional storage backends; provider breadth; remaining background job types; production Dockerfiles, compose profiles, entrypoints; every `docs/21-end-to-end-flows/` flow as an automated end-to-end test.
**Addresses:** CLI-01..17, ADMIN-01..07, SRCH-01..07, MCP-01/02, IDX-10/11, STOR-03..05, LLM-07/08, LLM-30/31, CHAN, CONN, TMPL, CHAT-25..27, DEPLOY-01, DEPLOY-05..11, DEPLOY-14..21.
**Avoids:** Pitfalls 2 (no hollow Go proxy), 18.
**Exit gate:** From a clean machine the documented instructions bring up the full stack; the CLI logs in, lists datasets, uploads and searches; every documented end-to-end flow passes; `BLOCKERS.md` lists anything undelivered.

### Phase Ordering Rationale

- **Dependencies:** schema before both servers; Go auth before any Python route; LLM layer before ingestion; ingestion before retrieval; retrieval before agents; whole REST surface before the CLI. The Core Value slice is strictly linear: DOC, ING, PARSE, CHUNK, IDX, RETR, CHAT.
- **Vertical, not layered:** each stage ships its API and its UI together and ends with a browser-level smoke test through Nginx. No phase should be named after a layer. If three stages complete without an answered question, the ordering has already failed.
- **Thin then wide:** one engine, one provider, one chunker, text-layer PDFs on the way to the gate; each widening axis afterwards is its own plan behind an already-proven interface.
- **If fewer phases are wanted:** merge stage 6 into its neighbour rather than merging 4 and 5; the ingestion/retrieval split is the natural verification boundary.
- **Cross-cutting, never a final phase:** security controls, tenant-matrix rows, contract tests and loading / error / empty states land with the feature they cover.

### Research Flags

Stages likely needing deeper research during planning (`/gsd:plan-phase --research-phase <N>`):
- **Stage 2:** cross-language token and password-hash compatibility; the Go middleware is described in two sentences; expiry and logout semantics; exact scheme in `docs/16-auth/authentication.md` (not read in full by any researcher).
- **Stage 4:** Redis Streams reclaim semantics; ES 8.11.3 `dense_vector` / kNN / hybrid behaviour and dimension limits; tokenizer choice (`infinity-sdk` supplies it even when ES is the engine); chunk ID construction (R-11).
- **Deep-parsing breadth pass:** DeepDoc model acquisition, licence and layout of `InfiniFlow/deepdoc`, CPU throughput, coordinate conventions. Highest research risk in the project.
- **Stage 5 (moderate):** ES vs Infinity scoring branches, citation insertion algorithm, delta-vs-cumulative streaming (R-26).
- **Stage 6:** DSL schema and node I/O contracts; sandbox manager (container pool, seccomp, Docker-socket exposure).
- **Stage 7:** how Go search bots obtain retrieval (R-04); scope of Go parity (R-03); additional engines (R-18); channel verification without third-party bot credentials.

Stages with standard patterns (skip research-phase):
- **Stage 0:** no technical research; it needs user decisions, not investigation.
- **Stage 1:** well specified; one bounded lookup only (column-level DDL from the reference `db_models.py`, and verifying image tags pull).
- **Stage 3:** well specified; provider conformance is test design, not research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | HIGH for what `docs/` prescribes. Version pins come from the reference lockfiles and were not re-verified against registries (Context7 unavailable). LOW for Go token library choice, NATS, sandbox image, TEI, and the `InfiniFlow/deepdoc` licence. Web claims (MySQL EOL, MinIO image discontinuation, LiteLLM compromise) are single-pass and not cross-checked against vendor pages |
| Features | HIGH / MEDIUM | HIGH as an inventory of what the docs say; every row is cited. MEDIUM for exact verbs and paths because the per-resource API docs are unreliable (R-30). Request/response bodies exist for only about ten endpoints; full DDL for 3 of about 40 entities |
| Architecture | MEDIUM | HIGH on component boundaries and data-flow direction (many docs agree). MEDIUM / LOW on specific contracts where docs conflict. `docs/20-security/*`, `docs/21-end-to-end-flows/*` and most per-resource API files were not read end to end by the architecture researcher |
| Pitfalls | HIGH / MEDIUM | HIGH where grounded in `docs/`, cited reference lines, or host measurements. MEDIUM for general RAG-engineering claims, which were not verified against external sources. Prior-attempt failure modes come from milestone context; the old git history was not inspected |

**Overall confidence:** MEDIUM. The shape of the system and the build order are well supported. The uncertainty is concentrated in a known, enumerated list: 52 register rows, of which 20 need the user.

### Gaps to Address

- **User decisions outstanding:** every "Yes" row above, and the three user actions in the blockers table. Nothing in this document has been confirmed by the user. Handle in stage 0 before plan approval.
- **`docs/apikey llm.md` unread:** may change LLM-layer requirements. Handle by user review (R-49); do not commit or open it until then.
- **Research files disagree in four places:** Go-to-Python proxying (R-04), object key layout (R-21), SSE terminator and reference timing (R-26), and where deep parsing sits in the build order. This summary proposes a resolution for each and flags all four for sign-off.
- **Host measurements disagree slightly:** available RAM (~5 vs ~6 GB) and Go toolchain version (1.25.5 vs 1.26.4). Re-measure in stage 1.
- **Under-specified contracts:** most endpoint bodies and most table DDL must be derived from the reference during each phase's research. Budget for it in every API phase.
- **Unverified externals:** image tag availability; `InfiniFlow/deepdoc` licence and layout; MySQL 8.4 driver behaviour; current shadcn CLI default for Tailwind v3; ES `dense_vector` limits at 8.11.3; whether the reference Go server proxies to Python.
- **Verification blocked by hardware or credentials:** `gpu` profile, chat channels (need third-party bot accounts), OAuth providers. Record in `BLOCKERS.md` as "complete with blocker" rather than "complete".
- **Documents not fully read by any researcher:** `docs/16-auth/authentication.md`, `docs/12-chat/complete-chat-flow.md`, `docs/21-end-to-end-flows/chat-streaming.md`, and the "Source File Map" lists inside sections 12, 13, 14, 16, 17. The relevant phase must read them.

## Sources

### Primary (HIGH confidence)
- `docs/spec.md` — implementation rules, priority order, anti-features, completion criteria
- `docs/00-overview` through `docs/21-end-to-end-flows`, `docs/apis.md` lines 1 to 139 — prescribed stack, components, flows, contracts (authoritative for "what the docs say"; internally contradictory in the places listed in the register)
- `.planning/PROJECT.md` — scope, constraints, pending key decisions
- Host measurements, 2026-10-05 — `free`, `df`, `nproc`, `sysctl vm.max_map_count`, `nvidia-smi` (absent), Docker and Compose versions

### Secondary (MEDIUM confidence)
- Reference checkout `/home/logan78/desktop x/ragflow` at commit `6677f14` (2026-08-12, RAGFlow 0.26.4) — `uv.lock`, `go.mod`, `web/package-lock.json`, `docker/.env`, `docker/nginx/*`, `docker/entrypoint.sh`, `common/doc_store/doc_store_base.py`, `common/constants.py`, `api/utils/api_utils.py`, `api/db/db_models.py`, `rag/svr/task_executor.py`, `rag/utils/redis_conn.py`, `rag/nlp/search.py`, `internal/utility/token.go`, `internal/common/password.go`, `deepdoc/vision/*`, `SECURITY.md`. Authoritative for what works together and for tie-breaking, never for overriding `docs/`
- `docs/22-code-tracing`, `docs/23-diagrams`, `docs/99-glossary` — used mainly as contradiction evidence

### Tertiary (LOW confidence)
- Single-pass web results, not cross-checked: MySQL 8.0 EOL (percona.com, openlogic.com); MinIO community image discontinuation and `pgsty/minio` fork (linuxiac.com, blog.vonng.com, infiniflow/ragflow issue 13840); LiteLLM 1.82.7 / 1.82.8 PyPI compromise (pypistats.com); Quart 0.20.0 as latest (quart.palletsprojects.com)
- General RAG-engineering domain knowledge in PITFALLS.md (Elasticsearch refresh behaviour, score-scale issues, provider quirks) — confirm during phase research

### Not consulted
- `docs/apikey llm.md` — off-limits pending user review; not opened by any researcher or by this synthesis

---
*Research completed: 2026-10-05*
*Ready for roadmap: yes, conditional on stage 0 user decisions and the host blockers marked "user action"*

## User-confirmed decisions (2026-10-05)

These supersede the "proposed, not user-confirmed" status of the matching register rows.

| Decision | User's choice |
|----------|---------------|
| Go parity scope (R-03) | Go Gin builds only its own routes (auth, user, tenant, system, search bots, MCP, CLI). Python owns all RAG/ML pipelines. Go mirror engines deferred to v2 and recorded as a deviation. |
| Billing content in `docs/apis.md` (R-48) | In scope for v1: build the metered billing/credits features (BILL-01..10). |
| Doc-store engines | Elasticsearch (default) and Infinity in v1 behind the DocStore abstraction. Qdrant, Milvus, PGVector deferred to v2. |
