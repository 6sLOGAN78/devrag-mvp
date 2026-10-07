# Requirements: devRag

**Defined:** 2026-10-05
**Core Value:** A user can upload a document into a knowledge base and get an accurate, cited answer to a question about it — end-to-end, through the real pipeline (parse → chunk → embed → index → hybrid retrieve → rerank → generate), with no mocked stages.

**Source:** Every requirement is lifted from `.planning/research/FEATURES.md`, which cites the `docs/` file each one comes from. `docs/` is authoritative; where docs contradict themselves, see the decision register in `.planning/research/SUMMARY.md`.

## v1 Requirements

Requirements for initial release. Each maps to exactly one roadmap phase.

### AUTH — Authentication, sessions, tokens, API keys

- [ ] **AUTH-01**: User can register with email, password, nickname via `POST /api/v1/users`; email format, nickname, and email uniqueness are validated
- [ ] **AUTH-02**: Passwords are stored only as salted hashes and verified on login
- [ ] **AUTH-03**: Registration atomically provisions a `tenant` row and a `user_tenant` link with `role='owner'`; failure rolls back all three inserts
- [ ] **AUTH-04**: Registration initializes the tenant's default model configuration (`tenant_llm`)
- [ ] **AUTH-05**: User can log in with email and password via `POST /api/v1/auth/login` and receives `access_token` plus user object; only users with valid status may log in
- [ ] **AUTH-06**: Login resolves the user's tenant id, role, and tenant default models (chat, embedding, rerank)
- [ ] **AUTH-07**: Protected routes on both servers accept `Authorization: Bearer <token>` and populate request user context (`g.user` / `c.Set("user")`)
- [ ] **AUTH-08**: Token validation rejects empty/whitespace tokens, tokens shorter than 32 chars, and tokens beginning `INVALID_`
- [ ] **AUTH-09**: User can log out; logout rewrites `user.access_token` to `INVALID_<hex>` so the old token returns 401 thereafter
- [ ] **AUTH-10**: Requests without an `Authorization` header fall back to a Redis-backed server session cookie (`_user_id`)
- [ ] **AUTH-11**: Login sets a signed `ragflow_auth` cookie
- [ ] **AUTH-12**: Auth resolution order is beta token, then JWT, then API token, then session cookie; no match returns HTTP 401
- [ ] **AUTH-13**: User can fetch own profile, avatar, tenant id and role via `GET /v1/user/info`
- [ ] **AUTH-14**: User can update nickname, avatar, and language via `POST /v1/user/setting`
- [ ] **AUTH-15**: User can change password by supplying old and new password via `POST /v1/user/setting/password`
- [ ] **AUTH-16**: User can request a password-reset OTP via `POST /api/v1/auth/password/forgot/otp`
- [ ] **AUTH-17**: User can verify the OTP via `POST /api/v1/auth/password/forgot/otp/verify`
- [ ] **AUTH-18**: User can reset password with email, OTP, and new password via `POST /api/v1/auth/password/reset`
- [ ] **AUTH-19**: User can create a programmatic API token via `POST /system/tokens`
- [ ] **AUTH-20**: User can list API tokens via `GET /system/tokens`
- [ ] **AUTH-21**: User can delete an API token via `DELETE /system/tokens/<token>`
- [ ] **AUTH-22**: API clients can authenticate with an API token (`AUTH_API`) which resolves to the owning tenant
- [ ] **AUTH-23**: Public bot, search-bot, and MCP routes authenticate with a beta token (`AUTH_BETA`, `BetaAuthMiddleware`)
- [ ] **AUTH-24**: User can log in through third-party OAuth2 / OIDC (GitHub, Google, enterprise OIDC)
- [ ] **AUTH-25**: Captcha generation for auth forms

### TEN — Multi-tenancy, roles, permissions

- [ ] **TEN-01**: Every tenant-owned entity (dataset, document, task, dialog, canvas, file) carries `tenant_id` and every service/DAO query filters by the caller's tenant
- [ ] **TEN-02**: Requesting another tenant's resource by id is denied (not found / permission error), never returned
- [ ] **TEN-03**: Docstore queries and index names are tenant-scoped so vector search cannot leak across tenants
- [ ] **TEN-04**: Users hold one of three roles per tenant (`owner`, `admin`, `normal`) stored in `user_tenant.role`
- [ ] **TEN-05**: The documented permission matrix (10 functional areas by `owner`/`admin`/`normal`/beta token/API token) is enforced; disallowed actions return HTTP 403
- [ ] **TEN-06**: User can retrieve tenant/workspace settings via `GET /v1/user/tenant_info`
- [ ] **TEN-07**: User can list tenants they can access via `GET /v1/tenant/list`
- [ ] **TEN-08**: User can list members of a tenant via `GET /tenants/<tenant_id>/users`
- [ ] **TEN-09**: Owner can invite/add a member via `POST /tenants/<tenant_id>/users`
- [ ] **TEN-10**: Invited user can accept membership via `PATCH /tenants/<tenant_id>`
- [ ] **TEN-11**: Owner can change a member's role
- [ ] **TEN-12**: Admin/owner can set the tenant's default chat and embedding models
- [ ] **TEN-13**: Multiple users can share one tenant's datasets, documents, models, and agent workflows
- [ ] **TEN-14**: Custom RBAC: admin can `CREATE ROLE`, `GRANT <permission> ON <resource> TO ROLE`, `REVOKE ... FROM ROLE`
- [ ] **TEN-15**: Invitation codes (`InvitationCode` entity)
- [ ] **TEN-16**: Dataset-level `permission` field on create

### KB — Knowledge bases (datasets)

- [ ] **KB-01**: User can create a dataset with `name`, `parser_id`, `embd_id` via `POST /api/v1/datasets`; duplicate name within the tenant is rejected
- [ ] **KB-02**: Creating a dataset validates the embedding model against tenant models and resolves its vector dimension
- [ ] **KB-03**: Creating a dataset provisions the docstore index with the matching dense-vector schema and analyzers
- [ ] **KB-04**: User can list datasets with `page`, `page_size`, `keywords` via `GET /api/v1/datasets`
- [ ] **KB-05**: User can get one dataset's detail via `GET /datasets/<dataset_id>`
- [ ] **KB-06**: User can update dataset name, parser, and parser config via `PUT /api/v1/datasets/<dataset_id>`
- [ ] **KB-07**: User can delete dataset(s) via `DELETE /api/v1/datasets`; documents, chunks, and the vector index are removed
- [ ] **KB-08**: Dataset stores `parser_config` JSON: `chunk_token_num`, `delimiter`, `pages`, `table_context_size`, `image_context_size`, layout-model toggle, auto-keyword count
- [ ] **KB-09**: Dataset stores avatar, language (default `English`), description, and status
- [ ] **KB-10**: User can aggregate tags across datasets via `GET /datasets/tags/aggregation`
- [ ] **KB-11**: User can list and delete tags of a dataset via `GET` / `DELETE /datasets/<dataset_id>/tags`
- [ ] **KB-12**: User can fetch flattened metadata across datasets via `GET /datasets/metadata/flattened`
- [ ] **KB-13**: User can read a dataset's auto-metadata configuration via `GET /datasets/<dataset_id>/metadata/config`
- [ ] **KB-14**: User can view an ingestion summary for a dataset via `GET /datasets/<dataset_id>/ingestions/summary`
- [ ] **KB-15**: User can list ingestion logs and fetch one log via `GET /datasets/<dataset_id>/ingestions/<log_id>`
- [ ] **KB-16**: User can check embedding-model compatibility for a dataset via `POST /datasets/<dataset_id>/embedding/check`
- [ ] **KB-17**: User can delete a derived index of a dataset by type via `DELETE /datasets/<dataset_id>/<index_type>` and trace it via `GET /datasets/<dataset_id>/artifacts/alteration`
- [ ] **KB-18**: User can run a retrieval test against a dataset with similarity threshold and vector/keyword weight controls
- [ ] **KB-19**: Dataset document counts and token/chunk totals are maintained

### DOC — Document upload, lifecycle, management

- [ ] **DOC-01**: User can upload one or more files to a dataset as multipart via `POST /api/v1/documents/upload`
- [ ] **DOC-02**: Upload rejects disallowed extensions / MIME types with HTTP 400
- [ ] **DOC-03**: Upload enforces max content size and quota limits
- [ ] **DOC-04**: Upload computes an xxh64 content hash and, on a duplicate within the tenant, reuses the stored blob and only links a new `Document`
- [ ] **DOC-05**: Upload writes the binary to object storage and records `location`
- [ ] **DOC-06**: Upload inserts `File`, `Document`, `File2Document` rows in one transaction with `run='0'`, `progress=0.0`
- [ ] **DOC-07**: Upload verifies dataset existence and caller permission before storing
- [ ] **DOC-08**: User can list documents in a dataset with paging and keyword filter via `GET /api/v1/datasets/<dataset_id>/documents`
- [ ] **DOC-09**: User can start parsing selected documents via `POST /api/v1/datasets/<dataset_id>/documents/parse` (`doc_ids`, `run`); document moves to RUNNING and tasks are queued
- [ ] **DOC-10**: User can cancel a running parse; document moves to CANCELLED
- [ ] **DOC-11**: User can re-parse a document; previous chunks are replaced
- [ ] **DOC-12**: Document exposes lifecycle state (`run`), `progress` float 0.0-1.0 (`-1` on failure), and `progress_msg`
- [ ] **DOC-13**: User can enable/disable documents for retrieval via `POST /api/v1/datasets/<dataset_id>/documents/batch-update-status`
- [ ] **DOC-14**: User can delete documents via `DELETE /api/v1/datasets/<dataset_id>/documents`; chunks are pruned from the index
- [ ] **DOC-15**: Deleting a document garbage-collects the blob only when no other `File2Document` row references it
- [ ] **DOC-16**: Documents can carry their own `parser_id` / `parser_config` overriding the dataset default
- [ ] **DOC-17**: User can batch-update document metadata via `PATCH /datasets/<dataset_id>/documents/metadatas`
- [ ] **DOC-18**: User can fetch an extracted image via `GET /documents/images/<image_id>`
- [ ] **DOC-19**: User can fetch a generated artifact via `GET /documents/artifact/<filename>`
- [ ] **DOC-20**: Documents have thumbnails
- [ ] **DOC-21**: User can preview a document's raw content
- [ ] **DOC-22**: User can query task status via `GET /v1/task/status/:task_id`
- [ ] **DOC-23**: Documents track `token_num`, `chunk_num`, `process_begin_at`, `process_duration`, `size`, `suffix`, `source_type`
- [ ] **DOC-24**: File manager with folder hierarchy (`file.parent_id`)

### STOR — Object and file storage

- [ ] **STOR-01**: Uniform storage interface (`get`, `put`, `rm`, `bucket_exists`) selected by `STORAGE_IMPL` through a factory *(Python implementation in v1; Go mirror deferred to v2)*
- [ ] **STOR-02**: MinIO driver
- [ ] **STOR-03**: AWS S3 driver
- [ ] **STOR-04**: Google Cloud Storage driver
- [ ] **STOR-05**: Alibaba Cloud OSS driver
- [ ] **STOR-06**: Local filesystem driver with path sanitization that blocks directory traversal
- [ ] **STOR-07**: Azure Blob Storage driver
- [ ] **STOR-08**: Missing buckets are created on first write
- [ ] **STOR-09**: Extracted images and table crops are stored under `{tenant_id}/{doc_id}/{img_id}.png` and `.../tables/{table_id}.png`
- [ ] **STOR-10**: Pre-signed download URLs with 3600s expiry
- [ ] **STOR-11**: Uploaded objects are stored under randomized UUID names

### PARSE — Parsers, OCR, layout, tables (DeepDoc)

- [ ] **PARSE-01**: File-type router dispatches each source file to its parser
- [ ] **PARSE-02**: PDF: extract native text spans with character bounding boxes
- [ ] **PARSE-03**: PDF: rasterize pages to images at zoom 3
- [ ] **PARSE-04**: Layout analysis (DLA) detects regions labelled Text, Title, Figure, Figure caption, Table, Table caption, Header, Footer, Reference, Equation
- [ ] **PARSE-05**: Text boxes are assigned to layout regions at overlap ratio >= 0.4; duplicates removed by IoU NMS; regions sorted into reading order
- [ ] **PARSE-06**: OCR fallback (text detection plus recognition) runs when a page's text layer is missing or corrupt
- [ ] **PARSE-07**: Table structure recognition reconstructs cropped tables into HTML `<table>`
- [ ] **PARSE-08**: Headers and footers are filtered from chunk content
- [ ] **PARSE-09**: DOCX parser: paragraphs, headings, embedded images, tables as HTML *(Python implementation in v1; Go mirror deferred to v2)*
- [ ] **PARSE-10**: XLSX parser: sheets to HTML/Markdown tables with header-row context
- [ ] **PARSE-11**: PPTX parser: slide titles, text frames, shape tables, speaker notes, images
- [ ] **PARSE-12**: HTML parser: DOM extraction with script/style stripping
- [ ] **PARSE-13**: TXT parser with encoding auto-detection
- [ ] **PARSE-14**: Markdown parser
- [ ] **PARSE-15**: JSON parser
- [ ] **PARSE-16**: EPUB parser
- [ ] **PARSE-17**: CSV ingestion
- [ ] **PARSE-18**: Image files (JPG, PNG) are parsed via OCR and/or VLM description
- [ ] **PARSE-19**: Embedded figures are extracted, hashed for dedup (`image2id`), captioned by a vision model, and stored
- [ ] **PARSE-20**: Audio files (MP3, WAV) are transcribed by an ASR model
- [ ] **PARSE-21**: Email (`.eml`) parsed into From, To, Subject, Date, Body
- [ ] **PARSE-22**: Pluggable external PDF parsers: Docling and MinerU wrappers
- [ ] **PARSE-23**: Additional parser backends: PaddleOCR, Mistral, TCADP, SoMark, OpenDataLoader, figure parser
- [ ] **PARSE-24**: DLA / OCR / TSR can be offloaded to a remote DeepDoc service (`DEEPDOC_URL`, `TENSORRT_DLA_SVR`; container port 9390)
- [ ] **PARSE-25**: Parsing honours the `pages` range in `parser_config`
- [ ] **PARSE-26**: Go PDF and DOCX parser implementations with CGO bindings (PDFium, OfficeOxide) *(Python implementation in v1; Go mirror deferred to v2)*

### CHUNK — Chunking strategies and chunk management

- [ ] **CHUNK-01**: `parser_id` resolver dispatches to the matching chunker (`FACTORY[parser_id]`)
- [ ] **CHUNK-02**: `naive`/`general`: token window with overlap, custom delimiters, max tokens (default 512)
- [ ] **CHUNK-03**: `paper`: section-aware (Abstract, Introduction, Method, ..., References)
- [ ] **CHUNK-04**: `book`: chapter/section hierarchy from headings or TOC depth
- [ ] **CHUNK-05**: `laws`: Chapter / Section / Article / Item hierarchy
- [ ] **CHUNK-06**: `presentation`: one chunk group per slide with slide title appended
- [ ] **CHUNK-07**: `table`: one chunk per row prefixed with table title and column headers
- [ ] **CHUNK-08**: `qa`: question/answer pairs from Excel/CSV/text; question stored in `question_tks`
- [ ] **CHUNK-09**: `resume`: structured CV entities (name, contact, work history, education, skills)
- [ ] **CHUNK-10**: `picture`: VLM description of images indexed as chunks
- [ ] **CHUNK-11**: `manual`: groups code blocks, parameter tables, subsection diagrams
- [ ] **CHUNK-12**: `email`: From/To/Subject/Date/Body sections
- [ ] **CHUNK-13**: `tag`: extracts tag features and tag weights
- [ ] **CHUNK-14**: `one`: whole document as a single chunk
- [ ] **CHUNK-15**: `audio`: ASR transcript segmented into timestamped chunks
- [ ] **CHUNK-16**: Every chunk carries content, page number, position `[page, x0, top, x1, bottom]`, and image ids
- [ ] **CHUNK-17**: Text preprocessing: full-to-half-width, traditional-to-simplified Chinese, URL/email stripping, tokenize, fine-grained tokenize, token positions
- [ ] **CHUNK-18**: User can list a document's chunks with text, bounding boxes, status, paging, keyword filter via `GET .../documents/<doc_id>/chunks`
- [ ] **CHUNK-19**: User can create a manual chunk via `POST .../documents/<doc_id>/chunks`
- [ ] **CHUNK-20**: User can edit a chunk's text
- [ ] **CHUNK-21**: User can enable/disable individual chunks
- [ ] **CHUNK-22**: LLM keyword extraction per chunk populates `important_kwd`
- [ ] **CHUNK-23**: LLM question proposal per chunk populates `question_tks`
- [ ] **CHUNK-24**: LLM content tagging against tag sets
- [ ] **CHUNK-25**: LLM auto-metadata generation (`gen_metadata`)
- [ ] **CHUNK-26**: RAPTOR hierarchical summarization (cluster, summarize, index summary chunks) when enabled on the dataset
- [ ] **CHUNK-27**: Public built-in pipeline listing: `GET /api/v1/pipelines?type=builtin`, `GET /api/v1/pipelines/:id`
- [ ] **CHUNK-28**: Go chunker mirrors for `naive`, `one`, `qa`, `table`, `presentation` *(Python implementation in v1; Go mirror deferred to v2)*

### ING — Background ingestion, queues, workers, Redis

- [ ] **ING-01**: Parsing creates `task` rows; large documents are split into page-range sub-tasks (`MAXIMUM_TASK_PAGE_NUMBER = 12`)
- [ ] **ING-02**: Tasks are published to Redis Streams (`XADD`) on `te.{priority}.common`
- [ ] **ING-03**: High-priority queue (`te.1.common`) is drained before normal (`te.0.common`)
- [ ] **ING-04**: Workers consume through a consumer group (`XREADGROUP`); N workers run concurrently
- [ ] **ING-05**: Un-acked messages from a crashed worker are reclaimed by the next consumer
- [ ] **ING-06**: A Redis distributed lock (`SET NX EX`) guards each task
- [ ] **ING-07**: Worker acknowledges (`XACK`) on completion
- [ ] **ING-08**: Worker reports progress (0.0-1.0, `-1` on failure) and message to `task`; a lock-guarded `update_progress` daemon rolls task progress up to the document
- [ ] **ING-09**: Concurrency limiters: `task_limiter`, `chunk_limiter`, `embed_limiter`, `minio_limiter`, `kg_limiter`
- [ ] **ING-10**: Worker heartbeat to Redis (`WORKER_HEARTBEAT_TIMEOUT`, default 120s)
- [ ] **ING-11**: Task failure records error trace, sets document to FAILED, tracks `retry_count`
- [ ] **ING-12**: Worker stops when the user cancels
- [ ] **ING-13**: Worker pipeline end-to-end: fetch blob, parse, chunk, embed, bulk index, mark done
- [ ] **ING-14**: Blocking compute (embedding, docstore calls) is offloaded to a thread pool so the asyncio loop is not blocked
- [ ] **ING-15**: Worker closes DB connections before long model inference
- [ ] **ING-16**: Task executor runs as a standalone process/container (`entrypoint_task_executor.sh`)
- [ ] **ING-17**: Background task types beyond parse: `raptor`, `graphrag`, `mindmap`, `memory`, `wiki`, `skill`, `structure_graph`, `structure_mindmap`, `timeline`, `session_graph`, `session_essence`, `structure`
- [ ] **ING-18**: Dataset-wide fan-out tasks using sentinel document ids
- [ ] **ING-19**: Go ingestion service and syncer (`--ingestor`, `--syncer` flags) *(Python implementation in v1; Go mirror deferred to v2)*
- [ ] **ING-20**: NATS JetStream as task queue
- [ ] **ING-21**: Redis also serves as session store, synonym cache (`synonym_{term}`), and LLM cache (`llm_cache_{hash}`)

### IDX — Embedding and indexing

- [ ] **IDX-01**: Chunks are embedded in batches of 64 using the dataset's embedding model
- [ ] **IDX-02**: Inputs are truncated to 8192 tokens before embedding; results are re-ordered by index to match inputs
- [ ] **IDX-03**: Vectors are L2-normalized
- [ ] **IDX-04**: Vector field is named `q_{dim}_vec`, allowing multiple embedding dimensions in one index
- [ ] **IDX-05**: Unified `DocStoreConnection` interface (create/drop index, insert, update, delete, search with text + dense + fusion expressions)
- [ ] **IDX-06**: Index schema: `id`, `doc_id`, `kb_id`, `content_ltks`, `title_tks`, `important_kwd`, `question_tks`, `position_int`, `q_{dim}_vec`, `available_int` (plus `title_sm_tks`, `important_tks`, `content_sm_ltks` from query fields)
- [ ] **IDX-07**: Chunks are bulk-upserted in batches of 64 with deterministic id `doc_id + "_" + order`
- [ ] **IDX-08**: Vector index is HNSW with cosine metric, `m=16`, `ef_construction=200`
- [ ] **IDX-09**: Elasticsearch 8 adapter
- [ ] **IDX-10**: Infinity adapter
- [ ] **IDX-14**: Document and dataset deletion remove their chunks from the index
- [ ] **IDX-15**: Go docstore drivers (Elasticsearch, Infinity, OceanBase) *(Python implementation in v1; Go mirror deferred to v2)*

### RETR — Retrieval, filters, reranking

- [ ] **RETR-01**: Dense KNN search with cosine similarity over `q_{dim}_vec` (`MatchDenseExpr`)
- [ ] **RETR-02**: BM25 full-text search over boosted fields (`important_kwd^30`, `important_tks^20`, `question_tks^20`, `title_tks^10`, `title_sm_tks^5`, `content_ltks^2`, `content_sm_ltks`)
- [ ] **RETR-03**: Query normalization, tokenization, term weighting, and engine-specific escaping
- [ ] **RETR-04**: Synonym expansion with Redis-cached synonym pairs
- [ ] **RETR-05**: Hybrid fusion of text and dense matches (`FusionExpr("weighted_sum", topk, weights)`) executed in the docstore
- [ ] **RETR-06**: Final score = `w_term * S_term + w_vector * S_vector + S_rank_feature`, with `vector_similarity_weight` configurable per query or assistant
- [ ] **RETR-07**: Reciprocal Rank Fusion (`k = 60`) as a fusion option
- [ ] **RETR-08**: Filters by `kb_ids`, `doc_ids`, `id`, `available_int`, `removed_kwd`, and `must_not` conditions
- [ ] **RETR-09**: Metadata conditions translate to Elasticsearch `bool.must` / `must_not` or Infinity `WHERE`
- [ ] **RETR-10**: Chunks of deleted documents are pruned from results
- [ ] **RETR-11**: Cross-encoder reranking (`rerank_by_model`) blending token similarity, rerank score, and rank features
- [ ] **RETR-12**: Without a reranker: KNN + token-overlap rerank on Elasticsearch, direct normalized scores on Infinity
- [ ] **RETR-13**: Rank-feature score = `10 * tag_score + pagerank`
- [ ] **RETR-14**: Results below `similarity_threshold` (default 0.2) are dropped; ordering is a stable sort by score
- [ ] **RETR-15**: Pagination (`page`, `page_size`) with a rerank window over `top` candidates (default 1024)
- [ ] **RETR-16**: Retrieval spans multiple datasets and tenants' indices in one call
- [ ] **RETR-17**: Each hit returns chunk id, content, doc id/name, dataset id, page, positions, and term/vector/overall similarity
- [ ] **RETR-18**: Retrieval-test API returns ranked hits for a question over selected datasets
- [ ] **RETR-19**: NaN / Infinity scores are sanitized to null before serialization
- [ ] **RETR-20**: Knowledge-graph filter keys (`knowledge_graph_kwd`, `entity_kwd`, `from_entity_kwd`, `to_entity_kwd`)
- [ ] **RETR-21**: Web-search augmentation merges web snippets with local chunks when the assistant enables it
- [ ] **RETR-22**: Chunks marked inaccurate by user feedback are downweighted or excluded
- [ ] **RETR-23**: Go retrieval driver *(Python implementation in v1; Go mirror deferred to v2)*

### LLM — Providers, model configuration, prompts

- [ ] **LLM-01**: Chat driver base interface: `chat`, `async_chat`, `chat_streamly`, `async_chat_streamly`
- [ ] **LLM-02**: LiteLLM-backed driver with provider prefix routing and default base URLs
- [ ] **LLM-03**: OpenAI chat and embeddings
- [ ] **LLM-04**: Azure OpenAI deployment mapping
- [ ] **LLM-05**: Ollama chat and embeddings with user-supplied base URL (no `/v1` suffix)
- [ ] **LLM-06**: DeepSeek with `<think>` reasoning-block extraction
- [ ] **LLM-07**: Provider registry of 40+ providers (Tongyi/DashScope, Zhipu, Moonshot, Anthropic, Gemini, Bedrock, Cohere, Groq, TogetherAI, xAI, NVIDIA, MiniMax, Hunyuan, SiliconFlow, OpenRouter, ...)
- [ ] **LLM-08**: Embedding drivers: OpenAI, Azure, Qwen, Zhipu, Ollama, HuggingFace/builtin, Jina, SiliconFlow
- [ ] **LLM-09**: Rerank drivers (Jina, Cohere, NVIDIA, Voyage, BGE/BCE, LocalAI, Qwen) with scores normalized to [0, 1]
- [ ] **LLM-10**: Vision (image-to-text) model type
- [ ] **LLM-11**: Speech-to-text (ASR) model type
- [ ] **LLM-12**: Text-to-speech (TTS) model type
- [ ] **LLM-13**: OCR model type
- [ ] **LLM-14**: `LLMBundle` resolves tenant credentials, instantiates the driver, resets/reports usage
- [ ] **LLM-15**: Composite model ids `model@instance@provider` and `model@provider` *(Python implementation in v1; Go mirror deferred to v2)*
- [ ] **LLM-16**: Per-tenant provider credentials (`tenant_llm`: factory, model type, API key, API base) stored encrypted
- [ ] **LLM-17**: Generation parameters are whitelisted (`ALLOWED_GEN_CONF_KEYS`) before provider calls
- [ ] **LLM-18**: Reasoning models (o1/o3) suppress `temperature` and use `max_completion_tokens`
- [ ] **LLM-19**: Provider errors map to `LLMErrorCode`; rate-limit and timeout errors are retried
- [ ] **LLM-20**: Stream sanitizer strips malformed fragments and control tokens
- [ ] **LLM-21**: Token usage is counted for streaming and non-streaming calls and recorded
- [ ] **LLM-22**: Model metadata registry: context window, max completion tokens, vision flag, input/output price
- [ ] **LLM-23**: User can list providers via `GET /providers`
- [ ] **LLM-24**: Admin/owner can add or update a provider's credentials via `PUT /providers`
- [ ] **LLM-25**: Admin/owner can delete a provider via `DELETE /providers/<provider_id_or_name>`
- [ ] **LLM-26**: User can list a provider's models via `GET /providers/<provider>/models`
- [ ] **LLM-27**: Admin/owner can create and view provider instances via `POST /providers/<provider>/instances` and `GET .../instances/<instance>`
- [ ] **LLM-28**: User can list configured models and tenant defaults via `GET /models`, `GET /models/default`
- [ ] **LLM-29**: Tenant model entities: `TenantModelProvider`, `TenantModelInstance`, `TenantModel`, `TenantModelGroup`, `TenantModelGroupMapping`
- [ ] **LLM-30**: Per-tenant Langfuse keys: set via `POST`/`PUT /langfuse/api-key`, delete via `DELETE /langfuse/api-key`
- [ ] **LLM-31**: LLM calls emit Langfuse observations when keys are configured
- [ ] **LLM-32**: Prompt generators: keyword extraction, question proposal, content tagging, metadata generation, chunk formatting
- [ ] **LLM-33**: Tool-schema decorator converts annotated functions to OpenAI function-call JSON schema
- [ ] **LLM-34**: Thinking/reasoning control injection (Qwen `enable_thinking`, Anthropic `thinking`)
- [ ] **LLM-35**: Go model service parity *(Python implementation in v1; Go mirror deferred to v2)*

### CHAT — Assistants, conversations, streaming, citations, memory

- [ ] **CHAT-01**: User can create a chat assistant with name, dataset ids, LLM id via `POST /api/v1/chats`
- [ ] **CHAT-02**: User can list assistants with paging/keywords via `GET /api/v1/chats`
- [ ] **CHAT-03**: User can update an assistant's configuration
- [ ] **CHAT-04**: User can delete an assistant via `DELETE /api/v1/chats/<chat_id>`
- [ ] **CHAT-05**: Assistant stores `prompt_config`: system prompt, prologue, empty-response text, parameters; and `prompt_type` (`simple` / `advanced`)
- [ ] **CHAT-06**: Assistant stores LLM settings: temperature, top_p, presence/frequency penalty, max tokens
- [ ] **CHAT-07**: Assistant stores retrieval settings: similarity threshold, vector weight, top-N, rerank model
- [ ] **CHAT-08**: User can create a conversation session
- [ ] **CHAT-09**: User can list sessions of an assistant via `GET /api/v1/chats/<chat_id>/sessions`
- [ ] **CHAT-10**: User can fetch a session with its full message history
- [ ] **CHAT-11**: User can delete a session
- [ ] **CHAT-12**: User can send a message and receive the answer as an SSE token stream via `POST /api/v1/chat/completions`
- [ ] **CHAT-13**: Each SSE frame is `data: {"code":0,"message":"","data":{"answer","reference","session_id"}}`; the stream ends with a terminator frame
- [ ] **CHAT-14**: Non-streaming completion when `stream=false`
- [ ] **CHAT-15**: With datasets attached the pipeline runs retrieve, rerank, build context, generate; without datasets it falls back to plain chat
- [ ] **CHAT-16**: Context construction deduplicates chunks by content hash, truncates to the token budget, and labels each chunk with document title and page
- [ ] **CHAT-17**: Conversation history is truncated newest-first to fit `max_tokens - system - knowledge - completion - margin`
- [ ] **CHAT-18**: Answers carry inline citation markers mapped to a `reference.chunks` payload
- [ ] **CHAT-19**: Post-generation citation insertion by sentence-to-chunk embedding similarity (`insert_citations`)
- [ ] **CHAT-20**: When retrieval returns nothing the assistant replies with the configured `empty_response`
- [ ] **CHAT-21**: The user turn and assistant answer with references are persisted to the conversation after the stream completes
- [ ] **CHAT-22**: User can stop generation mid-stream
- [ ] **CHAT-23**: User can give thumbs up/down feedback on an assistant message via `POST /v1/api/conversation/feedback`
- [ ] **CHAT-24**: User can annotate individual retrieved chunks as accurate/inaccurate (`ChunkFeedback`)
- [ ] **CHAT-25**: External API consumers get their own session store (`API4Conversation`)
- [ ] **CHAT-26**: Public chatbot completion via `POST /api/v1/chatbots/<dialog_id>/completions` with a beta token
- [ ] **CHAT-27**: OpenAI-compatible `/v1/chat/completions` endpoint
- [ ] **CHAT-28**: Mind-map generation from an answer (`gen_mindmap`)
- [ ] **CHAT-29**: Follow-up question proposals
- [ ] **CHAT-30**: Message file attachments
- [ ] **CHAT-31**: Answer latency and token counts recorded per turn

### SRCH — Search apps and search bots

- [ ] **SRCH-01**: User can create a search app via `POST /searches`
- [ ] **SRCH-02**: User can list search apps
- [ ] **SRCH-03**: User can get a search app via `GET /searches/<search_id>`
- [ ] **SRCH-04**: User can update a search app via `PUT /searches/<search_id>`
- [ ] **SRCH-05**: User can delete a search app
- [ ] **SRCH-06**: Search-bot Q&A via `POST /api/v1/searchbots/ask` (`question`, `kb_ids`) with beta auth
- [ ] **SRCH-07**: Search-bot retrieval test via `POST /api/v1/searchbots/retrieval_test` with beta auth

### AGT — Agents

- [ ] **AGT-01**: User can create an agent (title, description, DSL) via `POST /api/v1/agents`
- [ ] **AGT-02**: User can list agents with paging/keywords via `GET /api/v1/agents`
- [ ] **AGT-03**: User can fetch an agent's canvas DSL via `GET /api/v1/agents/<agent_id>`
- [ ] **AGT-04**: User can save an agent's canvas via `PUT /agents/<agent_id>`
- [ ] **AGT-05**: User can delete an agent via `DELETE /api/v1/agents/<agent_id>`
- [ ] **AGT-06**: User can run an agent and receive an SSE stream via `POST /api/v1/agents/chat/completions` (`agent_id`, `message`, `stream`)
- [ ] **AGT-07**: User can list, create, delete one, and bulk-delete agent sessions under `/agents/<agent_id>/sessions`
- [ ] **AGT-08**: User can list agent templates (`CanvasTemplate`)
- [ ] **AGT-09**: User can fetch agent prompt presets via `GET /agents/prompts`
- [ ] **AGT-10**: User can list agent tags via `GET /agents/tags` and set an agent's tags via `PUT /agents/<canvas_id>/tags`
- [ ] **AGT-11**: User can debug a single component via `POST /agents/<agent_id>/components/<component_id>/debug` (queued as a `dataflow` task)
- [ ] **AGT-12**: User can list and fetch agent versions via `GET /agents/<agent_id>/versions[/<version_id>]`
- [ ] **AGT-13**: User can fetch the execution log of a message via `GET /agents/<agent_id>/logs/<message_id>`
- [ ] **AGT-14**: Agent component runs a tool-calling loop up to `max_rounds` (default 5); returns the final answer or a max-rounds warning
- [ ] **AGT-15**: Bound tools get indexed function names (`google_search_0`) to prevent collisions
- [ ] **AGT-16**: Agent supports native function-calling mode and ReAct prompt mode
- [ ] **AGT-17**: Agent can enforce structured JSON output with repair
- [ ] **AGT-18**: An agent can be exposed as a tool to a supervising agent (`user_prompt`, `reasoning`, `context`)
- [ ] **AGT-19**: Agent can call tools on external MCP servers over SSE or stdio, with schemas translated to OpenAI tool format
- [ ] **AGT-20**: Tool observations are appended to the scratchpad as `tool` messages
- [ ] **AGT-21**: Agent output is written to canvas globals for downstream nodes
- [ ] **AGT-22**: RAG agent preset: query rewrite, parallel multi-KB retrieval, rerank, cited generation
- [ ] **AGT-23**: Tool: Retrieval (knowledge base)
- [ ] **AGT-24**: Tool: Google Custom Search
- [ ] **AGT-25**: Tool: DuckDuckGo
- [ ] **AGT-26**: Tool: Tavily
- [ ] **AGT-27**: Tool: ArXiv
- [ ] **AGT-28**: Tool: PubMed
- [ ] **AGT-29**: Tool: DeepL translation
- [ ] **AGT-30**: Tool: ExeSQL (SQL query execution)
- [ ] **AGT-31**: Tool: QWeather
- [ ] **AGT-32**: Tools: financial data (Tushare, AkShare, Yahoo Finance)
- [ ] **AGT-33**: Tools: SearxNG, Bing, Querit, Google Scholar
- [ ] **AGT-34**: Tool: code execution sends LLM-written code to the sandbox and returns stdout/stderr/result
- [ ] **AGT-35**: Sandbox executor manager service: `POST /execute`, pre-warmed container pool, timeout, memory cap, no-new-privileges, no network, optional seccomp
- [ ] **AGT-36**: Agents can be triggered by webhook `POST /v1/agent/<agent_id>/webhook` with security validation
- [ ] **AGT-37**: Each run executes against an immutable snapshot of the canvas (`CanvasReplicaService`)
- [ ] **AGT-38**: Run traces, component timings, inputs, and outputs are persisted per session
- [ ] **AGT-39**: Go Eino agent runtime *(Python implementation in v1; Go mirror deferred to v2)*

### FLOW — Workflow canvas engine

- [ ] **FLOW-01**: Workflows are serialized as JSON DSL with `components`, `history`, `retrieval`, `globals`, `path`; each component has `obj`, `downstream`, `upstream`
- [ ] **FLOW-02**: Graph engine loads a DSL, instantiates components, and executes from `begin` following downstream edges
- [ ] **FLOW-03**: DSL is validated before run: unknown components and cycles are rejected
- [ ] **FLOW-04**: Conditional nodes forward control only along the matched branch; unselected paths are skipped
- [ ] **FLOW-05**: System variables `sys.query`, `sys.user_id`, `sys.conversation_turns`, `sys.files`
- [ ] **FLOW-06**: Node parameters interpolate `{component_id.field}` and `{sys.*}` before execution
- [ ] **FLOW-07**: Node: Begin (inputs)
- [ ] **FLOW-08**: Node: Generate / LLM
- [ ] **FLOW-09**: Node: Retrieval
- [ ] **FLOW-10**: Node: Categorize (LLM intent classification)
- [ ] **FLOW-11**: Node: Switch (condition expressions in priority order)
- [ ] **FLOW-12**: Node: AgentWithTools
- [ ] **FLOW-13**: Node: Message (streams reply to client)
- [ ] **FLOW-14**: Node: Loop (inner subgraph until condition)
- [ ] **FLOW-15**: Node: Iteration (over array items)
- [ ] **FLOW-16**: Node: ExitLoop
- [ ] **FLOW-17**: Node: VariableAggregator
- [ ] **FLOW-18**: Node: VariableAssigner
- [ ] **FLOW-19**: Node: ListOperations (filter, sort, index, concat)
- [ ] **FLOW-20**: Node: DataOperations (JSON/dict)
- [ ] **FLOW-21**: Node: StringTransform (regex, split/join, format)
- [ ] **FLOW-22**: Node: ExcelProcessor
- [ ] **FLOW-23**: Node: DocsGenerator (Word/PDF report from template)
- [ ] **FLOW-24**: Node: Fillup (human-in-the-loop form)
- [ ] **FLOW-25**: Node: Invoke (external HTTP request)
- [ ] **FLOW-26**: Node: Browser (headless scraping)
- [ ] **FLOW-27**: Node: Code (Python via sandbox)
- [ ] **FLOW-28**: Nodes: Image Generate, Keyword Extract, Rewrite
- [ ] **FLOW-29**: Parallel branch execution
- [ ] **FLOW-30**: Runs stream SSE events `workflow_started`, `node_started`, `node_finished`, `message`, `workflow_finished` wrapped as `{type, data, message_id, created_at, session_id}`
- [ ] **FLOW-31**: `node_started` carries inputs, component id/name/type, thoughts; `node_finished` adds outputs and `elapsed_time`
- [ ] **FLOW-32**: Canvas state is checkpointed after each node to Redis/MySQL
- [ ] **FLOW-33**: A Fillup node pauses the run, emits `waiting_for_user`, and resumes from checkpoint when the user submits input
- [ ] **FLOW-34**: User can cancel a running workflow
- [ ] **FLOW-35**: Plugin manager discovers and loads tool plugins at server start
- [ ] **FLOW-36**: User can list plugin tools via `GET /plugin/tools`
- [ ] **FLOW-37**: Go Eino DAG compiler and runner *(Python implementation in v1; Go mirror deferred to v2)*

### MCP — Model Context Protocol

- [ ] **MCP-01**: MCP server at `POST /api/v1/mcp` speaking JSON-RPC, with beta auth
- [ ] **MCP-02**: MCP server exposes dataset search and chat assistants as tools
- [ ] **MCP-03**: User can list registered external MCP servers via `GET /mcp/servers` (`MCPServer` entity)

### CONN — Data-source connectors

- [ ] **CONN-01**: User can get a connector via `GET /connectors/<connector_id>`
- [ ] **CONN-02**: User can update a connector via `PATCH /connectors/<connector_id>`
- [ ] **CONN-03**: User can view sync logs via `GET /connectors/<connector_id>/logs`
- [ ] **CONN-04**: User can trigger a rebuild via `POST /connectors/<connector_id>/rebuild`
- [ ] **CONN-05**: User can test a connector via `POST /connectors/<connector_id>/test`
- [ ] **CONN-06**: Connectors link to datasets (`Connector2Kb`) and write `SyncLogs`

### CHAN — Chat channels (messaging integrations)

- [ ] **CHAN-01**: User can create/list chat channels via `POST /chat-channels`
- [ ] **CHAN-02**: User can get, update, and remove a channel via `/chat-channels/<channel_id>`
- [ ] **CHAN-03**: User can read a channel's runtime status via `GET /chat-channels/<channel_id>/runtime`
- [ ] **CHAN-04**: A reconciliation loop (every 10s) starts, stops, and reloads channel bots from the `chat_channel` table by credential fingerprint, without server restart
- [ ] **CHAN-05**: Channel: Feishu / Lark
- [ ] **CHAN-06**: Channel: DingTalk
- [ ] **CHAN-07**: Channel: WeCom
- [ ] **CHAN-08**: Channel: Discord
- [ ] **CHAN-09**: Channel: Telegram
- [ ] **CHAN-10**: Channel: LINE
- [ ] **CHAN-11**: Channel: WhatsApp
- [ ] **CHAN-12**: Channel: QQ Bot

### TMPL — Compilation templates and dataflow

- [ ] **TMPL-01**: User can list built-in compilation templates via `GET /compilation-templates/builtins`
- [ ] **TMPL-02**: User can list wiki presets via `GET /compilation-templates/wiki-presets`
- [ ] **TMPL-03**: User can list, view, create, and delete template groups under `/compilation-template-groups`
- [ ] **TMPL-04**: Dataflow result viewer shows stage-by-stage pipeline results

### SYS — System, health, stats

- [x] **SYS-01**: `GET /health` returns service health without auth
- [x] **SYS-02**: `GET /api/v1/system/ping`
- [x] **SYS-03**: `GET /api/v1/system/config` returns public configuration
- [x] **SYS-04**: `GET /api/v1/system/version`
- [x] **SYS-05**: `GET /api/v1/language` reports which engine answered (`go` / `python`)
- [x] **SYS-06**: `GET /system/status` reports dependency status (database, Redis, storage, docstore)
- [x] **SYS-07**: `GET /system/healthz`
- [ ] **SYS-09**: `GET /system/stats` returns usage statistics

### API — API-layer conventions and backend cross-cutting

- [x] **API-01**: Two backend servers: Go (Gin) for auth/user/tenant/system/search-bot/MCP; Python (Quart) for datasets/documents/chat/agents
- [x] **API-02**: Path-based routing in the reverse proxy sends each prefix to the owning server
- [x] **API-03**: All JSON responses use one envelope with numeric code, message, data
- [x] **API-04**: Routes are versioned under `/api/v1` and `/v1`
- [x] **API-05**: Go responses carry `X-API-Source: go`
- [x] **API-06**: Layered Handler, Service, DAO/Model structure in both servers
- [x] **API-07**: Request bodies are schema-validated before reaching services
- [x] **API-08**: OpenAPI v3 schema is generated for the Python API
- [x] **API-09**: Unhandled exceptions return a standardized error envelope
- [x] **API-10**: Request logging: method, path, status, duration
- [x] **API-11**: CORS middleware
- [x] **API-12**: Go server run modes via flags: `--api`, `--admin`, `--ingestor`, `--syncer`, `--migrate`
- [x] **API-13**: Python server boot: logger, DB init, optional superuser init, plugin load, background daemons
- [ ] **API-14**: Python/HTTP SDK client

### ADMIN — Administration

- [ ] **ADMIN-01**: Separate admin API server (ports 9381 Python, 9383 Go) with admin login *(Python implementation in v1; Go mirror deferred to v2)*
- [ ] **ADMIN-02**: Admin can list backend services and view one service's health, PID, host, memory
- [ ] **ADMIN-03**: Admin can start, stop, restart a service
- [ ] **ADMIN-04**: Admin can ping store, engine, MQ, and cache dependencies with latency
- [ ] **ADMIN-05**: Admin can list, show, and drop users across tenants
- [ ] **ADMIN-06**: Admin dashboard restricted to owner/admin shows system health metrics
- [ ] **ADMIN-07**: Superuser bootstrap on first start (`--init-superuser`)

### CLI — Command-line interface

- [ ] **CLI-01**: Go CLI binary with interactive REPL: line editing, auto-completion, persistent history
- [ ] **CLI-02**: Single-command batch mode
- [ ] **CLI-03**: Hand-written lexer and recursive-descent parser for the SQL-like grammar
- [ ] **CLI-04**: Output formats `table`, `plain`, `json`
- [ ] **CLI-05**: Flags: `-h/--host`, `-t/--token`, `-u/--user`, `-p/--password`, `-f/--config`, `-o/--output`, `-v/--verbose`, `--admin`, `--help`
- [ ] **CLI-06**: `rf.yml` config with named `api_servers` profiles
- [ ] **CLI-07**: Config precedence: flags, then `rf.yml`, then environment, then defaults
- [ ] **CLI-08**: `LOGIN USER`, `LOGOUT`, `REGISTER USER`
- [ ] **CLI-09**: `CREATE DATASET`, `LIST DATASETS`, `DROP DATASET`, `SHOW DATASET`
- [ ] **CLI-10**: `IMPORT FILE ... INTO DATASET`, `PARSE DOCUMENT`, `LIST DOCUMENTS`, `LIST CHUNKS`
- [ ] **CLI-11**: `SEARCH '<q>' ON DATASETS ... WITH top_k / similarity_threshold / vector_similarity_weight / keyword`
- [ ] **CLI-12**: `SET` / `RESET DEFAULT LLM` and `DEFAULT EMBEDDING`
- [ ] **CLI-13**: Virtual filesystem: `ls`, `cat`, `mkdir`, `rm`, `search` over `/datasets/{name}/...`
- [ ] **CLI-14**: `skill install` / `skill uninstall`
- [ ] **CLI-15**: Admin mode commands (services, users, roles, ping)
- [ ] **CLI-16**: Meta commands `\h`, `\q`, `\c <host:port>`, `\mode <api|admin>`, `\output <fmt>`
- [ ] **CLI-17**: Graceful cleanup on SIGINT/SIGTERM
- [ ] **CLI-18**: Benchmark runner

### UI — Frontend SPA

- [x] **UI-01**: SPA with lazy-loaded routes and layout wrappers (standard with header, full-bleed for canvas)
- [ ] **UI-02**: Auth guard redirects unauthenticated users to the login route
- [x] **UI-03**: HTTP client injects the bearer token, unwraps the envelope, surfaces non-zero codes as error notifications
- [ ] **UI-04**: HTTP 401 clears the token and session cache and redirects to login
- [ ] **UI-05**: SSE client streams tokens into UI state
- [ ] **UI-06**: Login and registration page
- [ ] **UI-07**: Session recovery on refresh by re-fetching user info
- [ ] **UI-08**: Tiered state: global stores (user, agent, chat, document), server-state hooks with caching/polling, local state, URL search params
- [ ] **UI-09**: Home dashboard
- [ ] **UI-10**: Datasets gallery with card grid and create-dataset dialog
- [ ] **UI-11**: Dataset workspace: document table with status badges
- [ ] **UI-12**: Upload dialog: drag-and-drop, extension and size validation, progress bars
- [ ] **UI-13**: Chunking-method dialog (General, Q&A, Paper, Book, Laws, Presentation, Table, Manual)
- [ ] **UI-14**: Parser configurator: chunk token size, delimiter, layout-model toggle, auto-keyword count
- [ ] **UI-15**: Live parsing progress bars, status badges (UNSTART, RUNNING, SUCCESS, FAIL), error log display
- [ ] **UI-16**: Chunk inspector: original document with highlighted bounding boxes beside chunk text
- [ ] **UI-17**: Chunk editor: edit text, toggle availability, add chunk
- [ ] **UI-18**: Retrieval-testing page: query input, similarity slider, vector/keyword weight, hit list with scores
- [ ] **UI-19**: Document viewer page
- [ ] **UI-20**: Chat playground: session sidebar, message list, input bar
- [ ] **UI-21**: Streaming token rendering with stop-generation control
- [ ] **UI-22**: Markdown rendering: GFM, syntax-highlighted code with copy button, KaTeX math, image popovers
- [ ] **UI-23**: Citation pills that open a drawer with chunk text and PDF bounding-box highlight
- [ ] **UI-24**: Feedback buttons and hit scores on assistant messages
- [ ] **UI-25**: Assistant configuration: dataset selection, LLM select, LLM setting sliders, similarity slider
- [ ] **UI-26**: Public shared chat page and embeddable chat widget (`/chats/share`, `/chats/widget`), unauthenticated
- [ ] **UI-27**: Agents list page with templates
- [ ] **UI-28**: Agent canvas: node palette, drag-and-drop graph, edge connections
- [ ] **UI-29**: Per-node configuration drawer (LLM, Retrieval, Code, Switch, Categorize, and remaining node types)
- [ ] **UI-30**: Run and debug log sheet with node execution-status animation
- [ ] **UI-31**: Embedded code editor in the Code node form
- [ ] **UI-32**: Public shared agent page (`/agent/share`)
- [ ] **UI-33**: Search app pages (`next-search`, `next-searches`)
- [ ] **UI-34**: User settings: profile
- [ ] **UI-35**: User settings: API key management dialog
- [ ] **UI-36**: User settings: team management
- [ ] **UI-37**: User settings: model provider credentials and default models
- [ ] **UI-38**: Admin pages: users, services
- [ ] **UI-39**: Compilation templates studio and pipeline operator tabs
- [ ] **UI-40**: Knowledge-graph structure visualization
- [ ] **UI-41**: Pages `files`, `skills`, `memory`, `memories`
- [ ] **UI-42**: Internationalization with locale files (zh, en, es, fr, ja, ...)
- [ ] **UI-43**: Dark / light theme
- [ ] **UI-44**: Loading, error, and empty states on every data view; responsive layout

### DATA — Relational database layer

- [x] **DATA-01**: MySQL schema for the documented entities (User, Tenant, UserTenant, InvitationCode, LLMFactories, LLM, TenantLLM, TenantLangfuse, Knowledgebase, Document, File, File2Document, Task, Dialog, Conversation, APIToken, API4Conversation, UserCanvas, CanvasTemplate, UserCanvasVersion, MCPServer, Search, Connector, Connector2Kb, ChatChannel, SyncLogs, PipelineOperationLog, CompilationTemplate, CompilationTemplateGroup, Memory, SystemSettings, FileCommit, FileCommitItem, TenantModel*)
- [x] **DATA-02**: Documented secondary indexes on `document`, `task`, `knowledgebase`, `file`
- [x] **DATA-03**: Pooled connections with retry and exponential backoff on connection loss (5 retries)
- [x] **DATA-04**: Multi-step mutations run in transactions
- [x] **DATA-05**: Schema migrations (column add, type change, index creation); `--migrate` flag on the Go server
- [x] **DATA-06**: Both servers share one schema (Peewee models and GORM structs)
- [ ] **DATA-07**: PostgreSQL and OceanBase as alternative relational backends
- [x] **DATA-08**: DB-backed lock (`DatabaseLock`)

### DEPLOY — Deployment

- [ ] **DEPLOY-01**: Multi-stage production image bundling web build, Python env, Go binaries, Nginx
- [x] **DEPLOY-02**: Base compose file for infrastructure: MySQL 8, Redis/Valkey, MinIO, with health checks and named volumes
- [x] **DEPLOY-03**: Application compose file with `cpu` profile; app waits for MySQL healthy
- [x] **DEPLOY-04**: Vector-engine profiles: `elasticsearch`, `infinity`
- [ ] **DEPLOY-06**: `gpu` profile with NVIDIA pass-through
- [ ] **DEPLOY-07**: `sandbox` profile running the executor manager
- [ ] **DEPLOY-08**: `deepdoc` profile running the layout-parsing service on 9390
- [ ] **DEPLOY-09**: `ragflow-go` profile with NATS
- [ ] **DEPLOY-10**: Entrypoint renders `service_conf.yaml` from a template with environment substitution, then starts Nginx, Go server, Python server, task executor
- [x] **DEPLOY-11**: `.env`-driven configuration covering the documented variable catalog
- [x] **DEPLOY-12**: Nginx reverse proxy: serves the SPA, routes API prefixes, TLS termination, SSE-safe buffering
- [x] **DEPLOY-13**: Single bridge network with service DNS aliases; only documented ports exposed
- [x] **DEPLOY-14**: Container health check on the app health endpoint every 10s
- [x] **DEPLOY-15**: MySQL initialized from `init.sql` on first boot
- [x] **DEPLOY-16**: Logs bind-mounted to host
- [ ] **DEPLOY-17**: Standalone task-executor container for horizontal scaling
- [ ] **DEPLOY-18**: TEI (text-embeddings-inference) image for local embedding/rerank
- [ ] **DEPLOY-19**: Helm chart / Kubernetes deployment
- [ ] **DEPLOY-20**: Compose variants for macOS and China mirrors
- [ ] **DEPLOY-21**: Documented setup instructions that bring the stack up from a clean checkout

### SEC — Security

- [x] **SEC-01**: Every non-public endpoint is behind the auth decorator/middleware
- [ ] **SEC-02**: API keys, access tokens, and LLM credentials are masked in API responses
- [ ] **SEC-03**: LLM provider keys are encrypted at rest
- [x] **SEC-04**: Secrets come from environment/config, never hard-coded, never logged
- [x] **SEC-05**: Restricted unpickler allows only whitelisted modules (`numpy`, `rag_flow`)
- [ ] **SEC-06**: Upload safety: extension check, sanitized names, UUID object keys, no path traversal
- [ ] **SEC-07**: Sandboxed code runs as non-root with memory cap, timeout, no-new-privileges, no network, seccomp filter
- [ ] **SEC-08**: Native document parsing isolated in the `deepdoc` container
- [ ] **SEC-09**: Tokens validated with an HMAC-signed secret key and expiry
- [x] **SEC-10**: Input validation prevents SQL and command injection
- [ ] **SEC-11**: Rate limiting backed by Redis

### TEST — Testing

- [x] **TEST-01**: Python unit tests (services, API, RAG) run by pytest via a `run_tests.py` runner with coverage and parallel options
- [x] **TEST-02**: Python API integration/E2E test cases against a running stack
- [x] **TEST-03**: Go unit tests (`go test ./internal/...`, with `-race`)
- [x] **TEST-04**: Go test tiers by build tag: `integration`, `e2e`, `manual`, `cgo`
- [ ] **TEST-05**: CLI lexer/parser unit tests
- [ ] **TEST-06**: Canvas state-machine unit tests and state benchmarks
- [ ] **TEST-07**: Sandbox security tests (seccomp, memory limit, blocked modules)
- [ ] **TEST-08**: Vector-engine integration tests against live engines
- [ ] **TEST-09**: Sandbox RPC integration tests
- [x] **TEST-10**: Frontend component tests (React Testing Library with Jest or Vitest)
- [ ] **TEST-11**: Database tests and pipeline tests
- [ ] **TEST-12**: Performance benchmarks

### E2E — Acceptance flows (must each pass against the real stack, no mocks)

- [ ] **E2E-01**: User registration creates user, tenant, owner link — passes against the real stack with no mocks (covers AUTH-01..04; flow: `21-end-to-end-flows/user-registration.md`)
- [ ] **E2E-02**: Login returns token, user, tenant, default models — passes against the real stack with no mocks (covers AUTH-05..07; flow: `21-.../login.md`)
- [ ] **E2E-03**: Create knowledge base provisions DB row and docstore index — passes against the real stack with no mocks (covers KB-01..03, IDX-05; flow: `21-.../create-knowledge-base.md`)
- [ ] **E2E-04**: Upload document stores blob and creates UNSTART document — passes against the real stack with no mocks (covers DOC-01..07, STOR; flow: `21-.../upload-document.md`)
- [ ] **E2E-05**: Document processing: parse request, queue, worker, DeepDoc, chunks — passes against the real stack with no mocks (covers DOC-09, ING, PARSE, CHUNK; flow: `21-.../document-processing.md`)
- [ ] **E2E-06**: Indexing: embed, optional enrichment, bulk insert, document finished — passes against the real stack with no mocks (covers IDX, CHUNK-22..26; flow: `21-.../indexing.md`)
- [ ] **E2E-07**: Ask question: tokenize, embed query, concurrent BM25 + vector search — passes against the real stack with no mocks (covers RETR-01..08; flow: `21-.../ask-question.md`)
- [ ] **E2E-08**: RAG answer: rerank, format context with citations, generate, persist — passes against the real stack with no mocks (covers RETR-11, CHAT-16..21; flow: `21-.../rag-answer.md`)
- [ ] **E2E-09**: Chat streaming over SSE with reference payload and final persistence — passes against the real stack with no mocks (covers CHAT-12, CHAT-13, UI-21, UI-23; flow: `21-.../chat-streaming.md`)
- [ ] **E2E-10**: Agent execution: load DSL, run graph, stream node events — passes against the real stack with no mocks (covers AGT-06, FLOW; flow: `21-.../agent-execution.md`)
- [ ] **E2E-11**: Workflow execution by webhook with replica snapshot and session persistence — passes against the real stack with no mocks (covers AGT-36..38; flow: `21-.../workflow-execution.md`)
- [ ] **E2E-12**: One request, full story: upload through cited streamed answer in the UI — passes against the real stack with no mocks (covers all of the above; flow: `21-.../ragflow-one-request.md`)

### BILL — Metered billing and API-key platform (from `docs/apis.md`, user-confirmed in scope)

- [ ] **BILL-01**: API keys stored as SHA-256 hash plus prefix, shown once, with ACTIVE/REVOKED/EXPIRED states, `last_used_at`, expiry
- [ ] **BILL-02**: Multiple keys per organization with rotation overlap
- [ ] **BILL-03**: Per-key permission scopes
- [ ] **BILL-04**: Redis rate limiting per key/organization (token bucket or sliding window), HTTP 429
- [ ] **BILL-05**: Plans and subscriptions
- [ ] **BILL-06**: Prepaid credit account with append-only ledger and atomic deduction; HTTP 402 at zero
- [ ] **BILL-07**: Per-endpoint / per-token cost metering and usage events
- [ ] **BILL-08**: Stripe checkout with verified webhook crediting
- [ ] **BILL-09**: `Idempotency-Key` support on paid endpoints
- [ ] **BILL-10**: Usage dashboard

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Go parity engines

- **GOPAR-01**: Go mirror of the document parsing/ingestion engine
- **GOPAR-02**: Go mirror of the retrieval engine
- **GOPAR-03**: Go mirror of chat completion
- **GOPAR-04**: Go (Eino) mirror of the agent/canvas workflow engine

### Additional doc-store engines

- **DSTORE-01**: Qdrant adapter behind the DocStore abstraction
- **DSTORE-02**: Milvus adapter
- **DSTORE-03**: PGVector adapter
- **DSTORE-04**: OpenSearch / OceanBase / Tantivy adapters
- **IDX-11**: OpenSearch adapter
- **IDX-12**: OceanBase adapter
- **IDX-13**: Further engines: ClickHouse, SereneDB, Qdrant, Milvus, PGVector, Tantivy, SeekDB
- **DEPLOY-05**: Additional engine profiles: `opensearch`, `oceanbase`, `serenedb`, `seekdb`, `clickhouse`
- **SYS-08**: `GET /system/oceanbase/status`

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full GraphRAG, retrieval evaluation harness, agent long-term memory product, skills marketplace, connector catalog, web crawler, text-to-SQL chat, SAML/SCIM, audit log, Prometheus/OTel, mobile UI, document versioning | Not described as behaviour in `docs/`; `spec.md` forbids adopting features purely because RAGFlow has them |
| Mocked, placeholder, or TODO-only implementations | Forbidden by `docs/spec.md` |
| Redesigning or simplifying documented architecture | `docs/` always wins |
| Cloning RAGFlow's visual appearance | `docs/spec.md` — reference for patterns only |
| Go mirror engines in v1 | User decision 2026-10-05: Go builds only its own routes; recorded deviation from docs |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 2 | Pending |
| AUTH-02 | Phase 2 | Pending |
| AUTH-03 | Phase 2 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| AUTH-07 | Phase 2 | Pending |
| AUTH-08 | Phase 2 | Pending |
| AUTH-09 | Phase 2 | Pending |
| AUTH-10 | Phase 2 | Pending |
| AUTH-11 | Phase 2 | Pending |
| AUTH-12 | Phase 2 | Pending |
| AUTH-13 | Phase 2 | Pending |
| AUTH-14 | Phase 2 | Pending |
| AUTH-15 | Phase 2 | Pending |
| AUTH-16 | Phase 2 | Pending |
| AUTH-17 | Phase 2 | Pending |
| AUTH-18 | Phase 2 | Pending |
| AUTH-19 | Phase 2 | Pending |
| AUTH-20 | Phase 2 | Pending |
| AUTH-21 | Phase 2 | Pending |
| AUTH-22 | Phase 2 | Pending |
| AUTH-23 | Phase 2 | Pending |
| AUTH-24 | Phase 8 | Pending |
| AUTH-25 | Phase 8 | Pending |
| TEN-01 | Phase 2 | Pending |
| TEN-02 | Phase 2 | Pending |
| TEN-03 | Phase 5 | Pending |
| TEN-04 | Phase 2 | Pending |
| TEN-05 | Phase 2 | Pending |
| TEN-06 | Phase 2 | Pending |
| TEN-07 | Phase 2 | Pending |
| TEN-08 | Phase 2 | Pending |
| TEN-09 | Phase 2 | Pending |
| TEN-10 | Phase 2 | Pending |
| TEN-11 | Phase 2 | Pending |
| TEN-12 | Phase 3 | Pending |
| TEN-13 | Phase 3 | Pending |
| TEN-14 | Phase 8 | Pending |
| TEN-15 | Phase 8 | Pending |
| TEN-16 | Phase 3 | Pending |
| KB-01 | Phase 3 | Pending |
| KB-02 | Phase 3 | Pending |
| KB-03 | Phase 3 | Pending |
| KB-04 | Phase 3 | Pending |
| KB-05 | Phase 3 | Pending |
| KB-06 | Phase 3 | Pending |
| KB-07 | Phase 3 | Pending |
| KB-08 | Phase 3 | Pending |
| KB-09 | Phase 3 | Pending |
| KB-10 | Phase 6 | Pending |
| KB-11 | Phase 6 | Pending |
| KB-12 | Phase 6 | Pending |
| KB-13 | Phase 6 | Pending |
| KB-14 | Phase 4 | Pending |
| KB-15 | Phase 4 | Pending |
| KB-16 | Phase 4 | Pending |
| KB-17 | Phase 6 | Pending |
| KB-18 | Phase 5 | Pending |
| KB-19 | Phase 4 | Pending |
| DOC-01 | Phase 3 | Pending |
| DOC-02 | Phase 3 | Pending |
| DOC-03 | Phase 3 | Pending |
| DOC-04 | Phase 3 | Pending |
| DOC-05 | Phase 3 | Pending |
| DOC-06 | Phase 3 | Pending |
| DOC-07 | Phase 3 | Pending |
| DOC-08 | Phase 3 | Pending |
| DOC-09 | Phase 4 | Pending |
| DOC-10 | Phase 4 | Pending |
| DOC-11 | Phase 4 | Pending |
| DOC-12 | Phase 4 | Pending |
| DOC-13 | Phase 4 | Pending |
| DOC-14 | Phase 3 | Pending |
| DOC-15 | Phase 3 | Pending |
| DOC-16 | Phase 3 | Pending |
| DOC-17 | Phase 6 | Pending |
| DOC-18 | Phase 6 | Pending |
| DOC-19 | Phase 6 | Pending |
| DOC-20 | Phase 4 | Pending |
| DOC-21 | Phase 4 | Pending |
| DOC-22 | Phase 4 | Pending |
| DOC-23 | Phase 4 | Pending |
| DOC-24 | Phase 8 | Pending |
| STOR-01 | Phase 3 | Pending |
| STOR-02 | Phase 3 | Pending |
| STOR-03 | Phase 8 | Pending |
| STOR-04 | Phase 8 | Pending |
| STOR-05 | Phase 8 | Pending |
| STOR-06 | Phase 3 | Pending |
| STOR-07 | Phase 8 | Pending |
| STOR-08 | Phase 3 | Pending |
| STOR-09 | Phase 6 | Pending |
| STOR-10 | Phase 3 | Pending |
| STOR-11 | Phase 3 | Pending |
| PARSE-01 | Phase 4 | Pending |
| PARSE-02 | Phase 4 | Pending |
| PARSE-03 | Phase 4 | Pending |
| PARSE-04 | Phase 6 | Pending |
| PARSE-05 | Phase 6 | Pending |
| PARSE-06 | Phase 6 | Pending |
| PARSE-07 | Phase 6 | Pending |
| PARSE-08 | Phase 6 | Pending |
| PARSE-09 | Phase 4 | Pending |
| PARSE-10 | Phase 4 | Pending |
| PARSE-11 | Phase 4 | Pending |
| PARSE-12 | Phase 4 | Pending |
| PARSE-13 | Phase 4 | Pending |
| PARSE-14 | Phase 6 | Pending |
| PARSE-15 | Phase 6 | Pending |
| PARSE-16 | Phase 6 | Pending |
| PARSE-17 | Phase 6 | Pending |
| PARSE-18 | Phase 6 | Pending |
| PARSE-19 | Phase 6 | Pending |
| PARSE-20 | Phase 6 | Pending |
| PARSE-21 | Phase 6 | Pending |
| PARSE-22 | Phase 6 | Pending |
| PARSE-23 | Phase 6 | Pending |
| PARSE-24 | Phase 6 | Pending |
| PARSE-25 | Phase 6 | Pending |
| PARSE-26 | Phase 6 | Pending |
| CHUNK-01 | Phase 4 | Pending |
| CHUNK-02 | Phase 4 | Pending |
| CHUNK-03 | Phase 6 | Pending |
| CHUNK-04 | Phase 6 | Pending |
| CHUNK-05 | Phase 6 | Pending |
| CHUNK-06 | Phase 6 | Pending |
| CHUNK-07 | Phase 6 | Pending |
| CHUNK-08 | Phase 6 | Pending |
| CHUNK-09 | Phase 6 | Pending |
| CHUNK-10 | Phase 6 | Pending |
| CHUNK-11 | Phase 6 | Pending |
| CHUNK-12 | Phase 6 | Pending |
| CHUNK-13 | Phase 6 | Pending |
| CHUNK-14 | Phase 6 | Pending |
| CHUNK-15 | Phase 6 | Pending |
| CHUNK-16 | Phase 4 | Pending |
| CHUNK-17 | Phase 4 | Pending |
| CHUNK-18 | Phase 4 | Pending |
| CHUNK-19 | Phase 4 | Pending |
| CHUNK-20 | Phase 4 | Pending |
| CHUNK-21 | Phase 4 | Pending |
| CHUNK-22 | Phase 6 | Pending |
| CHUNK-23 | Phase 6 | Pending |
| CHUNK-24 | Phase 6 | Pending |
| CHUNK-25 | Phase 6 | Pending |
| CHUNK-26 | Phase 6 | Pending |
| CHUNK-27 | Phase 6 | Pending |
| CHUNK-28 | Phase 6 | Pending |
| ING-01 | Phase 4 | Pending |
| ING-02 | Phase 4 | Pending |
| ING-03 | Phase 4 | Pending |
| ING-04 | Phase 4 | Pending |
| ING-05 | Phase 4 | Pending |
| ING-06 | Phase 4 | Pending |
| ING-07 | Phase 4 | Pending |
| ING-08 | Phase 4 | Pending |
| ING-09 | Phase 4 | Pending |
| ING-10 | Phase 4 | Pending |
| ING-11 | Phase 4 | Pending |
| ING-12 | Phase 4 | Pending |
| ING-13 | Phase 4 | Pending |
| ING-14 | Phase 4 | Pending |
| ING-15 | Phase 4 | Pending |
| ING-16 | Phase 4 | Pending |
| ING-17 | Phase 8 | Pending |
| ING-18 | Phase 6 | Pending |
| ING-19 | Phase 8 | Pending |
| ING-20 | Phase 8 | Pending |
| ING-21 | Phase 5 | Pending |
| IDX-01 | Phase 4 | Pending |
| IDX-02 | Phase 4 | Pending |
| IDX-03 | Phase 4 | Pending |
| IDX-04 | Phase 3 | Pending |
| IDX-05 | Phase 3 | Pending |
| IDX-06 | Phase 3 | Pending |
| IDX-07 | Phase 4 | Pending |
| IDX-08 | Phase 3 | Pending |
| IDX-09 | Phase 3 | Pending |
| IDX-10 | Phase 8 | Pending |
| IDX-14 | Phase 4 | Pending |
| IDX-15 | Phase 8 | Pending |
| RETR-01 | Phase 5 | Pending |
| RETR-02 | Phase 5 | Pending |
| RETR-03 | Phase 5 | Pending |
| RETR-04 | Phase 5 | Pending |
| RETR-05 | Phase 5 | Pending |
| RETR-06 | Phase 5 | Pending |
| RETR-07 | Phase 5 | Pending |
| RETR-08 | Phase 5 | Pending |
| RETR-09 | Phase 5 | Pending |
| RETR-10 | Phase 5 | Pending |
| RETR-11 | Phase 5 | Pending |
| RETR-12 | Phase 5 | Pending |
| RETR-13 | Phase 5 | Pending |
| RETR-14 | Phase 5 | Pending |
| RETR-15 | Phase 5 | Pending |
| RETR-16 | Phase 5 | Pending |
| RETR-17 | Phase 5 | Pending |
| RETR-18 | Phase 5 | Pending |
| RETR-19 | Phase 5 | Pending |
| RETR-20 | Phase 8 | Pending |
| RETR-21 | Phase 7 | Pending |
| RETR-22 | Phase 8 | Pending |
| RETR-23 | Phase 5 | Pending |
| LLM-01 | Phase 3 | Pending |
| LLM-02 | Phase 3 | Pending |
| LLM-03 | Phase 3 | Pending |
| LLM-04 | Phase 3 | Pending |
| LLM-05 | Phase 3 | Pending |
| LLM-06 | Phase 8 | Pending |
| LLM-07 | Phase 8 | Pending |
| LLM-08 | Phase 8 | Pending |
| LLM-09 | Phase 5 | Pending |
| LLM-10 | Phase 6 | Pending |
| LLM-11 | Phase 6 | Pending |
| LLM-12 | Phase 8 | Pending |
| LLM-13 | Phase 6 | Pending |
| LLM-14 | Phase 3 | Pending |
| LLM-15 | Phase 3 | Pending |
| LLM-16 | Phase 3 | Pending |
| LLM-17 | Phase 3 | Pending |
| LLM-18 | Phase 3 | Pending |
| LLM-19 | Phase 3 | Pending |
| LLM-20 | Phase 3 | Pending |
| LLM-21 | Phase 3 | Pending |
| LLM-22 | Phase 3 | Pending |
| LLM-23 | Phase 3 | Pending |
| LLM-24 | Phase 3 | Pending |
| LLM-25 | Phase 3 | Pending |
| LLM-26 | Phase 3 | Pending |
| LLM-27 | Phase 3 | Pending |
| LLM-28 | Phase 3 | Pending |
| LLM-29 | Phase 3 | Pending |
| LLM-30 | Phase 8 | Pending |
| LLM-31 | Phase 8 | Pending |
| LLM-32 | Phase 6 | Pending |
| LLM-33 | Phase 7 | Pending |
| LLM-34 | Phase 8 | Pending |
| LLM-35 | Phase 8 | Pending |
| CHAT-01 | Phase 5 | Pending |
| CHAT-02 | Phase 5 | Pending |
| CHAT-03 | Phase 5 | Pending |
| CHAT-04 | Phase 5 | Pending |
| CHAT-05 | Phase 5 | Pending |
| CHAT-06 | Phase 5 | Pending |
| CHAT-07 | Phase 5 | Pending |
| CHAT-08 | Phase 5 | Pending |
| CHAT-09 | Phase 5 | Pending |
| CHAT-10 | Phase 5 | Pending |
| CHAT-11 | Phase 5 | Pending |
| CHAT-12 | Phase 5 | Pending |
| CHAT-13 | Phase 5 | Pending |
| CHAT-14 | Phase 5 | Pending |
| CHAT-15 | Phase 5 | Pending |
| CHAT-16 | Phase 5 | Pending |
| CHAT-17 | Phase 5 | Pending |
| CHAT-18 | Phase 5 | Pending |
| CHAT-19 | Phase 5 | Pending |
| CHAT-20 | Phase 5 | Pending |
| CHAT-21 | Phase 5 | Pending |
| CHAT-22 | Phase 5 | Pending |
| CHAT-23 | Phase 5 | Pending |
| CHAT-24 | Phase 8 | Pending |
| CHAT-25 | Phase 8 | Pending |
| CHAT-26 | Phase 8 | Pending |
| CHAT-27 | Phase 8 | Pending |
| CHAT-28 | Phase 8 | Pending |
| CHAT-29 | Phase 8 | Pending |
| CHAT-30 | Phase 8 | Pending |
| CHAT-31 | Phase 5 | Pending |
| SRCH-01 | Phase 8 | Pending |
| SRCH-02 | Phase 8 | Pending |
| SRCH-03 | Phase 8 | Pending |
| SRCH-04 | Phase 8 | Pending |
| SRCH-05 | Phase 8 | Pending |
| SRCH-06 | Phase 8 | Pending |
| SRCH-07 | Phase 8 | Pending |
| AGT-01 | Phase 7 | Pending |
| AGT-02 | Phase 7 | Pending |
| AGT-03 | Phase 7 | Pending |
| AGT-04 | Phase 7 | Pending |
| AGT-05 | Phase 7 | Pending |
| AGT-06 | Phase 7 | Pending |
| AGT-07 | Phase 7 | Pending |
| AGT-08 | Phase 7 | Pending |
| AGT-09 | Phase 7 | Pending |
| AGT-10 | Phase 7 | Pending |
| AGT-11 | Phase 7 | Pending |
| AGT-12 | Phase 7 | Pending |
| AGT-13 | Phase 7 | Pending |
| AGT-14 | Phase 7 | Pending |
| AGT-15 | Phase 7 | Pending |
| AGT-16 | Phase 7 | Pending |
| AGT-17 | Phase 7 | Pending |
| AGT-18 | Phase 7 | Pending |
| AGT-19 | Phase 7 | Pending |
| AGT-20 | Phase 7 | Pending |
| AGT-21 | Phase 7 | Pending |
| AGT-22 | Phase 7 | Pending |
| AGT-23 | Phase 7 | Pending |
| AGT-24 | Phase 7 | Pending |
| AGT-25 | Phase 7 | Pending |
| AGT-26 | Phase 7 | Pending |
| AGT-27 | Phase 7 | Pending |
| AGT-28 | Phase 7 | Pending |
| AGT-29 | Phase 7 | Pending |
| AGT-30 | Phase 7 | Pending |
| AGT-31 | Phase 7 | Pending |
| AGT-32 | Phase 7 | Pending |
| AGT-33 | Phase 7 | Pending |
| AGT-34 | Phase 7 | Pending |
| AGT-35 | Phase 7 | Pending |
| AGT-36 | Phase 7 | Pending |
| AGT-37 | Phase 7 | Pending |
| AGT-38 | Phase 7 | Pending |
| AGT-39 | Phase 7 | Pending |
| FLOW-01 | Phase 7 | Pending |
| FLOW-02 | Phase 7 | Pending |
| FLOW-03 | Phase 7 | Pending |
| FLOW-04 | Phase 7 | Pending |
| FLOW-05 | Phase 7 | Pending |
| FLOW-06 | Phase 7 | Pending |
| FLOW-07 | Phase 7 | Pending |
| FLOW-08 | Phase 7 | Pending |
| FLOW-09 | Phase 7 | Pending |
| FLOW-10 | Phase 7 | Pending |
| FLOW-11 | Phase 7 | Pending |
| FLOW-12 | Phase 7 | Pending |
| FLOW-13 | Phase 7 | Pending |
| FLOW-14 | Phase 7 | Pending |
| FLOW-15 | Phase 7 | Pending |
| FLOW-16 | Phase 7 | Pending |
| FLOW-17 | Phase 7 | Pending |
| FLOW-18 | Phase 7 | Pending |
| FLOW-19 | Phase 7 | Pending |
| FLOW-20 | Phase 7 | Pending |
| FLOW-21 | Phase 7 | Pending |
| FLOW-22 | Phase 7 | Pending |
| FLOW-23 | Phase 7 | Pending |
| FLOW-24 | Phase 7 | Pending |
| FLOW-25 | Phase 7 | Pending |
| FLOW-26 | Phase 7 | Pending |
| FLOW-27 | Phase 7 | Pending |
| FLOW-28 | Phase 7 | Pending |
| FLOW-29 | Phase 7 | Pending |
| FLOW-30 | Phase 7 | Pending |
| FLOW-31 | Phase 7 | Pending |
| FLOW-32 | Phase 7 | Pending |
| FLOW-33 | Phase 7 | Pending |
| FLOW-34 | Phase 7 | Pending |
| FLOW-35 | Phase 7 | Pending |
| FLOW-36 | Phase 7 | Pending |
| FLOW-37 | Phase 7 | Pending |
| MCP-01 | Phase 8 | Pending |
| MCP-02 | Phase 8 | Pending |
| MCP-03 | Phase 7 | Pending |
| CONN-01 | Phase 8 | Pending |
| CONN-02 | Phase 8 | Pending |
| CONN-03 | Phase 8 | Pending |
| CONN-04 | Phase 8 | Pending |
| CONN-05 | Phase 8 | Pending |
| CONN-06 | Phase 8 | Pending |
| CHAN-01 | Phase 8 | Pending |
| CHAN-02 | Phase 8 | Pending |
| CHAN-03 | Phase 8 | Pending |
| CHAN-04 | Phase 8 | Pending |
| CHAN-05 | Phase 8 | Pending |
| CHAN-06 | Phase 8 | Pending |
| CHAN-07 | Phase 8 | Pending |
| CHAN-08 | Phase 8 | Pending |
| CHAN-09 | Phase 8 | Pending |
| CHAN-10 | Phase 8 | Pending |
| CHAN-11 | Phase 8 | Pending |
| CHAN-12 | Phase 8 | Pending |
| TMPL-01 | Phase 8 | Pending |
| TMPL-02 | Phase 8 | Pending |
| TMPL-03 | Phase 8 | Pending |
| TMPL-04 | Phase 8 | Pending |
| SYS-01 | Phase 1 | Complete |
| SYS-02 | Phase 1 | Complete |
| SYS-03 | Phase 1 | Complete |
| SYS-04 | Phase 1 | Complete |
| SYS-05 | Phase 1 | Complete |
| SYS-06 | Phase 1 | Complete |
| SYS-07 | Phase 1 | Complete |
| SYS-09 | Phase 8 | Pending |
| API-01 | Phase 1 | Complete |
| API-02 | Phase 1 | Complete |
| API-03 | Phase 1 | Complete |
| API-04 | Phase 1 | Complete |
| API-05 | Phase 1 | Complete |
| API-06 | Phase 1 | Complete |
| API-07 | Phase 1 | Complete |
| API-08 | Phase 1 | Complete |
| API-09 | Phase 1 | Complete |
| API-10 | Phase 1 | Complete |
| API-11 | Phase 1 | Complete |
| API-12 | Phase 1 | Complete |
| API-13 | Phase 1 | Complete |
| API-14 | Phase 8 | Pending |
| ADMIN-01 | Phase 8 | Pending |
| ADMIN-02 | Phase 8 | Pending |
| ADMIN-03 | Phase 8 | Pending |
| ADMIN-04 | Phase 8 | Pending |
| ADMIN-05 | Phase 8 | Pending |
| ADMIN-06 | Phase 8 | Pending |
| ADMIN-07 | Phase 8 | Pending |
| CLI-01 | Phase 8 | Pending |
| CLI-02 | Phase 8 | Pending |
| CLI-03 | Phase 8 | Pending |
| CLI-04 | Phase 8 | Pending |
| CLI-05 | Phase 8 | Pending |
| CLI-06 | Phase 8 | Pending |
| CLI-07 | Phase 8 | Pending |
| CLI-08 | Phase 8 | Pending |
| CLI-09 | Phase 8 | Pending |
| CLI-10 | Phase 8 | Pending |
| CLI-11 | Phase 8 | Pending |
| CLI-12 | Phase 8 | Pending |
| CLI-13 | Phase 8 | Pending |
| CLI-14 | Phase 8 | Pending |
| CLI-15 | Phase 8 | Pending |
| CLI-16 | Phase 8 | Pending |
| CLI-17 | Phase 8 | Pending |
| CLI-18 | Phase 8 | Pending |
| UI-01 | Phase 1 | Complete |
| UI-02 | Phase 2 | Pending |
| UI-03 | Phase 1 | Complete |
| UI-04 | Phase 2 | Pending |
| UI-05 | Phase 5 | Pending |
| UI-06 | Phase 2 | Pending |
| UI-07 | Phase 2 | Pending |
| UI-08 | Phase 2 | Pending |
| UI-09 | Phase 2 | Pending |
| UI-10 | Phase 3 | Pending |
| UI-11 | Phase 3 | Pending |
| UI-12 | Phase 3 | Pending |
| UI-13 | Phase 4 | Pending |
| UI-14 | Phase 4 | Pending |
| UI-15 | Phase 4 | Pending |
| UI-16 | Phase 4 | Pending |
| UI-17 | Phase 4 | Pending |
| UI-18 | Phase 5 | Pending |
| UI-19 | Phase 4 | Pending |
| UI-20 | Phase 5 | Pending |
| UI-21 | Phase 5 | Pending |
| UI-22 | Phase 5 | Pending |
| UI-23 | Phase 5 | Pending |
| UI-24 | Phase 5 | Pending |
| UI-25 | Phase 5 | Pending |
| UI-26 | Phase 8 | Pending |
| UI-27 | Phase 7 | Pending |
| UI-28 | Phase 7 | Pending |
| UI-29 | Phase 7 | Pending |
| UI-30 | Phase 7 | Pending |
| UI-31 | Phase 7 | Pending |
| UI-32 | Phase 7 | Pending |
| UI-33 | Phase 8 | Pending |
| UI-34 | Phase 2 | Pending |
| UI-35 | Phase 2 | Pending |
| UI-36 | Phase 2 | Pending |
| UI-37 | Phase 3 | Pending |
| UI-38 | Phase 8 | Pending |
| UI-39 | Phase 8 | Pending |
| UI-40 | Phase 8 | Pending |
| UI-41 | Phase 8 | Pending |
| UI-42 | Phase 2 | Pending |
| UI-43 | Phase 2 | Pending |
| UI-44 | Phase 8 | Pending |
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| DATA-06 | Phase 1 | Complete |
| DATA-07 | Phase 8 | Pending |
| DATA-08 | Phase 1 | Complete |
| DEPLOY-01 | Phase 8 | Pending |
| DEPLOY-02 | Phase 1 | Complete |
| DEPLOY-03 | Phase 1 | Complete |
| DEPLOY-04 | Phase 1 | Complete |
| DEPLOY-06 | Phase 8 | Pending |
| DEPLOY-07 | Phase 7 | Pending |
| DEPLOY-08 | Phase 6 | Pending |
| DEPLOY-09 | Phase 8 | Pending |
| DEPLOY-10 | Phase 8 | Pending |
| DEPLOY-11 | Phase 1 | Complete |
| DEPLOY-12 | Phase 1 | Complete |
| DEPLOY-13 | Phase 1 | Complete |
| DEPLOY-14 | Phase 1 | Complete |
| DEPLOY-15 | Phase 1 | Complete |
| DEPLOY-16 | Phase 1 | Complete |
| DEPLOY-17 | Phase 4 | Pending |
| DEPLOY-18 | Phase 5 | Pending |
| DEPLOY-19 | Phase 8 | Pending |
| DEPLOY-20 | Phase 8 | Pending |
| DEPLOY-21 | Phase 8 | Pending |
| SEC-01 | Phase 2 | Complete |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 3 | Pending |
| SEC-04 | Phase 1 | Complete |
| SEC-05 | Phase 1 | Complete |
| SEC-06 | Phase 3 | Pending |
| SEC-07 | Phase 7 | Pending |
| SEC-08 | Phase 6 | Pending |
| SEC-09 | Phase 2 | Pending |
| SEC-10 | Phase 1 | Complete |
| SEC-11 | Phase 8 | Pending |
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 1 | Complete |
| TEST-03 | Phase 1 | Complete |
| TEST-04 | Phase 1 | Complete |
| TEST-05 | Phase 8 | Pending |
| TEST-06 | Phase 7 | Pending |
| TEST-07 | Phase 7 | Pending |
| TEST-08 | Phase 3 | Pending |
| TEST-09 | Phase 7 | Pending |
| TEST-10 | Phase 1 | Complete |
| TEST-11 | Phase 4 | Pending |
| TEST-12 | Phase 8 | Pending |
| E2E-01 | Phase 2 | Pending |
| E2E-02 | Phase 2 | Pending |
| E2E-03 | Phase 3 | Pending |
| E2E-04 | Phase 3 | Pending |
| E2E-05 | Phase 4 | Pending |
| E2E-06 | Phase 4 | Pending |
| E2E-07 | Phase 5 | Pending |
| E2E-08 | Phase 5 | Pending |
| E2E-09 | Phase 5 | Pending |
| E2E-10 | Phase 7 | Pending |
| E2E-11 | Phase 7 | Pending |
| E2E-12 | Phase 5 | Pending |
| BILL-01 | Phase 8 | Pending |
| BILL-02 | Phase 8 | Pending |
| BILL-03 | Phase 8 | Pending |
| BILL-04 | Phase 8 | Pending |
| BILL-05 | Phase 8 | Pending |
| BILL-06 | Phase 8 | Pending |
| BILL-07 | Phase 8 | Pending |
| BILL-08 | Phase 8 | Pending |
| BILL-09 | Phase 8 | Pending |
| BILL-10 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 543 total
- Mapped to phases: 543
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-05*
*Last updated: 2026-10-05 after roadmap creation*
