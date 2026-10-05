# DECISIONS

Decision register for devRag. `docs/` wins over `spec.md`, existing code, RAGFlow and judgment. Gate: `python3 scripts/ci/check_decisions.py`.

## Status legend

- `user-confirmed`: the user explicitly answered this question (only R-03, R-17, R-18, R-48, dated 2026-10-05).
- `accepted (auto, not user-reviewed)`: chosen by the planner or executor from docs and reference evidence; the user has not reviewed it and may overturn it.
- `open`: deliberately settled by later-phase research, an owning phase, or user input.

## Register

| ID | Topic | Resolution | Status | Basis |
|----|-------|------------|--------|-------|
| R-01 | Server ports | Use the 18-deployment assignment: Python 9380, Python admin 9381, MCP 9382, Go admin 9383, Go 9384, plus sandbox 9385 and deepdoc 9390. | accepted (auto, not user-reviewed) | D-04 |
| R-02 | Route ownership and proxy table | Explicit Go prefixes (/health, /api/v1/system/, /api/v1/language, /api/v1/auth/, /api/v1/users, /v1/user/, /v1/tenant/, /api/v1/searchbots/, /api/v1/mcp), Python catch-all. Nginx config and Vite dev proxy generated from one route list. | accepted (auto, not user-reviewed) | D-05 |
| R-03 | Extent of Go parity | Go builds what the endpoint catalogue assigns it. Go mirrors of Python engines are deferred and recorded as undelivered parity items, never stubbed. | user-confirmed | user-confirmed 2026-10-05 (D-01) |
| R-04 | How Go reaches Python-owned capability | No Go-to-Python proxying. CLI targets canonical routes through the ingress. Go search-bot retrieval path decided by Phase 7 research. | accepted (auto, not user-reviewed) | D-06 |
| R-05 | Upload, parse trigger, public chatbot owner | Python owns upload, parse and chatbot completions. Upload does not enqueue; parsing is an explicit step. | accepted (auto, not user-reviewed) | D-07 |
| R-06 | Schema and migration owner | Peewee owns DDL and migrations as a one-shot step before servers start. GORM maps with AutoMigrate off; Go `--migrate` only verifies. init.sql creates the database and grants only. | accepted (auto, not user-reviewed) | D-10 |
| R-07 | Container topology | Single app container (Nginx + Go + Python) plus a standalone task-executor container. | accepted (auto, not user-reviewed) | D-24 |
| R-08 | DeepDoc placement | In-process in the worker by default; honour DEEPDOC_URL and ship the deepdoc profile later. Parsing never runs in the API process. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-09 | Identifier naming | Keep documented names: ragflow_server, index prefix ragflow_, bucket ragflow. Compose project is devrag-stack (R-59). | accepted (auto, not user-reviewed) | D-22 |
| R-10 | Task queue technology | Redis Streams behind an interface; NATS only if the Go ingestor is ever built. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-11 | Chunk ID scheme | Docs scheme doc_id + "_" + chunk_order with deterministic page-range ordering; a task deletes prior chunks for (doc_id, from_page, to_page) then upserts. Exact construction settled by research. | open | Phase 4 |
| R-12 | Redis distributed lock | Owner token, compare-and-delete release, TTL renewal while the task runs. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-13 | Embedding batch size | 64 per docs, configurable per provider. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-14 | Document and task state vocabulary | document.run codes per 06 (3 finished, 4 failed); document.status is the soft-delete flag; task state derives from progress (-1 failed). | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-15 | Dedup hash | xxh64. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-16 | Progress delivery to the UI | Polling: one list endpoint refetch with backoff while any row is running. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-17 | Default doc engine | Elasticsearch 8.11.3 for compose default and integration tests; Infinity as second adapter behind the same interface. | user-confirmed | user-confirmed 2026-10-05 (D-03) |
| R-18 | Engines beyond ES and Infinity | Order: ES, Infinity, then OpenSearch. Others need their own research and an explicit scope answer. | user-confirmed | user-confirmed 2026-10-05 (D-03) |
| R-19 | Index naming and vector-level isolation | One index per tenant, datasets separated by kb_id filter; adapter builds the index name from tenant_id. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-20 | Tenant scoping of documents and tasks | Follow the DDL; isolation transitive through knowledgebase.tenant_id, membership via user_tenant, tenant resolved in auth middleware. | accepted (auto, not user-reviewed) | D-12 |
| R-21 | Object storage layout | Bucket ragflow, key {tenant_id}/{doc_id} stored in document.location; no user-supplied filename in the key. | open | Phase 3 |
| R-22 | Queries across datasets with different embedding models | Embed the query with the dataset model; reject multi-dataset queries with differing embd_id; lock embd_id once chunks exist. | accepted (auto, not user-reviewed) | D-22 |
| R-23 | Fusion method and weight direction | Weighted sum is the default path, RRF an option; golden test fails if weights are swapped. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-24 | Response envelope keys | {code, message, data}, defined once per language and in one TS interface. | accepted (auto, not user-reviewed) | D-13 |
| R-25 | Path prefixes and legacy aliases | endpoint-catalog.md plus apis.md lines 1 to 139 are canonical; legacy aliases not served. | accepted (auto, not user-reviewed) | D-09 |
| R-26 | Chat SSE framing | Follow 12-chat/streaming.md: enveloped frames, reference on final frame, data: [DONE] terminator. Delta-vs-cumulative resolved by research. | open | Phase 5 |
| R-27 | Citation marker | ##N$$ in stored answers; prompt, post-processor, stored message and frontend parser agree. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-28 | Workflow SSE event names | Follow 14-workflows (workflow_started, node_started, node_finished, message, workflow_finished). | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-29 | Health endpoint | /health (Go) and /system/healthz (Python); health reports each dependency. | accepted (auto, not user-reviewed) | D-08 |
| R-30 | Reliability of per-resource API docs | Treat as evidence a route exists; confirm verb/body against the reference per phase. Define logout in Phase 2. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-31 | Table and column names | Follow 08-database; map agent_session to API4Conversation, canvas_replica to UserCanvasVersion; other columns from the reference model. | accepted (auto, not user-reviewed) | D-11 |
| R-32 | CORS policy | Configurable allow-list defaulting to same-origin; never wildcard with credentials. | accepted (auto, not user-reviewed) | D-14 |
| R-33 | Access-token format | Stored access_token model, Go issues, both verify by decode then row lookup, logout rewrites to INVALID_<hex>; shared test vectors. | open | Phase 2 |
| R-34 | Password hashing | Werkzeug-format hashes verified natively in Go; never unsalted SHA-256. | open | Phase 2 |
| R-35 | Client token storage | Bearer header from localStorage; cookie only for documented session fallback with CSRF protection. | open | Phase 2 |
| R-36 | Who may invite members | Owner only, following the permissions matrix. | open | Phase 2 |
| R-37 | Provider key storage | AES-GCM with env-supplied key, single masking serializer, log redaction; shared Go/Python test vector. | accepted (auto, not user-reviewed) | D-28 |
| R-38 | Restricted unpickler | No pickle on data crossing a trust boundary; exact (module, name) whitelist if a helper must exist; PoC kept as regression test. | accepted (auto, not user-reviewed) | D-25 |
| R-39 | Sandbox executor | Docker, Python + Node.js, 256m and 10 s defaults; own manager under agent/sandbox/. If unfinished it is a blocker, never host exec. | open | Phase 7 |
| R-40 | Auth snippet transcription | Treat as behavioural description; write an auth contract; default-deny routes; route-enumeration 401 test on both stacks. | open | Phase 2 |
| R-41 | Python version | Python 3.13 via uv, requires-python >=3.13,<3.14. | accepted (auto, not user-reviewed) | D-16 |
| R-42 | MySQL version | Parameterise as MYSQL_IMAGE, default mysql:8.0.40; 8.4 LTS needs user approval (B-12). | accepted (auto, not user-reviewed) | D-17 |
| R-43 | Redis 7 vs Valkey 8 | valkey/valkey:8; core commands only. | accepted (auto, not user-reviewed) | D-18 |
| R-44 | ML runtime and PDF library | onnxruntime + InfiniFlow/deepdoc models; pdfplumber + pypdfium2; no torch, no PyMuPDF. | accepted (auto, not user-reviewed) | D-21 |
| R-45 | Python framework wording | Quart + Hypercorn; Flask mentions are stale. | accepted (auto, not user-reviewed) | D-15 |
| R-46 | Frontend stack details | Vite only, shadcn/ui only (no antd), TanStack Query in use-*-request hooks. | accepted (auto, not user-reviewed) | D-19 |
| R-47 | Chunker and node catalogues | Build the 14 chunkers and 20 catalogued nodes plus Code; unimplemented parser_ids rejected explicitly. | accepted (auto, not user-reviewed) | SUMMARY Record |
| R-48 | Foreign content in docs/apis.md | Lines 1 to 139 are specification, remainder non-normative; billing (BILL-01..10) is in v1 scope per the user's answer. | user-confirmed | user-confirmed 2026-10-05 (D-02) |
| R-49 | docs/apikey llm.md | Never read, committed or relied on until the user reviews it; ignored via .gitignore; never git add docs/ wholesale. | accepted (auto, not user-reviewed) | D-26 |
| R-50 | Real model for verification | Ollama in compose with one small chat and one small embedding model, or a user-supplied OpenAI-compatible key. | accepted (auto, not user-reviewed) | D-31 |
| R-51 | [P]-flagged features | Scheduled as v1.x pending user confirmation; each needs phase research. | open | Later phases |
| R-52 | Rerank candidate window on CPU | Keep 1024 as documented default; configurable cap on the rerank call, dev value recorded after timing. | open | Phase 6 |
| R-53 | Go location matches | Exact-match Go locations for /api/v1/system/*, /api/v1/mcp and /api/v1/users. | accepted (auto, not user-reviewed) | Orchestrator |
| R-54 | Health path aliases | Serve canonical /api/v1/system/healthz|status AND literal /system/healthz|status from one route-list entry; explicit exception to D-09, flagged for user review. | accepted (auto, not user-reviewed) | Orchestrator |
| R-55 | /system/status exposure | Public in Phase 1 with minimal payload (status and elapsed_ms only); becomes authenticated in Phase 2. | accepted (auto, not user-reviewed) | Orchestrator |
| R-56 | Elasticsearch image and watermarks | docker.elastic.co/elasticsearch/elasticsearch:8.11.3 with dev disk watermarks low 1gb, high 750mb, flood_stage 500mb. | accepted (auto, not user-reviewed) | Orchestrator |
| R-57 | Go version | go 1.25.0 in go.mod, not 1.26.4. | accepted (auto, not user-reviewed) | Orchestrator |
| R-58 | Peewee and MySQL auth | peewee>=3.19,<4 and mysql_native_password on mysql:8.0.40. | accepted (auto, not user-reviewed) | Orchestrator |
| R-59 | Compose project and ports | Compose project devrag-stack, ingress 8080, Redis host port 6380, services bound to 127.0.0.1. | accepted (auto, not user-reviewed) | Orchestrator |
| R-60 | Schema columns | Documented columns exact; other columns from the reference model per table; none invented. | accepted (auto, not user-reviewed) | Orchestrator |
| R-61 | MySQL app user and secrets | Least-privilege MySQL app user; generated .env secrets with ${VAR:?}. | accepted (auto, not user-reviewed) | Orchestrator |
| R-62 | vm.max_map_count preflight | Fails by default; recorded override PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 (B-02). | accepted (auto, not user-reviewed) | Orchestrator |
| R-63 | HTTP status vs envelope | HTTP status mirrors the envelope error class. | accepted (auto, not user-reviewed) | Orchestrator |
| R-64 | App container healthcheck | Probes Go /health and Python /api/v1/system/healthz through Nginx. | accepted (auto, not user-reviewed) | Orchestrator |
| R-65 | Run modes and boot (API-12, API-13) | Delivered partially: real --api/--migrate, boot logger/DB verify/hooks; unbuilt modes exit non-zero naming phase and BLOCKERS entry, never stubbed. | accepted (auto, not user-reviewed) | Orchestrator, B-07, B-08 |
| R-66 | SEC-05 gate | Satisfied by deviation: no pickle on untrusted data, CI gate plus regression test. | accepted (auto, not user-reviewed) | Orchestrator, D-25 |
| R-67 | CI shape | Plain scripts scripts/ci/check_* run by make ci, plus .github/workflows/ci.yml calling the same target (B-06). | accepted (auto, not user-reviewed) | Orchestrator |
| R-68 | Migration mechanism | Versioned Peewee modules under api/db/migrations/; applied version stored as schema.version in system_settings. | accepted (auto, not user-reviewed) | Orchestrator |
| R-69 | Frontend versions not named in docs | CLAUDE.md majors followed (zustand 4.5.7, sonner 1.7.4, React 18, Tailwind 3, zod 3 with @hookform/resolvers 3 if forms added). Within-major bumps: react-router 7.18.4 (baseline 7.11.0), axios 1.20.0 (baseline 1.13.6), @tanstack/react-query 5.104.1 (baseline 5.90.14). Vitest resolved at install by plan 01-10: 5.0.3 (also jsdom 30.1.2, lucide-react 1.52.0, @testing-library/jest-dom 7.0.1). Also openapi-typescript and tailwind-merge 2.6.1. | accepted (auto, not user-reviewed) | Orchestrator |
| R-70 | Python web dependency versions | Quart 0.23.1 + quart-schema 0.25.0 + PyMySQL 1.2.3, falling back to reference pins (quart 0.20.0, quart-schema 0.23.0, PyMySQL 1.1.2). | accepted (auto, not user-reviewed) | Orchestrator |
| R-71 | UI design contract choices | From 01-UI-SPEC.md Auto-Selected Choices: teal accent, system fonts, 4 type sizes, nav shows only built routes. | accepted (auto, not user-reviewed) | 01-UI-SPEC |
| R-72 | Dev memory budget | Limits es01 2g, mysql 640m, minio 256m, valkey 160m, app 768m; measured figures appended by plan 01-15. | open | Plan 01-15 |
| R-73 | Envelope code sharing | Go and Python never share envelope code; defined once per language with a RetCode parity test. | accepted (auto, not user-reviewed) | Orchestrator |
| R-74 | DB lock connection and in-transaction retry | DatabaseLock holds MySQL GET_LOCK on its own dedicated PyMySQL connection outside the pool (pool recycling or DB.close() cannot release it early). The retrying pool does not retry a statement inside an open transaction (a reconnect would silently drop earlier statements and break atomicity); begin() and standalone statements are retried. | accepted (auto, not user-reviewed) | Plan 01-06, DATA-04/DATA-08 |
| R-75 | Migration atomicity under MySQL DDL | Each migration runs with its schema.version write inside db.atomic(); MySQL commits DDL implicitly, so migrations must keep DDL idempotent (add_column_if_missing and add_index_if_missing helpers). | accepted (auto, not user-reviewed) | Plan 01-06, DATA-05 |

## Deviations from docs

- D-13 envelope `{code, message, data}` versus `retcode/retmsg` in `04-api/api-overview.md`. Rationale: docs split evenly across files and the reference uses code/message. Fits: one definition per language plus one TS interface.
- D-16 Python 3.13 versus "3.10 slim" in docker.md. Rationale: 3.10 is end-of-life this month and the reference lock targets 3.13. Fits: uv-managed runtime, base image line is the only conflict.
- D-20 `pgsty/minio` image and exact `litellm==1.84.0`. Rationale: upstream minio images are no longer published; litellm 1.82.7/1.82.8 were malicious. Fits: same S3 protocol and same provider abstraction, hash-locked.
- D-21 no torch and no PyMuPDF. Rationale: reference runs onnxruntime and PyMuPDF is AGPL. Fits: docs' PyTorch/PaddleOCR/YOLO wording read as model lineage.
- D-25 pickle ban versus the docs' numpy whitelist. Rationale: the documented whitelist is bypassable via numpy.f2py.diagnose.run_command. Fits: stricter than the docs, PoC kept as regression test.
- D-15 Quart/Hypercorn versus Flask/Gunicorn wording. Rationale: every other doc says Quart ASGI. Fits: stale wording ignored.
- D-19 no `antd`. Rationale: two component systems double bundle size; the reference lacks antd. Fits: shadcn/ui only.

## Dependency policy

D-21: add each dependency only in the phase that builds the feature needing it; exact pins for security-sensitive packages (litellm); no torch, PyMuPDF, antd, Tailwind 4, React 19, zod 4 or Zustand 5; package installs that fail are checked for legitimacy by a human, never substituted.

## Open items for the user

- B-01: review `docs/apikey llm.md`.
- B-02: `vm.max_map_count` (needs sudo).
- B-03: free disk before the plan 01-15 clean-room runs.
- B-09: choose a real model source (key or Ollama models).
- B-12: approve or reject MySQL 8.4 LTS.
- R-54: review the health-path exception to D-09.

## Dev memory budget (measured)

Measured figures are appended here by plan 01-15.
