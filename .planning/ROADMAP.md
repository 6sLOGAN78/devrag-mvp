# Roadmap: devRag

## Overview

devRag implements the complete RAG platform specified in `docs/`: a dual-stack backend (Go Gin for identity, tenant, system, search bots, MCP and CLI; Python Quart for every RAG/ML pipeline), a React SPA, and MySQL / Valkey / MinIO / Elasticsearch persistence. The roadmap first reconciles the contradictions in the docs into a committed decision register and installs guardrails alongside the infrastructure and the two-server skeleton. It then drives one thin, entirely real vertical slice (identity, model config and upload, ingestion, retrieval and chat) to the Core Value: a user uploads a document and gets a streamed, cited answer with no mocked stage. Only after that gate does it widen: deep parsing and the remaining chunkers, agents and workflows, and finally the Go surface, CLI, integrations, metered billing and production deployment.

Every phase ships its API and its UI together and is verified against the real running stack through Nginx. Security controls, tenant-isolation tests and contract tests land with the feature they cover, never as a closing phase.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Reconciliation, Guardrails and Dual-Stack Foundation** - Decision register and CI guardrails committed; infrastructure, shared schema and both API servers healthy behind Nginx (completed 2026-10-06)
- [ ] **Phase 2: Identity, Tenancy and Authorization** - Users register and log in through Go, the same token works on Python, tenants are isolated and roles enforced
- [ ] **Phase 3: Models, Knowledge Bases and Upload** - Tenants configure a real model provider, create datasets backed by a real index, and upload documents to object storage
- [ ] **Phase 4: Ingestion Pipeline** - Uploaded documents are parsed, chunked, embedded and indexed by a reliable background worker with live progress
- [ ] **Phase 5: Retrieval and Cited Chat (Core Value Gate)** - A question about an uploaded document yields a streamed, cited answer in the UI with no mocked stage
- [ ] **Phase 6: Deep Parsing and Chunking Breadth** - Layout analysis, OCR, table recognition, every documented file type and chunker, LLM enrichment and RAPTOR
- [ ] **Phase 7: Agents and Workflows** - Users build, run and debug agent workflows on a canvas, with tools, sandboxed code and webhook triggers
- [ ] **Phase 8: Go Surface, CLI, Integrations, Billing and Production Deployment** - CLI, admin, search bots, MCP server, channels, connectors, metered billing, Infinity engine and the production image

## Phase Details

### Phase 1: Reconciliation, Guardrails and Dual-Stack Foundation

**Goal**: Every load-bearing doc contradiction is resolved in a decision register committed to the repo, guardrails against fakes and drift are enforced in CI, and a developer can bring up the infrastructure with both API servers answering through one ingress on one shared schema
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: DEPLOY-02..04, DEPLOY-11..16, DATA-01..06, DATA-08, API-01..13, SYS-01..07, UI-01, UI-03, SEC-04..05, SEC-10, TEST-01..04, TEST-10
**Success Criteria** (what must be TRUE):

  1. `.planning/DECISIONS.md` is committed and records a resolution and status for every row of the research register (R-01..R-52), including the three user-confirmed decisions (Go builds only its own routes; billing in v1; Elasticsearch default plus Infinity); `.planning/BLOCKERS.md` exists; `.gitignore` excludes `docs/apikey llm.md` and `.env*`; the CI gates fail a build that introduces a placeholder/fake in a production tree or a pickle load on untrusted data
  2. From a clean checkout, a preflight script reports host readiness (free disk, `vm.max_map_count`, RAM) with an actionable message for each failure, and `docker compose down -v && docker compose up` brings MySQL, Valkey, MinIO and Elasticsearch to healthy inside the recorded dev memory budget
  3. The schema is created from an empty database by a single migration owner, and the Go server's `--migrate` verification passes against that same schema
  4. Through Nginx, `GET /health` and `GET /api/v1/system/ping` are answered by Go with `X-API-Source: go`, `GET /system/healthz` is answered by Python, `GET /api/v1/language` names the answering engine, `GET /system/status` reports the live state of database, Redis, storage and docstore, and every response (including an unhandled error) uses the one decided envelope
  5. The SPA shell loads through Nginx with lazy routes and its HTTP client surfaces a non-zero envelope code as an error notification; the pytest, `go test` (with build-tag tiers) and frontend component harnesses all run green against the live stack

**Plans**: 24 plans (15 delivered + 9 gap-closure)
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Decision register (R-01..R-73), BLOCKERS.md, ignore rules, completeness gate

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Package legitimacy checkpoint, Python 3.13 toolchain, run_tests.py, wait helper

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — CI guardrails: placeholder, pickle, no-sleep, secrets gates; make ci
- [x] 01-04-PLAN.md — Compose base (MySQL, Valkey, MinIO, ES), env catalog, preflight, wait_stack
- [x] 01-05-PLAN.md — routes.yaml, generated Nginx config and Vite proxy, SSE-safe proxy, TLS check

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-06-PLAN.md — Config, redacting logging, retrying pool, transactions, DB lock, migration runner, first real DB write
- [x] 01-10-PLAN.md — SPA scaffold, HTTP client (envelope, token, toast, 401 purge), vitest unit and live projects

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-07-PLAN.md — 38-table Peewee schema, baseline migration, schema.json export
- [x] 01-08-PLAN.md — Quart server: envelope, errors, CORS, probes, OpenAPI, boot sequence
- [x] 01-09-PLAN.md — Go Gin server: envelope, system routes, run modes, Go test tiers

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-11-PLAN.md — Generated GORM entities, verify-only --migrate, Go transactions
- [x] 01-12-PLAN.md — SPA shell: lazy routes, layouts, System status page, generated API types

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 01-13-PLAN.md — App image, init job, app compose, healthcheck, bind-mounted logs

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 01-14-PLAN.md — Live ingress, ownership, envelope, outage and TLS tests

**Wave 9** *(blocked on Wave 8 completion)*

- [x] 01-15-PLAN.md — Clean-room exit gate x3, memory budget, browser check, final records

**Gap closure (from 01-VERIFICATION.md and 01-REVIEW.md)** *(Wave 1 plans are independent)*

- [x] 01-16-PLAN.md — DATA-03: restore real pooling, bounded reconnect, write-safe retry (CR-01, WR-01, WR-02)
- [x] 01-17-PLAN.md — Log redaction parity in Go and Python with shared vectors (WR-03, WR-04)
- [ ] 01-18-PLAN.md — HTTP client: same-origin token, token-aware 401 purge (WR-21, WR-22)
- [ ] 01-20-PLAN.md — Guard scripts: clean_room --runs validation, foreign-project refusal, run_tests exit 5, go-race -count=1 (WR-15, WR-16, WR-17)
- [ ] 01-21-PLAN.md — Container: TLS fail-closed, log dir ownership, direct healthchecks, pinned Go port (WR-11..WR-14)
- [ ] 01-22-PLAN.md — Python: 4xx envelope codes, migration runner db binding, startup hooks on serving loop (WR-07, WR-08, WR-09)
- [ ] 01-23-PLAN.md — render_conf escaping and CI workflow setup (WR-18, WR-19)

**Gap closure Wave 2** *(blocked on 01-16: shares DECISIONS.md)*

- [ ] 01-19-PLAN.md — Mark /system/version public_until_phase and enforce the marker rule (WR-05)

**Gap closure Wave 3**

- [ ] 01-24-PLAN.md — Re-run exit gate x3, deferred findings, truthful records

**UI hint**: yes

Scope notes: merges research stages 0 and 1. The decision register has no REQ-ID of its own; it is mandated by the PROJECT.md "Documentation" constraint and is a hard exit criterion for this phase. Host blockers marked "user action" in STATE.md must be cleared before criterion 2 can pass. Docs to read first: `docs/spec.md`, `00-overview`, `03-backend`, `08-database`, `18-deployment`, `04-api/api-overview.md`, `04-api/endpoint-catalog.md`.

### Phase 2: Identity, Tenancy and Authorization

**Goal**: Users can create an account and securely access their own workspace through either server, and no user can see or change another tenant's data
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: AUTH-01..23, TEN-01..02, TEN-04..11, UI-02, UI-04, UI-06..09, UI-34..36, UI-42..43, SEC-01, SEC-09, E2E-01..02
**Success Criteria** (what must be TRUE):

  1. A user can register in the SPA and is given a tenant with an owner link in one atomic step, then log in and land on the home dashboard; refreshing the browser keeps them signed in, and visiting a protected route while signed out redirects to login
  2. The token issued by Go at login is accepted by a protected Python route; after logout the same token returns HTTP 401 on both servers; every non-public route on both servers returns 401 without credentials (verified by enumerating the route tables)
  3. A user can change their password, reset a forgotten password with an OTP, and create, list and delete API tokens from the settings pages; a request authenticated only by an API token resolves to the owning tenant
  4. An owner can invite a member, the member can accept, and the owner can change the member's role; actions outside the documented permission matrix return HTTP 403
  5. Requesting another tenant's resource by id is indistinguishable from not-found on every tenant-owned route that exists so far, verified by a cross-tenant test matrix generated from the route table

**Plans**: TBD
**UI hint**: yes

Scope notes: the cross-language token and password-hash contract (R-33, R-34) needs phase research and shared test vectors. The cross-tenant matrix from criterion 5 is extended as an exit criterion by every later phase that adds a resource. Docs to read first: `16-auth`, `20-security`, `04-api` user/tenant files, `21-end-to-end-flows/user-registration.md`, `login.md`.

### Phase 3: Models, Knowledge Bases and Upload

**Goal**: A tenant can connect a real model provider, create a knowledge base whose index is provisioned with the right vector dimension, and upload documents into it
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: LLM-01..05, LLM-14..29, KB-01..09, TEN-12..13, TEN-16, STOR-01..02, STOR-06, STOR-08, STOR-10..11, DOC-01..08, DOC-14..16, IDX-04..06, IDX-08..09, UI-10..12, UI-37, SEC-02..03, SEC-06, TEST-08, E2E-03..04
**Success Criteria** (what must be TRUE):

  1. An owner can add provider credentials and set the tenant's default chat and embedding models in the settings UI; the key is masked in every API response and encrypted in MySQL; a real chat call and a real embedding call succeed for that tenant against the chosen provider (user-supplied key or local Ollama), with token usage recorded
  2. A user can create a dataset from the datasets gallery; creation rejects a duplicate name and an embedding model the tenant does not have, and a real Elasticsearch index exists afterwards with a `q_{dim}_vec` field matching the model's dimension and HNSW/cosine settings; the dataset can be listed, viewed, updated and deleted, and a second member of the tenant sees it
  3. A user can drag and drop one or more files into a dataset; each blob is stored in MinIO under a generated key and the document appears in the list in the not-started state at 0 progress; uploading the same content twice reuses the stored blob
  4. Upload rejects a disallowed extension with HTTP 400, an oversized file, a path-traversal filename, and a dataset the caller cannot access; nothing is stored in any of these cases
  5. Deleting a document removes its rows, and the blob is garbage-collected only when no other document still references it

**Plans**: TBD
**UI hint**: yes

Scope notes: the `DocStoreConnection` port and the Elasticsearch adapter are pulled forward from research stage 4 so that dataset creation (KB-03, E2E-03) is verified against a real index; the port's `search` signature must be defined here so Phase 5 does not reshape it. A real model source (R-50) must be chosen before this phase is planned. Docs to read first: `11-llm`, `09-storage`, `06-document-processing/upload.md`, `05-rag-pipeline/indexing.md`, `17-integrations`, `21-end-to-end-flows/create-knowledge-base.md`, `upload-document.md`.

### Phase 4: Ingestion Pipeline

**Goal**: A user can start parsing an uploaded document and watch it become searchable chunks, produced by a background worker that survives crashes, retries and cancellation
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: ING-01..16, PARSE-01..03, PARSE-09..13, CHUNK-01..02, CHUNK-16..21, IDX-01..03, IDX-07, IDX-14, DOC-09..13, DOC-20..23, KB-14..16, KB-19, UI-13..17, UI-19, DEPLOY-17, TEST-11, E2E-05..06
**Success Criteria** (what must be TRUE):

  1. A user can click Parse on a text-layer PDF longer than 12 pages and watch its status move from not-started through running with a live progress bar to finished; the document is split into page-range tasks, and its chunks are embedded with the dataset's real embedding model and present in Elasticsearch with dataset chunk and token totals updated
  2. The chunk inspector shows each chunk beside the original document with its bounding box on the correct page; a user can edit a chunk's text, add a manual chunk and disable a chunk, and each change is reflected in the index
  3. DOCX, XLSX, PPTX, HTML and TXT files parse to chunks with the `naive` chunker using the dataset's token size and delimiter; selecting a chunker that is not yet implemented is rejected explicitly rather than silently falling back
  4. Killing the worker mid-task leads to the task being reclaimed and completed with no duplicate chunks; a poison file fails terminally after the retry cap with its error visible in the UI; re-parsing a document leaves an identical chunk count; cancelling a running parse stops the worker and marks the document cancelled
  5. The task executor runs as its own container, a second executor can be added without configuration changes, and deleting a document or dataset removes its chunks from the index

**Plans**: TBD
**UI hint**: yes

Scope notes: thin by design: one engine, one embedding provider, one chunker, text-layer PDFs. Layout analysis, OCR and the other chunkers wait for Phase 6. One `ParsedBlock` and one `Chunk` type are defined before a second parser is written. Chunk ID construction (R-11) and the tightened Redis lock (R-12) need phase research. Docs to read first: `05-rag-pipeline`, `06-document-processing`, `10-cache-and-queues`, `21-end-to-end-flows/document-processing.md`, `indexing.md`.

### Phase 5: Retrieval and Cited Chat (Core Value Gate)

**Goal**: A user can ask a question about an uploaded document and receive an accurate, streamed, cited answer through the real pipeline (hybrid retrieve, rerank, generate) with no mocked stage
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: RETR-01..19, RETR-23, CHAT-01..23, CHAT-31, LLM-09, ING-21, TEN-03, KB-18, UI-05, UI-18, UI-20..25, DEPLOY-18, E2E-07..09, E2E-12
**Success Criteria** (what must be TRUE):

  1. On the retrieval-testing page a user enters a query against a dataset and sees ranked hits with term, vector and overall similarity; raising the similarity threshold drops hits and moving the vector/keyword weight changes the ranking; golden fusion tests fail if the documented weights are swapped
  2. A user can create an assistant bound to datasets, open a session, send a question and watch the answer stream token by token through Nginx (the first frame arrives before the last), stop generation mid-stream, and find the full turn with its references still there after a refresh
  3. The answer carries citation markers; clicking a citation opens a drawer with the chunk text and the highlighted region of the source PDF, and the cited chunk actually contains the stated fact; when retrieval finds nothing the assistant replies with its configured empty response
  4. Retrieval with a real rerank model reorders candidates, and retrieval that names another tenant's dataset ids returns nothing from that tenant's index
  5. One automated browser run against the real stack goes from registration through dataset creation, upload, parse and question to a cited streamed answer, using a real embedding model and a real chat model with no fake in any production path

**Plans**: TBD
**UI hint**: yes

Scope notes: this is the PROJECT.md Core Value. No Phase 6, 7 or 8 work starts until criterion 5 passes. SSE framing (R-26) and citation marker (R-27) are fixed in the decision register before planning; the CPU rerank candidate cap (R-52) is timed and recorded here. Docs to read first: `07-retrieval`, `12-chat` (including `complete-chat-flow.md`), `11-llm` rerank, `21-end-to-end-flows/ask-question.md`, `rag-answer.md`, `chat-streaming.md`, `ragflow-one-request.md`.

### Phase 6: Deep Parsing and Chunking Breadth

**Goal**: Users can ingest every documented file type with layout-aware parsing and choose any documented chunking strategy and enrichment, and answers cite the richer content correctly
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: PARSE-04..08, PARSE-14..26, CHUNK-03..15, CHUNK-22..28, LLM-10..11, LLM-13, LLM-32, STOR-09, DOC-17..19, KB-10..13, KB-17, ING-18, DEPLOY-08, SEC-08
**Success Criteria** (what must be TRUE):

  1. A scanned PDF with no text layer is parsed into chunks through OCR; a PDF with tables yields HTML table chunks; page headers and footers are absent from chunk text; chunks follow reading order with positions that highlight the right region in the chunk inspector
  2. Each of the documented chunking methods (`naive`, `paper`, `book`, `laws`, `presentation`, `table`, `qa`, `resume`, `picture`, `manual`, `email`, `tag`, `one`, `audio`) produces the documented chunk boundaries on its own fixture file when selected in the chunking-method dialog
  3. Markdown, JSON, EPUB, CSV, image, audio and `.eml` files each parse to chunks; embedded figures are extracted, deduplicated, captioned by a real vision model and retrievable through the image endpoint
  4. With enrichment enabled on a dataset, chunks carry LLM-generated keywords, questions, tags and metadata that are visible through the tag and metadata endpoints, and RAPTOR summary chunks are indexed and returned by retrieval
  5. Starting the `deepdoc` compose profile and setting `DEEPDOC_URL` moves layout, OCR and table recognition out of the worker process, and a parse still completes end to end

**Plans**: TBD

Scope notes: highest research risk in the project (DeepDoc ONNX model acquisition, licence, CPU throughput, coordinate conventions); needs `--research-phase`. Models are provisioned in a build/init step, never downloaded at first parse. PARSE-26 and CHUNK-28 are satisfied by their Python implementations per the user decision; the Go mirrors are v2. Docs to read first: `06-document-processing` (all parser, OCR, layout, chunking files), `05-rag-pipeline`, `20-security/file-security.md`.

### Phase 7: Agents and Workflows

**Goal**: Users can build an agent workflow on a canvas, run it and watch each node execute, give agents tools and sandboxed code, and trigger runs from outside
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: FLOW-01..37, AGT-01..39, MCP-03, LLM-33, RETR-21, UI-27..32, DEPLOY-07, SEC-07, TEST-06..07, TEST-09, E2E-10..11
**Success Criteria** (what must be TRUE):

  1. A user can create an agent from the agents list, drag Begin, Retrieval, LLM and Message nodes onto the canvas, connect and configure them, save, run, and watch node-started / node-finished events animate the graph while a cited answer streams; a DSL with a cycle or an unknown component is rejected before it runs
  2. An agent node with tools bound (knowledge-base retrieval plus at least one real external tool or MCP server) completes a multi-round tool-calling loop within `max_rounds` and returns a final answer; a supervising agent can call another agent as a tool
  3. Branching and iteration work as documented: Switch and Categorize forward control only along the matched branch, Loop and Iteration stop at their guard, parallel branches both execute, and a Fillup node pauses the run, waits for user input and resumes from its checkpoint
  4. A Code node runs LLM- or user-written Python in the sandbox and returns its output, while code that tries to reach the network, exceed the memory cap or outlive the timeout is stopped; the sandbox security tests pass against the running `sandbox` profile
  5. A webhook call triggers a run against an immutable snapshot of the canvas, and the run's trace, per-node timings, inputs and outputs are persisted and viewable afterwards in the run log, version list and session history

**Plans**: TBD
**UI hint**: yes

Scope notes: the DSL schema with golden fixtures and a headless `Graph` engine come before any canvas UI. Nodes land in tiers (Begin/LLM/Retrieval/Message, then Switch/Categorize/variables, then Loop/Iteration, then tools/Invoke/AgentWithTools, then sandboxed Code, then Fillup/Browser/generators). The Code node is never a host `exec`: if the sandbox cannot be completed it is a recorded blocker. AGT-39 and FLOW-37 are satisfied by the Python engine; the Go Eino mirror is v2. External tools that need third-party keys are verified where a key exists and listed in `BLOCKERS.md` otherwise. Docs to read first: `13-agents`, `14-workflows`, `20-security` sandbox files, `21-end-to-end-flows/agent-execution.md`, `workflow-execution.md`.

### Phase 8: Go Surface, CLI, Integrations, Billing and Production Deployment

**Goal**: The whole documented surface is reachable: operators drive the system from the CLI and admin console, external clients use search bots, MCP, channels and metered API keys, the second doc engine works, and the stack deploys from a clean machine using the documented instructions
**Mode:** mvp
**Depends on**: Phase 6, Phase 7
**Requirements**: CLI-01..18, ADMIN-01..07, SRCH-01..07, MCP-01..02, BILL-01..10, CONN-01..06, CHAN-01..12, TMPL-01..04, AUTH-24..25, TEN-14..15, DOC-24, STOR-03..05, STOR-07, ING-17, ING-19..20, IDX-10, IDX-15, RETR-20, RETR-22, LLM-06..08, LLM-12, LLM-30..31, LLM-34..35, CHAT-24..30, SYS-09, API-14, UI-26, UI-33, UI-38..41, UI-44, DATA-07, DEPLOY-01, DEPLOY-06, DEPLOY-09..10, DEPLOY-19..21, SEC-11, TEST-05, TEST-12
**Success Criteria** (what must be TRUE):

  1. Using the CLI binary against the running stack, a user can log in, create a dataset, import and parse a file, list its chunks and run `SEARCH ... ON DATASETS`, in REPL and single-command modes with `table`, `plain` and `json` output; in admin mode an admin can list services and users and ping dependencies
  2. With only a beta token, an external client gets an answer from the search-bot ask endpoint, a cited answer from the public chatbot endpoint and the shared chat page, and can call dataset search as a tool through the MCP server; the OpenAI-compatible completions endpoint answers a standard client
  3. A metered API key is shown once and stored only as a hash; exceeding its rate limit returns HTTP 429; calls deduct from a prepaid credit ledger and return HTTP 402 at zero; a verified Stripe test-mode webhook credits the account exactly once; the usage dashboard shows the resulting events
  4. Switching the compose profile to Infinity and re-running the upload-to-cited-answer flow passes unchanged; a user can manage search apps, chat channels, connectors, compilation templates and files in the UI, every data view shows loading, error and empty states, and a channel bot starts and stops from its database row without a server restart
  5. On a clean machine the documented setup instructions build the production image and bring up the full stack; all twelve documented end-to-end flows pass against it; `BLOCKERS.md` lists everything that could not be verified on this host (for example the `gpu` profile, channels and OAuth providers that need third-party credentials)

**Plans**: TBD
**UI hint**: yes

Scope notes: the largest phase (117 requirements across about ten independent subsystems); expect it to decompose into many parallel plans, one per subsystem. How Go search bots and MCP obtain retrieval without calling Python over HTTP (R-04) must be settled by phase research. Billing (BILL-01..10) is a new subsystem specified only by `docs/apis.md` from about line 140 and needs its own research; Stripe verification needs a user-supplied test-mode key. Mirror rows (ING-19, IDX-15, LLM-35, ADMIN-01 Go half) are satisfied by their Python implementations. UI-44 is applied view by view in every earlier phase; this phase is where it is audited across all views. Docs to read first: `15-cli`, `17-integrations`, `18-deployment`, `04-api` (search, bot, connector, MCP, plugin, langfuse, stats, system files), `docs/apis.md`.

## Coverage

543 of 543 v1 requirements mapped, each to exactly one phase (verified by script: ranges expanded and diffed against the IDs in REQUIREMENTS.md; 0 orphans, 0 duplicates, 0 unknown IDs).

| Phase | Requirements |
|-------|--------------|
| 1 | 46 |
| 2 | 48 |
| 3 | 65 |
| 4 | 60 |
| 5 | 61 |
| 6 | 54 |
| 7 | 92 |
| 8 | 117 |

**Scope update (2026-10-05):** IDX-11, IDX-12, IDX-13, DEPLOY-05 and SYS-08 were moved to v2, following the user decision that only Elasticsearch and Infinity are v1 doc stores. **Open scope question for the user:** ING-20 (NATS JetStream queue) and DEPLOY-09 (`ragflow-go` profile with NATS) remain in Phase 8; confirm or move to v2 before Phase 8 is planned.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Phases 6 and 7 both depend only on Phase 5 and may run in either order.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Reconciliation, Guardrails and Dual-Stack Foundation | 0/TBD | Not started | - |
| 2. Identity, Tenancy and Authorization | 0/TBD | Not started | - |
| 3. Models, Knowledge Bases and Upload | 0/TBD | Not started | - |
| 4. Ingestion Pipeline | 0/TBD | Not started | - |
| 5. Retrieval and Cited Chat (Core Value Gate) | 0/TBD | Not started | - |
| 6. Deep Parsing and Chunking Breadth | 0/TBD | Not started | - |
| 7. Agents and Workflows | 0/TBD | Not started | - |
| 8. Go Surface, CLI, Integrations, Billing and Production Deployment | 0/TBD | Not started | - |
