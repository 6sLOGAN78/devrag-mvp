# Feature Research

**Domain:** Enterprise RAG platform (devRag) — complete implementation of the system specified in `docs/` (reverse-engineered RAGFlow specification)
**Researched:** 2026-10-05
**Confidence:** HIGH for "what the docs say" (every row is cited to a doc file that was read in full); MEDIUM for exact endpoint verbs/paths (the docs contradict themselves — see "Ambiguities & Contradictions")

---

## How To Read This File

**Classification used for this project (per orchestrator):**

- **Table stakes** = explicitly documented in `docs/`. All are v1. The goal is the complete documented system, not an MVP.
- **Differentiators** = common in RAG products or present in the RAGFlow repo, but NOT described in `docs/`. Candidates to defer.
- **Anti-features** = things `docs/spec.md` forbids.

**ID scheme:** `CATEGORY-NN`. IDs are stable and meant to be lifted directly into REQUIREMENTS.md.

**Complexity (Cx):** `S` = under half a day, `M` = 1-2 days, `L` = 3-5 days, `XL` = a week or more and/or research-heavy.

**Flags in the Notes column:**

- `[P]` = mentioned only in passing (a name in a list, a diagram box, or a file listing) with no behavioural description. Scope must be confirmed or derived from the RAGFlow reference.
- `[C-n]` = the docs contradict themselves; `n` refers to the numbered entry in "Ambiguities & Contradictions".
- `[DUAL]` = docs describe both a Python and a Go implementation of the same capability.

**Source paths** are relative to `docs/`.

### Coverage Map (quality gate: every docs section 02-21 represented)

| Docs section | Represented by | Notes |
|---|---|---|
| `00-overview` | all categories (architecture context); DEPLOY, API | Non-feature narrative plus stack inventory |
| `01-*` | n/a | Section does not exist in `docs/` |
| `02-frontend` | UI | |
| `03-backend` | API, AUTH, TEN, ING | |
| `04-api` + `apis.md` | API, AUTH, TEN, KB, DOC, CHUNK, CHAT, AGT, SRCH, MCP, CONN, CHAN, TMPL, SYS, LLM | |
| `05-rag-pipeline` | PARSE, CHUNK, IDX, RETR, CHAT | |
| `06-document-processing` | DOC, PARSE, CHUNK, STOR, ING | |
| `07-retrieval` | RETR | |
| `08-database` | DATA | |
| `09-storage` | STOR | |
| `10-cache-and-queues` | ING | |
| `11-llm` | LLM | |
| `12-chat` | CHAT | |
| `13-agents` | AGT | |
| `14-workflows` | FLOW | |
| `15-cli` | CLI, ADMIN | |
| `16-auth` | AUTH, TEN | |
| `17-integrations` | CHAN, LLM, STOR, IDX, RETR, MCP | |
| `18-deployment` | DEPLOY | |
| `19-testing` | TEST | |
| `20-security` | SEC | |
| `21-end-to-end-flows` | E2E (acceptance flows) | |
| `22-code-tracing` | non-feature | Call-chain restatements of 05/12/13/14; no new capabilities |
| `23-diagrams` | non-feature | Mermaid sources of diagrams already covered |
| `24-learning` | non-feature | Reading guides |
| `99-glossary` | non-feature | Used only as evidence for contradictions C-2, C-3, C-4, C-6 |
| `apis.md` lines 1-139 | API | Endpoint catalog and Go/Python routing split |
| `apis.md` lines 140-2080 | NEEDS DECISION (BILL) | Pasted Q&A about a metered API-key billing platform; see "Needs User Decision" |
| `apikey llm.md` | NOT READ | Off-limits pending user review; contents not reflected here |

---

## Feature Landscape

### Table Stakes (Documented in `docs/` — must build, all v1)

#### AUTH — Authentication, sessions, tokens, API keys

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| AUTH-01 | User can register with email, password, nickname via `POST /api/v1/users`; email format, nickname, and email uniqueness are validated | M | `04-api/authentication-api.md`, `21-end-to-end-flows/user-registration.md` | Go-owned route `[C-5]` |
| AUTH-02 | Passwords are stored only as salted hashes and verified on login | S | `03-backend/authentication.md`, `21-.../user-registration.md` | Algorithm named inconsistently `[C-10]` |
| AUTH-03 | Registration atomically provisions a `tenant` row and a `user_tenant` link with `role='owner'`; failure rolls back all three inserts | M | `21-.../user-registration.md`, `04-api/user-api.md` | Rollback inferred from handler name `rollback_user_registration` |
| AUTH-04 | Registration initializes the tenant's default model configuration (`tenant_llm`) | M | `21-.../user-registration.md`, `04-api/user-api.md` | `[P]` — "configure default system models" with no detail |
| AUTH-05 | User can log in with email and password via `POST /api/v1/auth/login` and receives `access_token` plus user object; only users with valid status may log in | M | `04-api/authentication-api.md`, `04-api/api-call-flow.md`, `21-.../login.md` | |
| AUTH-06 | Login resolves the user's tenant id, role, and tenant default models (chat, embedding, rerank) | M | `21-.../login.md` | |
| AUTH-07 | Protected routes on both servers accept `Authorization: Bearer <token>` and populate request user context (`g.user` / `c.Set("user")`) | L | `16-auth/authentication.md`, `03-backend/middleware.md` | `[DUAL]`; token format `[C-11]` |
| AUTH-08 | Token validation rejects empty/whitespace tokens, tokens shorter than 32 chars, and tokens beginning `INVALID_` | S | `16-auth/tokens.md` | |
| AUTH-09 | User can log out; logout rewrites `user.access_token` to `INVALID_<hex>` so the old token returns 401 thereafter | S | `16-auth/tokens.md`, `16-auth/sessions.md`, `03-backend/authentication.md` | No logout endpoint path is documented `[C-13]` |
| AUTH-10 | Requests without an `Authorization` header fall back to a Redis-backed server session cookie (`_user_id`) | M | `16-auth/sessions.md`, `03-backend/authentication.md` | |
| AUTH-11 | Login sets a signed `ragflow_auth` cookie | S | `21-.../login.md`, `99-glossary/important-terms.md` | Conflicts with localStorage-only token model `[C-12]` |
| AUTH-12 | Auth resolution order is beta token, then JWT, then API token, then session cookie; no match returns HTTP 401 | M | `16-auth/authentication.md`, `20-security/authentication-security.md` | Per-route `auth_types` allow-list |
| AUTH-13 | User can fetch own profile, avatar, tenant id and role via `GET /v1/user/info` | S | `04-api/endpoint-catalog.md`, `apis.md` | |
| AUTH-14 | User can update nickname, avatar, and language via `POST /v1/user/setting` | S | `04-api/endpoint-catalog.md` | |
| AUTH-15 | User can change password by supplying old and new password via `POST /v1/user/setting/password` | S | `04-api/endpoint-catalog.md` | |
| AUTH-16 | User can request a password-reset OTP via `POST /api/v1/auth/password/forgot/otp` | M | `04-api/endpoint-catalog.md`, `apis.md` | Delivery channel (email/SMTP) not documented |
| AUTH-17 | User can verify the OTP via `POST /api/v1/auth/password/forgot/otp/verify` | S | `04-api/authentication-api.md` | `[P]` — absent from the master catalog |
| AUTH-18 | User can reset password with email, OTP, and new password via `POST /api/v1/auth/password/reset` | S | `04-api/endpoint-catalog.md` | |
| AUTH-19 | User can create a programmatic API token via `POST /system/tokens` | M | `04-api/system-api.md`, `16-auth/tokens.md` | `APIToken` table: tenant_id, token, beta, dialog_id |
| AUTH-20 | User can list API tokens via `GET /system/tokens` | S | `04-api/system-api.md` | |
| AUTH-21 | User can delete an API token via `DELETE /system/tokens/<token>` | S | `04-api/system-api.md` | |
| AUTH-22 | API clients can authenticate with an API token (`AUTH_API`) which resolves to the owning tenant | M | `16-auth/authentication.md`, `20-security/authentication-security.md` | Key format `ragflow-xxxx...` |
| AUTH-23 | Public bot, search-bot, and MCP routes authenticate with a beta token (`AUTH_BETA`, `BetaAuthMiddleware`) | M | `16-auth/tokens.md`, `03-backend/api-layer.md` | |
| AUTH-24 | User can log in through third-party OAuth2 / OIDC (GitHub, Google, enterprise OIDC) | L | `02-frontend/authentication.md`, `16-auth/authentication.md`, `21-.../login.md` | `[P]` — named in three docs, no endpoints, callbacks, or config documented |
| AUTH-25 | Captcha generation for auth forms | S | `04-api/authentication-api.md` | `[P]` — one phrase, no endpoint |

#### TEN — Multi-tenancy, roles, permissions

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| TEN-01 | Every tenant-owned entity (dataset, document, task, dialog, canvas, file) carries `tenant_id` and every service/DAO query filters by the caller's tenant | L | `16-auth/authorization.md`, `16-auth/multi-tenancy.md`, `20-security/authorization-security.md` | `[DUAL]` Peewee services and GORM DAOs |
| TEN-02 | Requesting another tenant's resource by id is denied (not found / permission error), never returned | M | `20-security/authorization-security.md` | Needs a dedicated isolation test suite |
| TEN-03 | Docstore queries and index names are tenant-scoped so vector search cannot leak across tenants | M | `16-auth/multi-tenancy.md`, `05-rag-pipeline/indexing.md` | Index naming `[C-3]` |
| TEN-04 | Users hold one of three roles per tenant (`owner`, `admin`, `normal`) stored in `user_tenant.role` | S | `16-auth/roles.md` | |
| TEN-05 | The documented permission matrix (10 functional areas by `owner`/`admin`/`normal`/beta token/API token) is enforced; disallowed actions return HTTP 403 | L | `16-auth/permissions.md`, `16-auth/authorization.md` | Invite rights contradict `[C-22]` |
| TEN-06 | User can retrieve tenant/workspace settings via `GET /v1/user/tenant_info` | S | `04-api/endpoint-catalog.md`, `apis.md` | "plan details" mentioned `[P]` |
| TEN-07 | User can list tenants they can access via `GET /v1/tenant/list` | S | `04-api/endpoint-catalog.md` | |
| TEN-08 | User can list members of a tenant via `GET /tenants/<tenant_id>/users` | S | `04-api/tenant-api.md` | |
| TEN-09 | Owner can invite/add a member via `POST /tenants/<tenant_id>/users` | M | `04-api/tenant-api.md`, `16-auth/permissions.md` | Handler names scrambled `[C-13]` |
| TEN-10 | Invited user can accept membership via `PATCH /tenants/<tenant_id>` | S | `04-api/tenant-api.md` | Semantics inferred from handler `agree` `[C-13]` |
| TEN-11 | Owner can change a member's role | S | `16-auth/permissions.md` | `[P]` — matrix row only, no endpoint |
| TEN-12 | Admin/owner can set the tenant's default chat and embedding models | S | `15-cli/commands.md` (`SET DEFAULT LLM`, `POST /v1/user/set_tenant_info`), `16-auth/multi-tenancy.md` | |
| TEN-13 | Multiple users can share one tenant's datasets, documents, models, and agent workflows | M | `16-auth/multi-tenancy.md` | |
| TEN-14 | Custom RBAC: admin can `CREATE ROLE`, `GRANT <permission> ON <resource> TO ROLE`, `REVOKE ... FROM ROLE` | L | `15-cli/commands.md`, `20-security/authorization-security.md` | `[P]` — CLI syntax only; no tables or API. `REVOKE` appears only in the security doc |
| TEN-15 | Invitation codes (`InvitationCode` entity) | S | `08-database/entities.md` | `[P]` — entity name only |
| TEN-16 | Dataset-level `permission` field on create | S | `21-.../create-knowledge-base.md` | `[P]` — parameter in a sequence diagram only |

#### KB — Knowledge bases (datasets)

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| KB-01 | User can create a dataset with `name`, `parser_id`, `embd_id` via `POST /api/v1/datasets`; duplicate name within the tenant is rejected | M | `04-api/endpoint-catalog.md`, `21-.../create-knowledge-base.md` | Path variants `[C-5]` |
| KB-02 | Creating a dataset validates the embedding model against tenant models and resolves its vector dimension | M | `21-.../create-knowledge-base.md` | |
| KB-03 | Creating a dataset provisions the docstore index with the matching dense-vector schema and analyzers | M | `21-.../create-knowledge-base.md` | Index-per-KB vs per-tenant `[C-3]` |
| KB-04 | User can list datasets with `page`, `page_size`, `keywords` via `GET /api/v1/datasets` | S | `04-api/endpoint-catalog.md` | |
| KB-05 | User can get one dataset's detail via `GET /datasets/<dataset_id>` | S | `04-api/dataset-api.md`, `15-cli/commands.md` | |
| KB-06 | User can update dataset name, parser, and parser config via `PUT /api/v1/datasets/<dataset_id>` | M | `04-api/endpoint-catalog.md`, `apis.md` | Embedding-model change rules undocumented |
| KB-07 | User can delete dataset(s) via `DELETE /api/v1/datasets`; documents, chunks, and the vector index are removed | M | `04-api/endpoint-catalog.md`, `apis.md` | |
| KB-08 | Dataset stores `parser_config` JSON: `chunk_token_num`, `delimiter`, `pages`, `table_context_size`, `image_context_size`, layout-model toggle, auto-keyword count | M | `06-document-processing/chunking-strategies.md`, `02-frontend/document-upload-ui.md` | |
| KB-09 | Dataset stores avatar, language (default `English`), description, and status | S | `08-database/schema.md` | |
| KB-10 | User can aggregate tags across datasets via `GET /datasets/tags/aggregation` | M | `04-api/dataset-api.md` | `[P]` — route only |
| KB-11 | User can list and delete tags of a dataset via `GET` / `DELETE /datasets/<dataset_id>/tags` | M | `04-api/dataset-api.md` | `[P]`; handler mismatch `[C-13]` |
| KB-12 | User can fetch flattened metadata across datasets via `GET /datasets/metadata/flattened` | M | `04-api/dataset-api.md` | `[P]` |
| KB-13 | User can read a dataset's auto-metadata configuration via `GET /datasets/<dataset_id>/metadata/config` | S | `04-api/dataset-api.md` | `[P]` |
| KB-14 | User can view an ingestion summary for a dataset via `GET /datasets/<dataset_id>/ingestions/summary` | M | `04-api/dataset-api.md` | `[P]` |
| KB-15 | User can list ingestion logs and fetch one log via `GET /datasets/<dataset_id>/ingestions/<log_id>` | M | `04-api/dataset-api.md`, `08-database/entities.md` (`PipelineOperationLog`) | `[P]` |
| KB-16 | User can check embedding-model compatibility for a dataset via `POST /datasets/<dataset_id>/embedding/check` | M | `04-api/dataset-api.md` | `[P]`; handler mismatch `[C-13]` |
| KB-17 | User can delete a derived index of a dataset by type via `DELETE /datasets/<dataset_id>/<index_type>` and trace it via `GET /datasets/<dataset_id>/artifacts/alteration` | M | `04-api/dataset-api.md` | `[P]`; index types (graph, raptor, mindmap) inferred from `10-cache-and-queues/background-jobs.md` |
| KB-18 | User can run a retrieval test against a dataset with similarity threshold and vector/keyword weight controls | M | `02-frontend/knowledge-base-ui.md`, `apis.md` (`/searchbots/retrieval_test`), `15-cli/commands.md` | See RETR-18 |
| KB-19 | Dataset document counts and token/chunk totals are maintained | S | `03-backend/services.md` | |

#### DOC — Document upload, lifecycle, management

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| DOC-01 | User can upload one or more files to a dataset as multipart via `POST /api/v1/documents/upload` | M | `04-api/endpoint-catalog.md`, `21-.../upload-document.md` | Owner and path `[C-8]` |
| DOC-02 | Upload rejects disallowed extensions / MIME types with HTTP 400 | S | `06-document-processing/upload.md` | Whitelist: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, JPG, PNG, MP3, WAV (`02-frontend/document-upload-ui.md`) |
| DOC-03 | Upload enforces max content size and quota limits | S | `06-document-processing/upload.md`, `02-frontend/document-upload-ui.md` | `[P]` — "checks quota limits" with no numbers |
| DOC-04 | Upload computes an xxh64 content hash and, on a duplicate within the tenant, reuses the stored blob and only links a new `Document` | M | `06-document-processing/upload.md` | "xxhash/md5" elsewhere `[C-9]` |
| DOC-05 | Upload writes the binary to object storage and records `location` | M | `21-.../upload-document.md`, `09-storage/storage-flow.md` | Key/bucket layout `[C-18]` |
| DOC-06 | Upload inserts `File`, `Document`, `File2Document` rows in one transaction with `run='0'`, `progress=0.0` | M | `06-document-processing/upload.md`, `08-database/transactions.md` | |
| DOC-07 | Upload verifies dataset existence and caller permission before storing | S | `21-.../upload-document.md` | |
| DOC-08 | User can list documents in a dataset with paging and keyword filter via `GET /api/v1/datasets/<dataset_id>/documents` | S | `04-api/endpoint-catalog.md` | |
| DOC-09 | User can start parsing selected documents via `POST /api/v1/datasets/<dataset_id>/documents/parse` (`doc_ids`, `run`); document moves to RUNNING and tasks are queued | M | `04-api/endpoint-catalog.md`, `21-.../document-processing.md` | Auto-enqueue on upload vs explicit parse `[C-8]` |
| DOC-10 | User can cancel a running parse; document moves to CANCELLED | M | `06-document-processing/document-lifecycle.md` | Via `run` parameter |
| DOC-11 | User can re-parse a document; previous chunks are replaced | M | `06-document-processing/document-lifecycle.md` | Implied by state machine |
| DOC-12 | Document exposes lifecycle state (`run`), `progress` float 0.0-1.0 (`-1` on failure), and `progress_msg` | M | `06-document-processing/document-lifecycle.md`, `08-database/schema.md` | Enum values `[C-4]` |
| DOC-13 | User can enable/disable documents for retrieval via `POST /api/v1/datasets/<dataset_id>/documents/batch-update-status` | M | `04-api/endpoint-catalog.md` | Flips chunk `available_int` |
| DOC-14 | User can delete documents via `DELETE /api/v1/datasets/<dataset_id>/documents`; chunks are pruned from the index | M | `04-api/endpoint-catalog.md` | |
| DOC-15 | Deleting a document garbage-collects the blob only when no other `File2Document` row references it | M | `09-storage/file-lifecycle.md` | |
| DOC-16 | Documents can carry their own `parser_id` / `parser_config` overriding the dataset default | S | `06-document-processing/chunking-strategies.md`, `08-database/schema.md` | |
| DOC-17 | User can batch-update document metadata via `PATCH /datasets/<dataset_id>/documents/metadatas` | M | `04-api/document-api.md` | `[P]`; handler mismatch `[C-13]` |
| DOC-18 | User can fetch an extracted image via `GET /documents/images/<image_id>` | S | `04-api/document-api.md` | |
| DOC-19 | User can fetch a generated artifact via `GET /documents/artifact/<filename>` | S | `04-api/document-api.md` | `[P]` |
| DOC-20 | Documents have thumbnails | M | `08-database/schema.md`, `04-api/document-api.md` | `[P]` — column plus handler name |
| DOC-21 | User can preview a document's raw content | M | `15-cli/commands.md` (`cat`, `GET /api/v1/documents/<doc_id>/preview`) | `[P]` — only via the CLI table |
| DOC-22 | User can query task status via `GET /v1/task/status/:task_id` | S | `04-api/workflow-api.md` | |
| DOC-23 | Documents track `token_num`, `chunk_num`, `process_begin_at`, `process_duration`, `size`, `suffix`, `source_type` | S | `08-database/schema.md` | |
| DOC-24 | File manager with folder hierarchy (`file.parent_id`) | L | `08-database/indexes.md`, `08-database/database-overview.md`, `02-frontend/pages.md` (`files`) | `[P]` — index row plus a page name |

#### STOR — Object and file storage

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| STOR-01 | Uniform storage interface (`get`, `put`, `rm`, `bucket_exists`) selected by `STORAGE_IMPL` through a factory | M | `06-document-processing/file-storage.md`, `09-storage/storage-overview.md` | `[DUAL]` Python and Go factories |
| STOR-02 | MinIO driver | M | `09-storage/object-storage.md` | Default in compose |
| STOR-03 | AWS S3 driver | M | `09-storage/object-storage.md` | |
| STOR-04 | Google Cloud Storage driver | M | `09-storage/storage-overview.md` | |
| STOR-05 | Alibaba Cloud OSS driver | M | `09-storage/storage-overview.md` | |
| STOR-06 | Local filesystem driver with path sanitization that blocks directory traversal | M | `09-storage/local-storage.md` | |
| STOR-07 | Azure Blob Storage driver | M | `17-integrations/storage-integrations.md`, `18-deployment/production-architecture.md` | `[P]`; absent from `09-storage` `[C-18]` |
| STOR-08 | Missing buckets are created on first write | S | `09-storage/storage-flow.md` | |
| STOR-09 | Extracted images and table crops are stored under `{tenant_id}/{doc_id}/{img_id}.png` and `.../tables/{table_id}.png` | S | `06-document-processing/file-storage.md` | |
| STOR-10 | Pre-signed download URLs with 3600s expiry | S | `17-integrations/storage-integrations.md` | `[P]` |
| STOR-11 | Uploaded objects are stored under randomized UUID names | S | `20-security/file-security.md` | |

#### PARSE — Parsers, OCR, layout, tables (DeepDoc)

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| PARSE-01 | File-type router dispatches each source file to its parser | S | `05-rag-pipeline/parsing.md` | |
| PARSE-02 | PDF: extract native text spans with character bounding boxes | M | `06-document-processing/pdf-processing.md` | PyMuPDF / pdfium |
| PARSE-03 | PDF: rasterize pages to images at zoom 3 | S | `05-rag-pipeline/parsing.md` | |
| PARSE-04 | Layout analysis (DLA) detects regions labelled Text, Title, Figure, Figure caption, Table, Table caption, Header, Footer, Reference, Equation | XL | `06-document-processing/layout-analysis.md` | ONNX model weights must be sourced; see PITFALLS |
| PARSE-05 | Text boxes are assigned to layout regions at overlap ratio >= 0.4; duplicates removed by IoU NMS; regions sorted into reading order | L | `06-document-processing/layout-analysis.md` | |
| PARSE-06 | OCR fallback (text detection plus recognition) runs when a page's text layer is missing or corrupt | XL | `06-document-processing/ocr.md`, `05-rag-pipeline/parsing.md` | DBNet + CRNN ONNX |
| PARSE-07 | Table structure recognition reconstructs cropped tables into HTML `<table>` | XL | `06-document-processing/tables.md` | |
| PARSE-08 | Headers and footers are filtered from chunk content | S | `05-rag-pipeline/chunking.md` | |
| PARSE-09 | DOCX parser: paragraphs, headings, embedded images, tables as HTML | M | `06-document-processing/office-documents.md` | `[DUAL]` Go port exists |
| PARSE-10 | XLSX parser: sheets to HTML/Markdown tables with header-row context | M | `06-document-processing/office-documents.md` | |
| PARSE-11 | PPTX parser: slide titles, text frames, shape tables, speaker notes, images | M | `06-document-processing/office-documents.md` | |
| PARSE-12 | HTML parser: DOM extraction with script/style stripping | S | `05-rag-pipeline/parsing.md` | |
| PARSE-13 | TXT parser with encoding auto-detection | S | `05-rag-pipeline/parsing.md` | |
| PARSE-14 | Markdown parser | S | `06-document-processing/parsers.md` | `[P]` — file listing |
| PARSE-15 | JSON parser | S | `06-document-processing/parsers.md` | `[P]` |
| PARSE-16 | EPUB parser | M | `06-document-processing/parsers.md`, `05-rag-pipeline/parsing.md` | `[P]` |
| PARSE-17 | CSV ingestion | S | `02-frontend/document-upload-ui.md`, `05-rag-pipeline/chunking.md` | Through `table` / `qa` chunkers |
| PARSE-18 | Image files (JPG, PNG) are parsed via OCR and/or VLM description | M | `06-document-processing/images.md` | |
| PARSE-19 | Embedded figures are extracted, hashed for dedup (`image2id`), captioned by a vision model, and stored | L | `06-document-processing/images.md` | |
| PARSE-20 | Audio files (MP3, WAV) are transcribed by an ASR model | M | `05-rag-pipeline/chunking.md`, `02-frontend/document-upload-ui.md` | |
| PARSE-21 | Email (`.eml`) parsed into From, To, Subject, Date, Body | M | `05-rag-pipeline/chunking.md` | |
| PARSE-22 | Pluggable external PDF parsers: Docling and MinerU wrappers | L | `05-rag-pipeline/parsing.md` | Described in one table row |
| PARSE-23 | Additional parser backends: PaddleOCR, Mistral, TCADP, SoMark, OpenDataLoader, figure parser | L | `06-document-processing/parsers.md` | `[P]` — file listing only |
| PARSE-24 | DLA / OCR / TSR can be offloaded to a remote DeepDoc service (`DEEPDOC_URL`, `TENSORRT_DLA_SVR`; container port 9390) | L | `06-document-processing/ocr.md`, `18-deployment/docker-compose.md` | |
| PARSE-25 | Parsing honours the `pages` range in `parser_config` | S | `06-document-processing/chunking-strategies.md` | |
| PARSE-26 | Go PDF and DOCX parser implementations with CGO bindings (PDFium, OfficeOxide) | XL | `05-rag-pipeline/parsing.md`, `19-testing/integration-tests.md` | `[DUAL]` `[C-20]` |

#### CHUNK — Chunking strategies and chunk management

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| CHUNK-01 | `parser_id` resolver dispatches to the matching chunker (`FACTORY[parser_id]`) | S | `05-rag-pipeline/chunking.md` | Count of chunkers varies `[C-19]` |
| CHUNK-02 | `naive`/`general`: token window with overlap, custom delimiters, max tokens (default 512) | M | `05-rag-pipeline/chunking.md`, `06-.../chunking-strategies.md` | UI default range 128-512 |
| CHUNK-03 | `paper`: section-aware (Abstract, Introduction, Method, ..., References) | L | `05-rag-pipeline/chunking.md` | |
| CHUNK-04 | `book`: chapter/section hierarchy from headings or TOC depth | L | `05-rag-pipeline/chunking.md` | |
| CHUNK-05 | `laws`: Chapter / Section / Article / Item hierarchy | L | `05-rag-pipeline/chunking.md` | |
| CHUNK-06 | `presentation`: one chunk group per slide with slide title appended | M | `05-rag-pipeline/chunking.md` | |
| CHUNK-07 | `table`: one chunk per row prefixed with table title and column headers | M | `05-rag-pipeline/chunking.md`, `06-.../tables.md` | |
| CHUNK-08 | `qa`: question/answer pairs from Excel/CSV/text; question stored in `question_tks` | M | `05-rag-pipeline/chunking.md` | |
| CHUNK-09 | `resume`: structured CV entities (name, contact, work history, education, skills) | L | `05-rag-pipeline/chunking.md` | |
| CHUNK-10 | `picture`: VLM description of images indexed as chunks | M | `05-rag-pipeline/chunking.md` | Depends on LLM-09 |
| CHUNK-11 | `manual`: groups code blocks, parameter tables, subsection diagrams | L | `05-rag-pipeline/chunking.md` | |
| CHUNK-12 | `email`: From/To/Subject/Date/Body sections | M | `05-rag-pipeline/chunking.md` | |
| CHUNK-13 | `tag`: extracts tag features and tag weights | M | `05-rag-pipeline/chunking.md` | |
| CHUNK-14 | `one`: whole document as a single chunk | S | `05-rag-pipeline/chunking.md` | |
| CHUNK-15 | `audio`: ASR transcript segmented into timestamped chunks | M | `05-rag-pipeline/chunking.md` | Depends on LLM-10 |
| CHUNK-16 | Every chunk carries content, page number, position `[page, x0, top, x1, bottom]`, and image ids | M | `05-rag-pipeline/ingestion-pipeline.md`, `05-.../indexing.md` | Needed by citation UI |
| CHUNK-17 | Text preprocessing: full-to-half-width, traditional-to-simplified Chinese, URL/email stripping, tokenize, fine-grained tokenize, token positions | L | `05-rag-pipeline/preprocessing.md` | Native tokenizer dependency |
| CHUNK-18 | User can list a document's chunks with text, bounding boxes, status, paging, keyword filter via `GET .../documents/<doc_id>/chunks` | M | `04-api/endpoint-catalog.md`, `apis.md` | |
| CHUNK-19 | User can create a manual chunk via `POST .../documents/<doc_id>/chunks` | M | `04-api/endpoint-catalog.md` | Must embed and index |
| CHUNK-20 | User can edit a chunk's text | M | `apis.md`, `02-frontend/knowledge-base-ui.md` | "create or edit" on one route; no separate update route |
| CHUNK-21 | User can enable/disable individual chunks | S | `02-frontend/state-management.md` (`changeChunkStatus`) | `[P]` — no endpoint |
| CHUNK-22 | LLM keyword extraction per chunk populates `important_kwd` | M | `05-rag-pipeline/prompt-construction.md`, `21-.../indexing.md` | Optional enrichment |
| CHUNK-23 | LLM question proposal per chunk populates `question_tks` | M | `05-rag-pipeline/prompt-construction.md`, `21-.../indexing.md` | Optional enrichment |
| CHUNK-24 | LLM content tagging against tag sets | M | `05-rag-pipeline/prompt-construction.md` | |
| CHUNK-25 | LLM auto-metadata generation (`gen_metadata`) | M | `05-rag-pipeline/prompt-construction.md` | |
| CHUNK-26 | RAPTOR hierarchical summarization (cluster, summarize, index summary chunks) when enabled on the dataset | XL | `21-.../indexing.md`, `10-cache-and-queues/background-jobs.md` | Only described in the indexing flow |
| CHUNK-27 | Public built-in pipeline listing: `GET /api/v1/pipelines?type=builtin`, `GET /api/v1/pipelines/:id` | S | `04-api/workflow-api.md` | Unauthenticated |
| CHUNK-28 | Go chunker mirrors for `naive`, `one`, `qa`, `table`, `presentation` | L | `05-rag-pipeline/chunking.md` | `[DUAL]` `[C-20]` |

#### ING — Background ingestion, queues, workers, Redis

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| ING-01 | Parsing creates `task` rows; large documents are split into page-range sub-tasks (`MAXIMUM_TASK_PAGE_NUMBER = 12`) | M | `10-cache-and-queues/scheduling.md` | |
| ING-02 | Tasks are published to Redis Streams (`XADD`) on `te.{priority}.common` | M | `10-cache-and-queues/queues.md` | Queue technology `[C-2]` |
| ING-03 | High-priority queue (`te.1.common`) is drained before normal (`te.0.common`) | S | `05-rag-pipeline/ingestion-pipeline.md` | |
| ING-04 | Workers consume through a consumer group (`XREADGROUP`); N workers run concurrently | M | `10-cache-and-queues/queues.md` | |
| ING-05 | Un-acked messages from a crashed worker are reclaimed by the next consumer | M | `10-cache-and-queues/workers.md` | |
| ING-06 | A Redis distributed lock (`SET NX EX`) guards each task | S | `10-cache-and-queues/redis.md` | |
| ING-07 | Worker acknowledges (`XACK`) on completion | S | `10-cache-and-queues/workers.md` | |
| ING-08 | Worker reports progress (0.0-1.0, `-1` on failure) and message to `task`; a lock-guarded `update_progress` daemon rolls task progress up to the document | M | `05-rag-pipeline/ingestion-pipeline.md`, `03-backend/entry-points.md` | |
| ING-09 | Concurrency limiters: `task_limiter`, `chunk_limiter`, `embed_limiter`, `minio_limiter`, `kg_limiter` | M | `06-document-processing/document-processing-workers.md` | |
| ING-10 | Worker heartbeat to Redis (`WORKER_HEARTBEAT_TIMEOUT`, default 120s) | S | `10-cache-and-queues/workers.md` | |
| ING-11 | Task failure records error trace, sets document to FAILED, tracks `retry_count` | M | `08-database/schema.md`, `06-.../document-lifecycle.md` | |
| ING-12 | Worker stops when the user cancels | M | `06-document-processing/document-lifecycle.md` | |
| ING-13 | Worker pipeline end-to-end: fetch blob, parse, chunk, embed, bulk index, mark done | L | `05-rag-pipeline/ingestion-pipeline.md` | Integration of PARSE, CHUNK, IDX |
| ING-14 | Blocking compute (embedding, docstore calls) is offloaded to a thread pool so the asyncio loop is not blocked | S | `10-cache-and-queues/async-processing.md` | |
| ING-15 | Worker closes DB connections before long model inference | S | `08-database/database-flow.md` | |
| ING-16 | Task executor runs as a standalone process/container (`entrypoint_task_executor.sh`) | S | `18-deployment/deployment-overview.md` | |
| ING-17 | Background task types beyond parse: `raptor`, `graphrag`, `mindmap`, `memory`, `wiki`, `skill`, `structure_graph`, `structure_mindmap`, `timeline`, `session_graph`, `session_essence`, `structure` | XL | `10-cache-and-queues/background-jobs.md` | `[P]` — a mapping dict; only `dataflow` and `raptor` are described elsewhere |
| ING-18 | Dataset-wide fan-out tasks using sentinel document ids | M | `10-cache-and-queues/background-jobs.md` | `[P]` |
| ING-19 | Go ingestion service and syncer (`--ingestor`, `--syncer` flags) | XL | `03-backend/entry-points.md`, `00-overview/high-level-architecture.md` | `[DUAL]` `[C-20]`; responsibilities not specified beyond the names |
| ING-20 | NATS JetStream as task queue | L | `18-deployment/production-architecture.md`, `18-deployment/docker-compose.md` | `[C-2]` — directly conflicts with ING-02 |
| ING-21 | Redis also serves as session store, synonym cache (`synonym_{term}`), and LLM cache (`llm_cache_{hash}`) | M | `10-cache-and-queues/redis.md` | Rate-limit counters mentioned `[P]` |

#### IDX — Embedding and indexing

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| IDX-01 | Chunks are embedded in batches of 64 using the dataset's embedding model | M | `05-rag-pipeline/embedding.md` | |
| IDX-02 | Inputs are truncated to 8192 tokens before embedding; results are re-ordered by index to match inputs | S | `11-llm/embeddings.md` | |
| IDX-03 | Vectors are L2-normalized | S | `05-rag-pipeline/embedding.md` | |
| IDX-04 | Vector field is named `q_{dim}_vec`, allowing multiple embedding dimensions in one index | S | `05-rag-pipeline/embedding.md` | |
| IDX-05 | Unified `DocStoreConnection` interface (create/drop index, insert, update, delete, search with text + dense + fusion expressions) | L | `05-rag-pipeline/indexing.md`, `07-retrieval/retrieval-overview.md` | |
| IDX-06 | Index schema: `id`, `doc_id`, `kb_id`, `content_ltks`, `title_tks`, `important_kwd`, `question_tks`, `position_int`, `q_{dim}_vec`, `available_int` (plus `title_sm_tks`, `important_tks`, `content_sm_ltks` from query fields) | M | `05-rag-pipeline/indexing.md`, `07-retrieval/full-text-search.md` | |
| IDX-07 | Chunks are bulk-upserted in batches of 64 with deterministic id `doc_id + "_" + order` | M | `05-rag-pipeline/ingestion-pipeline.md`, `05-.../indexing.md` | Idempotent re-index |
| IDX-08 | Vector index is HNSW with cosine metric, `m=16`, `ef_construction=200` | S | `07-retrieval/vector-search.md` | |
| IDX-09 | Elasticsearch 8 adapter | L | `05-rag-pipeline/indexing.md` | Compose profile `elasticsearch` |
| IDX-10 | Infinity adapter | L | `05-rag-pipeline/indexing.md` | Called "default vector DB"; compose profile `infinity` |
| IDX-11 | OpenSearch adapter | L | `17-integrations/vector-database-integrations.md`, `18-.../docker-compose.md` | `[P]` beyond a compose row |
| IDX-12 | OceanBase adapter | L | `05-rag-pipeline/indexing.md` | `[P]`; Go-only driver cited |
| IDX-13 | Further engines: ClickHouse, SereneDB, Qdrant, Milvus, PGVector, Tantivy, SeekDB | XL | `05-rag-pipeline/rag-overview.md`, `00-overview/technology-stack.md`, `18-.../docker-compose.md` | `[P]`; the list differs per doc `[C-17]` |
| IDX-14 | Document and dataset deletion remove their chunks from the index | S | `apis.md` | |
| IDX-15 | Go docstore drivers (Elasticsearch, Infinity, OceanBase) | XL | `05-rag-pipeline/indexing.md` | `[DUAL]` `[C-20]` |

#### RETR — Retrieval, filters, reranking

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| RETR-01 | Dense KNN search with cosine similarity over `q_{dim}_vec` (`MatchDenseExpr`) | M | `07-retrieval/vector-search.md` | |
| RETR-02 | BM25 full-text search over boosted fields (`important_kwd^30`, `important_tks^20`, `question_tks^20`, `title_tks^10`, `title_sm_tks^5`, `content_ltks^2`, `content_sm_ltks`) | M | `07-retrieval/full-text-search.md` | |
| RETR-03 | Query normalization, tokenization, term weighting, and engine-specific escaping | L | `07-retrieval/keyword-search.md`, `05-.../preprocessing.md` | |
| RETR-04 | Synonym expansion with Redis-cached synonym pairs | M | `07-retrieval/keyword-search.md` | |
| RETR-05 | Hybrid fusion of text and dense matches (`FusionExpr("weighted_sum", topk, weights)`) executed in the docstore | M | `07-retrieval/hybrid-retrieval.md` | |
| RETR-06 | Final score = `w_term * S_term + w_vector * S_vector + S_rank_feature`, with `vector_similarity_weight` configurable per query or assistant | M | `05-rag-pipeline/hybrid-search.md` | Default weights differ between functions `[C-23]` |
| RETR-07 | Reciprocal Rank Fusion (`k = 60`) as a fusion option | M | `05-rag-pipeline/hybrid-search.md`, `07-.../hybrid-retrieval.md` | When RRF vs weighted sum applies is not stated `[C-23]` |
| RETR-08 | Filters by `kb_ids`, `doc_ids`, `id`, `available_int`, `removed_kwd`, and `must_not` conditions | M | `07-retrieval/filters.md` | |
| RETR-09 | Metadata conditions translate to Elasticsearch `bool.must` / `must_not` or Infinity `WHERE` | M | `07-retrieval/filters.md` | |
| RETR-10 | Chunks of deleted documents are pruned from results | S | `07-retrieval/retrieval-flow.md` | |
| RETR-11 | Cross-encoder reranking (`rerank_by_model`) blending token similarity, rerank score, and rank features | M | `07-retrieval/reranking.md` | |
| RETR-12 | Without a reranker: KNN + token-overlap rerank on Elasticsearch, direct normalized scores on Infinity | M | `05-rag-pipeline/reranking.md` | |
| RETR-13 | Rank-feature score = `10 * tag_score + pagerank` | M | `07-retrieval/similarity.md` | |
| RETR-14 | Results below `similarity_threshold` (default 0.2) are dropped; ordering is a stable sort by score | S | `07-retrieval/retrieval-flow.md` | |
| RETR-15 | Pagination (`page`, `page_size`) with a rerank window over `top` candidates (default 1024) | M | `07-retrieval/retrieval-flow.md` | |
| RETR-16 | Retrieval spans multiple datasets and tenants' indices in one call | S | `07-retrieval/retrieval-flow.md` | |
| RETR-17 | Each hit returns chunk id, content, doc id/name, dataset id, page, positions, and term/vector/overall similarity | S | `05-rag-pipeline/final-answer.md`, `02-frontend/components.md` | |
| RETR-18 | Retrieval-test API returns ranked hits for a question over selected datasets | M | `apis.md`, `15-cli/commands.md` | |
| RETR-19 | NaN / Infinity scores are sanitized to null before serialization | S | `12-chat/complete-chat-flow.md` | |
| RETR-20 | Knowledge-graph filter keys (`knowledge_graph_kwd`, `entity_kwd`, `from_entity_kwd`, `to_entity_kwd`) | L | `07-retrieval/filters.md` | `[P]` — keys only; GraphRAG itself is not documented |
| RETR-21 | Web-search augmentation merges web snippets with local chunks when the assistant enables it | L | `17-integrations/search-integrations.md`, `12-chat/complete-chat-flow.md` | Providers named: Google, DuckDuckGo, Tavily, SearxNG, Querit, Bing |
| RETR-22 | Chunks marked inaccurate by user feedback are downweighted or excluded | M | `12-chat/messages.md` | `[P]` — "can be blacklisted or downweighted" |
| RETR-23 | Go retrieval driver | XL | `07-retrieval/retrieval-overview.md` | `[DUAL]` `[C-20]`; backs `/searchbots/*` |

#### LLM — Providers, model configuration, prompts

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| LLM-01 | Chat driver base interface: `chat`, `async_chat`, `chat_streamly`, `async_chat_streamly` | M | `11-llm/provider-abstraction.md` | |
| LLM-02 | LiteLLM-backed driver with provider prefix routing and default base URLs | M | `11-llm/provider-abstraction.md`, `11-llm/model-providers.md` | |
| LLM-03 | OpenAI chat and embeddings | M | `11-llm/openai.md` | |
| LLM-04 | Azure OpenAI deployment mapping | M | `11-llm/openai.md` | |
| LLM-05 | Ollama chat and embeddings with user-supplied base URL (no `/v1` suffix) | M | `11-llm/ollama.md` | Enables keyless local e2e tests |
| LLM-06 | DeepSeek with `<think>` reasoning-block extraction | S | `11-llm/other-providers.md` | |
| LLM-07 | Provider registry of 40+ providers (Tongyi/DashScope, Zhipu, Moonshot, Anthropic, Gemini, Bedrock, Cohere, Groq, TogetherAI, xAI, NVIDIA, MiniMax, Hunyuan, SiliconFlow, OpenRouter, ...) | L | `11-llm/model-providers.md`, `17-integrations/model-integrations.md` | Mostly config through LiteLLM; direct drivers (Baidu, Spark, VolcEngine) are `[P]` |
| LLM-08 | Embedding drivers: OpenAI, Azure, Qwen, Zhipu, Ollama, HuggingFace/builtin, Jina, SiliconFlow | L | `11-llm/embeddings.md` | |
| LLM-09 | Rerank drivers (Jina, Cohere, NVIDIA, Voyage, BGE/BCE, LocalAI, Qwen) with scores normalized to [0, 1] | L | `11-llm/rerank-models.md`, `07-retrieval/reranking.md` | |
| LLM-10 | Vision (image-to-text) model type | M | `11-llm/llm-architecture.md`, `06-.../images.md` | |
| LLM-11 | Speech-to-text (ASR) model type | M | `11-llm/llm-architecture.md` | `[P]` beyond the type name |
| LLM-12 | Text-to-speech (TTS) model type | M | `11-llm/llm-architecture.md` | `[P]` |
| LLM-13 | OCR model type | M | `11-llm/llm-architecture.md` | `[P]` |
| LLM-14 | `LLMBundle` resolves tenant credentials, instantiates the driver, resets/reports usage | M | `11-llm/llm-architecture.md` | |
| LLM-15 | Composite model ids `model@instance@provider` and `model@provider` | S | `11-llm/llm-architecture.md` | `[DUAL]` |
| LLM-16 | Per-tenant provider credentials (`tenant_llm`: factory, model type, API key, API base) stored encrypted | M | `11-llm/model-providers.md`, `20-security/secrets.md` | |
| LLM-17 | Generation parameters are whitelisted (`ALLOWED_GEN_CONF_KEYS`) before provider calls | S | `11-llm/llm-architecture.md` | |
| LLM-18 | Reasoning models (o1/o3) suppress `temperature` and use `max_completion_tokens` | S | `11-llm/openai.md` | |
| LLM-19 | Provider errors map to `LLMErrorCode`; rate-limit and timeout errors are retried | M | `11-llm/provider-abstraction.md` | |
| LLM-20 | Stream sanitizer strips malformed fragments and control tokens | M | `11-llm/llm-request-flow.md` | |
| LLM-21 | Token usage is counted for streaming and non-streaming calls and recorded | M | `11-llm/llm-architecture.md`, `21-.../rag-answer.md` | `tenant_token_usage` table named once `[P]` |
| LLM-22 | Model metadata registry: context window, max completion tokens, vision flag, input/output price | M | `11-llm/model-providers.md` | |
| LLM-23 | User can list providers via `GET /providers` | S | `04-api/provider-api.md` | |
| LLM-24 | Admin/owner can add or update a provider's credentials via `PUT /providers` | M | `04-api/provider-api.md` | Handler mismatch `[C-13]` |
| LLM-25 | Admin/owner can delete a provider via `DELETE /providers/<provider_id_or_name>` | S | `04-api/provider-api.md` | |
| LLM-26 | User can list a provider's models via `GET /providers/<provider>/models` | S | `04-api/provider-api.md` | |
| LLM-27 | Admin/owner can create and view provider instances via `POST /providers/<provider>/instances` and `GET .../instances/<instance>` | M | `04-api/provider-api.md`, `08-database/entities.md` | |
| LLM-28 | User can list configured models and tenant defaults via `GET /models`, `GET /models/default` | S | `04-api/models-api.md` | |
| LLM-29 | Tenant model entities: `TenantModelProvider`, `TenantModelInstance`, `TenantModel`, `TenantModelGroup`, `TenantModelGroupMapping` | M | `08-database/entities.md` | `[P]` — names only; overlaps `TenantLLM` |
| LLM-30 | Per-tenant Langfuse keys: set via `POST`/`PUT /langfuse/api-key`, delete via `DELETE /langfuse/api-key` | M | `04-api/langfuse-api.md` | |
| LLM-31 | LLM calls emit Langfuse observations when keys are configured | M | `11-llm/llm-architecture.md` | |
| LLM-32 | Prompt generators: keyword extraction, question proposal, content tagging, metadata generation, chunk formatting | M | `05-rag-pipeline/prompt-construction.md`, `11-llm/prompt-management.md` | |
| LLM-33 | Tool-schema decorator converts annotated functions to OpenAI function-call JSON schema | M | `11-llm/prompt-management.md` | |
| LLM-34 | Thinking/reasoning control injection (Qwen `enable_thinking`, Anthropic `thinking`) | S | `11-llm/provider-abstraction.md` | |
| LLM-35 | Go model service parity | L | `11-llm/llm-architecture.md` | `[DUAL]` `[C-20]` |

#### CHAT — Assistants, conversations, streaming, citations, memory

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| CHAT-01 | User can create a chat assistant with name, dataset ids, LLM id via `POST /api/v1/chats` | M | `04-api/endpoint-catalog.md`, `12-chat/chat-architecture.md` | Alternate path `POST /v1/api/dialog/set` `[C-5]` |
| CHAT-02 | User can list assistants with paging/keywords via `GET /api/v1/chats` | S | `04-api/endpoint-catalog.md` | |
| CHAT-03 | User can update an assistant's configuration | M | `04-api/chat-api.md` ("Create / Update") | No update route in the master catalog `[C-5]` |
| CHAT-04 | User can delete an assistant via `DELETE /api/v1/chats/<chat_id>` | S | `04-api/endpoint-catalog.md` | |
| CHAT-05 | Assistant stores `prompt_config`: system prompt, prologue, empty-response text, parameters; and `prompt_type` (`simple` / `advanced`) | M | `05-rag-pipeline/prompt-construction.md` | |
| CHAT-06 | Assistant stores LLM settings: temperature, top_p, presence/frequency penalty, max tokens | S | `02-frontend/components.md` | |
| CHAT-07 | Assistant stores retrieval settings: similarity threshold, vector weight, top-N, rerank model | S | `05-rag-pipeline/hybrid-search.md`, `02-frontend/components.md` | |
| CHAT-08 | User can create a conversation session | S | `12-chat/conversation.md` | Path `[C-5]` |
| CHAT-09 | User can list sessions of an assistant via `GET /api/v1/chats/<chat_id>/sessions` | S | `04-api/endpoint-catalog.md` | |
| CHAT-10 | User can fetch a session with its full message history | S | `12-chat/conversation.md` | |
| CHAT-11 | User can delete a session | S | `12-chat/conversation.md` | |
| CHAT-12 | User can send a message and receive the answer as an SSE token stream via `POST /api/v1/chat/completions` | L | `04-api/chat-api.md`, `12-chat/streaming.md`, `21-.../chat-streaming.md` | Path `[C-5]` |
| CHAT-13 | Each SSE frame is `data: {"code":0,"message":"","data":{"answer","reference","session_id"}}`; the stream ends with a terminator frame | M | `12-chat/streaming.md` | Terminator and reference timing `[C-6]` |
| CHAT-14 | Non-streaming completion when `stream=false` | S | `11-llm/llm-request-flow.md` | |
| CHAT-15 | With datasets attached the pipeline runs retrieve, rerank, build context, generate; without datasets it falls back to plain chat | M | `12-chat/complete-chat-flow.md` | |
| CHAT-16 | Context construction deduplicates chunks by content hash, truncates to the token budget, and labels each chunk with document title and page | M | `05-rag-pipeline/context-construction.md` | |
| CHAT-17 | Conversation history is truncated newest-first to fit `max_tokens - system - knowledge - completion - margin` | M | `12-chat/memory.md` | |
| CHAT-18 | Answers carry inline citation markers mapped to a `reference.chunks` payload | L | `12-chat/context.md`, `05-.../final-answer.md` | Marker syntax `[C-6]` |
| CHAT-19 | Post-generation citation insertion by sentence-to-chunk embedding similarity (`insert_citations`) | M | `05-rag-pipeline/final-answer.md` | |
| CHAT-20 | When retrieval returns nothing the assistant replies with the configured `empty_response` | S | `05-rag-pipeline/prompt-construction.md` | |
| CHAT-21 | The user turn and assistant answer with references are persisted to the conversation after the stream completes | M | `12-chat/complete-chat-flow.md` | Table names vary `[C-7]` |
| CHAT-22 | User can stop generation mid-stream | M | `02-frontend/components.md`, `02-frontend/state-management.md` (`stopStream`) | Server-side cancellation not described |
| CHAT-23 | User can give thumbs up/down feedback on an assistant message via `POST /v1/api/conversation/feedback` | S | `12-chat/messages.md` | |
| CHAT-24 | User can annotate individual retrieved chunks as accurate/inaccurate (`ChunkFeedback`) | M | `12-chat/messages.md` | `[P]` — no endpoint |
| CHAT-25 | External API consumers get their own session store (`API4Conversation`) | M | `12-chat/conversation.md` | |
| CHAT-26 | Public chatbot completion via `POST /api/v1/chatbots/<dialog_id>/completions` with a beta token | M | `04-api/chat-api.md`, `04-api/bot-api.md` | Engine: Go in one doc, Python in the other `[C-8]` |
| CHAT-27 | OpenAI-compatible `/v1/chat/completions` endpoint | M | `12-chat/chat-architecture.md` | `[P]` — one table row |
| CHAT-28 | Mind-map generation from an answer (`gen_mindmap`) | M | `12-chat/complete-chat-flow.md` | `[P]` |
| CHAT-29 | Follow-up question proposals | S | `05-rag-pipeline/prompt-construction.md` | `[P]` |
| CHAT-30 | Message file attachments | M | `02-frontend/components.md` | `[P]` — UI component feature only |
| CHAT-31 | Answer latency and token counts recorded per turn | S | `21-.../rag-answer.md` | `[P]` |

#### SRCH — Search apps and search bots

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| SRCH-01 | User can create a search app via `POST /searches` | M | `04-api/search-api.md` | Handler mismatch `[C-13]` |
| SRCH-02 | User can list search apps | S | `04-api/search-api.md` | Verb unclear `[C-13]` |
| SRCH-03 | User can get a search app via `GET /searches/<search_id>` | S | `04-api/search-api.md` | |
| SRCH-04 | User can update a search app via `PUT /searches/<search_id>` | S | `04-api/search-api.md` | |
| SRCH-05 | User can delete a search app | S | `04-api/search-api.md` | Inferred from handler `delete_search` `[C-13]` |
| SRCH-06 | Search-bot Q&A via `POST /api/v1/searchbots/ask` (`question`, `kb_ids`) with beta auth | L | `04-api/endpoint-catalog.md` | Go-owned; requires Go retrieval + LLM path |
| SRCH-07 | Search-bot retrieval test via `POST /api/v1/searchbots/retrieval_test` with beta auth | M | `04-api/endpoint-catalog.md` | Go-owned |

#### AGT — Agents

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| AGT-01 | User can create an agent (title, description, DSL) via `POST /api/v1/agents` | M | `04-api/endpoint-catalog.md` | |
| AGT-02 | User can list agents with paging/keywords via `GET /api/v1/agents` | S | `04-api/endpoint-catalog.md` | |
| AGT-03 | User can fetch an agent's canvas DSL via `GET /api/v1/agents/<agent_id>` | S | `04-api/endpoint-catalog.md` | |
| AGT-04 | User can save an agent's canvas via `PUT /agents/<agent_id>` | M | `04-api/agent-api.md` | Not in master catalog |
| AGT-05 | User can delete an agent via `DELETE /api/v1/agents/<agent_id>` | S | `04-api/endpoint-catalog.md` | |
| AGT-06 | User can run an agent and receive an SSE stream via `POST /api/v1/agents/chat/completions` (`agent_id`, `message`, `stream`) | L | `13-agents/agent-api.md`, `21-.../agent-execution.md` | |
| AGT-07 | User can list, create, delete one, and bulk-delete agent sessions under `/agents/<agent_id>/sessions` | M | `04-api/agent-api.md` | Handler mismatch `[C-13]` |
| AGT-08 | User can list agent templates (`CanvasTemplate`) | S | `04-api/agent-api.md`, `02-frontend/routing.md` | `[P]`; no clean route |
| AGT-09 | User can fetch agent prompt presets via `GET /agents/prompts` | S | `04-api/agent-api.md` | `[P]` |
| AGT-10 | User can list agent tags via `GET /agents/tags` and set an agent's tags via `PUT /agents/<canvas_id>/tags` | S | `04-api/agent-api.md` | `[P]` |
| AGT-11 | User can debug a single component via `POST /agents/<agent_id>/components/<component_id>/debug` (queued as a `dataflow` task) | M | `13-agents/agent-api.md` | |
| AGT-12 | User can list and fetch agent versions via `GET /agents/<agent_id>/versions[/<version_id>]` | M | `04-api/agent-api.md` | `UserCanvasVersion` |
| AGT-13 | User can fetch the execution log of a message via `GET /agents/<agent_id>/logs/<message_id>` | M | `04-api/agent-api.md` | |
| AGT-14 | Agent component runs a tool-calling loop up to `max_rounds` (default 5); returns the final answer or a max-rounds warning | L | `13-agents/agent-flow.md` | |
| AGT-15 | Bound tools get indexed function names (`google_search_0`) to prevent collisions | S | `13-agents/agent-architecture.md` | |
| AGT-16 | Agent supports native function-calling mode and ReAct prompt mode | M | `13-agents/planning.md` | |
| AGT-17 | Agent can enforce structured JSON output with repair | M | `13-agents/planning.md` | |
| AGT-18 | An agent can be exposed as a tool to a supervising agent (`user_prompt`, `reasoning`, `context`) | M | `13-agents/planning.md` | |
| AGT-19 | Agent can call tools on external MCP servers over SSE or stdio, with schemas translated to OpenAI tool format | L | `13-agents/tools.md` | |
| AGT-20 | Tool observations are appended to the scratchpad as `tool` messages | S | `13-agents/memory.md` | |
| AGT-21 | Agent output is written to canvas globals for downstream nodes | S | `13-agents/memory.md` | |
| AGT-22 | RAG agent preset: query rewrite, parallel multi-KB retrieval, rerank, cited generation | L | `13-agents/rag-agent.md` | |
| AGT-23 | Tool: Retrieval (knowledge base) | M | `13-agents/tools.md` | |
| AGT-24 | Tool: Google Custom Search | S | `13-agents/tools.md` | |
| AGT-25 | Tool: DuckDuckGo | S | `13-agents/tools.md` | |
| AGT-26 | Tool: Tavily | S | `13-agents/tools.md` | |
| AGT-27 | Tool: ArXiv | S | `13-agents/tools.md` | |
| AGT-28 | Tool: PubMed | S | `13-agents/tools.md` | |
| AGT-29 | Tool: DeepL translation | S | `13-agents/tools.md` | |
| AGT-30 | Tool: ExeSQL (SQL query execution) | M | `13-agents/tools.md` | |
| AGT-31 | Tool: QWeather | S | `13-agents/tools.md` | |
| AGT-32 | Tools: financial data (Tushare, AkShare, Yahoo Finance) | M | `13-agents/tools.md` | |
| AGT-33 | Tools: SearxNG, Bing, Querit, Google Scholar | M | `17-integrations/search-integrations.md` | `[P]` |
| AGT-34 | Tool: code execution sends LLM-written code to the sandbox and returns stdout/stderr/result | L | `13-agents/execution.md` | |
| AGT-35 | Sandbox executor manager service: `POST /execute`, pre-warmed container pool, timeout, memory cap, no-new-privileges, no network, optional seccomp | XL | `13-agents/execution.md`, `20-security/file-security.md`, `18-.../docker-compose.md` | Limits and languages `[C-15]` |
| AGT-36 | Agents can be triggered by webhook `POST /v1/agent/<agent_id>/webhook` with security validation | M | `21-.../workflow-execution.md` | |
| AGT-37 | Each run executes against an immutable snapshot of the canvas (`CanvasReplicaService`) | M | `21-.../workflow-execution.md` | |
| AGT-38 | Run traces, component timings, inputs, and outputs are persisted per session | M | `21-.../workflow-execution.md` | Table name `agent_session` vs `API4Conversation` `[C-7]` |
| AGT-39 | Go Eino agent runtime | XL | `13-agents/agent-overview.md` | `[DUAL]` `[C-20]` |

#### FLOW — Workflow canvas engine

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| FLOW-01 | Workflows are serialized as JSON DSL with `components`, `history`, `retrieval`, `globals`, `path`; each component has `obj`, `downstream`, `upstream` | M | `14-workflows/workflow-overview.md`, `14-workflows/edges.md` | |
| FLOW-02 | Graph engine loads a DSL, instantiates components, and executes from `begin` following downstream edges | L | `14-workflows/workflow-engine.md` | |
| FLOW-03 | DSL is validated before run: unknown components and cycles are rejected | M | `14-workflows/workflow-engine.md` | |
| FLOW-04 | Conditional nodes forward control only along the matched branch; unselected paths are skipped | M | `14-workflows/edges.md` | |
| FLOW-05 | System variables `sys.query`, `sys.user_id`, `sys.conversation_turns`, `sys.files` | S | `14-workflows/variables.md` | |
| FLOW-06 | Node parameters interpolate `{component_id.field}` and `{sys.*}` before execution | M | `14-workflows/variables.md` | |
| FLOW-07 | Node: Begin (inputs) | S | `14-workflows/nodes.md` | |
| FLOW-08 | Node: Generate / LLM | M | `14-workflows/nodes.md` | |
| FLOW-09 | Node: Retrieval | M | `14-workflows/nodes.md` | |
| FLOW-10 | Node: Categorize (LLM intent classification) | M | `14-workflows/nodes.md` | |
| FLOW-11 | Node: Switch (condition expressions in priority order) | M | `14-workflows/nodes.md` | |
| FLOW-12 | Node: AgentWithTools | S | `14-workflows/nodes.md` | Wraps AGT-14 |
| FLOW-13 | Node: Message (streams reply to client) | S | `14-workflows/nodes.md` | "Answer" in other docs `[C-19]` |
| FLOW-14 | Node: Loop (inner subgraph until condition) | L | `14-workflows/nodes.md` | |
| FLOW-15 | Node: Iteration (over array items) | L | `14-workflows/nodes.md` | |
| FLOW-16 | Node: ExitLoop | S | `14-workflows/nodes.md` | |
| FLOW-17 | Node: VariableAggregator | S | `14-workflows/nodes.md` | |
| FLOW-18 | Node: VariableAssigner | S | `14-workflows/nodes.md` | |
| FLOW-19 | Node: ListOperations (filter, sort, index, concat) | M | `14-workflows/nodes.md` | |
| FLOW-20 | Node: DataOperations (JSON/dict) | M | `14-workflows/nodes.md` | |
| FLOW-21 | Node: StringTransform (regex, split/join, format) | S | `14-workflows/nodes.md` | |
| FLOW-22 | Node: ExcelProcessor | M | `14-workflows/nodes.md` | |
| FLOW-23 | Node: DocsGenerator (Word/PDF report from template) | L | `14-workflows/nodes.md` | |
| FLOW-24 | Node: Fillup (human-in-the-loop form) | M | `14-workflows/nodes.md` | |
| FLOW-25 | Node: Invoke (external HTTP request) | M | `14-workflows/nodes.md` | SSRF guard needed |
| FLOW-26 | Node: Browser (headless scraping) | L | `14-workflows/nodes.md` | |
| FLOW-27 | Node: Code (Python via sandbox) | M | `02-frontend/agent-ui.md`, `21-.../agent-execution.md` | Not in the `14-workflows/nodes.md` catalog `[C-19]` |
| FLOW-28 | Nodes: Image Generate, Keyword Extract, Rewrite | M | `02-frontend/agent-ui.md`, `00-overview/high-level-architecture.md` | `[P]` — names only `[C-19]` |
| FLOW-29 | Parallel branch execution | L | `14-workflows/workflow-engine.md` | Go subgraph only; no node in the catalog `[C-19]` |
| FLOW-30 | Runs stream SSE events `workflow_started`, `node_started`, `node_finished`, `message`, `workflow_finished` wrapped as `{type, data, message_id, created_at, session_id}` | M | `14-workflows/workflow-execution-flow.md` | Event names differ in `21-...` `[C-14]` |
| FLOW-31 | `node_started` carries inputs, component id/name/type, thoughts; `node_finished` adds outputs and `elapsed_time` | S | `14-workflows/workflow-execution-flow.md` | |
| FLOW-32 | Canvas state is checkpointed after each node to Redis/MySQL | L | `14-workflows/execution.md` | Described for the Go runner only |
| FLOW-33 | A Fillup node pauses the run, emits `waiting_for_user`, and resumes from checkpoint when the user submits input | L | `14-workflows/execution.md` | Resume endpoint not specified |
| FLOW-34 | User can cancel a running workflow | M | `14-workflows/execution.md` | `[P]` — "job cancellation" |
| FLOW-35 | Plugin manager discovers and loads tool plugins at server start | M | `14-workflows/tools.md`, `03-backend/entry-points.md` | |
| FLOW-36 | User can list plugin tools via `GET /plugin/tools` | S | `04-api/plugin-api.md` | |
| FLOW-37 | Go Eino DAG compiler and runner | XL | `14-workflows/workflow-engine.md` | `[DUAL]` `[C-20]` |

#### MCP — Model Context Protocol

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| MCP-01 | MCP server at `POST /api/v1/mcp` speaking JSON-RPC, with beta auth | L | `04-api/endpoint-catalog.md` | Go-owned; port 9382 also named `[C-1]` |
| MCP-02 | MCP server exposes dataset search and chat assistants as tools | M | `17-integrations/integrations-overview.md` | |
| MCP-03 | User can list registered external MCP servers via `GET /mcp/servers` (`MCPServer` entity) | M | `04-api/mcp-api.md` | Create/update/delete routes not documented `[C-13]` |

#### CONN — Data-source connectors

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| CONN-01 | User can get a connector via `GET /connectors/<connector_id>` | S | `04-api/connector-api.md` | `[P]` — no connector types documented anywhere |
| CONN-02 | User can update a connector via `PATCH /connectors/<connector_id>` | M | `04-api/connector-api.md` | `[P]` `[C-13]` |
| CONN-03 | User can view sync logs via `GET /connectors/<connector_id>/logs` | S | `04-api/connector-api.md` | `[P]` |
| CONN-04 | User can trigger a rebuild via `POST /connectors/<connector_id>/rebuild` | M | `04-api/connector-api.md` | `[P]` |
| CONN-05 | User can test a connector via `POST /connectors/<connector_id>/test` | M | `04-api/connector-api.md` | `[P]` |
| CONN-06 | Connectors link to datasets (`Connector2Kb`) and write `SyncLogs` | M | `08-database/entities.md` | `[P]` |

#### CHAN — Chat channels (messaging integrations)

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| CHAN-01 | User can create/list chat channels via `POST /chat-channels` | M | `04-api/chat_channel-api.md` | Handler mismatch `[C-13]` |
| CHAN-02 | User can get, update, and remove a channel via `/chat-channels/<channel_id>` | M | `04-api/chat_channel-api.md` | |
| CHAN-03 | User can read a channel's runtime status via `GET /chat-channels/<channel_id>/runtime` | S | `04-api/chat_channel-api.md` | |
| CHAN-04 | A reconciliation loop (every 10s) starts, stops, and reloads channel bots from the `chat_channel` table by credential fingerprint, without server restart | L | `17-integrations/external-services.md` | |
| CHAN-05 | Channel: Feishu / Lark | L | `17-integrations/external-services.md` | Requires third-party credentials to verify |
| CHAN-06 | Channel: DingTalk | L | `17-integrations/external-services.md` | Same |
| CHAN-07 | Channel: WeCom | L | `17-integrations/external-services.md` | Same |
| CHAN-08 | Channel: Discord | L | `17-integrations/external-services.md` | Same |
| CHAN-09 | Channel: Telegram | L | `17-integrations/external-services.md` | Same |
| CHAN-10 | Channel: LINE | L | `17-integrations/external-services.md` | Same |
| CHAN-11 | Channel: WhatsApp | L | `17-integrations/external-services.md` | Same |
| CHAN-12 | Channel: QQ Bot | L | `17-integrations/external-services.md` | Same |

#### TMPL — Compilation templates and dataflow

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| TMPL-01 | User can list built-in compilation templates via `GET /compilation-templates/builtins` | S | `04-api/compilation_template-api.md` | `[P]` — "compilation" is never defined in the docs |
| TMPL-02 | User can list wiki presets via `GET /compilation-templates/wiki-presets` | S | `04-api/compilation_template-api.md` | `[P]` |
| TMPL-03 | User can list, view, create, and delete template groups under `/compilation-template-groups` | M | `04-api/compilation_template_group-api.md` | `[P]` `[C-13]` |
| TMPL-04 | Dataflow result viewer shows stage-by-stage pipeline results | M | `02-frontend/workflow-ui.md` | `[P]` |

#### SYS — System, health, stats

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| SYS-01 | `GET /health` returns service health without auth | S | `04-api/endpoint-catalog.md` | Health path variants `[C-21]` |
| SYS-02 | `GET /api/v1/system/ping` | S | `04-api/endpoint-catalog.md` | |
| SYS-03 | `GET /api/v1/system/config` returns public configuration | S | `04-api/endpoint-catalog.md` | |
| SYS-04 | `GET /api/v1/system/version` | S | `04-api/endpoint-catalog.md` | |
| SYS-05 | `GET /api/v1/language` reports which engine answered (`go` / `python`) | S | `04-api/endpoint-catalog.md` | |
| SYS-06 | `GET /system/status` reports dependency status (database, Redis, storage, docstore) | M | `04-api/system-api.md` | |
| SYS-07 | `GET /system/healthz` | S | `04-api/system-api.md` | |
| SYS-08 | `GET /system/oceanbase/status` | S | `04-api/system-api.md` | `[P]`; only meaningful with OceanBase |
| SYS-09 | `GET /system/stats` returns usage statistics | M | `04-api/stats-api.md` | `[P]` — metric set undocumented |

#### API — API-layer conventions and backend cross-cutting

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| API-01 | Two backend servers: Go (Gin) for auth/user/tenant/system/search-bot/MCP; Python (Quart) for datasets/documents/chat/agents | XL | `apis.md`, `04-api/api-overview.md`, `03-backend/backend-overview.md` | Ports `[C-1]` |
| API-02 | Path-based routing in the reverse proxy sends each prefix to the owning server | M | `apis.md`, `00-overview/architecture-diagram.md` | |
| API-03 | All JSON responses use one envelope with numeric code, message, data | S | `04-api/api-overview.md` | Field names `[C-7]` |
| API-04 | Routes are versioned under `/api/v1` and `/v1` | S | `04-api/api-overview.md` | |
| API-05 | Go responses carry `X-API-Source: go` | S | `03-backend/backend-architecture.md` | |
| API-06 | Layered Handler, Service, DAO/Model structure in both servers | M | `03-backend/backend-architecture.md` | |
| API-07 | Request bodies are schema-validated before reaching services | M | `20-security/api-security.md` | |
| API-08 | OpenAPI v3 schema is generated for the Python API | S | `04-api/api-overview.md`, `00-overview/technology-stack.md` | |
| API-09 | Unhandled exceptions return a standardized error envelope | S | `03-backend/middleware.md` | |
| API-10 | Request logging: method, path, status, duration | S | `03-backend/middleware.md` | |
| API-11 | CORS middleware | S | `03-backend/middleware.md` | Policy `[C-25]` |
| API-12 | Go server run modes via flags: `--api`, `--admin`, `--ingestor`, `--syncer`, `--migrate` | M | `03-backend/entry-points.md` | |
| API-13 | Python server boot: logger, DB init, optional superuser init, plugin load, background daemons | M | `03-backend/entry-points.md` | |
| API-14 | Python/HTTP SDK client | L | `00-overview/architecture-diagram.md`, `04-api/api-overview.md` | `[P]` — named as a client type only |

#### ADMIN — Administration

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| ADMIN-01 | Separate admin API server (ports 9381 Python, 9383 Go) with admin login | L | `18-deployment/services.md`, `15-cli/commands.md` | `[DUAL]` |
| ADMIN-02 | Admin can list backend services and view one service's health, PID, host, memory | M | `15-cli/commands.md` | |
| ADMIN-03 | Admin can start, stop, restart a service | L | `15-cli/commands.md` | |
| ADMIN-04 | Admin can ping store, engine, MQ, and cache dependencies with latency | M | `15-cli/commands.md` | |
| ADMIN-05 | Admin can list, show, and drop users across tenants | M | `15-cli/commands.md` | |
| ADMIN-06 | Admin dashboard restricted to owner/admin shows system health metrics | M | `16-auth/permissions.md`, `02-frontend/routing.md` | |
| ADMIN-07 | Superuser bootstrap on first start (`--init-superuser`) | S | `03-backend/entry-points.md` | |

#### CLI — Command-line interface

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| CLI-01 | Go CLI binary with interactive REPL: line editing, auto-completion, persistent history | L | `15-cli/cli-overview.md`, `15-cli/command-entry-points.md` | |
| CLI-02 | Single-command batch mode | S | `15-cli/command-entry-points.md` | |
| CLI-03 | Hand-written lexer and recursive-descent parser for the SQL-like grammar | L | `15-cli/cli-execution-flow.md` | |
| CLI-04 | Output formats `table`, `plain`, `json` | M | `15-cli/cli-overview.md` | |
| CLI-05 | Flags: `-h/--host`, `-t/--token`, `-u/--user`, `-p/--password`, `-f/--config`, `-o/--output`, `-v/--verbose`, `--admin`, `--help` | S | `15-cli/configuration.md` | |
| CLI-06 | `rf.yml` config with named `api_servers` profiles | S | `15-cli/configuration.md` | |
| CLI-07 | Config precedence: flags, then `rf.yml`, then environment, then defaults | S | `15-cli/configuration.md` | |
| CLI-08 | `LOGIN USER`, `LOGOUT`, `REGISTER USER` | M | `15-cli/commands.md` | CLI endpoint paths `[C-24]` |
| CLI-09 | `CREATE DATASET`, `LIST DATASETS`, `DROP DATASET`, `SHOW DATASET` | M | `15-cli/commands.md` | |
| CLI-10 | `IMPORT FILE ... INTO DATASET`, `PARSE DOCUMENT`, `LIST DOCUMENTS`, `LIST CHUNKS` | M | `15-cli/commands.md` | |
| CLI-11 | `SEARCH '<q>' ON DATASETS ... WITH top_k / similarity_threshold / vector_similarity_weight / keyword` | M | `15-cli/commands.md` | |
| CLI-12 | `SET` / `RESET DEFAULT LLM` and `DEFAULT EMBEDDING` | S | `15-cli/commands.md` | |
| CLI-13 | Virtual filesystem: `ls`, `cat`, `mkdir`, `rm`, `search` over `/datasets/{name}/...` | L | `15-cli/commands.md` | |
| CLI-14 | `skill install` / `skill uninstall` | M | `15-cli/commands.md` | `[P]` — `/v1/skill/*` is undocumented elsewhere |
| CLI-15 | Admin mode commands (services, users, roles, ping) | L | `15-cli/commands.md` | Depends on ADMIN |
| CLI-16 | Meta commands `\h`, `\q`, `\c <host:port>`, `\mode <api|admin>`, `\output <fmt>` | S | `15-cli/commands.md` | |
| CLI-17 | Graceful cleanup on SIGINT/SIGTERM | S | `15-cli/command-entry-points.md` | |
| CLI-18 | Benchmark runner | M | `15-cli/cli-overview.md` | `[P]` — a file name |

#### UI — Frontend SPA

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| UI-01 | SPA with lazy-loaded routes and layout wrappers (standard with header, full-bleed for canvas) | M | `02-frontend/routing.md` | |
| UI-02 | Auth guard redirects unauthenticated users to the login route | S | `02-frontend/routing.md` | `/login` vs `/login-next` |
| UI-03 | HTTP client injects the bearer token, unwraps the envelope, surfaces non-zero codes as error notifications | M | `02-frontend/api-client.md` | |
| UI-04 | HTTP 401 clears the token and session cache and redirects to login | S | `02-frontend/api-client.md` | |
| UI-05 | SSE client streams tokens into UI state | M | `02-frontend/api-client.md` | |
| UI-06 | Login and registration page | M | `02-frontend/authentication.md` | OAuth buttons depend on AUTH-24 |
| UI-07 | Session recovery on refresh by re-fetching user info | S | `02-frontend/authentication.md` | |
| UI-08 | Tiered state: global stores (user, agent, chat, document), server-state hooks with caching/polling, local state, URL search params | M | `02-frontend/state-management.md` | |
| UI-09 | Home dashboard | M | `02-frontend/routing.md` | `[P]` — "System dashboard & summary" |
| UI-10 | Datasets gallery with card grid and create-dataset dialog | M | `02-frontend/knowledge-base-ui.md` | |
| UI-11 | Dataset workspace: document table with status badges | M | `02-frontend/knowledge-base-ui.md` | |
| UI-12 | Upload dialog: drag-and-drop, extension and size validation, progress bars | M | `02-frontend/document-upload-ui.md` | |
| UI-13 | Chunking-method dialog (General, Q&A, Paper, Book, Laws, Presentation, Table, Manual) | M | `02-frontend/components.md` | Option list varies `[C-19]` |
| UI-14 | Parser configurator: chunk token size, delimiter, layout-model toggle, auto-keyword count | M | `02-frontend/document-upload-ui.md` | "overlap" control named in `components.md` only |
| UI-15 | Live parsing progress bars, status badges (UNSTART, RUNNING, SUCCESS, FAIL), error log display | M | `02-frontend/document-upload-ui.md` | Polling |
| UI-16 | Chunk inspector: original document with highlighted bounding boxes beside chunk text | L | `02-frontend/knowledge-base-ui.md`, `02-frontend/components.md` | |
| UI-17 | Chunk editor: edit text, toggle availability, add chunk | M | `02-frontend/knowledge-base-ui.md` | |
| UI-18 | Retrieval-testing page: query input, similarity slider, vector/keyword weight, hit list with scores | M | `02-frontend/knowledge-base-ui.md` | |
| UI-19 | Document viewer page | M | `02-frontend/pages.md` | `[P]` |
| UI-20 | Chat playground: session sidebar, message list, input bar | L | `02-frontend/chat-ui.md` | |
| UI-21 | Streaming token rendering with stop-generation control | M | `02-frontend/chat-ui.md`, `02-frontend/components.md` | |
| UI-22 | Markdown rendering: GFM, syntax-highlighted code with copy button, KaTeX math, image popovers | M | `02-frontend/components.md` | |
| UI-23 | Citation pills that open a drawer with chunk text and PDF bounding-box highlight | L | `02-frontend/chat-ui.md` | |
| UI-24 | Feedback buttons and hit scores on assistant messages | S | `02-frontend/components.md` | |
| UI-25 | Assistant configuration: dataset selection, LLM select, LLM setting sliders, similarity slider | M | `02-frontend/components.md` | |
| UI-26 | Public shared chat page and embeddable chat widget (`/chats/share`, `/chats/widget`), unauthenticated | M | `02-frontend/routing.md`, `02-frontend/chat-ui.md` | |
| UI-27 | Agents list page with templates | M | `02-frontend/routing.md` | |
| UI-28 | Agent canvas: node palette, drag-and-drop graph, edge connections | XL | `02-frontend/agent-ui.md` | `@xyflow/react` |
| UI-29 | Per-node configuration drawer (LLM, Retrieval, Code, Switch, Categorize, and remaining node types) | XL | `02-frontend/agent-ui.md` | One form per FLOW node |
| UI-30 | Run and debug log sheet with node execution-status animation | L | `02-frontend/agent-ui.md`, `02-frontend/frontend-architecture.md` | |
| UI-31 | Embedded code editor in the Code node form | M | `02-frontend/agent-ui.md` | |
| UI-32 | Public shared agent page (`/agent/share`) | M | `02-frontend/routing.md` | |
| UI-33 | Search app pages (`next-search`, `next-searches`) | L | `02-frontend/pages.md` | `[P]` — page names only |
| UI-34 | User settings: profile | S | `02-frontend/directory-structure.md` | |
| UI-35 | User settings: API key management dialog | M | `02-frontend/directory-structure.md` | |
| UI-36 | User settings: team management | M | `02-frontend/directory-structure.md` | |
| UI-37 | User settings: model provider credentials and default models | L | `02-frontend/frontend-overview.md` | |
| UI-38 | Admin pages: users, services | M | `02-frontend/routing.md` | |
| UI-39 | Compilation templates studio and pipeline operator tabs | L | `02-frontend/workflow-ui.md` | `[P]` |
| UI-40 | Knowledge-graph structure visualization | L | `02-frontend/components.md` | `[P]` |
| UI-41 | Pages `files`, `skills`, `memory`, `memories` | L | `02-frontend/pages.md` | `[P]` — bare names; no backing API documented |
| UI-42 | Internationalization with locale files (zh, en, es, fr, ja, ...) | M | `02-frontend/directory-structure.md` | |
| UI-43 | Dark / light theme | S | `02-frontend/state-management.md` | |
| UI-44 | Loading, error, and empty states on every data view; responsive layout | M | `spec.md` (Frontend) | |

#### DATA — Relational database layer

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| DATA-01 | MySQL schema for the documented entities (User, Tenant, UserTenant, InvitationCode, LLMFactories, LLM, TenantLLM, TenantLangfuse, Knowledgebase, Document, File, File2Document, Task, Dialog, Conversation, APIToken, API4Conversation, UserCanvas, CanvasTemplate, UserCanvasVersion, MCPServer, Search, Connector, Connector2Kb, ChatChannel, SyncLogs, PipelineOperationLog, CompilationTemplate, CompilationTemplateGroup, Memory, SystemSettings, FileCommit, FileCommitItem, TenantModel*) | L | `08-database/entities.md`, `08-database/schema.md` | Only `document`, `task`, `knowledgebase` have full DDL; the rest are names |
| DATA-02 | Documented secondary indexes on `document`, `task`, `knowledgebase`, `file` | S | `08-database/indexes.md` | |
| DATA-03 | Pooled connections with retry and exponential backoff on connection loss (5 retries) | M | `08-database/database-overview.md` | |
| DATA-04 | Multi-step mutations run in transactions | S | `08-database/transactions.md` | |
| DATA-05 | Schema migrations (column add, type change, index creation); `--migrate` flag on the Go server | M | `08-database/migrations.md` | |
| DATA-06 | Both servers share one schema (Peewee models and GORM structs) | L | `08-database/database-overview.md` | `[DUAL]`; drift risk |
| DATA-07 | PostgreSQL and OceanBase as alternative relational backends | L | `08-database/database-overview.md` | `[P]` — listed as supported; MySQL is the compose default |
| DATA-08 | DB-backed lock (`DatabaseLock`) | S | `08-database/entities.md` | `[P]` |

#### DEPLOY — Deployment

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| DEPLOY-01 | Multi-stage production image bundling web build, Python env, Go binaries, Nginx | L | `18-deployment/docker.md` | |
| DEPLOY-02 | Base compose file for infrastructure: MySQL 8, Redis/Valkey, MinIO, with health checks and named volumes | M | `18-deployment/docker-compose.md` | |
| DEPLOY-03 | Application compose file with `cpu` profile; app waits for MySQL healthy | M | `18-deployment/docker-compose.md` | |
| DEPLOY-04 | Vector-engine profiles: `elasticsearch`, `infinity` | M | `18-deployment/docker-compose.md` | One must be the default |
| DEPLOY-05 | Additional engine profiles: `opensearch`, `oceanbase`, `serenedb`, `seekdb`, `clickhouse` | L | `18-deployment/docker-compose.md` | Tied to IDX-11..13 |
| DEPLOY-06 | `gpu` profile with NVIDIA pass-through | M | `18-deployment/deployment-overview.md` | Cannot be verified without GPU hardware |
| DEPLOY-07 | `sandbox` profile running the executor manager | M | `18-deployment/docker-compose.md` | |
| DEPLOY-08 | `deepdoc` profile running the layout-parsing service on 9390 | M | `18-deployment/docker-compose.md` | |
| DEPLOY-09 | `ragflow-go` profile with NATS | M | `18-deployment/docker-compose.md` | `[C-2]` |
| DEPLOY-10 | Entrypoint renders `service_conf.yaml` from a template with environment substitution, then starts Nginx, Go server, Python server, task executor | M | `18-deployment/deployment-flow.md` | |
| DEPLOY-11 | `.env`-driven configuration covering the documented variable catalog | M | `18-deployment/environment-variables.md` | |
| DEPLOY-12 | Nginx reverse proxy: serves the SPA, routes API prefixes, TLS termination, SSE-safe buffering | M | `18-deployment/production-architecture.md` | |
| DEPLOY-13 | Single bridge network with service DNS aliases; only documented ports exposed | S | `18-deployment/networking.md` | |
| DEPLOY-14 | Container health check on the app health endpoint every 10s | S | `18-deployment/deployment-flow.md` | Path `[C-21]` |
| DEPLOY-15 | MySQL initialized from `init.sql` on first boot | S | `18-deployment/deployment-flow.md` | Overlaps DATA-05 |
| DEPLOY-16 | Logs bind-mounted to host | S | `18-deployment/volumes.md` | |
| DEPLOY-17 | Standalone task-executor container for horizontal scaling | M | `18-deployment/production-architecture.md` | |
| DEPLOY-18 | TEI (text-embeddings-inference) image for local embedding/rerank | M | `18-deployment/docker.md` | `[P]` |
| DEPLOY-19 | Helm chart / Kubernetes deployment | L | `18-deployment/deployment-overview.md`, `00-overview/repository-map.md` | `[P]` |
| DEPLOY-20 | Compose variants for macOS and China mirrors | S | `18-deployment/deployment-overview.md` | `[P]` |
| DEPLOY-21 | Documented setup instructions that bring the stack up from a clean checkout | S | `spec.md` (Completion Criteria 7) | |

#### SEC — Security

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| SEC-01 | Every non-public endpoint is behind the auth decorator/middleware | M | `20-security/api-security.md` | Audit test over the route table |
| SEC-02 | API keys, access tokens, and LLM credentials are masked in API responses | S | `20-security/api-security.md` | |
| SEC-03 | LLM provider keys are encrypted at rest | M | `20-security/secrets.md` | |
| SEC-04 | Secrets come from environment/config, never hard-coded, never logged | S | `20-security/secrets.md` | |
| SEC-05 | Restricted unpickler allows only whitelisted modules (`numpy`, `rag_flow`) | S | `20-security/file-security.md` | Applies only if pickle is used at all |
| SEC-06 | Upload safety: extension check, sanitized names, UUID object keys, no path traversal | S | `20-security/file-security.md` | |
| SEC-07 | Sandboxed code runs as non-root with memory cap, timeout, no-new-privileges, no network, seccomp filter | L | `20-security/file-security.md` | Part of AGT-35 |
| SEC-08 | Native document parsing isolated in the `deepdoc` container | M | `20-security/attack-surface.md` | Tied to PARSE-24 |
| SEC-09 | Tokens validated with an HMAC-signed secret key and expiry | S | `20-security/attack-surface.md` | `[C-11]` |
| SEC-10 | Input validation prevents SQL and command injection | M | `20-security/api-security.md` | |
| SEC-11 | Rate limiting backed by Redis | M | `00-overview/technology-stack.md`, `18-deployment/services.md`, `20-security/api-security.md` | `[P]` — named as a Redis role; no limits or policy documented |

#### TEST — Testing

| ID | Feature | Cx | Source | Notes |
|---|---|---|---|---|
| TEST-01 | Python unit tests (services, API, RAG) run by pytest via a `run_tests.py` runner with coverage and parallel options | L | `19-testing/testing-overview.md`, `19-testing/backend-tests.md` | |
| TEST-02 | Python API integration/E2E test cases against a running stack | L | `19-testing/testing-overview.md` | |
| TEST-03 | Go unit tests (`go test ./internal/...`, with `-race`) | L | `19-testing/backend-tests.md` | |
| TEST-04 | Go test tiers by build tag: `integration`, `e2e`, `manual`, `cgo` | M | `19-testing/test-architecture.md` | `cgo` tier only if PARSE-26 is built |
| TEST-05 | CLI lexer/parser unit tests | S | `19-testing/unit-tests.md` | |
| TEST-06 | Canvas state-machine unit tests and state benchmarks | M | `19-testing/unit-tests.md` | |
| TEST-07 | Sandbox security tests (seccomp, memory limit, blocked modules) | M | `19-testing/unit-tests.md` | |
| TEST-08 | Vector-engine integration tests against live engines | M | `19-testing/integration-tests.md` | |
| TEST-09 | Sandbox RPC integration tests | S | `19-testing/integration-tests.md` | |
| TEST-10 | Frontend component tests (React Testing Library with Jest or Vitest) | M | `19-testing/frontend-tests.md` | |
| TEST-11 | Database tests and pipeline tests | M | `spec.md` (Testing) | |
| TEST-12 | Performance benchmarks | M | `19-testing/testing-overview.md` | `[P]` — a directory name |

#### E2E — Acceptance flows (must each pass against the real stack, no mocks)

| ID | Flow | Depends on | Source |
|---|---|---|---|
| E2E-01 | User registration creates user, tenant, owner link | AUTH-01..04 | `21-end-to-end-flows/user-registration.md` |
| E2E-02 | Login returns token, user, tenant, default models | AUTH-05..07 | `21-.../login.md` |
| E2E-03 | Create knowledge base provisions DB row and docstore index | KB-01..03, IDX-05 | `21-.../create-knowledge-base.md` |
| E2E-04 | Upload document stores blob and creates UNSTART document | DOC-01..07, STOR | `21-.../upload-document.md` |
| E2E-05 | Document processing: parse request, queue, worker, DeepDoc, chunks | DOC-09, ING, PARSE, CHUNK | `21-.../document-processing.md` |
| E2E-06 | Indexing: embed, optional enrichment, bulk insert, document finished | IDX, CHUNK-22..26 | `21-.../indexing.md` |
| E2E-07 | Ask question: tokenize, embed query, concurrent BM25 + vector search | RETR-01..08 | `21-.../ask-question.md` |
| E2E-08 | RAG answer: rerank, format context with citations, generate, persist | RETR-11, CHAT-16..21 | `21-.../rag-answer.md` |
| E2E-09 | Chat streaming over SSE with reference payload and final persistence | CHAT-12, CHAT-13, UI-21, UI-23 | `21-.../chat-streaming.md` |
| E2E-10 | Agent execution: load DSL, run graph, stream node events | AGT-06, FLOW | `21-.../agent-execution.md` |
| E2E-11 | Workflow execution by webhook with replica snapshot and session persistence | AGT-36..38 | `21-.../workflow-execution.md` |
| E2E-12 | One request, full story: upload through cited streamed answer in the UI | all of the above | `21-.../ragflow-one-request.md` |

---

### Needs User Decision (present in `docs/` but not a devRag specification)

`docs/apis.md` lines 140-2080 are a pasted question-and-answer ("how to design production level api key system ... they paid 5 dollars and get some amount of call") describing a generic metered API platform. It is not written about RAGFlow or devRag, and its architecture contradicts the rest of `docs/` (PostgreSQL instead of MySQL; Stripe, Kafka, ClickHouse, Kong not present anywhere else). The off-limits `docs/apikey llm.md` may be related; it was not opened.

Because "anything explicitly documented in `docs/`" is table stakes under this project's rule, this block cannot be silently dropped or silently adopted. Recommendation: treat as OUT of v1 until the user confirms, because adopting it adds a payment provider and a billing ledger that no other doc, flow, UI page, or endpoint references.

| ID | Capability described | Cx | Notes |
|---|---|---|---|
| BILL-01 | API keys stored as SHA-256 hash plus prefix, shown once, with ACTIVE/REVOKED/EXPIRED states, `last_used_at`, expiry | M | Conflicts with documented `APIToken` table (plaintext `token` column, tenant_id as primary key) |
| BILL-02 | Multiple keys per organization with rotation overlap | M | |
| BILL-03 | Per-key permission scopes | M | |
| BILL-04 | Redis rate limiting per key/organization (token bucket or sliding window), HTTP 429 | M | Overlaps SEC-11 |
| BILL-05 | Plans and subscriptions | L | |
| BILL-06 | Prepaid credit account with append-only ledger and atomic deduction; HTTP 402 at zero | L | |
| BILL-07 | Per-endpoint / per-token cost metering and usage events | L | |
| BILL-08 | Stripe checkout with verified webhook crediting | L | New external dependency |
| BILL-09 | `Idempotency-Key` support on paid endpoints | M | |
| BILL-10 | Usage dashboard | M | |

---

### Differentiators (NOT described in `docs/` — defer)

Common in RAG products or present in the RAGFlow repository, but absent from `docs/`. Per `spec.md` ("RAGFlow must never override an explicit decision from `docs/`" and "do not introduce ... purely because RAGFlow uses them"), none of these are v1.

| Feature | Value Proposition | Cx | Notes |
|---|---|---|---|
| Full GraphRAG (entity/relation extraction, community reports, graph retrieval) | Multi-hop questions | XL | Docs contain only filter keys, a limiter name, a task-type string, and a UI component name. Not specified as behaviour |
| Retrieval evaluation harness (recall@k, MRR, answer faithfulness, golden sets) | Measurable retrieval quality | L | `spec.md` lists "evaluation" as something the pipeline "may include"; `docs/` documents no evaluation feature. Only the manual retrieval test (KB-18) exists |
| Agent long-term memory product (memory stores, extraction, recall) | Personalization across sessions | XL | `Memory` entity and `memory` page names only |
| Skills hub / marketplace | Reusable agent capabilities | L | CLI `skill install` and a page name only |
| Data-source connector catalog (Confluence, Notion, Google Drive, S3 sync, Slack, ...) | Continuous ingestion | XL | Docs give generic connector routes and no connector types |
| Web crawler / URL ingestion | Web pages as documents | M | Overview mentions "web pages" as a data type; no crawler is documented (HTML parser only) |
| Cross-language / multilingual query expansion | Recall across languages | M | Not in docs |
| TOC-enhanced / parent-child chunk retrieval | Better context windows | M | Not in docs |
| Text-to-SQL chat over tables | Structured data Q&A | L | Only the ExeSQL tool is documented |
| SSO via SAML, SCIM provisioning | Enterprise identity | L | Docs name only OAuth2/OIDC |
| Audit log of user actions | Compliance | M | Not in docs |
| Per-tenant storage/usage quotas with enforcement UI | Cost control | M | One phrase in the upload doc |
| Prometheus metrics / OpenTelemetry tracing | Operability | M | Docs specify Langfuse for LLM tracing only |
| Conversation export, share links with expiry | Collaboration | S | Not in docs |
| Mobile-specific UI | Reach | L | `spec.md` asks only for responsive behaviour |
| Document versioning (`FileCommit`) as a user feature | Change tracking | L | Entity names only |

---

### Anti-Features (forbidden by `docs/spec.md`)

| Anti-Feature | Why It Is Tempting | Why Forbidden / Problematic | Do Instead |
|---|---|---|---|
| Mocked or stubbed pipeline stages presented as complete (fake embeddings, canned LLM output, fake OCR) | Unblocks UI work without model weights or API keys | `spec.md`: no "mocked functionality presented as completed functionality"; Core Value requires the real pipeline | Use real local providers (Ollama, local ONNX models) for verification; mocks only inside unit tests |
| Placeholder, empty, or TODO-only functions | Fast scaffolding of 400+ features | `spec.md`: no placeholder implementations, empty functions, TODO-only implementations | Build fewer features per phase, each complete; document genuine blockers explicitly |
| Fake or seeded data where real data is expected | Nicer demos | `spec.md`: no "fake data where real implementation is expected" | Real fixtures ingested through the real pipeline |
| Silently skipping hard features (DLA/OCR/TSR, sandbox, Go engine, channels) | They are XL and research-heavy | `spec.md`: no "silently skipping difficult features" | Implement, or record a blocker with reason in project docs |
| Minimal demo / partial prototype scope | Faster "done" | `spec.md` Primary Goal: complete system | Full inventory above is v1 |
| Redesigning or simplifying the documented architecture (single backend, different queue, different storage model, different RAG pipeline) | Dual-stack is costly | `spec.md` Architecture Discipline: deviate only on genuine contradiction or blocker, and document it | Resolve the contradictions listed below explicitly and record each decision |
| New service, database, queue, framework, or abstraction not in `docs/` | Familiar tooling | `spec.md`: verify against documented architecture first | Smallest production-quality choice, documented |
| Copying RAGFlow source wholesale | It already works | `spec.md`: "Do not blindly copy RAGFlow"; reference only | Adapt patterns to the documented architecture |
| Cloning RAGFlow's visual appearance | Shortcut to a polished UI | `spec.md`: "Do not simply clone RAGFlow's visual appearance" | Reuse interaction patterns; own visual design |
| Adopting frameworks purely because RAGFlow uses them | Reference parity | `spec.md` Folder Structure rule 6 | Use only what `docs/` calls for |
| Undocumented deviations | Avoids process overhead | `spec.md` Documentation and Completion Criteria 9 | Record what, why, and how it fits |
| Giant files and tightly coupled modules | Speed | `spec.md` Backend Quality | Cohesive modules, typed interfaces |
| Declaring a feature complete from static inspection | Saves time | `spec.md` Verification: "not complete merely because code exists" | Realistic execution against the running stack |
| Moving forward with broken tests | Momentum | `spec.md` Testing | Fix, or document as a blocked dependency |

---

## Feature Dependencies

```
DEPLOY-02 (MySQL, Redis, MinIO, vector engine)
    └──required by──> DATA-01..05 ──> API-01..11 (both servers, envelope, errors)
                                          └──> AUTH-01..12 ──> TEN-01..05
                                                                  │
            ┌─────────────────────────────────────────────────────┤
            v                                                     v
   LLM-14..16 (tenant model config)                         AUTH-19..23 (API / beta tokens)
   LLM-01..09 (drivers)                                           │
            │                                                     └──> CHAT-26, SRCH-06/07, MCP-01
            v
   KB-01..03 (needs embedding dim + IDX-05 docstore abstraction + one of IDX-09/IDX-10)
            └──> STOR-01/02 ──> DOC-01..07 (upload)
                                   └──> ING-01..08 (tasks, queue, worker, progress)
                                           └──> PARSE-01..13 ──> CHUNK-01..17
                                                                    └──> IDX-01..07 (embed + index)
                                                                            └──> RETR-01..17
                                                                                    └──> CHAT-12..21 (streamed cited answer)
                                                                                            └──> UI-20..23

PARSE-04/06/07 (DLA, OCR, TSR) ──enhances──> PARSE-02 (PDF)       [PDF works on text layer first]
LLM-10 (vision)  ──required by──> CHUNK-10 (picture), PARSE-19 (figure captions)
LLM-11 (ASR)     ──required by──> CHUNK-15 (audio), PARSE-20
LLM-09 (rerank)  ──enhances──> RETR-11
CHUNK-22..26 (LLM enrichment, RAPTOR) ──enhance──> RETR-02 (boosted fields)
CHUNK-16 (positions) ──required by──> UI-16, UI-23 (bbox highlight)

FLOW-01..06 (DSL, engine, variables)
    └──> FLOW-07..26 (nodes) ──> AGT-06 (run) ──> FLOW-30/31 (events) ──> UI-28..30 (canvas)
FLOW-09 (Retrieval node), AGT-23 ──require──> RETR
FLOW-08 (LLM node), AGT-14 ──require──> LLM-01, LLM-33 (tool schema)
AGT-35 (sandbox service) ──required by──> AGT-34, FLOW-27 (Code node), DEPLOY-07, TEST-07/09
FLOW-32 (checkpoint) ──required by──> FLOW-33 (HITL resume) ──required by──> FLOW-24 (Fillup)
AGT-37 (replica snapshot) ──required by──> AGT-36 (webhook), AGT-12 (versions)
AGT-19 (MCP client) ──requires──> MCP-03 (server registry)

CHAT-12 ──required by──> CHAN-04..12 (channel bots call completions)
API-01 Go server ──required by──> CLI-01..17 (CLI is a Go binary), SRCH-06/07, MCP-01, ADMIN-01
ADMIN-01..05 ──required by──> CLI-15, UI-38
TEN-09/10 ──required by──> UI-36
LLM-23..28 ──required by──> UI-37, CLI-12

ING-02 (Redis Streams) ──conflicts──> ING-20 (NATS)            [C-2: pick one for the Python worker]
IDX-05 index-per-tenant ──conflicts──> KB-03 index-per-KB       [C-3]
Go mirrors (PARSE-26, CHUNK-28, IDX-15, RETR-23, LLM-35, AGT-39, FLOW-37, ING-19)
    ──duplicate──> their Python counterparts                    [C-20: scope decision]
```

### Dependency Notes

- **KB creation requires LLM configuration:** `21-.../create-knowledge-base.md` resolves the embedding model and its dimension before the index is created. Tenant model configuration (LLM-14..16, LLM-24) therefore precedes KB-01, and at least one embedding driver (Ollama is the keyless option) must work first.
- **Retrieval requires indexing requires parsing:** the Core Value slice is strictly linear: DOC, ING, PARSE, CHUNK, IDX, RETR, CHAT. Nothing downstream can be verified by "realistic execution" until the upstream stage is real.
- **PDF text-layer parsing can precede vision models:** PARSE-02 works without DLA/OCR/TSR. The vision stack (PARSE-04/06/07) enhances it and is the single largest research risk; it should be its own phase with its own research.
- **Agents require the workflow engine, not the reverse:** the Agent component is one node type (FLOW-12). Build FLOW engine and basic nodes first, then AGT-14.
- **Sandbox gates three features:** Code node, code-exec tool, and sandbox tests all wait on AGT-35.
- **HITL requires checkpointing:** Fillup (FLOW-24) is unusable without FLOW-32/33.
- **The Go server gates the CLI and the public bot surface:** CLI, search bots, MCP server, and admin are Go-owned in the docs. If the Go server is deferred, these are all blocked.
- **Channels are leaves:** every chat channel only needs CHAT-12 plus third-party credentials; schedule late and expect verification blockers without real bot accounts.
- **Queue technology is a fork, not a sequence:** ING-02 and ING-20 are alternative transports for the same job. Building both for the Python worker is duplication with no documented requirement.

---

## Ambiguities & Contradictions in `docs/`

Each needs an explicit, recorded decision (per `spec.md` Documentation rule). Where the RAGFlow reference was consulted to break a tie, that is stated.

| # | Topic | What the docs say | Recommendation |
|---|---|---|---|
| C-1 | Server ports | Go on `:9380` (`apis.md`, `00-overview/high-level-architecture.md` shows both servers on `:9380`); Python on `:9381` (`apis.md`); Python `:9380`, Go `:9384`, admin `:9381`/`:9383`, MCP `:9382` (`18-deployment/*`, `15-cli/configuration.md`) | Follow `18-deployment` (most detailed, internally consistent, and matches the reference `docker/.env`: `SVR_HTTP_PORT=9380`, `GO_HTTP_PORT=9384`) |
| C-2 | Task queue | Redis Streams `te.{prio}.common` with consumer groups (`05`, `10`); Redis list `ragflow_TASK_EXE_QUEUE` with RPUSH/LPOP (`21`, `99-glossary`); NATS JetStream (`18-deployment`) | Redis Streams for the Python worker (most detailed; reference confirms `SVR_QUEUE_NAME = "te"`). NATS only if the Go ingestor is in scope |
| C-3 | Docstore index naming | `ragflow_{tenant_id}` (`05-rag-pipeline/indexing.md`); `ragflow_{kb_id}` / `ragflow_{dataset_id}` (`21`, `99-glossary`) | Per-tenant with `kb_id` filter (reference `index_name(uid)` confirms); record the deviation from `21` |
| C-4 | Document `run` enum | `0` unstart, `1` running, `2` cancelled, `3` finished, `4` failed (`06-.../document-lifecycle.md`); `3` = FAIL (`99-glossary`); finished written as `run='1'` (`21-.../indexing.md`); UI shows UNSTART/RUNNING/SUCCESS/FAIL | Follow `06` (reference `TaskStatus` confirms 3 = DONE, 4 = FAIL) |
| C-5 | Chat / dataset / auth paths | Completion: `/api/v1/chat/completions` (`04`, `apis.md`), `/v1/session/completion` (`21`), `/v1/api/completion` (`12`), Go `/api/v1/chats/:id/completions` (`21`). Sessions: `/api/v1/chats/<id>/sessions` vs `/v1/api/new_conversation`, `/v1/api/conversations`. Assistant create: `POST /api/v1/chats` vs `POST /v1/api/dialog/set`. Dataset create: `/api/v1/datasets` vs `/v1/dataset` vs `/v1/dataset/create`. Login: `/api/v1/auth/login` vs `/v1/auth/login` vs `/v1/user/login` (CLI) | Treat `04-api/endpoint-catalog.md` + `apis.md` as canonical; other paths are legacy aliases — decide whether to serve aliases |
| C-6 | Citation marker and stream terminator | Marker `##N$$` (`12`, `21`, `99`), `[1]`/`[2]` (`05-.../final-answer.md`), `[ID:n]` / `[Document #1]` (`05-.../context-construction.md`, `11`). Terminator `data: [DONE]` (`12`, `04`) vs `data: {"code":0,"data":true}` (`21`). Reference sent in the final frame (`12`) vs the first frame (`21`) | `##N$$` in stored answers and `[DONE]` terminator (majority and most specific); pick reference timing once and make the UI tolerant |
| C-7 | Envelope and table names | Envelope `retcode`/`retmsg`/`data` (`04-api/api-overview.md`, `02`) vs `code`/`message`/`data` (SSE frames, all of `21`). Tables `dialog`/`conversation`/`api_4_conversation` (`12`, `08`) vs `chat_session`/`chat_dialog`/`agent_session`/`tenant_token_usage` (`21`) | One envelope for both servers (choose and record); table names per `08-database/entities.md` |
| C-8 | Upload ownership and auto-enqueue | Upload is "Python / Go" (`04`), Go proxies to MinIO (`apis.md`), Go path `/api/v1/datasets/:id/documents/upload` (`21`). `06-.../upload.md` enqueues a task on upload; `21` leaves the document UNSTART until the user clicks Parse. Public chatbot route is Go in `chat-api.md`, Python in `bot-api.md` | Upload on Python, explicit parse step (matches the UI flow and E2E-04/05) |
| C-9 | Dedup hash | `xxh64` (`06`) vs "xxhash/md5" (`21`) | xxh64 |
| C-10 | Password hashing | Bcrypt / PBKDF2 (`03`, `04`), PBKDF2/scrypt or Werkzeug (`21`) | One algorithm readable by both Go and Python; decide and record |
| C-11 | Access-token format | "Signed JWT" (`04`, `16-auth/tokens.md`) vs an itsdangerous serializer wrapping a UUID `access_token` stored in `user` (`03`, `16`, `20`); `20` also claims expiry checks | The stored-`access_token` model is the one specified in code-level detail, and AUTH-09 revocation depends on it |
| C-12 | Client token storage | `localStorage` key `ragflow_token` (`02`) vs signed cookie `ragflow_auth` (`21`, `99`) | Bearer header from localStorage per `02`; cookie only if session fallback (AUTH-10) needs it |
| C-13 | Per-file API docs are unreliable | `04-api/{agent,dataset,document,connector,search,tenant,user,system,provider,chat_channel,mcp,compilation_*}-api.md` pair routes with the wrong handler names (for example `DELETE /agents/<id>/sessions` with `list_agent_template`, `POST /auth/login` with `rollback_user_registration`), and several CRUD verbs are missing | Use these files as route existence evidence only; confirm verb and semantics against the RAGFlow reference during phase research. No logout endpoint is documented at all |
| C-14 | Workflow SSE event names | `workflow_started`/`node_started`/`node_finished`/`message`/`workflow_finished` (`14`) vs `component_start`/`component_end`, `node_start`/`node_end` (`21`) | Follow `14` (has payload schemas) |
| C-15 | Sandbox limits and runtimes | 10s timeout, 512 MB (`13-agents/execution.md`) vs 256m (`18`, `20`); Docker/Wasm and Python/SQL (`13`) vs Docker and Python/Node.js (`18`, `20`) | Docker, Python + Node.js, 256m default, configurable |
| C-16 | Python web framework | Quart ASGI (everywhere) vs "Python Flask application server with Gunicorn" (`18-deployment/docker.md`, `production-architecture.md`), "Flask REST Gateway" (`05-.../rag-overview.md`) | Quart |
| C-17 | Supported vector engines | Infinity/ES/OceanBase/ClickHouse/SereneDB (`05`); + OpenSearch/Qdrant/Milvus/PGVector/Tantivy (`00`, `16`); OpenSearch/PGVector (`17`); compose profiles add SeekDB. `05` calls Infinity the default | Fully implement Elasticsearch and Infinity (the only two with adapter-level detail); choose the default in STACK research; others are `[P]` |
| C-18 | Storage layout and backends | Bucket `ragflow`, key `{tenant_id}/{doc_id}` (`09`) vs bucket `ragflow-{tenant_id}` (`17`) vs randomized UUID object names (`20`). Backends MinIO/S3/GCS/OSS/Local (`09`) vs + Azure Blob (`17`, `18`) | One layout, recorded; Azure is `[P]` |
| C-19 | Chunker and node catalogs | "14 chunkers" (`05`), 8 in the strategy matrix (`06`), 7-9 in UI lists, 10 in the create-KB flow. Canvas nodes: 20 in `14-workflows/nodes.md`; `02` adds Code and Image Generate; `00` adds Keyword Extract and Rewrite; `21` uses "Answer"/"ExeSQL"/"Generate"; `Parallel` exists only as a Go subgraph | Build the 14 chunkers and the 20 catalogued nodes plus Code (it has a UI form and a sandbox path); the rest are `[P]` |
| C-20 | Dual implementation scope | Docs describe Python and Go implementations of parsers, chunkers, docstore drivers, retrieval, model service, agent runtime (Eino), workflow compiler, ingestion — "Dual Engine Synchronization: parity" (`11`) | Largest scope question in the project. Go must own what the routing table assigns it (auth, user, tenant, system, search bots, MCP, CLI, admin). Whether Go also re-implements the Python RAG/agent engines needs an explicit user decision; building both doubles roughly 8 XL features |
| C-21 | Health endpoint | `/health`, `/api/v1/system/ping`, `/system/healthz`, `/v1/system/health` (compose health check), `/v1/admin/health` | Serve `/health` and `/system/healthz`; point the compose check at one of them |
| C-22 | Who may invite members | Owner and admin (`16-auth/authorization.md`) vs owner only (`16-auth/permissions.md` matrix) | Follow the matrix (more specific) |
| C-23 | Fusion method and default weights | Weighted sum (`FusionExpr` with weights `0.001,1`) and RRF `k=60` are both presented without saying when each applies; `vector_similarity_weight=0.3` default (term 0.7) vs `rerank_by_model(tkweight=0.3, vtweight=0.7)` | Weighted sum as the implemented path, RRF as an option; keep both documented defaults in their respective functions |
| C-24 | CLI endpoint paths | CLI calls `/v1/user/login`, `/v1/dataset/create`, `/v1/dataset/list`, `/v1/api/retrieval`, `/v1/chunk/list`, `/v1/admin/*`, `/v1/skill/*`, none of which are in the endpoint catalog | Point the CLI at the canonical routes (C-5) |
| C-25 | CORS policy | `allow_origin="*"` (`03-backend/middleware.md`) vs whitelisted origins (`20-security/api-security.md`) | Configurable allow-list defaulting to same-origin behind the proxy |
| C-26 | Frontend stack details | Vite vs UmiJS; shadcn/ui vs Ant Design; "React Query" vs "custom hooks" (`00-overview/technology-stack.md`, `02`) | STACK research decides; PROJECT.md already records Vite + shadcn |
| C-27 | Foreign content in `apis.md` | Lines 140-2080 are a pasted generic billing-platform Q&A | See "Needs User Decision" |

---

## MVP Definition

This project has no MVP: `spec.md` and PROJECT.md make the complete documented system the goal. The grouping below is therefore **build order**, not a scope cut. Every table-stakes row above is v1.

### Launch With (v1) — in dependency order

- [ ] **Slice 0, foundation:** DEPLOY-02/03/04, DATA-01..05, API-01..11, SYS-01..07 — nothing else can run
- [ ] **Slice 1, identity:** AUTH-01..23, TEN-01..13, UI-01..08 — every later request is tenant-scoped
- [ ] **Slice 2, model configuration:** LLM-01..09, LLM-14..28, UI-37 — KB creation needs an embedding dimension
- [ ] **Slice 3, Core Value path:** KB-01..09, STOR-01/02, DOC-01..16, ING-01..16, PARSE-01..03 and 09..13, CHUNK-01/02/16..19, IDX-01..10, RETR-01..19, CHAT-01..23, UI-10..25, E2E-01..09 and E2E-12 — "upload a document and get a cited answer"
- [ ] **Slice 4, deep parsing:** PARSE-04..08, PARSE-18..25, remaining CHUNK-03..15, CHUNK-20..27 — the "DeepDoc" promise
- [ ] **Slice 5, workflow and agents:** FLOW-01..36, AGT-01..38, UI-27..32, E2E-10/11
- [ ] **Slice 6, Go-owned surface:** CLI-01..17, ADMIN-01..07, SRCH-06/07, MCP-01..03, UI-38
- [ ] **Slice 7, integrations and breadth:** STOR-03..06, IDX-11/12, LLM-07 breadth, LLM-30/31, SRCH-01..05, CHAN-01..12, CONN, TMPL, CHAT-25..27
- [ ] **Throughout:** SEC-01..10 and TEST-01..11 land with the features they cover, not as a final phase

### Add After Validation (v1.x) — only if the user confirms scope

- [ ] `[P]`-flagged rows with no behavioural spec (AUTH-24/25, TEN-14..16, DOC-24, ING-17/18, IDX-13, RETR-20, LLM-11..13, CHAT-28..31, AGT-33, FLOW-28, UI-33/39/40/41, DATA-07, DEPLOY-18..20, SEC-11, TEST-12) — each needs phase research against the RAGFlow reference before it can be specified
- [ ] Go mirrors of Python engines (PARSE-26, CHUNK-28, IDX-15, RETR-23, LLM-35, AGT-39, FLOW-37, ING-19, ING-20, DEPLOY-09) — pending decision C-20

### Future Consideration (v2+)

- [ ] Everything under "Differentiators" — undocumented
- [ ] BILL-01..10 — pending the "Needs User Decision" outcome

---

## Feature Prioritization Matrix

By category. "User value" is relative to the Core Value in PROJECT.md (upload a document, get a cited answer through the real pipeline).

| Category | Rows | User Value | Implementation Cost | Priority |
|---|---|---|---|---|
| API (conventions, both servers) | 14 | HIGH | HIGH | P1 |
| DATA | 8 | HIGH | MEDIUM | P1 |
| AUTH | 25 | HIGH | MEDIUM | P1 |
| TEN | 16 | HIGH | MEDIUM | P1 |
| LLM | 35 | HIGH | HIGH | P1 |
| KB | 19 | HIGH | MEDIUM | P1 |
| DOC | 24 | HIGH | MEDIUM | P1 |
| STOR | 11 | HIGH | LOW | P1 |
| ING | 21 | HIGH | HIGH | P1 |
| PARSE | 26 | HIGH | HIGH | P1 (vision stack is the top research risk) |
| CHUNK | 28 | HIGH | HIGH | P1 |
| IDX | 15 | HIGH | HIGH | P1 |
| RETR | 23 | HIGH | HIGH | P1 |
| CHAT | 31 | HIGH | HIGH | P1 |
| UI | 44 | HIGH | HIGH | P1 |
| SEC | 11 | HIGH | MEDIUM | P1 |
| TEST | 12 | HIGH | HIGH | P1 |
| DEPLOY | 21 | HIGH | MEDIUM | P1 |
| SYS | 9 | MEDIUM | LOW | P1 |
| FLOW | 37 | MEDIUM | HIGH | P1 |
| AGT | 39 | MEDIUM | HIGH | P1 |
| CLI | 18 | MEDIUM | HIGH | P1 |
| ADMIN | 7 | MEDIUM | MEDIUM | P1 |
| SRCH | 7 | MEDIUM | MEDIUM | P1 |
| MCP | 3 | MEDIUM | MEDIUM | P1 |
| CHAN | 12 | LOW | HIGH | P2 (documented, but unverifiable without third-party bot credentials) |
| CONN | 6 | LOW | MEDIUM | P2 (routes only; no connector types specified) |
| TMPL | 4 | LOW | MEDIUM | P2 (concept undefined in docs) |
| BILL | 10 | unknown | HIGH | P3 pending user decision |

**Priority key:** P1 = documented with enough detail to build and verify; P2 = documented but under-specified or externally blocked — needs phase research first; P3 = not confirmed as in scope.

---

## Reference Product Comparison

Not a market survey (the feature set is prescribed). This table records how devRag relates to its reference.

| Area | RAGFlow (reference repo) | What `docs/` prescribes | devRag approach |
|---|---|---|---|
| Backend | Python Quart plus a newer Go server, both live | Dual-stack with a route-ownership table | Build both; Go owns what the routing table says; Python engine parity in Go is decision C-20 |
| Queue | Redis Streams (`te.*`), NATS for Go worker | Three conflicting descriptions | Redis Streams (C-2) |
| Parsing | DeepDoc ONNX models + many external parser wrappers | DLA, OCR, TSR specified; wrappers mostly `[P]` | Build the DeepDoc path; wrappers after research |
| UI | Ant Design / shadcn hybrid with RAGFlow branding | Page inventory, component responsibilities | Same capabilities and interaction patterns, own visual design (anti-feature: cloning) |
| GraphRAG, memory, skills, connectors | Implemented | Names only | Deferred (differentiators) |

---

## Sources

All HIGH confidence as statements of "what the docs say" (each file read in full unless noted):

- `docs/spec.md` — implementation rules, anti-features, completion criteria
- `.planning/PROJECT.md` — scope, constraints, key decisions
- `docs/apis.md` — endpoint/routing catalog (lines 1-139); foreign billing Q&A (lines 140-2080)
- `docs/00-overview/*` (6 files)
- `docs/02-frontend/*` (14 files)
- `docs/03-backend/*` (10 files)
- `docs/04-api/*` (24 files)
- `docs/05-rag-pipeline/*` (14 files)
- `docs/06-document-processing/*` (12 files)
- `docs/07-retrieval/*` (9 files)
- `docs/08-database/*` (8 files)
- `docs/09-storage/*` (5 files)
- `docs/10-cache-and-queues/*` (6 files)
- `docs/11-llm/*` (10 files)
- `docs/12-chat/*` (7 files)
- `docs/13-agents/*` (9 files)
- `docs/14-workflows/*` (8 files)
- `docs/15-cli/*` (5 files)
- `docs/16-auth/*` (7 files)
- `docs/17-integrations/*` (6 files)
- `docs/18-deployment/*` (9 files)
- `docs/19-testing/*` (6 files)
- `docs/20-security/*` (7 files)
- `docs/21-end-to-end-flows/*` (12 files)
- `docs/99-glossary/important-terms.md` — contradiction evidence only
- `docs/22-code-tracing`, `23-diagrams`, `24-learning` — scanned for endpoints only; no new features

Reference repository (`/home/logan78/desktop x/ragflow`), consulted only to break ties for C-1..C-4:

- `common/constants.py` — `TaskStatus` (0 unstart, 1 running, 2 cancel, 3 done, 4 fail), `SVR_QUEUE_NAME = "te"`
- `rag/nlp/search.py` — `index_name(uid)` returns `ragflow_{uid}`
- `docker/.env` — `SVR_HTTP_PORT=9380`, `ADMIN_SVR_HTTP_PORT=9381`, `GO_HTTP_PORT=9384`

Not read: `docs/apikey llm.md` (off-limits pending user review).

Known gaps in this inventory:

- "Source File Map" bullet lists inside `12-chat`, `13-agents`, `14-workflows`, `16-auth`, `17-integrations` were skimmed, not itemized; they are file pointers into the reference repo and may name sub-features not captured here.
- Entities in `08-database/entities.md` have no column definitions except `document`, `task`, `knowledgebase`; DATA-01 will need per-phase schema research.
- Request/response bodies are documented for only about ten endpoints; every other route needs its contract derived during phase research.

---
*Feature research for: enterprise RAG platform (devRag)*
*Researched: 2026-10-05*
