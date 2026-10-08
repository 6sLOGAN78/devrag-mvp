# Phase 3: Models, Knowledge Bases and Upload - Context

**Gathered:** 2026-10-08
**Status:** Ready for planning

<domain>
## Phase Boundary

A workspace connects a real model provider, sets default chat and embedding models, creates a knowledge base (dataset) whose Elasticsearch index is provisioned with the vector dimension of its embedding model, and uploads documents into it. Documents land in the "not started" state at 0 progress.

In scope: provider credentials and model settings (API and settings UI), chat and embedding drivers proven with real calls, token usage recording, dataset create/list/get/update/delete, the `DocStoreConnection` port and the Elasticsearch adapter (index provisioning; the `search` signature is defined here so Phase 5 does not reshape it), the storage interface with MinIO and local drivers, upload with validation and content-hash dedupe, document list and delete with blob garbage collection, datasets gallery, dataset workspace and upload dialog.

Not in scope: parsing, chunking, embedding of documents and progress (Phase 4); retrieval and rerank (Phase 5/6); chat (later phases); the remaining documented providers beyond the set in D-15; billing quotas.
</domain>

<decisions>
## Implementation Decisions

Every decision in the four discussed sections was chosen by the user on 2026-10-08.

### Real model source (closes BLOCKERS B-09, refines R-50)
- **D-01:** Real chat and embedding calls go to the user's own key. The provider is **OpenRouter**, used through its OpenAI-compatible API, with **one key for both chat and embeddings**.
- **D-02:** The user places the key in the git-ignored `docker/.env`. It is never pasted in chat, never committed, never printed, and never stored on GitHub.
- **D-03:** Local Ollama is not used as the test model source in this phase. The Ollama driver is still built (LLM-05) and proven by contract tests only; a live Ollama proof is deferred.
- **D-04:** When no key is available, the local phase exit gate fails (the no-mocks rule: live tests call the real provider). GitHub CI keeps running only the offline tiers, as it does today; no provider key is configured there.
- **D-05:** Live provider tests are kept tiny: a handful of short calls per run (for example one chat, one streamed chat, one embedding batch, one provider-error case) on the cheapest suitable models. The cost of a full gate (three clean runs) should be pennies.
- **D-06:** Research must confirm that OpenRouter serves embeddings on the same key and choose the cheapest suitable chat and embedding model pair, recording the embedding dimension. If embeddings do not work on OpenRouter, stop and ask the user; do not switch source silently.

### Who manages models and datasets
- **D-07:** The workspace **owner and admins** may add, change and delete provider credentials and set the default models. Normal members can list which models exist and use them, and never see or change keys. (This differs from team management and API tokens, which stay owner-only from Phase 2.)
- **D-08:** A new dataset is visible **only to its creator** by default (permission `me`). The creator can choose `team` in the create dialog or change it later.
- **D-09:** In a dataset shared with the team, any member may upload documents and remove their own documents. Changing the dataset's settings or deleting the dataset is for its creator and the workspace owner and admins.
- **D-10:** Deleting a dataset uses a confirmation dialog that names the dataset and states its document count. Deletion is permanent: documents, stored files (subject to the shared-blob rule) and the search index are removed.

### Upload rules
- **D-11:** Maximum single file size is **100 MB**, set by configuration. Nginx and the server enforce it; an oversized file is refused and nothing is stored.
- **D-12:** Upload accepts **all documented file types** now (PDF, DOCX, PPTX, XLSX, TXT, Markdown, HTML, CSV, JSON, images and the rest the docs list). Files wait in "not started" until Phase 4 can parse them. Any other extension or MIME type is refused with HTTP 400.
- **D-13:** Configurable limits with generous defaults: documents per dataset and files per upload request, each with a clear error when exceeded. No per-workspace storage quota in bytes in this phase; that belongs to the billing work.
- **D-14:** A file whose name already exists in the dataset is kept and auto-renamed (`report.pdf` becomes `report(1).pdf`). Nothing is overwritten. Identical content still shares one stored blob (xxh64 dedupe within the tenant, as the docs specify).

### Provider coverage and the settings page
- **D-15:** The settings page offers **OpenAI, Azure OpenAI, Ollama, OpenRouter and a generic "OpenAI-compatible" entry with a base URL**. Only OpenRouter is proven with live calls in this phase; the others are proven by contract tests until a key exists. The remaining documented providers arrive in the later LLM phase.
- **D-16:** Saving a provider key **tests it first** with one tiny real call. A bad key or base URL is refused with the provider's reason and nothing is stored.
- **D-17:** A saved key is **never shown again**. API responses and the UI carry at most a mask and the last 4 characters and a "configured" state. To change a key the user enters a new one. Nobody, including the owner, can read a provider key back.
- **D-18:** Default chat and embedding models are an **explicit choice** by an owner or admin from the configured providers. Until an embedding default exists, "Create dataset" explains what is missing and links to the model settings; nothing is auto-picked.

### Carried from earlier phases (locked)
- **D-19:** Python owns every route in this phase; Go owns identity only. One envelope `{code, message, data}`; every route declared in `conf/routes.yaml` with a per-endpoint registry row; default-deny gates on both servers; permission decisions through the generated permission table (`conf/permissions.yaml`), extended for the Models and Datasets areas rather than ad-hoc role checks.
- **D-20:** Tenant isolation rule from Phase 2: another tenant's resource is indistinguishable from not-found (404, same body); a member lacking the role gets 403. Every new tenant-scoped route gets a fixture builder in the cross-tenant matrix (the matrix fails without one).
- **D-21:** Peewee owns the schema; Go only verifies. Elasticsearch 8.11.3 is the engine; MinIO is the object store. English and draft Chinese with key parity. Hand-written shadcn components; no new package without asking the user.
- **D-22:** Test discipline: test-first, live tiers against the real stack, no mocks of own services, no fixed sleeps, nothing weakened or skipped. Phase exit is `scripts/clean_room.sh --runs 3` on web port 8088 with at least 4096 MB of available RAM.
- **D-23:** No secret in logs or responses: provider keys join the existing redaction rules in the Go and Python loggers and the Nginx log format; the leak sweep from Phase 2 is extended to the new routes.

### Claude's Discretion
- The encryption scheme and key source for provider credentials at rest, within `docs/20-security/secrets.md` and `docs/11-llm/model-providers.md`.
- Default values for the configurable limits in D-13 and the exact allowed-extension list taken from the docs.
- Index naming, mapping details and analyzers, within `docs/05-rag-pipeline/indexing.md` and the documented `q_{dim}_vec` HNSW/cosine schema.
- Layout details of the settings page, datasets gallery, dataset workspace and upload dialog, to be fixed in the UI design contract (`/gsd-ui-phase 3`).
- Which cheap OpenRouter models to use for tests (D-06), and how usage is recorded.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.** `docs/` is authoritative over everything else.

### Models and providers
- `docs/11-llm/llm-architecture.md`, `provider-abstraction.md`, `model-providers.md`, `llm-request-flow.md` — driver interfaces, `LLMBundle`, composite model ids, tenant model entities
- `docs/11-llm/openai.md`, `ollama.md`, `other-providers.md`, `embeddings.md` — per-provider behaviour (OpenRouter is used through the OpenAI-compatible path)
- `docs/20-security/secrets.md` — encryption and masking of provider keys
- `docs/apikey llm.md` — token and key format notes

### Knowledge bases and index
- `docs/21-end-to-end-flows/create-knowledge-base.md` — the flow E2E-03 proves
- `docs/05-rag-pipeline/indexing.md`, `docs/17-integrations/vector-database-integrations.md` — index schema, `DocStoreConnection`
- `docs/04-api/` dataset and document API files, `docs/04-api/endpoint-catalog.md`

### Upload and storage
- `docs/06-document-processing/upload.md`, `docs/21-end-to-end-flows/upload-document.md` — validation, xxh64 dedupe, rows written
- `docs/09-storage/storage-overview.md`, `object-storage.md`, `local-storage.md`, `file-lifecycle.md`, `storage-flow.md` — storage interface, drivers, garbage collection
- `docs/20-security/file-security.md` — path traversal and file validation

### Permissions and frontend
- `docs/16-auth/permissions.md`, `docs/16-auth/multi-tenancy.md`
- `docs/02-frontend/frontend-architecture.md`, `components.md`, `document-upload-ui.md`, `api-client.md`

### Project records
- `.planning/ROADMAP.md` (Phase 3 goal, success criteria, scope notes), `.planning/REQUIREMENTS.md` (LLM-01..05, LLM-14..29, KB-01..09, TEN-12..13, TEN-16, STOR-01..02, STOR-06, STOR-08, STOR-10..11, DOC-01..08, DOC-14..16, IDX-04..06, IDX-08..09, UI-10..12, UI-37, SEC-02..03, SEC-06, TEST-08, E2E-03..04)
- `.planning/DECISIONS.md` (R-50, R-129 to R-135), `.planning/BLOCKERS.md` (B-09 closed by D-01; B-17, B-21, B-22 still open)
- `.planning/phases/02-identity-tenancy-and-authorization/02-CONTEXT.md`, `02-UI-SPEC.md`, `02-VERIFICATION.md`

### Reference implementation (read-only, lower priority than docs)
- `/home/logan78/desktop x/ragflow` — `rag/llm/`, `api/db/services/` (file, document, knowledgebase, tenant_llm services), `rag/utils/es_conn.py`, `common/doc_store/`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Python gate and credential resolution (`api/apps/auth.py`), route policy and permission tables generated by `scripts/gen_routes.py` from `conf/routes.yaml` and `conf/permissions.yaml`
- Two-tenant fixtures and the generated cross-tenant matrix and leak sweep (Phase 2, plan 02-25)
- SPA building blocks: form primitives, dialog, alert-dialog, table, native select, card, badge, masked-value pattern from the API tokens page, settings navigation group, i18n with en/zh parity

### Established Patterns
- Handler → service → dao layering; services under `api/db/services`; startup hooks under `common/bootstrap`
- Body-size limits generated per Nginx location (16k default for Go routes, large limit kept for Python upload routes); request logs use route templates and mask token-shaped values
- Rate limits are configuration values and fail closed

### Integration Points
- New Python blueprints under `api/apps/restful_apis`; new registry rows flip `implemented` as they land
- MinIO, Elasticsearch and Valkey are already in the compose stack and health checks
- `tenant` rows already carry default model id columns (empty until configured, per Phase 2 D-22)
</code_context>

<specifics>
## Specific Ideas

- The user wants the model key supplied by them in `docker/.env`, for OpenRouter, covering chat and embeddings.
- Provider keys are treated more strictly than API tokens: never readable after saving.
- Safe defaults were preferred throughout: private datasets, test-before-save, confirm before delete, nothing overwritten on upload.
</specifics>

<deferred>
## Deferred Ideas

- Live Ollama proof and the remaining documented providers — later LLM phase
- Per-workspace storage quota in bytes — billing work
- Running live provider tests on GitHub CI — not wanted now (D-04)
- Trusted-proxy client address (B-17, R-135) — deployment work
</deferred>

---

*Phase: 03-models-knowledge-bases-and-upload*
*Context gathered: 2026-10-08*
