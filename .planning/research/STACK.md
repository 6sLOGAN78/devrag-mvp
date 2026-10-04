# Stack Research

**Domain:** Enterprise RAG platform (devRag) — implementation of the reverse-engineered RAGFlow spec in `docs/`
**Researched:** 2026-10-05
**Confidence:** MEDIUM overall. HIGH for what `docs/` prescribes (read directly). MEDIUM for version pins (taken from the reference repo's lockfiles at commit `6677f14`, 2026-08-12, RAGFlow 0.26.4 — a known mutually-compatible set, but not individually re-checked against registries today). LOW where flagged.

## How to read this file

- **Source column** names the `docs/` file that prescribes the choice. `OPEN` means docs are silent or self-contradictory; see "Open decisions".
- **Version pins** come from `ragflow/uv.lock`, `ragflow/go.mod`, `ragflow/web/package-lock.json`, `ragflow/docker/docker-compose-base.yml`. They are the baseline that is known to work together. Newer releases may exist; I did not verify each against PyPI/npm/pkg.go.dev (Context7 unavailable). Treat pins as "start here", not "latest".
- `docs/apikey llm.md` was not opened.

## Recommended Stack

### Core Technologies — Frontend (`web/`)

| Technology | Version | Purpose | Why / Source | Conf. |
|---|---|---|---|---|
| React + react-dom | 18.3.1 | SPA view layer | `docs/00-overview/technology-stack.md`, `docs/02-frontend/frontend-architecture.md` say React 18. Stay on 18, not 19: docs are explicit and the ref's dependency set (react-pdf-highlighter, lexical, xyflow) is resolved against 18. | HIGH |
| TypeScript | 5.9.3 | Typing | technology-stack.md | HIGH |
| Vite + @vitejs/plugin-react | 7.3.0 / 5.1.2 | Build/dev server | Docs say "Vite/UmiJS"; PROJECT.md says Vite; ref `package.json` is "migrated to Vite" and has no `umi`. Use Vite only. | HIGH |
| React Router (`react-router`) | 7.11.0 | Routing, `createBrowserRouter`, lazy routes | frontend-architecture.md | HIGH |
| Zustand | 4.5.7 | Global client state | `docs/02-frontend/state-management.md` | HIGH |
| TanStack React Query | 5.90.14 | Server state, wrapped in `hooks/use-*-request.ts` | frontend-architecture.md ("TanStack React Query / Axios hooks") | HIGH |
| Axios | 1.13.6 | HTTP client + auth/401 interceptors | `docs/02-frontend/api-client.md` | HIGH |
| TailwindCSS | 3.4.19 | Styling | technology-stack.md. Stay on v3: ref uses `tailwind.config.js` + `tailwindcss-animate` + `@tailwindcss/typography` (v3-era config); v4 is a config rewrite with no doc mandate. | MEDIUM |
| shadcn/ui (Radix primitives + cva + tailwind-merge + lucide-react) | radix ^1.x–2.x, cva 0.7.1, tailwind-merge 2.6.1, lucide-react 1.7.0 | Component kit | technology-stack.md | HIGH |
| @xyflow/react | 12.10.0 | Agent/workflow canvas | technology-stack.md, frontend-overview.md | HIGH |
| i18next + react-i18next | 23.16.8 / 14.1.3 | i18n | technology-stack.md | HIGH |
| react-markdown, remark-gfm, remark-math, rehype-katex, rehype-raw | 9.1.0 / 4.0.1 / 6.0.0 / 7.0.1 / 7.0.0 | Chat answer rendering, citations, LaTeX | technology-stack.md | HIGH |

### Core Technologies — Python engine (`api/`, `rag/`, `deepdoc/`, `agent/`, `common/`)

| Technology | Version | Purpose | Why / Source | Conf. |
|---|---|---|---|---|
| Python | 3.13 (floor per docs: 3.10+) | Runtime | technology-stack.md says "3.10+"; `docs/18-deployment/docker.md` says "Python 3.10 slim". Ref requires `>=3.13,<3.14` and its lock is resolved for 3.13. Python 3.10 reaches end-of-life this month. See Open decision D3. | MEDIUM |
| uv | 0.9.x | Env + lockfile | `docs/18-deployment/docker.md` ("uses `uv`") | HIGH |
| Quart | 0.20.0 | ASGI app, SSE streaming | technology-stack.md, `docs/03-backend/backend-overview.md`. 0.20.0 is the latest release (Feb 2025). | HIGH |
| Hypercorn | 0.18.0 | ASGI server under `app.run`/prod | Implied by Quart; `docs/03-backend/entry-points.md` ("Starts ASGI server"). Ignore docker.md's "Flask + Gunicorn/WSGI" wording — it contradicts every other doc. | MEDIUM |
| quart-schema | 0.23.0 | Request validation + OpenAPI | technology-stack.md, `docs/04-api/api-overview.md` (`QuartSchema(app)`) | HIGH |
| quart-cors | 0.8.0 | CORS | backend-overview.md (routing layer: CORS) | MEDIUM |
| Pydantic | 2.12.5 | Typed request/response models (via quart-schema) | spec.md "typed interfaces, input validation" | MEDIUM |
| Peewee | 3.19.0 | ORM, pooled retrying DBs, `playhouse.migrate` | `docs/08-database/database-overview.md`, `migrations.md` | HIGH |
| PyMySQL | 1.1.2 | MySQL driver for Peewee | Implied by Peewee MySQL | MEDIUM |
| itsdangerous | 2.2.0 | Access-token signing (`URLSafeTimedSerializer`) | `docs/16-auth/`, `docs/03-backend/authentication.md` | HIGH |
| LiteLLM | 1.84.0 (exact pin) | Chat provider abstraction (`LiteLLMBase`) | `docs/11-llm/provider-abstraction.md`. Exact pin is mandatory: 1.82.7/1.82.8 were malicious PyPI releases (Mar 2026); ref notes regressions at 1.88.0 and CVEs below 1.84.0. | HIGH |
| openai SDK | 2.41.0 | Direct OpenAI/Azure/OpenAI-compatible embed + chat | `docs/11-llm/openai.md` | HIGH |
| ollama SDK | 0.6.1 | `OllamaEmbed` (`client.embed`) | `docs/11-llm/ollama.md` | HIGH |
| tiktoken | 0.12.0 | Token counting / truncation (`cl100k_base`) | `docs/11-llm/embeddings.md`, `llm-request-flow.md` | HIGH |
| langfuse | 4.7.1 | LLM tracing / token accounting | `docs/11-llm/llm-architecture.md`, `docs/04-api/langfuse-api.md` | MEDIUM |
| mcp (Python SDK) | 1.28.1 | MCP client/tools on the Python side | `docs/04-api/mcp-api.md` | MEDIUM |

### Core Technologies — Go engine (`cmd/`, `internal/`)

| Technology | Version | Purpose | Why / Source | Conf. |
|---|---|---|---|---|
| Go | 1.26.x (docs floor: 1.22+) | Runtime; host already has 1.26.4 | technology-stack.md | HIGH |
| gin-gonic/gin | 1.12.0 | HTTP framework | technology-stack.md | HIGH |
| gorm.io/gorm + gorm.io/driver/mysql | 1.25.7 / 1.5.2 | DAO layer, `--migrate` | technology-stack.md, database-overview.md. Ref pins are old; newer GORM exists (unverified which). Keep ref pins unless a bug forces a bump. | MEDIUM |
| go.uber.org/zap (+ lumberjack 2.2.1) | 1.27.1 | Structured logging + rotation | technology-stack.md | HIGH |
| redis/go-redis/v9 | 9.18.0 | Cache, distributed locks | technology-stack.md | HIGH |
| spf13/viper | 1.18.2 | `service_conf.yaml` + env loading | `docs/15-cli/configuration.md`, `docs/18-deployment/` (conf template) | MEDIUM |
| golang-jwt/jwt/v5 | 5.3.0 | Token handling | `docs/16-auth/tokens.md` — but see D7 (must interoperate with itsdangerous) | LOW |
| minio/minio-go/v7 | 7.0.99 | Go storage adapter | `docs/09-storage/storage-overview.md` (`internal/storage/minio.go`) | HIGH |
| aws-sdk-go-v2 (s3) | 1.41.3 / s3 1.96.4 | Go S3 adapter | storage-overview.md | MEDIUM |
| elastic/go-elasticsearch/v8 | 8.19.1 | Go doc-engine client (searchbots, retrieval test) | `docs/04-api/endpoint-catalog.md` (Go `searchBotHandler`) | MEDIUM |
| peterh/liner | 1.2.2 | `ragflow-cli` REPL | `docs/15-cli/cli-overview.md` (named explicitly) | HIGH |
| nats-io/nats.go | 1.52.0 | Only if NATS path is built (D2) | `docs/18-deployment/services.md` | LOW |

### Infrastructure (Docker Compose)

| Technology | Image / Version | Purpose | Why / Source | Conf. |
|---|---|---|---|---|
| MySQL | `mysql:8.0.40` per docs | Relational metadata | `docs/18-deployment/docker-compose.md`. MySQL 8.0 went EOL 2026-04-30 — see D4. | HIGH (doc) |
| Redis-protocol cache/queue | `valkey/valkey:8` | Sessions, locks, Redis Streams task queue, LLM cache | docker-compose.md table. technology-stack.md says "Redis 7.0"; Valkey 8 is wire-compatible. See D5. | MEDIUM |
| Object storage | `pgsty/minio:RELEASE.2026-03-25T00-00-00Z` | Raw files, page images, thumbnails | docker-compose.md. Do not use `minio/minio`: upstream stopped publishing images (Oct 2025) and archived the repo (Feb 2026). | HIGH |
| Vector/full-text engine (default) | `elasticsearch:8.11.3` (`STACK_VERSION`) | Hybrid BM25 + dense | `docs/18-deployment/environment-variables.md`; see section (b) below | HIGH |
| Vector/full-text engine (second) | `infiniflow/infinity:v0.7.2-x64-v3` (docs) / `v0.7.3` (ref) | Alt engine, `infinity` profile | docker-compose.md | MEDIUM |
| Nginx | mainline 1.31.x | SPA static + path routing to 9380/9384/9381/9383 | `docs/18-deployment/production-architecture.md` | HIGH |
| NATS JetStream | `nats:2.14.2`, profile `ragflow-go` | Optional queue | docker-compose.md; see D2 | LOW |
| Sandbox executor manager | own image, port 9385, profile `sandbox` | Agent code-node execution | `docs/18-deployment/services.md`, `docs/20-security/file-security.md`. Docs reference `infiniflow/sandbox-executor-manager`; availability of that public image is unverified — see D9. | LOW |
| TEI (text-embeddings-inference) | `infiniflow/text-embeddings-inference:cpu-1.8` (ref `.env`) | Optional local embedding/rerank server | `docs/18-deployment/docker.md` (`Dockerfile_tei`) | LOW |

Ports are fixed by docs: Python API 9380, Python admin 9381, MCP 9382, Go admin 9383, Go API 9384, deepdoc 9390, sandbox 9385 (`docs/18-deployment/networking.md`). `docs/00-overview/high-level-architecture.md` draws both engines on `:9380`; that is a diagram simplification — the deployment docs are specific and consistent, follow them.

### Supporting Libraries — Python

| Library | Version | Purpose | When / Source |
|---|---|---|---|
| valkey (Python client) | 6.0.2 | Redis Streams `XADD`/`XREADGROUP`/`XACK`, `SET NX EX` locks | `docs/10-cache-and-queues/redis.md`, `queues.md`. `redis-py` is an acceptable equivalent. |
| minio | 7.2.4 | MinIO adapter | `docs/09-storage/` |
| boto3 | 1.42.x | S3 adapter | storage-overview.md |
| elasticsearch + elasticsearch-dsl | 8.19.3 / 8.12.0 | ES DocStore adapter | `docs/17-integrations/vector-database-integrations.md` |
| infinity-sdk | 0.7.3 | Infinity DocStore adapter (Thrift 23817) | same. Must match the server minor (0.7.x). |
| opensearch-py | 2.7.1 | OpenSearch adapter | technology-stack.md (later phase) |
| onnxruntime | 1.23.2 | DeepDoc OCR / layout / TSR inference | `docs/06-document-processing/ocr.md`; see section (c) |
| opencv-python-headless | 4.10.0.84 | Image ops for DeepDoc | technology-stack.md |
| numpy | 1.26.4 | Arrays. Stay <2: onnxruntime/opencv/xgboost pins in this set are resolved against 1.26. | lock |
| xgboost | 1.6.0 | Text-concatenation model in PDF parser | ref `deepdoc/parser/pdf_parser.py` (docs silent) |
| huggingface-hub | 1.3.1 | Download `InfiniFlow/deepdoc` models | section (c) |
| pdfplumber (+ pypdfium2 5.12.1), pypdf | 0.11.10 / 6.15.0 | PDF text spans, rasterisation | `docs/06-document-processing/pdf-processing.md` says "PyMuPDF fitz / pdfium" — see D6 |
| python-docx, python-pptx, openpyxl | 1.2.0 / 1.0.2 / 3.1.5 | Office parsers | `docs/06-document-processing/office-documents.md` |
| beautifulsoup4, readability-lxml, html-text, chardet | 4.13.5 / 0.8.4.1 / 0.6.2 / 5.2.0 | HTML/TXT parsers | `docs/05-rag-pipeline/parsing.md` |
| Pillow, shapely, pyclipper | 12.3.0 / 2.1.2 / 1.4.0 | OCR post-processing (DBNet boxes) | ocr.md |
| nltk | >=3.10.0 | Tokenisation/stemming. Below 3.10.0 has a CRITICAL CVE (CVE-2025-14009). | technology-stack.md |
| json-repair | 0.60.1 | Repair LLM JSON output | agent/graph extraction |
| cohere, dashscope, anthropic | 5.6.2 / 1.25.11 / 0.76.0 | Direct-SDK rerank/embedding drivers | `docs/11-llm/rerank-models.md`, `other-providers.md`. Add per provider, not up front. |
| pycryptodomex | 3.20.0 | RSA password transport, key encryption | `docs/16-auth/`, `docs/20-security/secrets.md` |
| httpx / aiohttp | 0.28.1 / 3.14.3 | Async outbound HTTP (Jina/NVIDIA rerank, web search tools) | rerank-models.md |

### Supporting Libraries — Frontend

| Library | Version | Purpose | When |
|---|---|---|---|
| eventsource-parser | 1.1.2 | Parse SSE over `fetch` (POST + `Authorization` header) | Chat/agent streaming. `docs/02-frontend/api-client.md` says "`fetchEventSource` or native `EventSource`"; native `EventSource` cannot send headers or POST bodies, so use fetch + this parser. |
| react-hook-form + zod + @hookform/resolvers | 7.69.0 / 3.25.76 / 3.9.x | Forms + validation | All config forms. Keep zod 3 with resolvers 3. |
| @tanstack/react-table | 8.20.x | Document/chunk tables | Dataset UI |
| react-dropzone | 14.3.x | Upload dialog | `docs/02-frontend/document-upload-ui.md` |
| react-pdf-highlighter | 6.1.0 | Chunk bbox highlights on PDF pages | `docs/02-frontend/components.md` (`document-preview`) |
| react-syntax-highlighter (or highlight.js) | 15.5.x | Code blocks in chat | technology-stack.md names `highlight.js`; ref uses react-syntax-highlighter. Either satisfies the doc's intent. |
| dompurify | 3.3.2 | Sanitise rendered HTML from `rehype-raw` | Required whenever raw HTML is rendered |
| sonner, next-themes, cmdk | 1.7.4 / 0.4.6 / 1.0.4 | Toasts, theme, command menu | shadcn companions |
| @monaco-editor/react | 4.7.0 | Code node editor in canvas | Workflow phase only |
| immer, lodash, dayjs, uuid | 10.1.1 / 4.18.x / 1.11.x / 9.0.1 | Utilities | As needed |

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| pytest 9.0.2, pytest-asyncio 1.3.0, pytest-xdist 3.8.0, pytest-cov 7.0.0, hypothesis | Python tests | `docs/19-testing/testing-overview.md`. `asyncio_mode = "auto"`; ref disables the anyio plugin on 3.13 (`-p no:anyio`). Provide a `run_tests.py` wrapper with `-p/-t/-m/--coverage` as `test-architecture.md` specifies. |
| `go test` with build tags `integration`, `e2e`, `manual`, `cgo` | Go test tiers | `docs/19-testing/test-architecture.md` (5 tiers). |
| DATA-DOG/go-sqlmock 1.5.2, alicebob/miniredis/v2 2.38.0, glebarez/sqlite 1.11.0 | Go tier-1 fakes | Ref evidence; lets unit tier run without services. |
| Vitest + @testing-library/react 15 + jsdom | Frontend tests | `docs/19-testing/frontend-tests.md` allows "Jest / Vitest". Choose Vitest: shares the Vite transform, no `esbuild-jest`/`identity-obj-proxy` shims. Vitest version unverified — resolve at install. |
| ruff | Python lint/format | Ref config: line-length 200, `ASYNC` rules. |
| oxlint / oxfmt (or eslint + prettier) | Frontend lint/format | Ref uses oxlint 1.75 / oxfmt 0.60. OPEN, low stakes. |
| Docker Compose v2 with `include:` and `profiles:` | Local stack | `docs/18-deployment/docker-compose.md`. Host has Docker 29.1.3. |
| pytest-playwright 0.8.0 | Browser E2E | Only for the E2E-flows phase. |

## Explicit answers to the three required questions

### (a) Dual-stack: what Go owns vs what Python owns

Consistent across `docs/00-overview/high-level-architecture.md`, `docs/03-backend/backend-overview.md`, `backend-architecture.md`, `docs/04-api/api-overview.md`, `endpoint-catalog.md`:

| Go Gin (`:9384`, admin `:9383`; sets `X-API-Source: go`) | Python Quart (`:9380`, admin `:9381`) |
|---|---|
| `/health`, `/api/v1/system/{ping,config,version}`, `/api/v1/language` | Datasets CRUD (`/api/v1/datasets`) |
| Login, register, password OTP/reset (`/api/v1/auth/*`, `/api/v1/users`) | Documents: parse trigger, status, list, delete; chunks |
| `/v1/user/{info,tenant_info,setting,setting/password}`, `/v1/tenant/list` | Chats, sessions, `/api/v1/chat/completions` (SSE) |
| Search bots (`/api/v1/searchbots/{ask,retrieval_test}`) | Agents/canvas, `/api/v1/agents/chat/completions` (SSE) |
| MCP server endpoint (`/api/v1/mcp`) | DeepDoc parsing, embeddings, rerank, all ML |
| Ingestion task dispatch, background syncer (`--ingestor`, `--syncer`), `--migrate` | Task executor workers (`rag/svr/task_executor.py`), `update_progress` daemon, chat-channel bridges |
| `ragflow-cli` (Go binary, targets `:9384` / `:9383`) | `init_web_db()` table creation, Peewee migrations |

Shared: both read/write the same MySQL schema (Peewee models and GORM DAOs must describe identical tables) and the same Redis. Document upload is marked "Python / Go". Nginx does path-based routing between them.

The catalogue in `endpoint-catalog.md` assigns 17 routes to Go, 20 to Python, 1 to both; the larger per-domain API docs (`docs/04-api/*-api.md`, `docs/apis.md`) need the same Engine column checked during planning — I tallied only the catalogue.

Unresolved by docs: (1) schema ownership — both `init_web_db()` (Python) and `--migrate` (Go) create/alter tables; (2) token interop — Python validates with itsdangerous, Go must accept the same token; (3) the CLI calls `:9384/v1/dataset/list`, a route the catalogue assigns to Python. See D1, D7.

### (b) Default vector/full-text engine: Elasticsearch 8.11.3

Evidence:
- `docs/18-deployment/environment-variables.md` documents `STACK_VERSION=8.11.3`, `ES_PORT`, `ELASTIC_PASSWORD`; ref `docker/.env` has `DOC_ENGINE=${DOC_ENGINE:-elasticsearch}` and `common/settings.py` defaults to `"elasticsearch"`.
- `docs/17-integrations/vector-database-integrations.md` names only Infinity, Elasticsearch 8+, OpenSearch, PGVector as "primary", with source maps for ES and Infinity clients only.
- The Infinity image is `x64-v3` only (needs AVX2-class CPU, no arm64), which makes it a poor default for CI and contributor machines.
- ES gives BM25 + `dense_vector` kNN in one engine, matching the documented `content_ltks` + `q_{dim}_vec` index schema.

Use for compose default and for the integration-test tier. Ship Infinity as the second adapter behind the same DocStore interface (`docs/19-testing/integration-tests.md` expects a live Infinity client test on 23817).

Practical constraint: docs set `MEM_LIMIT=8g`. This host has 15 GB RAM with roughly 6 GB available and no GPU. Run ES single-node with `ES_JAVA_OPTS=-Xms1g -Xmx1g` and a 2 GB container limit in the dev/test compose override.

Docs also list Qdrant, Milvus, PGVector, OceanBase, Tantivy, ClickHouse, SereneDB. The reference repo has no Qdrant, Milvus, or PGVector adapter at all (grep over `rag/`, `common/`, `internal/`, `api/` returns nothing), so there is no pattern to follow for those three. See D8.

### (c) Heavy ML dependencies: what docs require and how to get them

What docs say: technology-stack.md lists "PyTorch, OpenCV, YOLOv8, PaddleOCR" and "HuggingFace Transformers, NLTK, Jieba, HanLP". `parsing.md` says "YOLOv10/ONNX". `ocr.md` says "DBNet ONNX" detector + "CRNN CTC" recogniser. `async-processing.md` says "ONNX vision models". `embedding.md` shows a "Local BGE / FlagEmbedding → PyTorch" branch and a "FastEmbed ONNX" branch.

What the reference actually runs (the docs are a description of it):
- Inference is **onnxruntime 1.23.2** (`onnxruntime-gpu` on x86_64 Linux). `torch` is **not in `uv.lock`**; it is imported only inside `try` blocks to detect CUDA. `paddleocr`, `ultralytics`, `transformers`, `jieba`, `hanlp`, `pymupdf` are not imported anywhere in `deepdoc/`, `rag/`, `api/`, `common/`, `agent/`.
- Models are ONNX files pulled with `huggingface_hub.snapshot_download` from **`InfiniFlow/deepdoc`** (OCR det/rec, layout, TSR) and **`InfiniFlow/text_concat_xgb_v1.0`** (XGBoost) into `rag/res/deepdoc/`. The OCR models are PaddleOCR-derived and the layout model is YOLO-derived, which is what the docs' "PaddleOCR / YOLO" wording refers to.
- Tokeniser: ref `rag/nlp/rag_tokenizer.py` delegates to `infinity.rag_tokenizer` from `infinity-sdk` — so `infinity-sdk` is a dependency even when ES is the engine.
- Local embeddings/rerank are served out-of-process (TEI image or Ollama), not in-process PyTorch.

Recommendation:
1. Require `onnxruntime` (CPU) + `opencv-python-headless` + `numpy<2` + `xgboost` + `huggingface-hub`. This satisfies the documented pipeline (DLA → OCR → TSR) with roughly 300 MB of wheels instead of 2+ GB for torch.
2. Do **not** add PyTorch, PaddleOCR, ultralytics, or transformers to the base dependency set. Offer `torch` only as an optional extra for a local BGE/FlagEmbedding driver, and prefer Ollama (`bge-m3`, `nomic-embed-text`, per `docs/11-llm/ollama.md`) or TEI for local embeddings.
3. Fetch models in a build/bootstrap step (`download_deps.py`-style script, cached volume), never at first request. Also pre-fetch `cl100k_base.tiktoken` and `nltk_data` so workers run offline.
4. Honour `DEEPDOC_URL` so OCR/DLA can be offloaded to the `deepdoc` profile container on 9390 (`ocr.md`, `docker-compose.md`).

This reads the docs' "PyTorch" line as descriptive of model lineage rather than a runtime requirement. That is an interpretation, so it is recorded as D6 for sign-off. I did not verify the licence or current file layout of the `InfiniFlow/deepdoc` Hugging Face repo — check both before the document-processing phase (LOW confidence).

## Open decisions (docs silent or contradictory)

| # | Decision | Conflict / gap | Recommendation |
|---|---|---|---|
| D1 | Schema ownership between Peewee and GORM | Python `init_web_db()` + `playhouse.migrate`; Go `--migrate` + `internal/dao/migration.go`; plus `docker/init.sql` on first boot (`deployment-flow.md`) | One writer: Python Peewee models own DDL and migrations. Go GORM maps the same tables with AutoMigrate disabled in normal runs; `--migrate` only verifies/aligns. Add a CI test that diffs the two definitions. `init.sql` creates the database and grants only. |
| D2 | Task queue: Redis Streams vs NATS JetStream | `docs/10-cache-and-queues/queues.md` says Redis Streams is "primary" (`te.{priority}.common`, consumer groups, XACK). `docs/18-deployment/production-architecture.md` routes tasks through NATS, but the compose table puts NATS under the non-default `ragflow-go` profile. | Redis Streams is the default and only queue for the Python task executor. Put the queue behind an interface; add NATS only when the Go ingestor (`--ingestor`) is built. The CLI's `PING MQ` then reports "not configured" unless the profile is on. |
| D3 | Python version | Docs: "3.10+" and "3.10 slim" image. Ref: 3.13 only. 3.10 is EOL October 2026. | Python 3.13, `requires-python = ">=3.13,<3.14"`, installed via uv (host system Python is 3.10.12). Record as a deviation from the docker.md base-image line. |
| D4 | MySQL version | Docs pin `mysql:8.0.40`; 8.0 has had no security patches since 2026-04-30. | Parameterise as `MYSQL_IMAGE`. Default to `mysql:8.0.40` to match docs; ask the user to approve `mysql:8.4` LTS. If approved, verify auth-plugin behaviour with PyMySQL and go-sql-driver in the infrastructure phase (I did not test this). |
| D5 | Redis 7 vs Valkey 8 | technology-stack.md and PROJECT.md say Redis 7; deployment docs say `valkey/valkey:8`. | `valkey/valkey:8` (most specific doc, wire-compatible). Avoid Redis-Stack-only commands so either works. |
| D6 | ML runtime and PDF library | "PyTorch / PaddleOCR / YOLOv8" vs "ONNX"; "PyMuPDF fitz / pdfium" vs ref's pdfplumber + pypdfium2. PyMuPDF is AGPL-licensed, which would constrain distribution. | onnxruntime + `InfiniFlow/deepdoc` models; pdfplumber/pypdfium2 (the "pdfium" half of the doc's wording). No torch, no PyMuPDF in base deps. |
| D7 | Cross-engine token format and password hashing | Docs call tokens "JWT" but show `itsdangerous` `Serializer.loads`; Go side unspecified. Password hashing is "PBKDF2 / Bcrypt" with no parameters. | Define one token format and implement it in both languages with shared test vectors. Simplest: Go owns login and stores `access_token` in the `user` row; both engines authenticate by decoding then looking up that row, as the docs' flow already does. Resolve hashing scheme from `docs/16-auth/` + ref `api/db/services/user_service.py` in the auth phase. |
| D8 | Which engines beyond ES and Infinity | Docs list 8+; ref implements ES, Infinity, OpenSearch, OceanBase, SereneDB; none for Qdrant/Milvus/PGVector | Order: ES → Infinity → OpenSearch (near-free given the ES adapter). Treat Qdrant/Milvus/PGVector/OceanBase/Tantivy as a later phase needing its own research; ask the user whether they are in scope for "complete". |
| D9 | Sandbox executor | Docs reference `infiniflow/sandbox-executor-manager` + base images; needs the Docker socket | Build our own manager under `agent/sandbox/` rather than depend on an unverified third-party image. Flag the phase for deeper research (seccomp, pool management). |
| D10 | Ant Design | technology-stack.md lists "TailwindCSS + Shadcn/ui + Ant Design components"; PROJECT.md omits it; ref has only `@ant-design/icons`, no `antd` | shadcn/ui only; do not install `antd`. Two component systems double bundle size and styling rules. Record as a deviation. |
| D11 | Go's route for CLI calls to Python-owned endpoints | `docs/15-cli/cli-execution-flow.md` calls `http://127.0.0.1:9384/v1/dataset/list` | Go server reverse-proxies unmatched `/v1` and `/api` paths to Python `:9380`, so `:9384` is a complete entry point. Unverified against the ref's Go router — check in the CLI phase. |
| D12 | API path prefix and envelope keys | Docs mix `/v1/...` and `/api/v1/...`; envelope shown as `retcode/retmsg` in api-overview.md but `code/message` in the SSE frame (`llm-request-flow.md`) | Not a stack choice, but it blocks the API client. Settle in the API phase from `docs/apis.md`. |

## Installation

```bash
# Python (uv, Python 3.13)
uv python install 3.13
uv add "quart==0.20.0" "hypercorn==0.18.0" "quart-schema==0.23.0" "quart-cors==0.8.0" \
  "peewee>=3.19,<4" "pymysql>=1.1.2" "itsdangerous>=2.2" "pydantic>=2.12,<3" \
  "litellm==1.84.0" "openai>=2.41,<3" "ollama>=0.6" "tiktoken>=0.12" \
  "valkey==6.0.2" "minio==7.2.4" "boto3>=1.42" \
  "elasticsearch>=8.19,<9" "elasticsearch-dsl==8.12.0" "infinity-sdk==0.7.3" \
  "onnxruntime==1.23.2" "opencv-python-headless==4.10.0.84" "numpy>=1.26,<2" \
  "xgboost==1.6.0" "huggingface-hub>=1.3" "pdfplumber==0.11.10" "pypdf>=6.15" \
  "python-docx>=1.2,<2" "python-pptx>=1.0.2,<2" "openpyxl>=3.1.5" \
  "beautifulsoup4>=4.13" "chardet>=5.2,<6" "pillow>=12.3,<13" "shapely>=2.1" "pyclipper>=1.4" \
  "nltk>=3.10.0" "json-repair==0.60.1" "pycryptodomex==3.20.0" "httpx>=0.28" "langfuse>=4.0.1"
uv add --group test "pytest>=9" "pytest-asyncio>=1.3" "pytest-xdist>=3.8" "pytest-cov>=7" hypothesis

# Go (1.26)
go get github.com/gin-gonic/gin@v1.12.0 gorm.io/gorm@v1.25.7 gorm.io/driver/mysql@v1.5.2 \
  go.uber.org/zap@v1.27.1 gopkg.in/natefinch/lumberjack.v2@v2.2.1 \
  github.com/redis/go-redis/v9@v9.18.0 github.com/spf13/viper@v1.18.2 \
  github.com/minio/minio-go/v7@v7.0.99 github.com/elastic/go-elasticsearch/v8@v8.19.1 \
  github.com/peterh/liner@v1.2.2 github.com/google/uuid@v1.6.0
go get github.com/DATA-DOG/go-sqlmock@v1.5.2 github.com/alicebob/miniredis/v2@v2.38.0

# Frontend (Node 22)
npm i react@18.3.1 react-dom@18.3.1 react-router@^7.11 zustand@^4.5.7 \
  @tanstack/react-query@^5.90 axios@^1.13 @xyflow/react@^12.10 \
  i18next@^23.16 react-i18next@^14.1 react-markdown@^9.1 remark-gfm@^4 remark-math@^6 \
  rehype-katex@^7 rehype-raw@^7 dompurify@^3.3 eventsource-parser@^1.1.2 \
  react-hook-form@^7.69 zod@^3.25 @hookform/resolvers@^3.9 \
  class-variance-authority clsx tailwind-merge@^2.6 lucide-react sonner next-themes
npm i -D typescript@^5.9 vite@^7.3 @vitejs/plugin-react@^5.1 tailwindcss@^3.4 postcss autoprefixer \
  tailwindcss-animate @tailwindcss/typography vitest jsdom @testing-library/react@^15 @testing-library/jest-dom
```

## Alternatives Considered

| Recommended | Alternative | When the alternative is right |
|---|---|---|
| Elasticsearch 8.11.3 default | Infinity 0.7.x default | x86-64-v3 hosts only, and when memory is tight; Infinity is lighter than ES. Docs support it via the `infinity` profile. |
| Redis Streams queue | NATS JetStream | Once the Go ingestor exists and multi-node fan-out is needed (`ragflow-go` profile). |
| onnxruntime CPU | onnxruntime-gpu | `gpu` compose profile with NVIDIA runtime (`docs/18-deployment/deployment-overview.md`). Not usable on this host (no GPU). |
| Ollama/TEI for local embeddings | In-process torch + FlagEmbedding | Only if a user requires a built-in embedding model with no sidecar. |
| Vitest | Jest 29 | If component tests are ported verbatim from the ref (it uses Jest). |
| Peewee-owned migrations | GORM AutoMigrate-owned | If the Python engine were ever made optional; it is not under these docs. |

## What NOT to Use

| Avoid | Why | Use instead |
|---|---|---|
| FastAPI, Flask, Django | Docs prescribe Quart; replacing it violates `spec.md` | Quart 0.20 + quart-schema |
| SQLAlchemy / Alembic | Docs prescribe Peewee + `playhouse.migrate` | Peewee |
| Celery, RQ, Kafka, RabbitMQ | Docs define a Redis Streams worker protocol with specific keys and consumer groups | Custom task executor on Redis Streams |
| LangChain / LlamaIndex as the pipeline core | Docs define their own chunkers, retriever, prompt generator, and canvas engine | Own `rag/`, `agent/` modules. (Ref pins `langgraph`; docs do not mention it — do not add.) |
| `minio/minio` image | No longer published; repo archived Feb 2026 | `pgsty/minio` (docs) |
| litellm unpinned or `>=` | 1.82.7/1.82.8 were malicious; frequent regressions | `litellm==1.84.0`, hash-locked in `uv.lock` |
| PyMuPDF | AGPL licence; not used by the ref | pdfplumber + pypdfium2 |
| UmiJS, Ant Design, Redux | Ref removed Umi; antd absent from ref; docs name Zustand | Vite, shadcn/ui, Zustand |
| Tailwind v4, React 19, zod 4, Zustand 5 | Major versions not called for by docs and not what the companion libraries here were resolved against | The pinned majors above |
| Native `EventSource` | Cannot send `Authorization` header or POST body | fetch + eventsource-parser |
| Pinecone, Weaviate, Chroma | Not in the documented engine list | ES / Infinity / OpenSearch |
| Ref's long connector tail (akshare, selenium-wire, discord-py, yfinance, tika, crawl4ai, browser-use, …) in base deps | ~120 direct deps; many CVE constraint overrides in the ref's `[tool.uv]` | Add each only in the phase that builds the feature (channels, connectors, agent tools) |

## Stack Patterns by Variant

**CPU dev / CI (this host: 16 cores, 15 GB RAM, no GPU):**
- Compose profiles `elasticsearch,cpu`; ES heap 1 GB; one task-executor worker; onnxruntime CPU.
- LLM/embedding via a remote OpenAI-compatible key or local Ollama. No API keys are configured in the session, so E2E RAG tests need either Ollama with small models or a key from the user — a blocker for the "no mocked stages" core value until one is provided.

**GPU production:**
- Profile `gpu`, `onnxruntime-gpu`, optional TEI GPU image, `deepdoc` service split out on 9390.

**Go-heavy deployment:**
- Profile `ragflow-go` adds NATS and the Go ingestor/syncer; Nginx switches more paths to 9384.

## Version Compatibility

| Package | Compatible with | Notes |
|---|---|---|
| infinity-sdk 0.7.3 | Infinity server 0.7.x | Docs table says server `v0.7.2`, ref compose says `v0.7.3`. Keep SDK and server on the same patch; use 0.7.3 for both. |
| elasticsearch-py 8.19.3 / go-elasticsearch 8.19.1 | ES server 8.11.3 | 8.x clients talk to older 8.x servers; avoid APIs added after 8.11. Do not move to ES 9 clients. |
| onnxruntime 1.23.2 | numpy 1.26.4, Python 3.13 | Keep numpy <2 with this set. |
| Quart 0.20.0 | Werkzeug >=3.1.7, Hypercorn 0.18.0 | Werkzeug 3.1.5 corrupts multipart uploads (pallets/werkzeug#3088) — directly affects document upload. |
| pytest-asyncio 1.3.0 | pytest 9, Python 3.13 | Disable the anyio pytest plugin (`-p no:anyio`). |
| zod 3.25 | @hookform/resolvers 3.9 | Resolvers 3.x target zod 3. |
| Tailwind 3.4 | tailwindcss-animate, shadcn "v3" templates | shadcn CLI defaults may now target Tailwind v4; pick the v3 config explicitly (unverified current CLI default). |
| GORM 1.25.7 | driver/mysql 1.5.2, go-sql-driver/mysql 1.7.0 | Old but matched set from the ref. |
| valkey-py 6.0.2 / go-redis 9.18.0 | Valkey 8 or Redis 7 | Both speak RESP; Streams + `SET NX EX` are available in both. |

## Sources

- `docs/00-overview/technology-stack.md`, `high-level-architecture.md`, `repository-map.md` — prescribed stack and layering (HIGH)
- `docs/02-frontend/{frontend-overview,frontend-architecture,state-management,api-client,components}.md` — frontend stack (HIGH)
- `docs/03-backend/{backend-overview,backend-architecture,entry-points}.md`, `docs/04-api/{api-overview,endpoint-catalog}.md` — Go/Python ownership (HIGH)
- `docs/05-rag-pipeline/{parsing,embedding}.md`, `docs/06-document-processing/{ocr,layout-analysis,pdf-processing,office-documents,tables,parsers}.md` — parsing/ML (HIGH for content; docs internally inconsistent on PyTorch vs ONNX)
- `docs/08-database/{database-overview,migrations}.md`, `docs/09-storage/storage-overview.md`, `docs/10-cache-and-queues/*` (HIGH)
- `docs/11-llm/*`, `docs/17-integrations/*`, `docs/18-deployment/*`, `docs/19-testing/*` (HIGH)
- Reference repo `/home/logan78/desktop x/ragflow` @ `6677f14` (2026-08-12): `pyproject.toml`, `uv.lock`, `go.mod`, `web/package.json`, `web/package-lock.json`, `docker/docker-compose-base.yml`, `docker/.env`, `docker/nginx/ragflow.conf.hybrid`, `ragflow_deps/download_deps.py`, `deepdoc/vision/*.py` — version pins and actual ML runtime (MEDIUM: authoritative for what works together, not for "latest")
- Web search, single-pass, not cross-checked against vendor pages:
  - MySQL 8.0 EOL 2026-04-30 — https://www.percona.com/?p=35183 , https://www.openlogic.com/blog/mysql-8-end-of-life (MEDIUM)
  - MinIO CE images discontinued / repo archived; `pgsty/minio` fork — https://linuxiac.com/minio-ends-active-development/ , https://blog.vonng.com/en/db/minio-is-dead/ , https://github.com/infiniflow/ragflow/issues/13840 (MEDIUM)
  - litellm 1.82.7/1.82.8 PyPI compromise (2026-03-24) — https://pypistats.com/blog/litellm-pypi-supply-chain-compromise-how-a-popular-llm-proxy-became-a-credential-stealing-backdoor-march-24-2026 (MEDIUM)
  - Quart 0.20.0 latest — https://quart.palletsprojects.com/en/latest/reference/versioning/ (MEDIUM)
- Not verified: current latest versions of each pinned package; `InfiniFlow/deepdoc` licence and contents; availability of `infiniflow/sandbox-executor-manager` and `deepdoc_oss` images; MySQL 8.4 behaviour with these drivers; the Engine column in `docs/apis.md` beyond the 38-row catalogue; whether Go proxies to Python in the ref.

---
*Stack research for: enterprise RAG platform (devRag)*
*Researched: 2026-10-05*
