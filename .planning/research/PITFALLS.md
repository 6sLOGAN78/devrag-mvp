# Pitfalls Research

**Domain:** Enterprise multi-tenant RAG platform (devRag) built from a reverse-engineered RAGFlow specification by AI coding agents
**Researched:** 2026-10-05
**Confidence:** HIGH for pitfalls grounded in `docs/` and the local reference checkout (`~/desktop x/ragflow`, commit `6677f14bd`, 2026-08-12); MEDIUM for general RAG-engineering pitfalls (domain knowledge, not re-verified against external sources in this session)

**Evidence legend:** `[DOC]` = stated in `docs/`; `[REF]` = verified in the reference checkout; `[HOST]` = measured on this machine; `[HIST]` = from the prior abandoned attempt's history as described in the milestone context; `[DOMAIN]` = general RAG engineering knowledge, not verified here.

---

## Read this first: three facts that change the roadmap

1. **The spec contradicts itself and the reference in load-bearing places** (ports, queue technology, chunk IDs, citation markers, default engine, score-fusion weights, secret encryption). See Pitfall 1 for the full table. Each contradiction must be resolved in writing *before* the phase that depends on it, or agents will each resolve it differently.
2. **This host cannot currently run the documented stack** `[HOST]`: 6.0 GB free disk (97% full), 15 GB RAM with ~5 GB available, no NVIDIA GPU, `vm.max_map_count = 65530`. The documented `MEM_LIMIT` is 8 GB *per engine container* `[DOC]`. See Pitfall 12.
3. **The reference ships three routing modes and defaults to Python-only** `[REF]`: `docker/.env` has `API_PROXY_SCHEME=python`; `hybrid` and `go` are opt-in. The docs describe the dual stack as the architecture. Route ownership is therefore a *decision to make*, not a fact to look up. See Pitfall 2.

---

## Critical Pitfalls

### Pitfall 1: Spec drift — silently simplifying or "resolving" the documented architecture

**What goes wrong:**
Agents implement a plausible generic RAG system instead of the documented one: a single index with a `tenant_id` filter instead of per-tenant indices, RRF instead of the documented weighted fusion, fixed-size chunking instead of the 14 `parser_id` chunkers, one backend instead of two. Later phases discover the mismatch and trigger "refactor to strictly match RAGFlow architecture" commits — exactly what killed the prior attempt `[HIST]`.

**Why it happens:**
- The docs are a *reverse-engineered description*, not a design. They are thin on many files (most are 1-5 KB) and link to source for the detail. Agents fill gaps from training-data priors about "how RAG works".
- The docs contain real contradictions, so "follow the docs" is underdetermined:

| Topic | Statement A | Statement B | Evidence |
|---|---|---|---|
| Backend ports | Go and Python both on `:9380` (`00-overview/high-level-architecture.md`) | Python `9380`, Go `9384`, Go admin `9383`, Python admin `9381`, MCP `9382` (`18-deployment/environment-variables.md`) | `[DOC]`; B matches `[REF]` `docker/.env` |
| Task queue | Redis Streams `te.{priority}.common`, `XADD`/`XREADGROUP` (`10-cache-and-queues/queues.md`) | NATS JetStream (`18-deployment/production-architecture.md`, `19-testing/integration-tests.md`; `nats` under profile `ragflow-go`) | `[DOC]` |
| Chunk ID | `doc_id + "_" + chunk_order` (`05-rag-pipeline/indexing.md`) | `xxhash64(content + doc_id)` | `[DOC]` vs `[REF]` `rag/svr/task_executor.py:404` |
| Citation marker | `##0$$` (`12-chat/streaming.md`) | `[ID:i]` | `[DOC]` vs `[REF]` `rag/prompts/citation_prompt.md` |
| Default doc engine | "Infinity Connection (Default Vector DB)" (`05-rag-pipeline/indexing.md`) | `DOC_ENGINE=elasticsearch` | `[DOC]` vs `[REF]` `docker/.env:20` |
| Fusion weights | `vector_similarity_weight` e.g. 0.3, term 0.7 (`hybrid-search.md`) | `rerank_by_model(tkweight=0.3, vtweight=0.7)` (`reranking.md`); RRF k=60 also documented | `[DOC]` |
| Tenant isolation in index | per-tenant index `ragflow_{uid}` (`indexing.md`) | "index chunks with `tenant_id` fields" (`16-auth/multi-tenancy.md`) | `[DOC]` |
| Supported engines | Qdrant, Milvus, PGVector, Tantivy (`00-overview`) | Infinity, ES, OceanBase, ClickHouse, SereneDB (`indexing.md`) | `[DOC]`; `[REF]` `rag/utils/` has only `es_conn`, `infinity_conn`, `ob_conn`, `opensearch_conn`, `serenedb_conn` — no Qdrant/Milvus/PGVector adapter found |
| Python framework | Quart (most docs) | "Python Flask API server" (`production-architecture.md`) | `[DOC]` |
| LLM key storage | "encrypted before insertion into `tenant_llm`" (`20-security/secrets.md`) | plain `TextField` | `[DOC]` vs `[REF]` `api/db/db_models.py:810` |
| Frontend | "Vite/UmiJS", "Shadcn/ui + Ant Design" (`technology-stack.md`) | PROJECT.md lists Vite + shadcn only | `[DOC]` |

**How to avoid:**
- **Phase 0 deliverable: `.planning/DECISIONS.md` (spec-conflict register).** One row per contradiction above: the two statements, the chosen resolution, the rule that chose it (`docs/` > `spec.md` > confirmed code > RAGFlow > judgment), and the phases affected. No phase plan may be approved while it depends on an unresolved row.
- **Every phase plan carries a "docs read" list and a "conformance table"**: documented constant/name/shape -> file and symbol that implements it. Reviewer checks the table, not prose. Constants worth pinning in tests: `MAXIMUM_TASK_PAGE_NUMBER = 12`, `BATCH_SIZE=64`, `WORKER_HEARTBEAT_TIMEOUT=120`, queue names `te.1.common`/`te.0.common`, vector column `q_{dim}_vec`, index `ragflow_{tenant_id}`, field boosts (`title_tks^10`, `important_kwd^30`, `question_tks^20`, `content_ltks^2`), layout overlap threshold `0.4`, default chunk tokens 512, retrieval `topk=1024`.
- **Deviation protocol:** any departure is a `DECISIONS.md` entry *before* code, with "contradiction" or "implementation blocker" as the only accepted reasons (per `docs/spec.md`).
- **Architecture conformance tests** (cheap, run in CI): assert the constants above; assert compose service names/ports; assert no module imports across forbidden boundaries.

**Warning signs:**
- A plan or summary contains "for simplicity", "for now", "MVP", "simplified", "instead of", "equivalent to".
- A commit message contains "refactor to match" — drift already happened.
- A new service/queue/framework appears that is not in `docs/00-overview/technology-stack.md`.
- A phase summary cites no `docs/` file paths.

**Phase to address:** Phase 0 (spec reconciliation) creates the register; every phase enforces it at plan-check and verification.

---

### Pitfall 2: Dual-stack route ownership confusion and duplicated business logic

**What goes wrong:**
Both Go and Python implement the same endpoint, auth check, or DB model; they diverge; the bug only appears depending on which server Nginx routed to. Or the opposite: the Go server becomes a hollow shell that proxies everything to Python, which is "silently simplifying documented architecture".

**Why it happens:**
- The docs describe a *mirrored* implementation for nearly every layer (handler/service/DAO, PDF parser, chunkers `naive/one/qa/table/presentation`, engine drivers, canvas) `[DOC]`. Mirroring everything doubles the project; mirroring nothing violates the spec.
- Two ORMs (Peewee, GORM) on one MySQL schema, two migrators (`api/db/db_models.py`, `internal/dao/migration.go`) `[DOC]` — two sources of truth for DDL.
- Two auth implementations must accept the same token. The documented "JWT" is not a standard JWT: it is an `itsdangerous`-style `Serializer(secret_key).loads()` that yields an `access_token` looked up in the `user` table `[DOC: 20-security/authentication-security.md]`. A Go implementation using a stock JWT library will reject Python-issued tokens.
- The reference itself is mid-migration: recent commit is "Port dataset nav and structure graph fixes to Go" and default mode is Python-only `[REF]`.

**How to avoid:**
- **Decide ownership once, as a routing table, and make Nginx the only place it lives.** The reference's `docker/nginx/ragflow.conf.hybrid` `[REF]` is the concrete precedent: Go owns `/v1/user/(login|logout)`, `/v1/system/config`, `/api/v1/chat/completions`, `/api/v1/datasets/search`, `/api/v1/skills`, `/api/v1/admin` (9383); Python owns the remaining `/(v1|api)` (9380) and selected admin routes (9381). Reconcile this against `docs/03-backend/backend-architecture.md` ("Go for user/tenant/auth/sync; Python for heavy ML/agent execution") and record the final table in `DECISIONS.md`.
- **Rule: one owner per route, one owner per table's DDL.** Pick a single migration authority (recommend: one stack owns all DDL; the other only maps existing tables and has a startup check that fails if a column it expects is missing).
- **Shared-contract test suite that runs against both servers:** token issued by A is accepted by B; identical error envelope `{code, message, data}`; identical tenant-scoping behaviour.
- **Response header `X-API-Source: go`** is documented `[DOC]` — implement it on Go and add an equivalent on Python so every integration test can assert which stack answered.
- Go-side "mirror" components that are not on the chosen route path (e.g. Go chunkers) must be an explicit `DECISIONS.md` scope entry: either built and tested, or documented as a blocker — never a stub.

**Warning signs:**
- Same path registered in both routers.
- A Peewee model and a GORM struct disagree on a column type/length/default.
- Login works but a subsequent call 401s intermittently.
- A Go handler body is only an HTTP call to `:9380`.

**Phase to address:** Phase 0 (ownership table), Backend-foundation phase (shared error envelope, config, migrations authority), Auth phase (cross-stack token test).

---

### Pitfall 3: Scope explosion and wrong phase ordering

**What goes wrong:**
The roadmap tries to give every documented subsystem equal early weight; breadth is built before the core value works. The prior attempt reached ES mapping after ~8 parts and never produced an answer `[HIST]`.

**Why it happens:**
The documented surface is enormous `[DOC]`: 14 chunkers, 20+ canvas node types (Begin, LLM, Retrieval, Categorize, Switch, AgentWithTools, Message, Loop, Iteration, ExitLoop, VariableAggregator/Assigner, List/Data operations, StringTransform, ExcelProcessor, DocsGenerator, Fillup, Invoke, Browser, ...), 13 background task types (RAPTOR, GraphRAG, mindmap, memory, wiki, skill, timeline, ...), 6+ engine backends, 24 API docs, sandbox executor, MCP, bots/chat channels, connectors, Langfuse, CLI with a SQL-like grammar, RBAC with GRANT/REVOKE.

**How to avoid:**
- **Order by the Core Value, then widen.** A thin *real* vertical slice first: register -> login -> create KB -> upload one text-layer PDF -> parse -> `naive` chunk -> embed -> index -> hybrid retrieve -> generate -> streamed cited answer in the UI. Every stage real, one implementation each.
- **Then widen along each axis in its own phase**: more parsers/OCR/layout; more chunkers; rerank; more providers; agents; canvas; CLI; integrations.
- **Tier the requirement list** in REQUIREMENTS.md: (T1) on the Core Value path; (T2) documented end-to-end flows in `docs/21-end-to-end-flows/`; (T3) everything else documented. "Complete system" still means all three — tiers set order, not scope.
- **One engine is the default and fully tested**; additional engines are separate later plans behind the `DocStoreConnection` interface. Do not start two engines in parallel.
- Count before planning: `docs/04-api/endpoint-catalog.md` and `docs/apis.md` enumerate the surface. Turn them into a checklist so "full REST API" is a number, not a feeling.

**Warning signs:**
- Three or more phases complete and no question has been answered from an uploaded document.
- A phase named after a layer ("Database schema") rather than a capability.
- Phase plans exceeding what one context window can verify.

**Phase to address:** Roadmap creation; re-checked at every phase transition.

---

### Pitfall 4: Mocked or placeholder functionality passing as done

**What goes wrong:**
An agent, with no API key and no GPU in its sandbox, ships a `FakeEmbedder` returning random/hash vectors, an OCR that returns `""`, a reranker that returns input order, a parser that reads only `page.get_text()`, or a canvas node whose `invoke()` returns its input. Unit tests pass. The phase is marked complete.

**Why it happens:**
- `[HOST]` no API keys are configured in the session and there is no GPU. The path of least resistance to green tests is a fake.
- Tests written by the same agent that wrote the fake assert on the fake.
- Static verification ("code exists") is accepted in place of execution, which `docs/spec.md` explicitly forbids.

**How to avoid:**
- **Make real execution possible without secrets.** Add a local model path to the dev/test compose: Ollama (documented provider, `docs/11-llm/ollama.md`) with a small chat model and a small embedding model, or FastEmbed ONNX (documented in `embedding.md`). This removes the excuse for fakes on the critical path. Record model names and dimensions in `DECISIONS.md`.
- **Fakes live only under `tests/`** and may never be importable from production packages. CI grep gate on production trees for: `TODO`, `FIXME`, `NotImplemented`, `pass  #`, `mock`, `fake`, `dummy`, `placeholder`, `lorem`, `return []  #`, `panic("not implemented")`.
- **Behavioural acceptance tests that a fake cannot pass:**
  - Retrieval: index 3 topically distinct documents; a query about topic A must rank a topic-A chunk first, for both vector-only and term-only modes.
  - OCR: a scanned (image-only) fixture PDF must yield the known sentence.
  - Rerank: a deliberately mis-ordered candidate list must be reordered.
  - Citation: the cited chunk's `content` must contain the fact in the answer; `position_int` must point at the right page.
- **Blockers are documented, not disguised**: `.planning/BLOCKERS.md` with what, why, what is needed. A phase with an entry there is "complete with blocker", never "complete".
- Verifier agent must run the end-to-end script, not read the code.

**Warning signs:**
- Embedding tests that assert only shape/dtype.
- Retrieval tests whose corpus has one document.
- A provider class with no network call in it.
- Phase summary says "verified by inspection".

**Phase to address:** Phase 0 (grep gate, BLOCKERS.md convention, local-model decision); every phase's verification step.

---

### Pitfall 5: Multi-tenant data isolation leaks (MySQL, vector index, object store, cache)

**What goes wrong:**
Tenant B reads Tenant A's dataset, chunk, file, conversation, or canvas by guessing or reusing an ID.

**Why it happens (grounded in `docs/20-security` and `docs/16-auth`):**
- Isolation is **by convention**: "explicitly appending `tenant_id = current_user.tenant_id` to every query filter" at the service layer (`authorization-security.md`). One forgotten filter is a leak. With two stacks, the convention must hold in two codebases.
- **Child entities have no `tenant_id` of their own.** The documented ER diagram puts `tenant_id` on Knowledgebase, Dialog, Canvas, Task; documents, chunks, files, conversations, and messages are reached through a parent. `GET /document/{id}` that queries by `id` alone leaks.
- **Vector index**: per-tenant index `ragflow_{uid}` is the documented scheme, but retrieval takes `kb_ids` from the request body. If the handler does not verify each `kb_id` belongs to the caller's tenant before building the index name/filter, isolation is void. The same applies to chunk APIs that accept a `chunk_id`.
- **Workspace model**: users belong to tenants through `USER_TENANT` with a `role` (`multi-tenancy.md`). "Current tenant" is not simply `user.id`; joined-team access needs an explicit membership check. Note the documented auth code resolves API tokens with `UserService.query(id=objs[0].tenant_id)` — treating tenant ID as user ID. Copying that literally bakes in a tenant==owner assumption.
- **API keys and beta tokens** map to a tenant; a key must never widen to other tenants the owning user belongs to.
- **Object storage**: files stored under randomized UUID object names (`file-security.md`); a download endpoint that takes a bucket/object name from the client bypasses DB scoping.
- **Redis**: documented key patterns (`llm_cache_{hash}`, `synonym_{term}`, `lock:task_{task_id}`) are not tenant-namespaced. An LLM-response cache keyed only on prompt hash can serve one tenant's cached answer to another.
- **Background workers** run without a request context; a task payload carrying only `doc_id` lets the worker write into whichever tenant index it derives — derive tenant from the DB row, not the message.

**How to avoid:**
- **Structural, not conventional.** Python: a `TenantScopedService` base whose query methods require `tenant_id` positionally (no default). Go: a GORM scope `ForTenant(tid)` and a lint/test that fails on any handler-reachable query on a tenant-owned table without it.
- **Single ownership-resolution function per entity** (`authorize_dataset(user, kb_id)`, `authorize_document(user, doc_id)` -> joins to KB -> tenant). Handlers may not query by raw ID.
- **DocStore adapter API takes `tenant_id` as a required argument** and builds the index name itself; callers never pass an index name. `kb_ids` are validated against the tenant before the call.
- **Cross-tenant test matrix, generated from the route table**: for every route with an ID parameter, tenant B calling with tenant A's ID must get the same response as for a non-existent ID (no existence oracle). Run it against both stacks. Add a vector-level test: identical document in two tenants, tenant B's query returns only tenant B chunk IDs.
- Tenant-namespace any Redis cache that stores tenant-derived content.
- Return the documented "Access denied or dataset does not exist" uniformly `[DOC]`.

**Warning signs:**
- `Model.get_by_id(x)` / `db.First(&m, id)` in a handler.
- Index name built from request data.
- A list endpoint without a `tenant_id` predicate in its SQL log.
- Isolation tests exist only for datasets.

**Phase to address:** Auth/tenancy phase (base classes, authorization helpers, test-matrix generator); re-applied in KB, Document, Retrieval, Chat, Agent, Canvas phases — each adds its routes to the matrix as an exit criterion.

---

### Pitfall 6: Ingestion worker unreliability — duplicates, stuck tasks, lost progress

**What goes wrong:**
Documents stay at "parsing 37%" forever; re-parse doubles the chunk count; a crashed worker's task is never retried, or is retried forever; cancel does nothing; progress exceeds 100% or goes backwards.

**Why it happens:**
- **Redis Streams are at-least-once.** Unacked messages are re-delivered via the pending list (`UNACKED_ITERATOR`) `[DOC]`. Without idempotent writes, redelivery duplicates chunks.
- **Chunk-ID choice decides idempotency.** The documented `doc_id + "_" + chunk_order` `[DOC]` makes a retried sub-task overwrite its own chunks only if order is deterministic *and scoped per page range*; with 12-page sub-tasks running in parallel, a global `chunk_order` is not known to a sub-task. The reference's content hash `[REF]` is naturally idempotent but collapses identical chunks. This must be decided in `DECISIONS.md`, and re-parse must delete the document's (or the task's page-range) chunks first either way.
- **The documented lock is unsafe as written**: `acquire` = `SET NX EX 60`, `release` = unconditional `DELETE` (`10-cache-and-queues/redis.md`). A task longer than 60 s loses the lock; its `release` then deletes another worker's lock. The reference uses a token and `delete_if_equal` `[REF: rag/utils/redis_conn.py:537-565]`.
- **Partial failure across three stores**: MySQL task row, doc-engine chunks, MinIO images. No transaction spans them. Crash after index-write but before `progress=1.0` and `XACK`.
- **Document progress is an aggregate of N page-range sub-tasks** (`scheduling.md`). Naive "last writer wins" updates produce wrong totals; one failed sub-task must fail the document, not leave it at 92%.
- **Poison messages**: a PDF that crashes the native parser kills the worker, gets redelivered, kills the next worker. The reference caps `retry_count` at 3 `[REF: api/db/services/task_service.py:223]`.
- **Heartbeats** (`WORKER_HEARTBEAT_TIMEOUT=120`) without a reaper are decorative.
- **Blocking the event loop**: OCR/ONNX/tokenizer calls on the asyncio loop stall heartbeats and progress; docs require `thread_pool_exec` offloading (`async-processing.md`).
- Outbox gap: `Document`+`Task` rows committed in `DB.atomic()` `[DOC]`, then `XADD` fails -> task row exists, never queued.

**How to avoid:**
- Idempotent pipeline contract: `(task_id)` is the unit; start of task deletes prior chunks for `(doc_id, from_page, to_page)`; chunk writes are upserts by deterministic ID.
- Lock with owner token, compare-and-delete release (Lua), and TTL renewal while the task runs.
- Ack only after the terminal state is persisted. On exception: persist `progress=-1` + message, then ack (documented convention: `prog=-1` = failed) so failures are visible instead of looping.
- `retry_count` on the task row, max 3, then terminal failure with the error in `progress_msg`.
- Reaper: periodically claim pending entries idle beyond the heartbeat timeout (`XAUTOCLAIM`/`XPENDING`+`XCLAIM`); also a sweeper for task rows that are `RUNNING` with no live worker and for `Task` rows with no stream entry (covers the outbox gap).
- Per-stage timeouts (reference uses `@timeout` on build/embed/index stages `[REF]`).
- Cancellation checked between stages and between embedding batches (`has_canceled`) `[REF]`.
- Document progress computed from sub-task rows in SQL (aggregate), not incremented.
- Graceful `SIGTERM`: stop collecting, finish or release, exit.
- All documented limiters present (`task_limiter`, `chunk_limiter`, `embed_limiter`, `minio_limiter`, `kg_limiter`) `[DOC]`.

**Warning signs:**
- Chunk count changes when the same document is re-parsed.
- `XPENDING` grows monotonically.
- Tests cover only the happy path; no test kills a worker mid-task.
- Progress updates implemented as `progress += x`.

**Phase to address:** Queue/worker phase (must ship with a kill-the-worker test, a poison-message test, and a re-parse idempotency test); revisited when page-range splitting and background job types (RAPTOR/GraphRAG) are added.

---

### Pitfall 7: Embedding dimension / index mapping mismatches

**What goes wrong:**
Changing a KB's embedding model, or adding a second KB with a different model in the same tenant, causes index-write failures or — worse — silent zero-recall vector search.

**Why it happens:**
- The scheme is **one index per tenant** (`ragflow_{tenant_id}`) with **dimension-named columns** (`q_768_vec`, `q_1024_vec`, `q_1536_vec`) `[DOC]`. The mapping must be created/extended dynamically; a static mapping with one vector field (the prior attempt stopped at "Elasticsearch mapping" `[HIST]`) breaks as soon as a second dimension appears.
- Query side computes the column from the *query* vector length (`f"q_{len(embedding_data)}_vec"`) `[DOC]`. If the query is embedded with the tenant default model while the KB was indexed with another, the query hits a column that is empty for those chunks -> zero vector hits, term search still returns results, so nothing looks broken.
- Same dimension, different model (two 1024-d models) is undetectable by column name and produces garbage similarity.
- Elasticsearch `dense_vector` requires the dimension in the mapping and it is immutable; default dynamic mapping will type a float array as `float`, not `dense_vector`. ES `dense_vector` has an upper dimension limit that depends on version (verify against the pinned `STACK_VERSION` before promising 3072-d support). `[DOMAIN, verify]`
- Missing L2 normalisation (documented step) changes scores if the engine uses dot product.
- Provider batch limits differ: docs say `BATCH_SIZE=64`; reference default is `EMBEDDING_BATCH_SIZE=16` `[REF]`; some providers reject larger batches or over-length inputs.

**How to avoid:**
- KB stores `embd_id`; **queries are always embedded with the KB's model**; a multi-KB query across different `embd_id`s is rejected with a clear error (or grouped per model) — decide and record.
- Lock `embd_id` once a KB has chunks; changing it requires an explicit re-embed job.
- Use ES dynamic templates (or explicit `put_mapping` on first use of a new dimension) so `q_*_vec` fields are `dense_vector` with the right dims and `cosine` similarity; assert the mapping in an integration test after first index of each dimension.
- Probe the model's real dimension at configuration time (embed one string) rather than trusting a table.
- Truncate inputs to the model's max tokens before embedding; record truncation.
- Tests: two KBs in one tenant with 384-d and 1024-d models both retrievable; model mismatch at query time raises.

**Warning signs:**
- Hybrid search "works" but `vector_similarity` is 0 for all hits.
- Mapping JSON in the repo contains a hard-coded `dims`.
- Index errors mentioning `mapper_parsing_exception` or dimension mismatch.

**Phase to address:** Embedding + indexing phase; re-verified in Retrieval phase and LLM-provider phase.

---

### Pitfall 8: Hybrid score fusion and reranking mistakes

**What goes wrong:**
Results are dominated by one signal; `similarity_threshold` filters out everything or nothing; adding a reranker makes results worse; pagination returns different items per page.

**Why it happens:**
- **Incomparable scales.** Raw BM25 is unbounded; cosine is in [-1, 1]. The documented formula uses a *normalised* token-similarity (`qryr.token_similarity()`), not the engine's BM25 `_score` `[DOC]`. Plugging ES `_score` into `w_term * S_term` breaks the weighting and the threshold.
- **Weight direction ambiguity** (see Pitfall 1 table): `vector_similarity_weight` (0.3 example) vs `tkweight=0.3, vtweight=0.7` defaults. Swapping them inverts behaviour without any error.
- **Three fusion methods are documented** (weighted sum, RRF k=60, per-engine paths: `rerank_by_model`, `rerank_with_knn` for ES, `rerank` for OceanBase, direct score for Infinity). Implementing "RRF everywhere" is drift; RRF scores (~0.016-0.03) also break any 0-1 threshold.
- Cross-encoder outputs are unbounded logits; docs require normalisation to 0-1 before mixing `[DOC]`. Normalising per-batch makes scores incomparable across pages.
- Reranking `topk=1024` candidates through a cross-encoder on CPU is minutes, not milliseconds `[HOST: no GPU]`.
- Rerank happens over a candidate window; paginating *after* rerank requires a stable window, or page 2 overlaps page 1.
- `S_rank_feature` (tag features + pagerank) is additive and can push scores above 1.
- Field boosts and the analysed fields (`title_tks`, `important_kwd`, `question_tks`, `content_ltks`, `*_sm_*` fine-grained variants) presuppose the documented tokenisation at *both* index and query time. Indexing with the ES standard analyser and querying with a custom tokenizer yields poor term recall.
- `available_int = 1` filter omitted -> disabled chunks returned.

**How to avoid:**
- Implement the documented path for the chosen default engine exactly, and name the functions after the documented ones so reviewers can map them.
- Unit-test fusion as a pure function with golden vectors: given term-sims, vector-sims, weights -> expected ordering and expected thresholded set. Include a test that fails if the two weights are swapped.
- Return `similarity`, `term_similarity`, `vector_similarity` per chunk (as the reference API does) so the UI's retrieval-test page exposes problems immediately.
- Bound rerank candidates by a configurable cap and by rerank-provider batch limits; time it on CPU and set defaults accordingly; record in `DECISIONS.md` if the cap differs from 1024.
- A small labelled retrieval fixture (10-20 queries over 3-5 docs) with a recall@k floor, run in CI for vector-only, term-only, hybrid, hybrid+rerank; hybrid+rerank must not be worse than hybrid.

**Warning signs:**
- All `similarity` values cluster near 0 or exceed 1.
- Changing `vector_similarity_weight` from 0 to 1 does not change ordering.
- Threshold slider in the UI is all-or-nothing.

**Phase to address:** Retrieval phase (fusion + golden tests); Rerank phase (normalisation, caps); surfaced in the Frontend retrieval-testing UI.

---

### Pitfall 9: Chunking and citation/source-position tracking

**What goes wrong:**
Answers cite the wrong chunk, citations point at page 0, PDF highlight boxes are offset or mirrored, citation markers leak into the UI as raw text, or the stream shows half a marker.

**Why it happens:**
- **Position must survive five transformations**: PDF points -> rasterised image at `zoom=3` -> layout/OCR boxes -> merged sections -> chunks -> `position_int = [page_num, x0, top, x1, bottom]` `[DOC]`. Any stage that concatenates text without carrying boxes destroys citations irrecoverably. Coordinate bugs: zoom factor not divided out, 0- vs 1-based pages, page offset from 12-page sub-task ranges (`from_page`) not added back, y-axis origin differences between PDF libraries, cropped/rotated pages.
- **A chunk spanning pages needs multiple positions**; a single 5-tuple cannot represent it (the reference stores a list of positions).
- **Token counting with the wrong tokenizer** — "max 512 tokens" measured in characters or whitespace words yields chunks that overflow the embedding model's window.
- **Tables and figures** need their own handling (table rows prefixed with table title; figure crops stored in MinIO and referenced by chunk) `[DOC]`; flattening them into text loses both meaning and position.
- **Citation marker format conflict** (`##0$$` in docs vs `[ID:i]` in reference). Whichever is chosen, the frontend parser, the prompt, the post-processor and the stored message must agree.
- **Citation index refers to the position in the *retrieved list sent in that turn***; if the reference list is re-sorted, de-duplicated, or truncated to fit the context window after the prompt was built, indices shift.
- **Streaming**: a marker can be split across SSE frames (`##1` | `2$$`); the documented protocol sends `reference: null` on intermediate frames and the full reference on the final frame `[DOC]`, so the UI must render pending markers gracefully and re-resolve at the end.
- LLMs hallucinate out-of-range indices; the reference additionally post-inserts citations by answer-sentence vs chunk similarity (`insert_citations`) `[REF]`.
- 14 chunkers share little code; implementing them independently yields 14 inconsistent chunk dict shapes.

**How to avoid:**
- Define one **`ParsedBlock`** type (text, layout label, page, bbox in PDF points, optional image ref) at the parser boundary and one **`Chunk`** type (content, tokens, list of positions, doc/kb ids, title/keyword/question fields). All parsers emit the former; all chunkers consume it and emit the latter. Enforce by type checks/tests.
- Normalise coordinates once, at the parser boundary, to the unit the frontend PDF viewer uses; document it.
- **Round-trip test**: fixture PDF with a known sentence at a known location -> ingest -> retrieve -> assert page number and bbox within tolerance. Repeat with a >12-page PDF so a sentence lands in the second sub-task.
- Use the embedding model's tokenizer (or the documented tokenizer) for chunk sizing; test that no chunk exceeds the model limit.
- Freeze the retrieved-chunk list before prompt construction; persist exactly that list as the message's `reference`; validate marker indices against its length and drop invalid ones.
- Client: buffer-aware marker parser with tests for split frames.
- Build `naive` first with the shared types; each additional chunker is a plan with its own fixture and expected chunk boundaries.

**Warning signs:**
- A parser function returns `str`.
- `position_int` is empty or constant across chunks.
- Citations render correctly only for single-page documents.
- Raw `##3$$` visible in chat.

**Phase to address:** Parsing phase (ParsedBlock + coordinates), Chunking phase (Chunk type, token sizing), Chat phase (marker contract, frozen reference list), Frontend chat phase (split-frame parser, highlight viewer).

---

### Pitfall 10: SSE streaming through the reverse proxy and two servers

**What goes wrong:**
Tokens arrive in one burst at the end, streams die at 60 s, generation continues (and bills) after the user closes the tab, errors mid-stream leave the UI spinning.

**Why it happens:**
- **Nginx buffers proxied responses by default.** The reference disables it for all API locations: `proxy_buffering off; proxy_http_version 1.1; proxy_set_header Connection ""; proxy_read_timeout 3600s; proxy_send_timeout 3600s` `[REF: docker/nginx/proxy.conf]`. The default `proxy_read_timeout` of 60 s kills slow first-token responses (reranking + long context).
- **gzip on `text/event-stream`** buffers; reference `gzip_types` does not include it `[REF]` — keep it that way.
- **The Vite dev proxy** behaves differently from Nginx; streaming "works in dev" then fails in compose (or vice versa).
- **Browser `EventSource` cannot send `POST` bodies or an `Authorization` header.** The documented completions call is a POST with a bearer token, so the client must use `fetch` + `ReadableStream` and parse `data: ...\n\n` frames itself, handling frames split across network chunks and multiple frames per chunk.
- **Wire-format specifics** `[DOC: 12-chat/streaming.md]`: every frame is `data: <JSON>\n\n` with envelope `{code, message, data:{answer, reference, session_id}}`; termination is the literal frame `data: [DONE]`. Whether `answer` is cumulative or a delta is not explicit in the doc excerpt — the intermediate and final examples suggest the final frame carries the full annotated answer. Decide (check `docs/21-end-to-end-flows/chat-streaming.md` and `docs/12-chat/complete-chat-flow.md`), record, and test; mixing delta and cumulative semantics duplicates text in the UI.
- **Errors after headers are sent** cannot change the HTTP status; they must be an in-band frame with non-zero `code`, followed by termination.
- **Two SSE controllers** (Quart `chat_api.py`, Gin `openai_chat.go`) `[DOC]` — two framings to keep identical. In hybrid mode the reference routes `/api/v1/chat/completions` to Go `[REF]`.
- **Client disconnect**: Quart generators need cancellation handling; Go needs `ctx.Done()`; otherwise the upstream LLM call runs to completion.
- **Persistence**: the assistant message must be saved when the stream ends *or* is aborted, exactly once.
- A blocking retrieval/rerank call on the event loop delays the first frame for *all* concurrent streams (`async-processing.md`).

**How to avoid:**
- Ship the reference-equivalent `proxy.conf` in the first compose phase; set `X-Accel-Buffering: no` and `Cache-Control: no-cache` on SSE responses as defence in depth.
- **Streaming integration test runs through Nginx**, not against the app port: assert that the first `data:` frame arrives well before the last (inter-frame time gap > 0 with a deliberately slow fake upstream in the *test harness*), and that the terminator arrives.
- One shared SSE frame-encoder per stack with a contract test comparing bytes for the same event sequence across Go and Python.
- Client stream parser as a pure function with tests: split frames, multi-frame chunks, error frame, missing terminator, abort.
- Cancellation test: client aborts -> upstream call cancelled within N seconds -> partial message persisted once.

**Warning signs:**
- Streaming verified only with `curl localhost:9380`.
- UI test asserts final text only.
- Nginx config has `location /` proxying without the buffering directives.

**Phase to address:** Infrastructure phase (proxy config), Chat phase (protocol + cancellation + persistence), Frontend chat phase (parser), Agent/Canvas phases reuse the same encoder.

---

### Pitfall 11: Secrets and per-tenant LLM API key handling (grounded in `docs/20-security/secrets.md`, `api-security.md`)

**What goes wrong:**
Provider keys leak via API responses, logs, error messages, the frontend bundle, git history, or a DB dump.

**Why it happens:**
- The docs **require** encryption at rest in `tenant_llm` and masking in responses; the reference stores `api_key` as a plain `TextField` `[REF]`. An agent "following RAGFlow" will store plaintext. Per the priority order, docs win: encrypt.
- Masking is specified per-response ("`ragflow-xxxx...xxxx`") `[DOC]` — easy to miss on one of many endpoints (list models, get provider, tenant info, export), and trivially missed on the *second* stack.
- **Masked value round-trip**: UI loads masked key, user edits another field, form posts the masked string back, backend overwrites the real key with `sk-****`.
- Structured request logging dumps bodies including `api_key`; provider SDK exceptions (LiteLLM) can echo request headers/URLs containing keys.
- Documented defaults are weak and public: `MYSQL_PASSWORD`, `MINIO_PASSWORD`, `REDIS_PASSWORD`, `ELASTIC_PASSWORD` all `infini_rag_flow` `[DOC]`. Compose that publishes `3306/6379/9000/9200` to the host with those defaults is an open door.
- `.env` committed. **This repo already has a live instance of the risk**: `docs/apikey llm.md` is untracked (whole `docs/` is `??` in git status) and flagged as possible credential material. A blanket `git add docs/` commits it.
- `secrets.md` describes "SHA256 / AES encryption for password hashing" `[DOC]`. Unsalted SHA-256 is not an acceptable password hash; treat this as an under-specified description, use a real password KDF, and record the decision. (The reference encrypts the password in transit with RSA and hashes server-side; verify the exact scheme in `docs/16-auth/authentication.md` before the auth phase.)
- Two stacks must share the encryption key and algorithm for `tenant_llm.api_key`, or one cannot decrypt what the other wrote.
- The token secret (`settings.get_secret_key()`) silently regenerating on restart invalidates all sessions; a hard-coded fallback makes tokens forgeable.

**How to avoid:**
- **Immediately**: add `docs/apikey llm.md` and `.env*` (except `.env.example`) to `.gitignore`; never `git add docs/` wholesale until the user has reviewed that file. Do not read it.
- Envelope: AES-GCM with a key from env (`DEVRAG_SECRET_KEY`-style), ciphertext + nonce + key-version stored; one test vector shared by Go and Python test suites.
- A single response serializer for model/provider objects that masks; a test that calls *every* GET route as an authenticated user and asserts no response body contains any seeded secret value (seed distinctive canary keys).
- Update semantics: empty or masked `api_key` on update = "unchanged".
- Log redaction filter (keys: `api_key`, `authorization`, `password`, `access_token`, `token`, `secret`) in both Zap and Python logging, with a canary test over captured logs after a failing provider call.
- Compose: required-variable syntax (`${VAR:?}`) for secrets, bind infra ports to `127.0.0.1` or do not publish them, `.env.example` with placeholders.
- No secret may enter the Vite bundle (`VITE_*` variables are public).
- App fails fast at startup if the secret key is unset.

**Warning signs:**
- `api_key` column readable in MySQL as `sk-...`.
- A response fixture in tests contains a full key.
- `git status` shows `.env` or the off-limits file staged.

**Phase to address:** Phase 0 (gitignore, off-limits file), Infrastructure phase (compose secrets), LLM-provider phase (encryption, masking, redaction, canary tests).

---

### Pitfall 12: Heavy ML dependencies, image size, and a host that cannot hold them

**What goes wrong:**
`docker compose up` fills the disk; Elasticsearch is OOM-killed or refuses to start; the first PDF parse hangs downloading models; OCR of a 50-page scan takes tens of minutes on CPU; CI cannot build the image.

**Why it happens:**
- `[HOST]` **6.0 GB free disk (97% used)**, 15 GB RAM (~5 GB available), 16 cores, **no NVIDIA GPU**, `vm.max_map_count=65530`.
- Documented `MEM_LIMIT=8g` per engine container `[DOC]`; reference `.env` sets `MEM_LIMIT=8073741824` `[REF]`. ES + MySQL + MinIO + Redis + Python server + worker with ONNX models + Go server + Vite will not fit alongside a desktop session in 15 GB without tuning.
- RAGFlow's quickstart requires `vm.max_map_count >= 262144` for Elasticsearch `[REF: docs/quickstart.mdx]`.
- The documented stack includes PyTorch, OpenCV, YOLO, PaddleOCR, Transformers, HanLP `[DOC]`. A naive `pip install torch` pulls multi-GB CUDA wheels that are useless here. The reference notes "v0.22+ doesn't include embedding models" in the image and runs embeddings via a separate TEI service or remote API `[REF]` — it moved heavy models *out* of the main image.
- DeepDoc models are **downloaded at runtime** from Hugging Face (`snapshot_download(repo_id="InfiniFlow/deepdoc")`) in OCR, layout, and TSR `[REF]` — first parse blocks on network; offline/CI fails; concurrent workers race the download.
- The documented Infinity image tag is `v0.7.2-x64-v3` `[DOC]`, which implies an x86-64-v3 CPU requirement (this host reports AVX2, so acceptable here; not portable to all CI runners).
- Docs mention native CGO parsers (PDFium, OfficeOxide static libs) for the Go engine `[DOC]` — a build-toolchain cliff.
- Rasterising at `zoom=3` `[DOC]` for a large PDF is hundreds of MB per task; with parallel sub-tasks this is the main worker OOM source.
- The docs allow remote DLA/OCR via `DEEPDOC_URL`/`TENSORRT_DLA_SVR` and a `deepdoc` compose profile `[DOC]` — the sanctioned way to isolate the heavy part.

**How to avoid:**
- **Phase 0 blocker: free disk.** Record a disk/RAM budget in `DECISIONS.md` (per image and per container). Do not start the infra phase until there is headroom (order of tens of GB) — raise this with the user; it is not something agents can fix.
- Set `vm.max_map_count` as a documented prerequisite (requires sudo — user action) and make the compose preflight script check it.
- Dev compose profile with reduced limits: ES heap capped (e.g. `ES_JAVA_OPTS=-Xms1g -Xmx1g`), single node, no replicas; MySQL buffer pool reduced; `mem_limit` per service sized to the budget.
- CPU-only wheels (PyTorch CPU index) or ONNX Runtime only for inference (docs reference ONNX OCR/DLA); no CUDA layers in the default image. GPU is a compose profile, per the docs.
- Models fetched in a **build step or an init job into a named volume**, pinned by revision, with checksum; worker fails fast with a clear error if models are absent. No runtime download on the request path.
- Separate `deepdoc` service/image (documented profile) so the API image stays small and rebuilds fast.
- Cap pages rendered concurrently; release page images after each stage; apply `task_limiter`.
- Measure and record: image sizes, cold-start time, pages/minute for OCR on this CPU. Size integration fixtures accordingly (2-3 page PDFs).

**Warning signs:**
- `docker build` > 15 minutes or image > 5 GB.
- Worker log shows Hugging Face download during a test.
- `Exited (137)` on any container.
- `no space left on device`.

**Phase to address:** Phase 0 (budget, prerequisites), Infrastructure phase (dev profile limits, preflight), Document-parsing phase (model provisioning, deepdoc service boundary).

---

### Pitfall 13: Flaky, timing-dependent integration tests

**What goes wrong:**
Tests pass locally, fail in sequence or under load; the "fix" is a longer sleep; the suite gets slower and less trustworthy until it is ignored. This is a recorded failure mode of the prior attempt `[HIST]`.

**Why it happens:**
- **Elasticsearch is near-real-time**: a document indexed is not searchable until refresh (default ~1 s). Search-right-after-index tests need `refresh=wait_for` or an explicit refresh, not a sleep. `[DOMAIN]`
- Async ingestion: tests `sleep(N)` then assert progress.
- Services not ready: `depends_on` without health conditions; app connects before MySQL accepts connections (reference healthchecks use up to 120 retries `[REF]`).
- Shared state: tests reuse one tenant/KB/index/stream; order-dependent; documented parallel runs (`pytest-xdist`, `go test -parallel`) `[DOC]` make collisions certain.
- Real LLM calls in tests: nondeterministic, rate-limited, slow.
- Redis consumer-group leftovers from a previous run redeliver old tasks into the next test.
- CPU-bound OCR timing varies 5x with machine load.

**How to avoid:**
- **Ban `sleep` in tests** (CI grep gate on `time.sleep`, `asyncio.sleep`, `time.Sleep` under test dirs). Provide one helper: `wait_until(predicate, timeout, interval)` that polls an observable terminal state (task `progress in {1.0, -1}`, index count == expected) and fails with the last observed state.
- Test-mode index writes use `refresh=wait_for` (or explicit refresh in the test helper) — record in `DECISIONS.md` that production keeps the default.
- **Isolation by construction**: each test creates its own tenant (-> own index `ragflow_{tenant}`), own queue suffix/consumer group, own MinIO prefix; teardown deletes them. This also exercises tenancy.
- Adopt the documented tiers `[DOC: test-architecture.md]`: unit (no services), integration (build tag / pytest marker, real MySQL/Redis/ES/MinIO), e2e (running stack). Unit tier must run in seconds with no network.
- Deterministic model layer for *integration* tests: a local stub HTTP server speaking the OpenAI-compatible API (in the test harness only), with scripted streaming; real-model tests live in a separate, explicitly-marked tier that uses the local Ollama/ONNX models.
- Compose healthchecks + `depends_on: condition: service_healthy`; app-level connect-with-backoff (documented for DB `begin()` retries).
- **Flake policy**: a test that fails intermittently is quarantined with an issue and a root cause; increasing a timeout is not an accepted fix without a written root cause.
- Run the integration suite 3x in a row as a phase exit check for worker/retrieval phases.

**Warning signs:**
- Commit messages: "increase wait", "fix flaky test", "retry".
- Suite duration growing faster than test count.
- Tests pass individually, fail together.

**Phase to address:** Phase 0 / test-foundation (helpers, tiers, grep gate, per-test tenant fixture); enforced in every phase.

---

### Pitfall 14: Workflow canvas / agent engine complexity underestimated

**What goes wrong:**
The canvas editor and the execution engine are built as two separate guesses at the same DSL; graphs saved by the UI do not execute; loops never terminate; a "Code" node executes LLM-generated code on the host.

**Why it happens:**
- 20+ node types with distinct semantics `[DOC: 14-workflows/nodes.md]`, including control flow (Switch, Categorize, Loop, Iteration, ExitLoop), state (VariableAssigner/Aggregator), human-in-the-loop (Fillup — requires suspend/resume across requests), autonomous tool use (AgentWithTools, MCP), outbound HTTP (Invoke), headless browser (Browser), and code execution.
- The documented engine has checkpointing, loop semantics, and state serialisation tested at unit level `[DOC: unit-tests.md: canvas_test, checkpoint_store_test, loop_semantics_test]` — signals of where the reference found bugs.
- Docs describe both a Python agent runtime (`agent/`) and a Go canvas (`internal/agent/canvas/`) `[DOC]` — another mirror decision (Pitfall 2).
- **Security** (`docs/20-security/attack-surface.md`, `file-security.md`): code execution must run in sandbox containers with `SANDBOX_MAX_MEMORY=256m`, `SANDBOX_TIMEOUT=10s`, `no-new-privileges`, no network by default, managed by `sandbox-executor-manager` on 9385 — which mounts `/var/run/docker.sock` `[DOC]`, i.e. root-equivalent on the host if that service is compromised. `Invoke`/`Browser` nodes are SSRF vectors into the compose network (MySQL, Redis, MinIO, ES, cloud metadata).
- Prompt injection: retrieved document text flows into an agent that has tools.
- Canvas DSL stored as JSON in MySQL; no schema version -> saved canvases break on change.
- React Flow state (positions, handles) mixed with execution semantics in one blob.

**How to avoid:**
- **DSL schema first** (versioned JSON Schema, shared by frontend and backend; generated TS types). The first canvas plan delivers the schema, a validator, and 3-5 golden DSL fixtures; UI and engine are both tested against those fixtures.
- Engine before editor: run golden fixtures headlessly (API) with streamed events before any canvas UI work.
- Build nodes in tiers: (1) Begin, LLM, Retrieval, Message — reuses the chat path; (2) Switch, Categorize, variables; (3) Loop/Iteration/ExitLoop with max-iteration guard; (4) tools, Invoke, AgentWithTools; (5) code execution with sandbox; (6) Fillup (suspend/resume), Browser, document generators.
- Global guards: max steps, max wall-clock, max tokens per run; cycle detection outside declared Loop nodes; cancellation.
- Code node is **not shippable without the sandbox**; if the sandbox cannot be completed, it is a documented blocker, never a host `exec`. Sandbox tests mirror the documented security tests (memory limit, timeout, network denial, forbidden syscalls).
- Outbound HTTP nodes: block private/link-local ranges and compose service names by default (allow-list configurable); the reference has an analogous guard (`ALLOW_ANY_HOST=0`) for DB connection testing `[REF]`.
- Tenant scoping for canvases, runs, and every KB a Retrieval node references (validated at run time, not only at save time).
- Agent run events use the same SSE encoder as chat.

**Warning signs:**
- Canvas UI phase scheduled before the engine can run a fixture.
- Node implemented in UI palette but absent from engine registry (or vice versa) — add a parity test.
- `subprocess`/`exec`/`eval` in agent code.
- No max-iteration constant.

**Phase to address:** Agent phase (runtime, tools, guards), Workflow-engine phase (DSL schema, tiers), Sandbox phase (separate, security-reviewed), Frontend canvas phase (after engine).

---

### Pitfall 15: Unsafe deserialization and file-upload handling (grounded in `docs/20-security/file-security.md`, `attack-surface.md`)

**What goes wrong:**
Remote code execution via a pickle payload; path traversal or stored XSS via uploaded files; worker crash/DoS via crafted documents.

**Why it happens:**
- The docs present `RestrictedUnpickler` with `safe_module = {"numpy", "rag_flow"}` as *the mitigation*, while the same doc names `numpy.f2py.diagnose.run_command` as the exploit primitive `[DOC]`; the reference `SECURITY.md` confirms that allowing the `numpy` module is exactly what makes the bypass possible `[REF: SECURITY.md:21]`. **Implementing the documented whitelist verbatim reproduces a known RCE.** This is a genuine spec defect -> `DECISIONS.md` deviation.
- Upload handling documented as: validated, extension-checked, sanitised, stored under randomised UUID object names `[DOC]`. Typical misses:
  - trusting client `Content-Type`/extension, no magic-byte check;
  - original filename used in an object key, a temp path, or a `Content-Disposition` header (traversal, header injection);
  - no size limit at each hop — Nginx reference allows `client_max_body_size 1024M` `[REF]`; Quart has its own `MAX_CONTENT_LENGTH`; Gin has its own multipart memory limit; the worker has `DOC_MAXIMUM_SIZE` `[REF]`. Mismatched limits produce confusing 413s or memory blow-ups;
  - whole-file buffering in memory in the API process;
  - **archive/decompression bombs**: DOCX/PPTX/XLSX are zip files; huge-page-count or huge-dimension PDFs rasterised at zoom 3;
  - **XXE** in OOXML/SVG/HTML parsers;
  - serving uploaded HTML/SVG inline from the app origin -> stored XSS against a token held in browser storage;
  - "web pages" ingestion (PROJECT.md) and URL-based upload -> SSRF;
  - native parser memory corruption -> docs prescribe running `deepdoc` as a separate sandboxed container process `[DOC]`;
  - thumbnails/crops written to MinIO with predictable names;
  - duplicate-filename handling within a KB.
- MinIO console/API published to the host with default credentials.

**How to avoid:**
- **Do not use pickle for any data that crosses a trust boundary.** Use JSON/msgpack/`.npy` with `allow_pickle=False` for vectors. If the documented `deserialize_b64` helper must exist for parity, whitelist *exact* `(module, name)` pairs (e.g. `numpy.core.multiarray._reconstruct`, `numpy.ndarray`, `numpy.dtype`), never a top-level module; include the documented PoC as a regression test that must raise `UnpicklingError`.
- Upload pipeline contract: stream to MinIO (no full buffering); size limit enforced at Nginx, app, and worker with one configured value; extension allow-list *and* magic-byte sniff; object key = `{kb_id}/{uuid}` with the original name stored only in MySQL; sanitise name for display and for `Content-Disposition` (RFC 5987 encoding).
- Downloads: `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, never inline for HTML/SVG; authorise via DB ownership then fetch object (never accept bucket/key from client).
- Parser guards: max pages, max pixels per page, max uncompressed size and entry count for zip-based formats, per-document timeout, XML parsers with external entities disabled.
- Parsing runs in the worker (or the `deepdoc` container), never in the API process; worker container non-root, read-only root FS where practical, no Docker socket.
- URL ingestion: SSRF guard shared with canvas Invoke/Browser nodes.
- Tests: traversal filenames (`../../x`, absolute paths, NUL, very long, unicode RTL), wrong-extension content, zip bomb fixture, oversize upload, the pickle PoC.

**Warning signs:**
- `pickle.loads` or `np.load(..., allow_pickle=True)` anywhere.
- `os.path.join(upload_dir, file.filename)`.
- `await request.files` followed by `.read()` of the whole body.
- Only `.pdf` in tests.

**Phase to address:** Upload/storage phase (pipeline contract, tests), Parsing phase (parser guards, process isolation), Backend foundation (ban pickle via lint), Security review pass before milestone completion.

---

### Pitfall 16: Authentication copied literally from the documented snippet (grounded in `docs/20-security/authentication-security.md`)

**What goes wrong:**
Sessions cannot be revoked or expired correctly; a missing header crashes the handler; token types are confused; an API key is accepted where only a user session should be.

**Why it happens:**
- The documented `_load_user()` snippet:
  - does `authorization[:7]` with no `None` guard -> exception -> 500 instead of 401 when the header is absent;
  - tries **Beta token -> JWT -> API token in sequence on the same string**, so any credential type is tried against every scheme the route enables; the per-route `auth_types` list is the only separation;
  - the "JWT" wraps a DB-stored `access_token`; validity = row lookup. The doc says "short-lived" and "expiration checks", but the snippet shows no expiry — expiry and logout semantics must be specified (logout must invalidate the stored `access_token`);
  - API/beta tokens resolve to a user via `UserService.query(id=objs[0].tenant_id)` (tenant==user assumption, see Pitfall 5).
- `access_token` stored and compared in plaintext; API tokens likewise.
- "CORS & CSRF controls via whitelisted origins" `[DOC: api-security.md]` — a permissive `*` with credentials during development tends to survive; the doc also mentions a session cookie path, which needs CSRF protection if used.
- "Every non-public endpoint is protected with `@login_required`" `[DOC]` is opt-in protection: a new route without the decorator is public. Go's middleware groups are opt-out. The two stacks have opposite failure modes.
- Rate limiting is listed as a Redis responsibility `[DOC]` but no algorithm is specified; login brute force is the documented threat (`attack-surface.md`).
- `REGISTER_ENABLED` exists in the reference `[REF]`; open registration on an exposed instance creates tenants freely.
- RBAC (`CREATE ROLE`, `GRANT ... ON ... TO ROLE`) is specified via CLI admin commands `[DOC: authorization-security.md]`; implementing role *tables* without *enforcement* in handlers is a classic "looks done".

**How to avoid:**
- Treat the snippet as a behavioural description, not code to transcribe. Write the auth contract: accepted schemes per route group, header parsing rules, error codes, expiry, logout invalidation, and token storage. Record in `DECISIONS.md` where it tightens the doc.
- **Default-deny**: Python routes registered through a wrapper that requires an explicit `public=True`; a test enumerates all registered routes on both stacks and asserts each non-allow-listed route returns 401 without credentials.
- Negative test set: no header, empty header, `Bearer` only, malformed token, expired token, logged-out token, API key on session-only route, token from deleted/disabled user (`status` invalid).
- Constant-time comparison; API tokens stored hashed if the docs' flows permit (they are shown once at creation) — otherwise record why not.
- Login rate limit in Redis keyed by account+IP; test it.
- RBAC: each permission has at least one enforcement point test (granted -> 200, revoked -> 403).
- CORS allow-list from config; no wildcard with credentials.

**Warning signs:**
- 500 responses on unauthenticated requests.
- A route list diff with no matching auth test diff.
- Roles exist in DB but no handler reads them.

**Phase to address:** Auth/tenancy phase; route-enumeration test extended in every API phase.

---

### Pitfall 17: Frontend-backend contract drift

**What goes wrong:**
The SPA calls endpoints that do not exist, sends `kb_id` where the server expects `dataset_id`, treats HTTP 200 with `code != 0` as success, or renders `undefined` because a field was renamed. Each side has passing tests against its own mocks.

**Why it happens:**
- Frontend and backend phases are executed by different agent runs, each reading different doc sections (`02-frontend/` vs `04-api/`), each filling gaps independently.
- The documented API uses an **application-level envelope** `{code, message, data}` `[DOC]`; errors frequently arrive with HTTP 200. A client that checks only `response.ok` hides every error.
- Two path families (`/v1/...` and `/api/v1/...`) and two servers (Pitfall 2) `[REF: nginx configs]`.
- Field naming inherits Python snake_case; TS code drifts to camelCase.
- Frontend tests with hand-written mock responses (MSW/fixtures) encode the frontend agent's guess.
- `docs/apis.md` (2,079 lines) and `docs/04-api/endpoint-catalog.md` are the contract but are prose/tables, not machine-checkable.

**How to avoid:**
- **Single machine-readable contract**: an OpenAPI document. The docs already specify `quart_schema` (OpenAPI v3 generation) for the Python server `[DOC]`; generate TS types from it (and from the Go server's spec for Go-owned routes). The frontend API client is typed from generated types; hand-written response interfaces are disallowed for API payloads.
- Seed the OpenAPI from `docs/apis.md` in the backend-foundation phase as a checklist; each API phase turns its section "implemented + contract-tested".
- **Contract tests in CI**: backend responses validated against the schema; frontend mock fixtures *generated from or validated against* the same schema.
- One API client module (documented: Axios client + interceptor `[DOC]`) that: unwraps the envelope, throws on `code != 0`, handles 401 -> logout/refresh, attaches auth. No `fetch` calls elsewhere except the SSE reader.
- **Vertical phase exit criterion**: every backend capability phase that has a UI counterpart ends with a browser-level smoke test (Playwright) against the real stack through Nginx — at minimum the documented end-to-end flows in `docs/21-end-to-end-flows/`.
- Prefer vertical slices (API + UI together per capability) over "all backend, then all frontend".
- Every data view implements loading/error/empty states (`docs/spec.md` requirement); add a checklist item per page.

**Warning signs:**
- `any` or hand-typed interfaces in the API layer.
- Frontend suite green with backend down.
- UI phase scheduled many phases after its API.
- Toast says "success" while network tab shows `code: 102`.

**Phase to address:** Backend foundation (envelope, OpenAPI generation), Frontend foundation (generated client, interceptor), every capability phase (browser smoke test).

---

### Pitfall 18: Docker Compose resource and startup-ordering failures

**What goes wrong:**
First `up` fails nondeterministically; the app crash-loops while MySQL initialises; ES is "up" but red; the MinIO bucket does not exist; port 9380 is contested by two processes; data disappears between runs or stale volumes break a schema change.

**Why it happens:**
- Documented dependency is only `mysql: healthy` for the app `[DOC]`; Redis, MinIO, and the doc engine have healthchecks but the app does not wait on them in the documented table.
- The reference runs **Nginx + Python server + Go server + task executors inside one container** via `entrypoint.sh` `[REF]`; docs show ports 80/443/9380-9384 all on `ragflow-cpu` `[DOC]`. Re-creating that as one container vs. splitting into services is a decision; either way the internal `127.0.0.1` upstreams in Nginx only work in the single-container form.
- Port confusion from the `:9380`-for-both diagram (Pitfall 1).
- Profiles: `COMPOSE_PROFILES=${DOC_ENGINE},${DEVICE}` `[REF]`; running `docker compose up` without the profile starts no engine and the app fails obscurely.
- Config templating: `service_conf.yaml.template` + `envsubst` in entrypoint `[DOC: secrets.md]` — missing variable -> empty string -> confusing connection errors.
- Two processes racing to run migrations / create the tenant index / create the consumer group on startup. The reference guards periodic jobs with a Redis lock `[DOC: backend-architecture.md]`.
- MySQL first-boot init (`init.sql`) only runs on an empty volume; changing it later has no effect.
- `[HOST]` memory/disk limits (Pitfall 12); MySQL 8 + ES + everything else.
- Documented image pins include unusual tags (`pgsty/minio:RELEASE.2026-03-25...`, `valkey/valkey:8`, `infiniflow/infinity:v0.7.2-x64-v3`, `serenedb/serenedb:26.07.5`) `[DOC]` — verify each tag exists and pulls before pinning; do not invent substitutes silently.
- Healthcheck credentials leaking into `docker inspect` (`redis-cli -a ${REDIS_PASSWORD}`, `mysqladmin -p...`) `[DOC]`.
- Path with a space: the project lives at `/home/logan78/desktop x/devRag_@` — unquoted paths in scripts, Makefiles, compose bind mounts, and test runners will break. The `@` in the directory name also becomes part of the default compose project name; set `name:` explicitly.

**How to avoid:**
- `depends_on` with `condition: service_healthy` for **every** infra dependency; app-level bounded retry with clear logs on top.
- A one-shot `init` service (or entrypoint stage) that: waits for deps, runs migrations under a lock, creates the MinIO bucket, creates the Redis consumer group idempotently (`XGROUP CREATE ... MKSTREAM`, tolerate `BUSYGROUP`), then exits; app services depend on `service_completed_successfully`.
- Decide and record the container topology (single app container like the reference vs. split services); if split, Nginx upstreams use service names.
- Explicit `name:` for the compose project; quote every path; add a CI/lint check running scripts from a path containing a space.
- `make up` / preflight script: checks disk, RAM, `vm.max_map_count`, required env vars, chosen profile; prints actionable errors.
- A **clean-room bring-up test** as the infrastructure phase's exit criterion and again at milestone end: `down -v`, `up`, wait healthy, run the end-to-end smoke — from documented setup instructions only (Completion Criterion 7).
- Health endpoint (`/v1/system/health` `[DOC]`) reports each dependency's status, not just process liveness.

**Warning signs:**
- "Works after restart".
- `sleep 30` in an entrypoint.
- README setup steps that differ from what the agent actually ran.
- Containers `Restarting (1)`.

**Phase to address:** Infrastructure phase; re-run at every phase that adds a service (deepdoc, sandbox, Go server, worker).

---

### Pitfall 19: LLM provider abstraction that leaks or lies

**What goes wrong:**
Adding the second provider requires touching chat, embedding, rerank, and agent code; streaming works for OpenAI but not Ollama; token limits are wrong; tool-calling silently unsupported; a provider error surfaces as an empty answer.

**Why it happens:**
- The documented design is LiteLLM **plus** direct provider integrations `[DOC]`, across four model types (chat, embedding, rerank, vision/VLM — plus ASR/TTS implied by the `audio` and `picture` chunkers). Each type has its own abstraction in the reference.
- Per-tenant configuration: tenant defaults (`llm_id`, `embd_id` on TENANT `[DOC]`), per-KB embedding model, per-dialog chat model, per-tenant keys in `tenant_llm`. Resolution order is easy to get wrong; a global env key used as silent fallback bills the operator for tenant usage and crosses tenants.
- Provider differences: streaming chunk shapes, usage reporting only at stream end, rate-limit/429 semantics, max context, embeddings batch/size limits, base-URL quirks (Ollama inside Docker cannot reach `localhost` on the host), rerank APIs that are not OpenAI-shaped at all.
- Model capability tables (context window, dims, supports tools) hard-coded from training data and stale. `[verify against provider docs at implementation time]`
- Errors swallowed in a streaming generator -> stream ends with no content.
- No timeouts/retries on provider calls -> worker tasks hang (interacts with Pitfall 6).

**How to avoid:**
- One interface per model type with a conformance test suite that every provider implementation must pass against a stub server (streaming, non-streaming, error, timeout, usage accounting) and — in the real-model tier — against Ollama.
- Model resolution in one function: `(tenant, purpose, explicit_id) -> configured client`, no env-key fallback unless explicitly configured as a system default and recorded.
- Timeouts, bounded retries with backoff on 429/5xx, and errors mapped to the documented error envelope and to an in-band SSE error frame.
- Capability metadata from provider API/probe where possible; otherwise a data file with a "verified on" date.
- "Test connection" on save (the reference does this) so bad keys fail at configuration, not at first chat.
- Key handling per Pitfall 11.

**Warning signs:**
- `if provider == "openai"` outside the provider package.
- Only one provider in tests.
- Empty assistant messages in the DB.

**Phase to address:** LLM-layer phase (before embedding/chat phases consume it — or a minimal interface in the vertical slice, widened later).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Python-only now, "add Go later" | Half the work up front | Repeats the abandoned attempt; later Go port forces schema/auth/route refactors | Never as an unrecorded choice. Acceptable only as an explicit `DECISIONS.md` sequencing decision with the Go ownership table already fixed |
| Single index + `tenant_id` filter instead of `ragflow_{tenant}` | Simpler mapping | Spec drift; one missing filter = cross-tenant leak | Never |
| Hard-coded embedding dimension in mapping | Quick first index | Breaks on second model; reindex required | Never (dynamic `q_{dim}_vec` is the spec) |
| Fake embedder/reranker/OCR in production tree | Green tests without models | Violates core project rule; hides integration failures | Never; fakes only under `tests/` |
| `sleep()` in tests | Fast to write | Flaky and slow suite | Never |
| Hand-written TS API types | No codegen setup | Contract drift | Only for the SSE frame type, with a shared fixture |
| Plaintext `tenant_llm.api_key` "like RAGFlow" | Matches reference | Violates `docs/20-security/secrets.md` | Never |
| Runtime model download from Hugging Face | Small image | First-parse hang, offline failure, download races | Only in dev with an explicit flag; never in tests/CI |
| One generic chunker registered under all 14 `parser_id`s | "Supports" all parsers | Placeholder functionality | Never; unimplemented IDs must be rejected with a clear error and listed as pending |
| Skipping page-range sub-tasks (one task per doc) | Simpler progress | Drift from `scheduling.md`; large PDFs time out | Only inside the first vertical slice, recorded, and replaced in the worker phase |
| Publishing infra ports with default passwords | Easy debugging | Exposed services | Dev only, bound to `127.0.0.1` |
| Giant `task_executor`-style module | Mirrors reference | Violates "no giant files"; unreviewable | Never — reference file is ~1,900 lines; split by stage |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Elasticsearch | Search immediately after index; default dynamic mapping; multi-node defaults; `vm.max_map_count` unset | `refresh=wait_for` in tests; explicit/dynamic-template mapping; single-node dev settings with capped heap; preflight check |
| Elasticsearch security | Disabling security to "make it work" while docs specify `ELASTIC_PASSWORD` | Keep auth on; pass credentials from env in both stacks |
| Redis Streams | No consumer group creation; ack before persist; ignoring pending list; unconditional lock delete | `XGROUP CREATE MKSTREAM` idempotently; ack after terminal state; reaper with `XAUTOCLAIM`; token-based lock |
| Valkey vs Redis | Assuming module/feature parity with a specific Redis version | Docs pin `valkey/valkey:8`; restrict to core commands (streams, SET NX EX, hashes) and test against the pinned image |
| MinIO | Bucket not created; path-style vs virtual-host addressing; presigned URLs signed for the internal hostname (`minio:9000`) unusable by the browser | Init job creates bucket; path-style; serve downloads through the API (authorised) rather than presigned internal URLs |
| MySQL 8 | utf8 (3-byte) charset breaks emoji/CJK; connection drops after idle; two ORMs with different defaults; long `TEXT` in indexed columns | `utf8mb4`; pool with ping/recycle + documented `begin()` retry; single DDL authority; index prefix lengths |
| Peewee in async Quart | Blocking DB calls on the event loop; connection leaked across awaits | Run DB work via thread executor / connection-per-request context as the reference does; never hold a transaction across an `await` on network I/O |
| LiteLLM / providers | Key in logs; no timeout; assuming OpenAI stream shape | Redaction; explicit timeouts; conformance tests per provider |
| Ollama in Docker | `localhost:11434` from inside a container | Service name or `host.docker.internal` with `extra_hosts`; make base URL configurable per tenant model |
| Hugging Face | Unpinned `snapshot_download` at runtime | Pin revision; pre-provision into a volume; `HF_HUB_OFFLINE=1` in tests |
| Nginx | Default buffering/timeouts; `client_max_body_size` default 1 MB rejects uploads | Reference `proxy.conf` settings; body size aligned with app limit |
| NATS (if `ragflow-go` profile adopted) | Building two queue systems half-way | Resolve Redis-Streams-vs-NATS in `DECISIONS.md` first; one queue on the critical path |
| Infinity engine | Assuming ES semantics; x64-v3 CPU requirement | Separate adapter plan with its own integration tests; verify image/CPU compatibility |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Cross-encoder rerank over `topk=1024` on CPU | Chat first token takes tens of seconds | Configurable candidate cap, batch, timeout; remote rerank provider option | Immediately on this host (no GPU) |
| OCR/DLA every page at `zoom=3` | Worker RSS climbs, exit 137 | Only OCR when text layer missing/corrupt (documented branch); page-concurrency cap; free images per stage | PDFs over ~50 pages or parallel sub-tasks |
| Blocking calls on asyncio loop | All SSE streams stall together; heartbeats missed | `thread_pool_exec` for embedding, doc-store, tokenizers (documented) | 2+ concurrent users |
| Embedding one chunk per request | Ingestion dominated by HTTP overhead | Batch (documented 64; reference 16), `embed_limiter` | Any document > 100 chunks |
| Fetching raw vectors from the engine for local rerank | Large responses, slow retrieval | Use engine-side scoring where documented (`rerank_with_knn`); exclude vector fields from `_source` | Result windows in the hundreds |
| N+1 queries building document lists with progress | Slow KB page | Aggregate task progress in SQL; paginate | KBs with hundreds of docs |
| Progress write per chunk | MySQL write storm, lock contention | Throttle progress updates (per batch/stage) | Large documents, multiple workers |
| Per-tenant index proliferation | ES shard count/heap pressure | One shard, zero replicas per tenant index in dev; note as a known scaling limit | Hundreds-thousands of tenants (not a near-term concern) |
| Frontend polling every document's status individually | Request flood | One list endpoint poll with backoff; stop polling when all terminal | KBs with many in-flight docs |
| Unbounded chat history in prompt | Context overflow errors, cost | Token-budgeted context construction (`docs/12-chat/context.md`) | Long conversations |
| React Flow re-rendering whole canvas on each stream event | Canvas jank during runs | Keep run-state out of node data; memoised nodes; selective Zustand selectors | Canvases with dozens of nodes |

## Security Mistakes

All rows grounded in `docs/20-security/` (file noted); risk ranked.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Implementing `RestrictedUnpickler` with module-level `numpy` whitelist as documented (`file-security.md`) | **Critical** — RCE via `numpy.f2py.diagnose.run_command`, confirmed in reference `SECURITY.md` | Avoid pickle on untrusted input; exact-symbol whitelist if needed; PoC regression test |
| Query by ID without tenant scope (`authorization-security.md`, `attack-surface.md`) | **Critical** — cross-tenant data disclosure | Structural tenant scoping + generated cross-tenant test matrix, both stacks |
| `kb_ids`/index name taken from request without ownership check (`multi-tenancy.md`) | **Critical** — cross-tenant retrieval | DocStore adapter requires `tenant_id`; validate `kb_ids` |
| Code-execution node without sandbox, or sandbox-manager with Docker socket exposed to tenants (`file-security.md`) | **Critical** — host compromise | Sandbox constraints as documented (256m, 10s, no-new-privileges, no network); manager reachable only from the app; treat socket mount as a documented risk |
| Plaintext provider keys in `tenant_llm`; unmasked in responses (`secrets.md`, `api-security.md`) | **High** — credential theft, billing abuse | AES-GCM at rest; single masking serializer; canary tests |
| Committing `.env` / `docs/apikey llm.md` (`secrets.md`: "never hardcoded in source repositories") | **High** — leaked credentials in git history | `.gitignore` first; user review; no wholesale `git add docs/` |
| Default infra passwords with published ports (`environment-variables.md`) | **High** on any reachable host | Required env vars; loopback binding |
| Routes missing `@login_required` (`api-security.md`) | **High** — unauthenticated access | Default-deny registration + route enumeration test |
| Literal `_load_user` transcription (`authentication-security.md`) | **Medium** — 500s, no expiry, token-type confusion | Auth contract + negative tests |
| Unsalted SHA-256 for passwords (literal reading of `secrets.md`) | **High** — offline cracking | Password KDF; record decision |
| Upload filename/extension trusted; inline serving (`file-security.md`) | **High** — traversal, stored XSS | UUID keys, magic bytes, attachment disposition, nosniff |
| Parsing untrusted files in the API process (`attack-surface.md`: sandboxed deepdoc) | **Medium-High** — DoS/memory corruption reach | Parse in worker/deepdoc container with limits |
| SSRF via web-page ingestion, Invoke/Browser nodes, model base URLs | **High** — access to MySQL/Redis/MinIO/ES on the compose network | Shared egress guard; block private ranges and service names by default |
| Prompt injection from retrieved content into tool-using agents (`attack-surface.md` lists LLM prompt injection vectors) | **Medium** — data exfiltration via tools | Tool allow-lists per agent; no secrets in prompts; tenant-scoped tools; outbound guard |
| Permissive CORS with credentials (`api-security.md`) | **Medium** | Configured origin allow-list |
| Secrets/PII in logs (`secrets.md`: "never emitted in log files") | **Medium** | Redaction filter + canary log test |
| Shared LLM/response cache keys without tenant namespace (`redis.md` key patterns) | **Medium** — cross-tenant content bleed | Namespace by tenant or restrict cache to tenant-agnostic content |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Document shows a spinner with no stage or error | User cannot tell stuck from slow | Show progress %, current stage message (`progress_msg`), failure reason, and a re-parse/cancel action |
| Upload accepted, parse fails later with no surfaced reason | Silent data loss perception | Persist `progress=-1` + message; show it in the document row |
| Citations that are numbers with no way to inspect | No trust in answers | Hover/click shows chunk text, document name, page; open document at highlighted position |
| Streaming answer jumps/reflows when references resolve at the end | Jarring | Render pending citation markers as placeholders during stream |
| "No answer found" indistinguishable from "retrieval returned nothing" from "LLM error" | Users cannot self-correct | Distinct empty states; retrieval-test page exposing per-chunk similarities |
| Changing embedding model on a populated KB allowed without warning | KB silently unsearchable | Lock + explicit re-embed flow |
| Model not configured -> chat fails with a generic 500 | Dead end on first use | First-run guidance: detect missing default chat/embedding model and link to model settings |
| Masked API key field overwrites the real key on save | Provider breaks after an unrelated edit | "Leave blank to keep" semantics |
| Canvas save succeeds but graph is invalid | Failure only at run time | Validate against DSL schema on save; highlight offending nodes |
| Missing loading/error/empty states (explicit `spec.md` requirement) | App feels broken | Per-page checklist enforced at phase verification |
| Cloning RAGFlow's look (explicitly out of scope) | Violates project rule | Own design system on shadcn/ui; reuse interaction patterns only |

## "Looks Done But Isn't" Checklist

- [ ] **Spec conformance:** phase summary lists `docs/` files read and a conformance table — verify constants in tests, not prose.
- [ ] **Dual stack:** every route has exactly one owner in the Nginx table — verify `X-API-Source` in integration tests.
- [ ] **Auth:** verify unauthenticated call to *every* registered route returns 401 (route enumeration), logout invalidates token, API key cannot call session-only routes.
- [ ] **Tenancy:** cross-tenant matrix covers every ID-bearing route on both stacks, plus vector-level and MinIO download checks.
- [ ] **Upload:** traversal names, wrong-magic files, oversize, zip bomb, and non-PDF types tested; object key contains no user input.
- [ ] **Parsing:** scanned-PDF fixture yields text via OCR; table fixture yields table structure; multi-column fixture reads in order; models load from a provisioned volume with network disabled.
- [ ] **Chunking:** each of the 14 `parser_id`s is either implemented with a fixture or rejected explicitly; no chunk exceeds embedding token limit; `position_int` populated and correct on a >12-page PDF.
- [ ] **Workers:** kill -9 mid-task -> task recovers or fails terminally; re-parse leaves identical chunk count; poison file stops after 3 retries; cancel works; `XPENDING` returns to 0.
- [ ] **Embedding/index:** two dimensions coexist in one tenant index; mapping shows `dense_vector` with correct dims; query uses the KB's model.
- [ ] **Retrieval:** weight 0 vs 1 changes ordering; threshold behaves monotonically; `available_int=0` chunks excluded; labelled fixture recall floor met; rerank not worse than no-rerank.
- [ ] **Chat:** streaming verified **through Nginx** with first frame before last; termination frame sent; error mid-stream produces an in-band error; abort cancels upstream; message persisted once; citation indices valid.
- [ ] **LLM layer:** second provider added without touching callers; bad key yields a clear error; keys encrypted in DB, masked in every response, absent from logs.
- [ ] **Agents/canvas:** every palette node exists in the engine registry and vice versa; loop guard triggers; code node runs only in sandbox; outbound nodes cannot reach `mysql:3306`.
- [ ] **Frontend:** client types generated from OpenAPI; `code != 0` surfaces as error; loading/error/empty states per page; Playwright run of documented end-to-end flows against the real stack.
- [ ] **Compose:** `down -v && up` from documented instructions reaches healthy and passes the smoke test; no `sleep` in entrypoints; works from a path containing a space.
- [ ] **CLI:** commands hit the real API with real auth; not a separate code path with its own logic.
- [ ] **No placeholders:** grep gate clean in production trees; `BLOCKERS.md` lists anything not implemented.
- [ ] **Tests:** no `sleep`; integration suite passes 3 consecutive runs and in parallel mode.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Spec drift discovered late | HIGH | Stop feature work; diff implementation vs conformance tables; write the missing `DECISIONS.md` entries; fix or formally accept each deviation; add the conformance test that would have caught it |
| Route/logic duplicated across stacks | MEDIUM | Choose owner; delete the other; add contract test; move shared constants to a generated file consumed by both |
| Fake found in production path | MEDIUM | Replace with real implementation or move to `BLOCKERS.md`; add behavioural test; audit sibling components for the same pattern |
| Tenant leak found | HIGH | Treat as incident: add failing test first; fix at the service base layer, not the handler; re-run full matrix; audit logs if any real data existed |
| Duplicate/stale chunks in index | MEDIUM | Delete-by-`doc_id` and re-ingest; add idempotency test; fix chunk-ID scheme (requires full reindex) |
| Wrong vector mapping/dimension | MEDIUM | Create corrected mapping; reindex from stored chunks (keep chunk text in the engine or re-run embedding); lock `embd_id` |
| Positions lost in parser | HIGH | Requires parser output type change and re-ingestion of all documents; do it before more chunkers are built on the wrong type |
| Score fusion wrong | LOW | Pure-function fix + golden tests; no reindex needed unless analyser/tokenisation was wrong (then HIGH: reindex) |
| SSE buffered | LOW | Proxy config + headers; add through-proxy test |
| Secret committed | HIGH | Rotate the key first; then history rewrite and force-push with user approval; add gitignore and secret scan |
| Plaintext keys in DB | MEDIUM | Migration to encrypt in place with key versioning; verify both stacks decrypt |
| Flaky suite | MEDIUM | Quarantine; replace sleeps with `wait_until`; per-test tenant isolation; root-cause each flake |
| Disk/RAM exhaustion | LOW-MEDIUM | Prune images/volumes (with user consent — may delete their data); slim images; dev profile limits |
| Canvas DSL mismatch UI/engine | HIGH | Introduce versioned schema; write migration for stored canvases; golden fixtures |
| Scope overrun mid-milestone | MEDIUM | Re-tier requirements; finish the vertical slice; move T3 items to later phases explicitly (not silently dropped) |

## Pitfall-to-Phase Mapping

Phase names are indicative; the roadmap owns final numbering.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Spec drift | **Phase 0: Spec reconciliation & guardrails**; enforced every phase | `DECISIONS.md` has a resolved row for each contradiction; conformance tests pass |
| 2 Dual-stack ownership | Phase 0 (table) -> Backend foundation -> Auth | No duplicate routes; cross-stack token test; `X-API-Source` asserted |
| 3 Scope/ordering | Roadmap creation | A cited answer from an uploaded PDF exists before any breadth phase starts |
| 4 Mocks as done | Phase 0 (gates) -> every phase verification | Grep gate clean; behavioural acceptance tests; `BLOCKERS.md` reviewed |
| 5 Tenant isolation | Auth/tenancy -> each resource phase | Generated cross-tenant matrix green on both stacks; vector-level test |
| 6 Worker reliability | Queue & worker phase | Kill-worker, poison-message, re-parse idempotency, cancel tests |
| 7 Embedding/mapping | Embedding & indexing phase | Two-dimension coexistence test; mapping assertion; model-mismatch error |
| 8 Fusion/rerank | Retrieval phase; Rerank phase | Golden fusion tests incl. swapped-weights; labelled recall fixture |
| 9 Chunking/citations | Parsing -> Chunking -> Chat -> Frontend chat | Round-trip position test on >12-page PDF; split-frame marker tests |
| 10 SSE via proxy | Infrastructure -> Chat -> Frontend chat | Through-Nginx incremental-delivery test; abort test |
| 11 Secrets/LLM keys | Phase 0 (gitignore) -> Infrastructure -> LLM layer | Canary tests on responses and logs; ciphertext in DB; shared test vector Go/Python |
| 12 Heavy ML / host limits | Phase 0 (budget, user action) -> Infrastructure -> Parsing | Preflight passes; image size and cold-start recorded; offline model load test |
| 13 Flaky tests | Phase 0 / test foundation; every phase | No-sleep gate; 3x consecutive green; parallel-mode green |
| 14 Canvas/agent complexity | Agent -> Workflow engine -> Sandbox -> Canvas UI | Golden DSL fixtures run headless; palette/registry parity; sandbox security tests |
| 15 Deserialization/upload | Backend foundation (lint) -> Upload/storage -> Parsing | Pickle PoC regression; upload abuse tests; parser limit tests |
| 16 Auth literal transcription | Auth/tenancy | Route-enumeration 401 test; negative token test set; RBAC enforcement tests |
| 17 Contract drift | Backend foundation -> Frontend foundation -> every capability phase | OpenAPI-generated client; schema-validated responses; Playwright flows |
| 18 Compose ordering/resources | Infrastructure; re-run when services are added | Clean-room `down -v && up` + smoke from documented instructions |
| 19 Provider abstraction | LLM layer | Provider conformance suite; second provider without caller changes |

### Phases most likely to need deeper phase-specific research

- **Document parsing (DeepDoc)**: model provisioning, ONNX vs PyTorch, CPU throughput, licence/availability of `InfiniFlow/deepdoc` weights, coordinate conventions.
- **Doc-engine adapter**: ES version-specific `dense_vector`/kNN/hybrid query behaviour for the pinned `STACK_VERSION` (docs: 8.11.3); Infinity as documented default vs ES as reference default.
- **Go/Python split**: exact ownership, shared auth token format, migration authority, whether Go mirrors of chunkers/parsers are in scope.
- **Sandbox executor**: container-pool manager, seccomp, Docker-socket exposure.
- **Canvas DSL**: exact schema from `docs/14-workflows/` + reference `agent/` for node I/O contracts.
- **Queue**: Redis Streams vs NATS JetStream resolution.

## Sources

**Project specification (`/home/logan78/desktop x/devRag_@/docs/`)** — HIGH confidence as statements of what the spec says:
- `spec.md`; `00-overview/high-level-architecture.md`, `technology-stack.md`
- `20-security/` all seven files (`api-security`, `attack-surface`, `authentication-security`, `authorization-security`, `file-security`, `secrets`, `security-overview`)
- `19-testing/` all six files
- `10-cache-and-queues/` all six files; `08-database/transactions.md`, `migrations.md`
- `06-document-processing/document-processing-workers.md`, `pdf-processing.md`, `ocr.md`, `layout-analysis.md`
- `05-rag-pipeline/chunking.md`, `embedding.md`, `indexing.md`, `hybrid-search.md`, `reranking.md`
- `12-chat/streaming.md`; `16-auth/multi-tenancy.md`; `18-deployment/docker-compose.md`, `environment-variables.md`
- Partial reads: `03-backend/backend-architecture.md`, `18-deployment/production-architecture.md`, `14-workflows/nodes.md` (headings/tables), grep of `18-deployment/networking.md`, `services.md`
- **Not read (off-limits):** `docs/apikey llm.md`

**Reference checkout (`/home/logan78/desktop x/ragflow`, commit `6677f14bd`, 2026-08-12)** — HIGH confidence for the specific lines cited:
- `docker/.env` (`DOC_ENGINE`, `API_PROXY_SCHEME=python`, `MEM_LIMIT`, `EMBEDDING_BATCH_SIZE`, ports)
- `docker/nginx/proxy.conf`, `ragflow.conf.hybrid`, `ragflow.conf.python`, `nginx.conf`
- `docker/entrypoint.sh` (proxy-scheme selection, process layout)
- `rag/svr/task_executor.py` (chunk ID hashing, `@timeout`, cancellation, progress), `api/db/services/task_service.py` (`retry_count >= 3`)
- `rag/utils/redis_conn.py` (`RedisDistributedLock` with token + `delete_if_equal`); `rag/utils/` directory listing (available doc-store adapters)
- `api/db/db_models.py` (`tenant_llm.api_key` as `TextField`)
- `rag/prompts/citation_prompt.md`, `rag/nlp/search.py` (`[ID:i]`, `insert_citations`)
- `deepdoc/vision/ocr.py`, `layout_recognizer.py`, `table_structure_recognizer.py` (runtime `snapshot_download`)
- `SECURITY.md` (numpy pickle bypass); `docs/quickstart.mdx` (`vm.max_map_count`)

**Host measurements (2026-10-05):** `free`, `df`, `nproc`, `sysctl vm.max_map_count`, `nvidia-smi` (absent), Docker 29.1.3 / Compose v5.0.0, Go 1.25.5, Python 3.10.12.

**Not verified in this session (flagged `[DOMAIN]` / "verify"):** Elasticsearch refresh and `dense_vector` dimension-limit behaviour for the pinned version; existence/pullability of the documented image tags; provider-specific batch/context limits; the exact password scheme and streaming delta-vs-cumulative semantics in doc sections not read (`16-auth/authentication.md`, `12-chat/complete-chat-flow.md`, `21-end-to-end-flows/chat-streaming.md`). No external web sources were consulted; general RAG-engineering claims rest on domain knowledge and should be confirmed during phase research. The prior attempt's git history was not inspected; its failure modes are taken from the milestone context.

---
*Pitfalls research for: enterprise multi-tenant RAG platform (devRag) from a reverse-engineered RAGFlow spec*
*Researched: 2026-10-05*
