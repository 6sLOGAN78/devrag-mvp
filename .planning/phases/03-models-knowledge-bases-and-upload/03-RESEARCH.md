# Phase 3: Models, Knowledge Bases and Upload - Research

**Researched:** 2026-10-08
**Domain:** Multi-tenant model-provider layer (LiteLLM/OpenAI-compatible/Ollama drivers), Elasticsearch doc-store port, object storage + upload pipeline, datasets/documents REST API, settings/gallery/workspace SPA
**Confidence:** MEDIUM-HIGH (live-verified: OpenRouter embeddings contract, Elasticsearch 8.11.3 mapping behaviour, Quart multipart internals, package resolution; not live-verified: any real OpenRouter call, because no key is available to this agent)

## BLOCKER CHECK (D-06): none

**OpenRouter does serve embeddings on the same key as chat.** No question for the user on that point.

- `POST https://openrouter.ai/api/v1/embeddings` exists, authenticated with the same `Authorization: Bearer <key>` header as chat. Request: `model`, `input` (string or array of strings), optional `dimensions`, `encoding_format` (`float` | `base64`). Response: `{"data":[{"embedding":[...],"index":0,"object":"embedding"}],"model":...,"object":"list","usage":{"prompt_tokens":N,"total_tokens":N}}`. [VERIFIED: openrouter.ai/openapi.json, fetched 2026-10-08, paths `/embeddings` and `/embeddings/models`]
- Chat usage is returned in the response body, and for streams "exactly once in the final chunk before `[DONE]`" (so a streamed chat needs no extra parameter to get tokens). [CITED: openrouter.ai/docs/api/reference/overview]
- **Chosen pair (cheapest suitable, public price list of 2026-10-08):**

| Role | Model id | Price (per 1M tokens) | Context | Dimension |
|------|----------|----------------------|---------|-----------|
| Chat | `meta-llama/llama-3.1-8b-instruct` | $0.05 in / $0.08 out | 131072 | n/a |
| Embedding | `baai/bge-m3` | $0.01 in | 8194 | **1024** (OpenRouter listing) |
| Chat fallback | `mistralai/mistral-nemo` ($0.019 / $0.03) | | 131072 | |
| Embedding fallback | `openai/text-embedding-3-small` ($0.02) | | 8192 | 1536 (not stated by the listing; known OpenAI default) |

  [VERIFIED: `https://openrouter.ai/api/v1/models` and `/api/v1/embeddings/models`, public endpoints, queried 2026-10-08]. Rejected: every `:free` model (rate-limited, and the free embedding listing states requests "may be retained and used to train"); reasoning models such as `openai/gpt-oss-20b` (reasoning tokens distort output and usage, LLM-18 special-casing). Cost of one gate run (about 6 chat calls of under 100 tokens and 3 embedding batches of under 100 tokens) is far below one cent [ASSUMED arithmetic].
- **The dimension must be asserted live, never hard-coded in application code.** The dimension in the listing is metadata; the live test asserts `len(vector) == 1024` for bge-m3 and the application records whatever length the provider actually returns (see Pattern 3). If bge-m3 misbehaves on first live use, switch the test config to the fallback pair; no code change.
- **State of docker/.env:** a names-only grep of `docker/.env` (no values read or printed) found no variable whose name contains `OPENROUTER` or `LLM`. The plan must therefore define the variable name (recommend `OPENROUTER_API_KEY`) and include a `checkpoint:human-verify` telling the user exactly what to add. [VERIFIED: names-only grep]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
**Real model source (closes BLOCKERS B-09, refines R-50)**
- **D-01:** Real chat and embedding calls go to the user's own key. The provider is **OpenRouter**, used through its OpenAI-compatible API, with **one key for both chat and embeddings**.
- **D-02:** The user places the key in the git-ignored `docker/.env`. It is never pasted in chat, never committed, never printed, and never stored on GitHub.
- **D-03:** Local Ollama is not used as the test model source in this phase. The Ollama driver is still built (LLM-05) and proven by contract tests only; a live Ollama proof is deferred.
- **D-04:** When no key is available, the local phase exit gate fails (the no-mocks rule: live tests call the real provider). GitHub CI keeps running only the offline tiers, as it does today; no provider key is configured there.
- **D-05:** Live provider tests are kept tiny: a handful of short calls per run (for example one chat, one streamed chat, one embedding batch, one provider-error case) on the cheapest suitable models. The cost of a full gate (three clean runs) should be pennies.
- **D-06:** Research must confirm that OpenRouter serves embeddings on the same key and choose the cheapest suitable chat and embedding model pair, recording the embedding dimension. If embeddings do not work on OpenRouter, stop and ask the user; do not switch source silently.

**Who manages models and datasets**
- **D-07:** The workspace **owner and admins** may add, change and delete provider credentials and set the default models. Normal members can list which models exist and use them, and never see or change keys. (This differs from team management and API tokens, which stay owner-only from Phase 2.)
- **D-08:** A new dataset is visible **only to its creator** by default (permission `me`). The creator can choose `team` in the create dialog or change it later.
- **D-09:** In a dataset shared with the team, any member may upload documents and remove their own documents. Changing the dataset's settings or deleting the dataset is for its creator and the workspace owner and admins.
- **D-10:** Deleting a dataset uses a confirmation dialog that names the dataset and states its document count. Deletion is permanent: documents, stored files (subject to the shared-blob rule) and the search index are removed.

**Upload rules**
- **D-11:** Maximum single file size is **100 MB**, set by configuration. Nginx and the server enforce it; an oversized file is refused and nothing is stored.
- **D-12:** Upload accepts **all documented file types** now (PDF, DOCX, PPTX, XLSX, TXT, Markdown, HTML, CSV, JSON, images and the rest the docs list). Files wait in "not started" until Phase 4 can parse them. Any other extension or MIME type is refused with HTTP 400.
- **D-13:** Configurable limits with generous defaults: documents per dataset and files per upload request, each with a clear error when exceeded. No per-workspace storage quota in bytes in this phase; that belongs to the billing work.
- **D-14:** A file whose name already exists in the dataset is kept and auto-renamed (`report.pdf` becomes `report(1).pdf`). Nothing is overwritten. Identical content still shares one stored blob (xxh64 dedupe within the tenant, as the docs specify).

**Provider coverage and the settings page**
- **D-15:** The settings page offers **OpenAI, Azure OpenAI, Ollama, OpenRouter and a generic "OpenAI-compatible" entry with a base URL**. Only OpenRouter is proven with live calls in this phase; the others are proven by contract tests until a key exists. The remaining documented providers arrive in the later LLM phase.
- **D-16:** Saving a provider key **tests it first** with one tiny real call. A bad key or base URL is refused with the provider's reason and nothing is stored.
- **D-17:** A saved key is **never shown again**. API responses and the UI carry at most a mask and the last 4 characters and a "configured" state. To change a key the user enters a new one. Nobody, including the owner, can read a provider key back.
- **D-18:** Default chat and embedding models are an **explicit choice** by an owner or admin from the configured providers. Until an embedding default exists, "Create dataset" explains what is missing and links to the model settings; nothing is auto-picked.

**Carried from earlier phases (locked)**
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

### Deferred Ideas (OUT OF SCOPE)
- Live Ollama proof and the remaining documented providers — later LLM phase
- Per-workspace storage quota in bytes — billing work
- Running live provider tests on GitHub CI — not wanted now (D-04)
- Trusted-proxy client address (B-17, R-135) — deployment work
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LLM-01 | Chat driver base interface | Pattern 1; `rag/llm/chat_model.py` `Base` with the four documented methods |
| LLM-02 | LiteLLM driver, prefix routing, default base URLs | Standard Stack (litellm), Pattern 1, prefix table below |
| LLM-03 | OpenAI chat + embeddings | `openai` SDK `OpenAIEmbed`; OpenRouter proven live through it |
| LLM-04 | Azure OpenAI deployment mapping | Contract-test URL shape in Pattern 1 |
| LLM-05 | Ollama chat + embeddings, base URL with no `/v1` | `ollama` SDK `Client.embed`; `ollama_chat/` prefix |
| LLM-14 | `LLMBundle` resolves tenant credentials, resets/reports usage | Pattern 2 |
| LLM-15 | Composite model ids | Pattern 2 (`model@instance@provider`, `model@provider`) |
| LLM-16 | Per-tenant credentials, encrypted | Pattern 4 (AES-256-GCM envelope), data model decision |
| LLM-17 | `ALLOWED_GEN_CONF_KEYS` whitelist | Code Examples |
| LLM-18 | Reasoning models suppress temperature | Pitfall 11 |
| LLM-19 | Error mapping + retry of rate-limit/timeout | Pattern 1 error table, Pitfall 9 |
| LLM-20 | Stream sanitizer | Pattern 1 |
| LLM-21 | Token usage counted and recorded | Pattern 5 |
| LLM-22 | Model metadata registry | `rag/llm/model_meta.py`, seeded for the five D-15 providers |
| LLM-23..28 | `/providers`, `/models` routes | Route table in Architecture Patterns |
| LLM-29 | Tenant model entities | Already in schema (Phase 1 baseline); services added |
| KB-01..09 | Dataset CRUD, dimension, index, parser_config | Patterns 3, 6; Pitfalls 4, 12 |
| TEN-12, 13, 16 | Default models, shared datasets, `permission` | Pattern 7 (tenant scope), permission rows |
| STOR-01, 02, 06, 08, 10, 11 | Storage interface, MinIO, local, bucket-on-write, presign, UUID keys | Pattern 8 |
| DOC-01..08, 14..16 | Upload, validation, dedupe, rows, list, delete, GC, per-doc parser | Patterns 9, 10; Pitfalls 1 to 3, 5 to 8 |
| IDX-04, 05, 06, 08, 09 | `q_{dim}_vec`, port, schema, HNSW, ES adapter | Pattern 3 and the live-verified mapping |
| UI-10, 11, 12, 37 | Gallery, workspace, upload dialog, settings | Frontend section |
| SEC-02, 03, 06 | Masking, encryption at rest, upload safety | Security Domain |
| TEST-08 | Vector-engine integration tests against live ES | Validation Architecture (contract suite) |
| E2E-03, E2E-04 | Create-KB and upload flows, no mocks | Validation Architecture |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- `docs/` always wins over `spec.md`, existing code, RAGFlow, and judgment. Do not add a service, database, queue, framework or abstraction layer without checking `docs/`.
- No critical placeholders; every feature verified by realistic execution; each phase ends working with passing tests.
- Backend must be production-oriented: typed interfaces, config/env handling, input validation, structured errors/logging, migrations, transactions, async processing, retries, timeouts, idempotency, health checks; no giant files.
- Decisions not covered by `docs/` must be recorded (what, why, how it fits) in `.planning/DECISIONS.md`. Every new decision in this document that is marked "record" must become a DECISIONS row.
- Stack rules from CLAUDE.md "What NOT to use": no FastAPI/Flask/SQLAlchemy/Celery/LangChain; `litellm` must be an exact pin, hash-locked in `uv.lock`; PyMuPDF and Ant Design are excluded; no `EventSource` (not relevant here); numpy stays below 2 (not needed in this phase).
- File changes go through a GSD workflow (this research is part of one).
- Project path contains a space and `@`: always quote paths.

## Summary

Phase 3 is the first phase where the platform talks to the outside world (a paid model provider) and the first that moves user bytes (uploads). Its risk is not in any single library; it is in six seams: (1) tenant context, because a Python `Principal` only carries the caller's **own** workspace while D-07/D-09 and success criterion 2 require acting in a workspace the caller merely joined; (2) secret handling for provider keys end to end (encryption, masking, log redaction, error echo, SSRF through a user-supplied base URL); (3) the shared blob lifecycle (xxh64 dedupe vs garbage collection under concurrency); (4) the Elasticsearch index shape, where the docs contradict each other (`ragflow_{uid}` per tenant vs `ragflow_{kb_id}` per dataset); (5) upload plumbing limits that default far too high or too low (Quart 60 s body timeout, Nginx 1024m Python default, SPA axios 10 s timeout); and (6) new packages, which D-21 says need user approval.

Everything the schema needs already exists: Phase 1 shipped all 38 tables (`knowledgebase`, `document`, `file`, `file2document`, `tenant_llm`, `tenant_model_provider/instance/model`, ...), so **no migration is required** if the dedupe lookup uses `document.content_hash` (indexed) and name/count uniqueness is serialised with the existing `DatabaseLock`. The reference RAGFlow uses one Elasticsearch index per tenant with dynamic templates; I verified live on ES 8.11.3 that an explicit per-dataset `put_mapping` of `q_{dim}_vec` (dense_vector, cosine, hnsw m=16, ef_construction=200) onto that shared index is idempotent, readable back, and gives the exact check the success criterion asks for.

**Primary recommendation:** Build `rag/llm` (LiteLLM chat + OpenAI-SDK embeddings), `common/doc_store` port with an ES adapter on one `ragflow_{tenant_id}` index per tenant plus an explicit `q_{dim}_vec` mapping per dataset, a `rag/utils` storage factory (MinIO + local), and Python-only routes behind a new `tenant_scope` helper that resolves an explicit acting tenant; encrypt provider keys with AES-256-GCM (direct-declared `pycryptodome`, no new download) under a dedicated `LLM_KEY_ENCRYPTION_KEY`; and put a package-approval checkpoint (litellm, openai, ollama, xxhash, tiktoken, pycryptodome) at the start of Wave 1.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Provider key entry, masking, "configured" state | Browser (settings form) | API (Python) | The browser only ever holds the key between typing and POST; the API is the sole holder afterwards (D-17) |
| Test-before-save (tiny real call), error mapping | API / Backend (Python) | External provider | Server-side only, so the key never needs to be echoed; bounded timeout |
| Key encryption/decryption | API / Backend | Database (ciphertext) | Key material lives only in server config (env); DB holds only the envelope |
| Default chat/embedding model selection | API / Backend | Browser | Permission-checked in Python (`tenant_settings` area); UI is a form |
| Dataset create/list/update/delete | API / Backend | Database, Doc store | Row in MySQL + index mapping in ES must succeed or roll back together |
| Vector index provisioning (`q_{dim}_vec`) | Doc store (ES) via adapter | API | Provisioned through the `DocStoreConnection` port, never from handlers |
| Upload validation (extension, size, name, count) | API / Backend | Browser (early UX check), Nginx (hard size cap) | Browser and Nginx are advisory/coarse; the server is authoritative (SEC-06) |
| Blob storage, dedupe, GC | Storage (MinIO) + Database refcount | API | Blob bytes in MinIO under UUID keys; reference counting in `file2document` |
| Cross-tenant isolation | API / Backend + Database | Doc store filter | Every query filters by the resolved acting tenant; ES filters by `kb_id` and tenant index |
| Upload progress UI, drag and drop | Browser | API | XHR upload progress per file; no streaming server push needed |
| Body size / timeout enforcement | CDN-Ingress (Nginx) | API (Quart) | Nginx rejects early (413 envelope); Quart enforces the same figure when reached directly |
| Token usage recording | API / Backend | Database | Atomic increment on the tenant model row after each provider call |

## Standard Stack

### Core (new in this phase; **all require user approval per D-21 before install**)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| litellm | `==1.103.2` exact, hash-locked | Chat provider abstraction (`LiteLLMBase`, LLM-02) | Mandated by `docs/11-llm/provider-abstraction.md`. 1.103.2 was released 2026-10-01 and has **0** OSV advisories; 1.84.0 (the CLAUDE.md baseline) has 2 (GHSA-3cv6-jpf6-8222 / PYSEC-2026-4066, proxy-server SSRF fixed in 1.88.6+; the SDK path is not the proxy, but scanners flag it). Imports cleanly under `python -W error`. [VERIFIED: PyPI JSON + api.osv.dev queried 2026-10-08] |
| openai | `>=2.20,<3` (resolves to 2.54.0) | `OpenAIEmbed`, Azure/OpenRouter/compat embeddings (LLM-03) | `docs/11-llm/openai.md`. **Do not take 3.x**: `openai 3.26.1` requires `httpx2`, and litellm requires `openai<3`. [VERIFIED: PyPI requires_dist] |
| ollama | `==0.6.3` | `OllamaEmbed` (`Client.embed`) (LLM-05) | `docs/11-llm/ollama.md`; depends only on httpx + pydantic. [VERIFIED: PyPI] |
| xxhash | `==4.0.1` | xxh64 content hash (DOC-04) | `docs/06-document-processing/upload.md`; zero dependencies. [VERIFIED: PyPI] |
| tiktoken | `>=0.12,<1` (resolves to 0.14.0) | Token counting/truncation (`cl100k_base`) | `docs/11-llm/embeddings.md`; already a transitive of litellm. Offline-safe via litellm's vendored rank file (Pitfall 10). [VERIFIED: PyPI + litellm wheel contents] |
| pycryptodome | `==3.24.0` | AES-256-GCM for provider keys (SEC-03) | **Already in `uv.lock`** (transitive of `minio`); declare it directly as D-28 did for itsdangerous. Zero new download. CLAUDE.md names `pycryptodomex` for this role; same code, different import namespace (`Crypto` vs `Cryptodome`); using the one already installed avoids a duplicate. [VERIFIED: uv.lock line 477, `.venv` pip list] |

Resolution check: `uv pip install --dry-run "litellm==1.84.0" ...` resolved 51 packages; a real `--target` install of `litellm==1.103.2 openai ollama xxhash tiktoken` measured **202 MB** and 60 packages (including aiohttp, tokenizers, huggingface-hub, jsonschema). Host has 6.7 GB free (B-03): fits, but note it. First `import litellm` takes about 4 s: import it lazily inside the driver, not at module top. [VERIFIED: local measurement]

### Already present (no action)

| Library | Version | Used for |
|---------|---------|----------|
| elasticsearch | 8.19.3 (`>=8.19,<9`) | ES adapter (sync client; `elasticsearch.dsl` is bundled, no separate `elasticsearch-dsl`) |
| minio | 7.2.20 | MinIO driver (`put_object`, `presigned_get_object`) |
| httpx | 0.28.1 | Fake-provider contract tests, SSRF-safe URL probing |
| pydantic / quart-schema | 2.13.5 / 0.25.0 | Request models |
| peewee / PyMySQL | 3.19.0 / 1.2.3 | ORM, `DatabaseLock` |
| valkey | 6.1.1 | Rate limits (reuse Phase 2 limiter for provider-test calls) |

### Frontend: no new package

Everything needed exists: `axios` (upload progress via `onUploadProgress`), `@radix-ui/react-dialog`, `alert-dialog`, `react-hook-form`+`zod`, `@tanstack/react-query`, `table`, `native-select`, `badge`, `card`, `skeleton`. **No** drag-and-drop library (`react-dropzone` is absent and not approved): use the native `dragenter/dragover/drop` events plus a hidden `<input type="file" multiple>`. **No** tabs/switch/progress primitives: hand-write them (D-21). [VERIFIED: web/package.json, web/src/components/ui]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| litellm 1.103.2 | litellm 1.84.0 (CLAUDE.md baseline) | 1.84.0 has 2 proxy-only advisories; the ref pinned it for a regression at 1.88.0 that I could not verify. Fall back to 1.84.0 (or 1.96.2) if the live gate fails on 1.103.2. Either way: exact pin, hash-locked. |
| `openai` SDK for embeddings | `litellm.aembedding` | LiteLLM's OpenRouter embedding support was not verified; the docs prescribe `OpenAIEmbed` on the OpenAI SDK for OpenAI-compatible endpoints. Use the SDK. |
| AES-GCM envelope | Fernet (needs `cryptography`, not installed) | New 20 MB wheel for no gain. |
| Per-dataset ES index (`ragflow_{kb_id}`) | Per-tenant index (recommended) | See Pattern 3 and the docs contradiction. |
| `elasticsearch[async]` | Sync client in a bounded thread pool | Async extra pulls aiohttp (arrives with litellm anyway) but the Phase 4 task executor is sync; one sync adapter serves both. |

**Installation (after the approval checkpoint):**
```bash
cd "/home/logan78/desktop x/devRag_@"
uv add "litellm==1.103.2" "openai>=2.20,<3" "ollama==0.6.3" "xxhash==4.0.1" "tiktoken>=0.12,<1" "pycryptodome==3.24.0"
uv lock   # hash-locks; commit uv.lock
```

## Package Legitimacy Audit

slopcheck was installed and run (`slopcheck install ...`; its `--json` flag does not exist in the installed version, so the plain report was used). **Note:** `slopcheck install` also runs `pip install` for the checked names; here every package was "already satisfied" in the user-site of the system Python 3.10, so nothing was changed; the project `.venv` was not touched.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| litellm | PyPI | since 2023-07 (3 yrs) | very high | github.com/BerriAI/litellm | [OK] | Approved, exact pin, hash-locked. History: 1.82.7/1.82.8 were malicious (CLAUDE.md); no yanked release in the recent window |
| openai | PyPI | since 2020-02 | very high | github.com/openai/openai-python | [OK] | Approved, `<3` |
| ollama | PyPI | since 2024-01 | high | github.com/ollama/ollama-python | [OK] | Approved |
| xxhash | PyPI | since 2014-07 | very high | github.com/ifduyue/python-xxhash | [OK] | Approved |
| tiktoken | PyPI | since 2022-12 | very high | github.com/openai/tiktoken | [OK] | Approved |
| pycryptodome | PyPI | long-established | very high | github.com/Legrandin/pycryptodome | [OK] | Approved; already locked via minio |

**Packages removed due to [SLOP]:** none. **Packages flagged [SUS]:** none. All six were discovered from the official docs/CLAUDE.md/`uv.lock`, not from search, so they may be treated as verified; the planner still adds the D-21 approval checkpoint because the user must approve each new package. Postinstall scripts: not applicable (PyPI wheels). Slopcheck's age/download figures are summarised from its OK verdict and PyPI first-release dates; exact weekly download counts were not retrieved [ASSUMED: "very high"].

## Architecture Patterns

### System Architecture Diagram

```
                       Browser (SPA, Nginx :8088)
        settings/models page      datasets gallery        dataset workspace + upload dialog
              |                        |                        |        (XHR, one POST per file)
              v                        v                        v
   ----------------------- Nginx (generated from conf/routes.yaml) -----------------------
   /api/v1/providers*,/models*   /api/v1/datasets*        /api/v1/documents/upload (101m body cap)
              \________________________|__________________________/
                                       v
                        Python Quart gate (default-deny, Principal)
                                       v
              tenant_scope.resolve(principal, requested_tenant) --> (tenant_id, role) | 404
                                       v
          handlers (api/apps/restful_apis)  -- no peewee, no models (layering test)
                                       v
      services (api/db/services)  --- permission: allowed(subject, area, action) + object rule
        |             |                   |                      |                   |
        v             v                   v                      v                   v
  provider/model   LLMBundle         knowledgebase_service   document/file_service  tenant_scope
  services         (rag.llm)         (DatabaseLock per       (hash -> dedupe ->     (joined tenants)
        |             |               tenant for name)        put blob -> 1 tx)
        |             |                   |                      |
        v             v                   v                      v
   secretbox     LiteLLM chat      DocStoreConnection       Storage factory
   (AES-GCM)     OpenAI-SDK embed   (common/doc_store)      (rag/utils: minio | local)
        |        Ollama SDK              |                      |
        v             |                  v                      v
      MySQL           v           Elasticsearch 8.11.3        MinIO bucket "ragflow"
 (tenant_llm,   OpenRouter /      index ragflow_{tenant_id}   key {tenant_id}/{uuid}
  tenant_model*) Azure/Ollama/    + explicit q_{dim}_vec
                 compat endpoint  mapping per dataset
                 (base_url guard)
```

Data-flow trace, "create dataset": SPA POST `/api/v1/datasets` -> gate -> `tenant_scope` -> permission `datasets.manage_dataset` -> service takes `DatabaseLock("kb:<tenant>")` -> duplicate-name check -> embedding model must exist in tenant and carry a recorded dimension -> `DocStoreConnection.create_idx(index, kb_id, dim)` (index created if absent, `q_{dim}_vec` mapped if absent) -> insert `knowledgebase` row -> release lock. If the row insert fails after the mapping succeeded the mapping is left (it is idempotent and shared); if `create_idx` fails nothing is inserted.

Data-flow trace, "upload": SPA POST multipart -> Nginx (413 over cap) -> gate -> permission + dataset visibility (404/403) -> parse multipart under a raised body timeout -> validate **every** file (name, extension, declared MIME, magic bytes, size, count) -> stream-hash each spooled file (xxh64 + size) -> under the dataset lock: auto-rename, dedupe lookup, put new blobs -> one DB transaction (File, Document, File2Document, `doc_num`) -> on failure delete only the blobs this request created.

### Recommended Project Structure

```
rag/
├── llm/
│   ├── __init__.py          # SupportedProvider enum, FACTORY_DEFAULT_BASE_URL, LITELLM_PROVIDER_PREFIX
│   ├── chat_model.py        # Base, LiteLLMBase, LLMErrorCode, ModelException, StreamSanitizer, ALLOWED_GEN_CONF_KEYS
│   ├── embedding_model.py   # Base, OpenAIEmbed, AzureEmbed, OllamaEmbed, _sorted_by_index, truncate
│   └── model_meta.py        # context window, max completion, vision flag, prices (LLM-22)
├── utils/
│   ├── storage_factory.py   # STORAGE_IMPL -> driver (STOR-01)
│   ├── minio_conn.py        # MinIO driver (STOR-02, 08, 10)
│   ├── local_conn.py        # local driver + sanitize_path (STOR-06)
│   └── es_conn.py           # ESConnection(DocStoreConnection)
common/
├── doc_store/doc_store_base.py   # the port: dataclasses + DocStoreConnection ABC (shared by Phase 4/5/6)
├── security/secretbox.py         # AES-256-GCM envelope, key id, mask helper
└── net/url_guard.py              # base_url validation (scheme, userinfo, link-local/metadata deny)
api/db/services/
├── llm_service.py                # LLMBundle (LLM-14)
├── tenant_llm_service.py         # credential store + usage increment
├── tenant_model_{provider,instance,model}_service.py
├── tenant_scope.py               # acting-tenant resolution (Pattern 7)
├── knowledgebase_service.py
├── document_service.py
└── file_service.py               # save/dedupe/GC
api/apps/restful_apis/{provider_api,models_api,dataset_api,document_api}.py
test/ ...                          # see Validation Architecture
web/src/pages/{datasets,dataset-detail,user-setting/models}/ + hooks/use-{dataset,document,model}-request.ts
```

Layering is enforced by `test/unit_test/test_layering.py`: handlers must not import `api.db.models`, `api.db.database` or `peewee`; services must not import quart; `rag/` must import neither `api.apps` nor quart (add a test for the new package). [VERIFIED: test_layering.py]

### Routes (all Python-owned, all added to `conf/routes.yaml` with `implemented` flipped when built)

| Method | Path | Gate | Permission (area.action) | Scope |
|--------|------|------|--------------------------|-------|
| GET | `/api/v1/providers` | api | any member (`view_models`, new) | tenant |
| PUT | `/api/v1/providers` | **jwt** | `tenant_settings.update_llm_keys` | tenant |
| DELETE | `/api/v1/providers/{provider}` | jwt | `tenant_settings.update_llm_keys` | tenant |
| GET | `/api/v1/providers/{provider}/models` | api | `view_models` | tenant |
| POST | `/api/v1/providers/{provider}/instances` | jwt | `update_llm_keys` | tenant |
| GET | `/api/v1/providers/{provider}/instances/{instance}` | api | `view_models` | tenant |
| GET | `/api/v1/models` | api | `view_models` | tenant |
| GET | `/api/v1/models/default` | api | `view_models` | tenant |
| PATCH | `/api/v1/models/default` | jwt | `tenant_settings.set_default_models` (new) | tenant |
| POST | `/api/v1/datasets` | api | `datasets.manage_dataset` + object rule | tenant |
| GET | `/api/v1/datasets` | api | member | tenant |
| GET/PUT | `/api/v1/datasets/{dataset_id}` | api | visibility + creator/owner/admin for PUT | tenant |
| DELETE | `/api/v1/datasets` | api | creator/owner/admin | tenant |
| POST | `/api/v1/documents/upload` | api | `datasets.manage_document` | tenant |
| GET | `/api/v1/datasets/{dataset_id}/documents` | api | visibility | tenant |
| DELETE | `/api/v1/datasets/{dataset_id}/documents` | api | own doc, or creator/owner/admin | tenant |

Why `jwt` and not `api` for the key-writing routes: the permission table already denies the `api_token` subject `update_llm_keys`, but making the gate `jwt` removes a whole class of mistakes (Pitfall 6). Body limits: JSON dataset/provider routes get an explicit small `body_limit` (for example `1m`); today every Python route inherits `1024m` from the `/api/` catch-all. [VERIFIED: scripts/gen_routes.py `PY_BODY_LIMIT = "1024m"`]

### Pattern 1: Drivers (`rag/llm`)

**What:** `Base` chat interface (`chat`, `async_chat`, `chat_streamly`, `async_chat_streamly`) and `LiteLLMBase` that builds `f"{PREFIX}{model}"` and passes `api_base`, `api_key`, `timeout`, and whitelisted generation params to `litellm.acompletion`. Embeddings use the OpenAI SDK (`OpenAIEmbed`, `AzureEmbed`) and the Ollama SDK (`OllamaEmbed`) with `get_embedding(texts, max_attempts=5) -> (vectors, total_tokens)`.

Provider table for D-15 (prefixes from the reference's `LITELLM_PROVIDER_PREFIX`, which routes every OpenAI-compatible gateway through `openai/` + `api_base`):

| Provider | LiteLLM model prefix | Default base URL | Embedding driver |
|----------|---------------------|------------------|------------------|
| OpenAI | `openai/` | `https://api.openai.com/v1` | `OpenAIEmbed` |
| Azure OpenAI | `azure/` (model = deployment name) + `api_version` | resource URL, required | `AzureEmbed` (`.../openai/deployments/{deployment}/embeddings?api-version=...`, header `api-key`) |
| Ollama | `ollama_chat/` | none (user supplies, **no `/v1`**) | `OllamaEmbed` (`POST /api/embed`, tokens from `prompt_eval_count`) |
| OpenRouter | `openai/` | `https://openrouter.ai/api/v1` | `OpenAIEmbed` |
| OpenAI-compatible | `openai/` | none (user supplies) | `OpenAIEmbed` |

[CITED: docs/11-llm/model-providers.md, provider-abstraction.md; ref rag/llm/__init__.py lines 73-135]

Error map (LLM-19), exceptions to `LLMErrorCode`/HTTP at the API edge:

| Provider condition | `LLMErrorCode` | Retry | Our HTTP/envelope |
|--------------------|----------------|-------|-------------------|
| 401/403 bad key | ERROR_AUTHENTICATION | no | **400** `ARGUMENT_ERROR` with a sanitized reason. **Never 401 and never code 401** (Pitfall 7) |
| 400/404/422 bad model, bad base URL | ERROR_INVALID_REQUEST | no | 400 |
| 402 insufficient credits (OpenRouter) | ERROR_INVALID_REQUEST | no | 400, message states credits are exhausted |
| 429 | ERROR_RATE_LIMIT | yes (bounded backoff + jitter, honour Retry-After) | 503 with `Retry-After` if retries exhausted |
| connect/read timeout | ERROR_TIMEOUT | yes | 504 |
| content filter | ERROR_CONTENT_FILTER | no | 400 |
| anything else | n/a | no | 502, generic message, details only in the server log (redacted) |

Retry and timeout numbers are configuration values (suggest chat 60 s, embedding 30 s, key test 20 s, 3 retries) [ASSUMED; record].

**Stream sanitizer (LLM-20):** strip control tokens and a trailing partial JSON/error fragment; skip chunks whose `choices` is empty (OpenRouter's final usage chunk) or has no `delta.content`; capture `usage` from whichever chunk carries it.

**Contract tests for non-live providers (D-15):** run a tiny in-process fake OpenAI-compatible server (Quart app on an ephemeral port, started by a fixture; this is a stand-in for a third party, not a mock of an own service) that records method, path, query, headers and body, and returns canned chat/embedding/error bodies. Assertions: OpenAI sends `Authorization: Bearer` to `/v1/chat/completions` and `/v1/embeddings`; Azure sends `api-key` to `/openai/deployments/{d}/...?api-version=`; Ollama sends `POST /api/embed {"model","input"}` with no `/v1`; compat uses the configured base URL; streaming usage is read; 401/429/timeout map as in the table. The same fake can serve the base-URL guard tests.

### Pattern 2: `LLMBundle` and composite ids (LLM-14, LLM-15)

`LLMBundle(tenant_id, model_id, model_type)` parses `model@instance@provider` or `model@provider` (instance defaults to `default`), loads the credential row, decrypts the key in memory only for the duration of the call, builds the driver, and exposes `chat`, `chat_streamly`, `encode`. It owns `_reset_last_usage()` / `_report_usage(total_tokens)`. Parsing rules: split on `@`, exactly 2 or 3 non-empty parts, no `@` inside names; model names may contain `/` and `:` (OpenRouter ids) so route parameters for models must use Quart's `<path:model_name>` converter (the ref does). [CITED: docs/11-llm/llm-architecture.md; ref provider_api.py routes]

### Pattern 3: Doc store port and Elasticsearch layout (IDX-04..09, KB-03)

**Index naming (docs conflict, decision to record).** `docs/05-rag-pipeline/indexing.md` ("Tenant Index Isolation Scheme": `index_name(uid) = f"ragflow_{uid}"`) and IDX-04 ("multiple embedding dimensions in one index") describe one index per tenant; `docs/21-end-to-end-flows/create-knowledge-base.md` and `indexing.md` (flow) write `ragflow_{kb_id}`. The reference uses the per-tenant index and explicitly keeps it alive on dataset deletion ("all kb under this tenant are in one index", `es_conn_base.delete_idx`). **Recommendation: `ragflow_{tenant_id}`** (CONTEXT names `indexing.md` as the discretion boundary; IDX-04 only makes sense with it; Phase 5 can search several datasets of a tenant in one request). Record as a DECISIONS row naming the contradiction. `INDEX_PREFIX = "ragflow_"` already exists in `common/constants.py`. `index_name()` must validate the tenant id against `^[0-9a-f]{32}$`: the port accepts comma lists and wildcards, so an unvalidated id such as `*` would address every tenant's index.

**Explicit per-dataset vector field.** At dataset creation `create_idx(index, dataset_id, vector_size)` ensures the tenant index exists (create, ignore `resource_already_exists_exception`), then `PUT /{index}/_mapping`:

```json
{"properties": {"q_1024_vec": {"type": "dense_vector", "dims": 1024, "index": true,
  "similarity": "cosine", "index_options": {"type": "hnsw", "m": 16, "ef_construction": 200}}}}
```

Live results on `elasticsearch:8.11.3` (single node, throwaway container, removed afterwards) [VERIFIED: local run 2026-10-08]:
- Re-putting the identical mapping is accepted (idempotent). Adding `q_1536_vec` and `q_4096_vec` alongside works.
- `dims` outside 1..4096 is a 400 (`should be in the range [1, 4096] but was [4097]`): validate and refuse such models up front with a clean 400.
- Re-mapping an existing field with different dims is a 400 conflict. The adapter must treat "already exists with the same dims and options" as success and a conflict as an error.
- `GET /{index}/_mapping/field/q_1024_vec` returns `{"type":"dense_vector","dims":1024,"index":true,"similarity":"cosine","index_options":{"type":"hnsw","m":16,"ef_construction":200}}`: this is exactly what E2E-03 and TEST-08 assert (use the Python client `indices.get_field_mapping`).
- **Cosine rejects zero-magnitude vectors at both insert and query** (`document_parsing_exception` / `query_shard_exception`), and a vector whose length differs from `dims` is rejected at insert. Phase 4 must guard against all-zero embeddings (empty text); the port should raise a typed error rather than let the bulk call half-fail.
- kNN with a `filter` on `kb_id` works.

Base settings and dynamic templates: start from the reference `conf/mapping.json` (scripted similarity for `*_tks`, whitespace analyzer for `*_tks` and `*_ltks`, keyword for `*_kwd|*_id|id`, `*_int`, `*_flt`, `*_with_weight` not indexed), **minus** its four hard-coded `*_512/768/1024/1536_vec` templates (the explicit mapping above replaces them and removes the 4-dimension ceiling). The scripted similarity script is Painless and was accepted by 8.11.3 in the live run. Use 1 shard, 0 replicas by default (single node), configurable; the reference uses 2 shards. `whitespace` analyzer because application-side tokenisation (Phase 4) emits space-separated tokens. Fields from IDX-06: `id`, `doc_id`, `kb_id`, `content_ltks`, `title_tks`, `important_kwd`, `question_tks`, `position_int`, `available_int`, plus `title_sm_tks`, `important_tks`, `content_sm_ltks` (covered by the `*_tks`/`*_ltks` templates). [CITED: docs/05-rag-pipeline/indexing.md; VERIFIED: ref conf/mapping.json]

**Port surface (define now so Phase 5 does not reshape it).** Mirror the reference's names (docs path `rag/utils/es_conn.py` for the adapter; port in `common/doc_store/doc_store_base.py`), but make three safety changes: `dataset_ids` is **required and non-empty** on every read/write (the reference silently drops the kb filter when the list is empty), `condition` may never be empty for `delete`/`update` (the reference turns an empty delete condition into `match_all`), and index names are validated.

```python
# common/doc_store/doc_store_base.py  (sketch; Source: ref common/doc_store/doc_store_base.py, hardened)
@dataclass(frozen=True)
class MatchTextExpr:   fields: list[str]; matching_text: str; topn: int; extra_options: dict | None = None  # minimum_should_match
@dataclass(frozen=True)
class MatchDenseExpr:  vector_column_name: str; embedding_data: Sequence[float]; embedding_data_type: str  # "float"
                       distance_type: str; topn: int = 10; extra_options: dict | None = None            # similarity threshold
@dataclass(frozen=True)
class MatchSparseExpr: ...   # reserved: Infinity only; ES adapter raises NotSupported
@dataclass(frozen=True)
class FusionExpr:      method: str; topn: int; fusion_params: dict | None = None                        # weighted_sum, weights="0.05,0.95"
class OrderByExpr:     asc(field) / desc(field)

class DocStoreConnection(ABC):
    def db_type(self) -> str: ...
    def health(self) -> dict: ...
    def create_idx(self, index_name: str, dataset_id: str, vector_size: int, parser_id: str | None = None) -> bool: ...
    def delete_idx(self, index_name: str, dataset_id: str) -> None: ...      # ES: dataset_id non-empty -> delete_by_query kb_id, keep the index
    def index_exist(self, index_name: str, dataset_id: str | None = None) -> bool: ...
    def search(self, select_fields: list[str], highlight_fields: list[str], condition: dict,
               match_expressions: list[MatchExpr], order_by: OrderByExpr | None, offset: int, limit: int,
               index_names: str | list[str], dataset_ids: list[str],
               agg_fields: list[str] | None = None, rank_feature: dict | None = None) -> SearchResult: ...
    def get(self, chunk_id: str, index_name: str, dataset_ids: list[str]) -> dict | None: ...
    def insert(self, rows: list[dict], index_name: str, dataset_id: str) -> list[str]: ...   # returns failed ids
    def update(self, condition: dict, new_value: dict, index_name: str, dataset_id: str) -> bool: ...
    def delete(self, condition: dict, index_name: str, dataset_id: str) -> int: ...
    # result helpers: get_total, get_doc_ids, get_fields, get_highlight, get_aggregation
```

Keep `sql()` out of Phase 3 (text-to-SQL is later); mark it on the ABC with a default raising `NotSupported`. `SearchResult` is a small dataclass (`total`, `hits`, `aggregations`) so callers never touch engine-specific response dicts. Phase 5 adds behaviour (RRF/weighted fusion details, rank features, highlight), not parameters. In ES the dense expression becomes top-level `knn` with the bool query as `filter`; `k = min(topn, 10000)`, `num_candidates = min(2k, 10000)` (reference behaviour).

### Pattern 4: Provider key encryption (SEC-03, SEC-02, D-17)

- **Scheme:** AES-256-GCM, 12-byte random nonce, 16-byte tag, envelope string `v1:<kid>:<base64url(nonce||ciphertext||tag)>`. **AAD** = `f"{tenant_id}|{provider}|{instance}"` so a ciphertext copied to another row fails to decrypt. A `kid` allows key rotation (decrypt with any configured id, encrypt with the active one).
- **Key source:** a dedicated `LLM_KEY_ENCRYPTION_KEY` (32 random bytes, base64) generated by `scripts/init_env.sh` through the existing `# secret` marker convention, passed through `docker-compose.yml` (`${...:?must be set}` like `SECRET_KEY`), rendered into `service_conf.yaml` by `render_conf.py`, parsed into a frozen settings dataclass with `repr` masked (`MASK`), validated at startup (length, not a placeholder), and added to `test_env_catalog.py` and `check_secrets`. Do **not** derive it from `security.secret_key`: that key signs sessions and is rotated for unrelated reasons; coupling would silently destroy stored provider keys. The model routes fail closed (503, logged once) if the key is missing; the app still boots for everything else.
- **Fit:** `tenant_model_instance.api_key` is `VARCHAR(512)` and `tenant_llm.api_key` is LONGTEXT; a 100-character key becomes about 175 characters. [VERIFIED: models/llm.py]
- **Masking (D-17):** responses carry `{"configured": true, "last4": "ab12"}` only (compute `last4` at save time and store it in the instance `extra` JSON; never decrypt to mask). Nobody can read a key back; changing it replaces the envelope.
- **Where the ciphertext lives (data-model decision, record it):** the reference and Phase 2 both use `tenant_llm` as the per-model credential row (Phase 2 registration writes `tenant_llm` rows with lower-case `chat/embedding/rerank` types; `docs/11-llm/model-providers.md` and LLM-16 name it), while the provider routes address `tenant_model_provider/instance/model` (LLM-23..29). Recommended: ciphertext in `tenant_llm.api_key` (+ `api_base`, `max_tokens`, `used_tokens`); the `tenant_model_*` rows carry the structure (ids for composite names and `tenant.tenant_llm_id`/`tenant_embd_id`) and per-model `extra` (recorded `dimension`, `max_tokens`); `tenant_model_instance.api_key` (NOT NULL) stores the non-secret display mask. One service function writes all of them in one transaction. This is an interpretation of two overlapping documented tables [ASSUMED]; see Open Question 2.

### Pattern 5: Token usage recording (LLM-21)

After every successful provider call `LLMBundle._report_usage` does an atomic `UPDATE tenant_llm SET used_tokens = LEAST(used_tokens + :n, 2147483647) WHERE tenant_id=:t AND llm_factory=:f AND llm_name=:m` (a single statement, no read-modify-write) and writes one structured log line (`tenant`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, no content, no key). `used_tokens` is a 32-bit `INT` (`IntegerField`) so cap it rather than overflow, or add a BIGINT migration (needs `conf/schema.json` regeneration and Go entity regeneration; not worth it this phase). Source of numbers: provider `usage` when present (OpenRouter chat and embeddings, OpenAI); Ollama `prompt_eval_count`/`eval_count`; fall back to tiktoken only when the provider gives none (streams without usage). The live test asserts `used_tokens` rose after the real call. Langfuse (docs mention it) is out of scope. [CITED: docs/apikey llm.md "Local Analytics Tracking"; docs/11-llm/llm-request-flow.md]

### Pattern 6: Dataset lifecycle (KB-01..09)

- Create: body `name` (1..128, trimmed), `embd_id` (composite id), `parser_id` (default `naive`; validate against the documented set `naive, qa, resume, manual, paper, laws, table, book, presentation, picture`, plus `one`, `email`, `tag`, `knowledge_graph` only if the planner finds them in docs), `permission` (`me` default per D-08, or `team`), optional `description`, `language` (default `English`), `avatar`, `parser_config`. Defaults for `parser_config` (KB-08): `{"pages":[[1,1000000]],"chunk_token_num":512,"delimiter":"\n!?;。；！？","table_context_size":0,"image_context_size":0,"layout_recognize":true,"auto_keywords":0}` [CITED: docs/06-document-processing/chunking-strategies.md; model default in `api/db/models/knowledge.py` lacks the extra keys, so merge].
- **Duplicate name:** serialise on `DatabaseLock(f"kb-create:{tenant_id}")` (GET_LOCK on a dedicated connection, outside the pool, already in `api/db/database.py`), then check, then insert. No unique index exists on `(tenant_id, name)` and adding one deviates from the documented DDL. MySQL's `utf8mb4_unicode_ci` makes the comparison case- and accent-insensitive; the 409/400 test should include a case variant. [VERIFIED: database.py, knowledge.py indexes]
- **Embedding model check (KB-02):** the `embd_id` must resolve to a `tenant_model` row of the acting tenant with the embedding bit set; the row's `extra.dimension` (recorded when the model was registered and tested, Pattern 3 / D-16) supplies the dimension. No live provider call at dataset creation. Reject `dimension` outside 1..4096.
- **Update:** name/description/parser/parser_config/permission/avatar freely (duplicate check excludes self); `embd_id` changeable only while `chunk_num == 0` and `doc_num == 0` [ASSUMED rule from the reference; record].
- **Delete (D-10):** request body `{"ids":[...]}`. Order: (1) authorise all ids first (all-or-nothing); (2) ES `delete_by_query` on `kb_id` through the port (idempotent; if ES is down answer 503 with nothing changed); (3) one DB transaction removing `task`, `file2document`, `document`, `file` (unreferenced) and the `knowledgebase` row, collecting blob keys of `file` rows that lost their last reference; (4) after commit, delete those blobs (best effort, logged, never fails the request). The delete dialog's document count comes from `doc_num` or a `COUNT(*)`.
- **Visibility query:** see Pattern 7.

### Pattern 7: Acting tenant (the main unresolved design seam)

Phase 2's Python `Principal.tenant_id` is the caller's **own** (owner) workspace only; a member of someone else's workspace has `tenant_id` of their own. Meanwhile D-07 (owner/admin of a workspace manage its keys), D-09 (members of a shared dataset upload) and success criterion 2 ("a second member of the tenant sees it") need the Python routes to operate in a workspace the caller joined. [VERIFIED: api/db/services/auth_service.py `_principal_for_user`; the SPA lists joined workspaces on the Team page but has no switcher]

**Recommendation (record as a decision; see Open Question 1):** add `api/db/services/tenant_scope.py`:
- `joined(user_id) -> {tenant_id: role}` from `user_tenant` (status `1`, role in `owner|admin|normal`; never `invite`), plus the caller's own tenant as `owner`. Cached for the request only.
- `resolve(principal, requested_tenant_id | None) -> (tenant_id, role)`: default is `principal.tenant_id`; an explicit id must be in `joined(...)` else the one **404** envelope (D-20). For an **API token** principal the tenant is fixed to the token's tenant and a different request is a 404.
- **Permission subject:** `subject = "api_token" if auth_type == "api" else "beta_token" if auth_type == "beta" else role`. `Principal.role` for a token principal is the *owner's* role, so calling `allowed(principal.role, ...)` would let an API token change provider keys (Pitfall 6).
- Id-addressed routes (dataset, document) derive the tenant from the resource (`knowledgebase.tenant_id`) and then check the caller's role in **that** tenant; routes without an id (create dataset, list datasets, providers, models) accept an optional `tenant_id` query/body parameter that defaults to the caller's own workspace.
- Dataset visibility for a caller: visible iff the caller belongs to `kb.tenant_id` (any role, own workspace included) AND (`kb.created_by == caller` OR `kb.permission == 'team'`). A `me` dataset is invisible to everyone else, owners and admins included (strict reading of D-08) [ASSUMED; Open Question 3]. Invisible -> the same 404 as non-existent.
- Object rules on top of the coarse matrix (the matrix says `normal` may `manage_dataset`; D-09 narrows it to "own"): update/delete dataset needs `created_by == caller` or role in tenant in `{owner, admin}`; remove a document needs `document.created_by == caller` or the same elevated check; a member lacking the elevated role on a visible dataset gets **403**, an invisible dataset **404**.
- SPA: a workspace selector is a UI-contract item for `/gsd-ui-phase 3` (settings and gallery default to the caller's own workspace; the Team page already lists joined ones). The minimal viable alternative, if the user does not want a selector, is: members see joined workspaces' `team` datasets in the gallery list and can open and upload to them (id-addressed routes), while keys and defaults are managed in the caller's own workspace only; then D-07 effectively applies to workspaces the person owns. The planner must not silently pick; surface it.

### Pattern 8: Storage layer (STOR-01, 02, 06, 08, 10, 11)

- Interface `put(bucket, key, data|stream, length?)`, `get(bucket, key) -> bytes`, `rm(bucket, key)`, `bucket_exists(bucket)`, plus `presigned_get_url(bucket, key, expires=3600)` (STOR-10) and `exists`. Factory reads `STORAGE_IMPL` (`MINIO` default, `LOCAL`) and returns a process-wide driver. Settings currently have only `minio`; add a `storage` section (`impl`, `local_base_dir`). Bucket `ragflow` already exists (`common.constants.BUCKET_NAME`, created by `ensure_bucket`); STOR-08 still requires create-on-first-write inside `put` (`bucket_exists` then `make_bucket`, tolerating `BucketAlreadyOwnedByYou`/`BucketAlreadyExists`, the pattern in `common/bootstrap/ensure_bucket.py`).
- **Key scheme:** `bucket = ragflow`, `key = f"{tenant_id}/{uuid4().hex}"` generated by the server, never derived from the client file name (STOR-11, `docs/09-storage/storage-flow.md`). The documented `{tenant_id}/{doc_id}` is satisfied for a first upload when the new `doc_id` is used as the uuid; a deduped document reuses the original key, so `document.location` is the source of truth, not `doc_id`.
- **Local driver (STOR-06):** resolve with `Path(base, bucket, key).resolve()` and require `is_relative_to(base)` (docs `sanitize_path`), reject absolute keys, `..`, NUL and backslashes before resolving, `0o700` directory and `O_EXCL` creation, atomic write via temp file + `os.replace`. Note the docs' base directory is a developer machine path; use a configured directory.
- **MinIO driver:** `put_object(bucket, key, data, length)` with `part_size` default for streams of known length; `presigned_get_object(bucket, key, expires=timedelta(seconds=3600))`. The presigned URL embeds the internal endpoint (`minio:9000`), unreachable from a browser behind Nginx: implement and test the method (STOR-10) but **do not expose it through a public route in this phase**. Use a short-timeout `urllib3.PoolManager` like the existing probes.
- Blocking driver calls run in a bounded dedicated thread pool (same reasoning as R-133), never on the loop's default executor.

### Pattern 9: Upload pipeline (DOC-01..07, SEC-06)

1. Route policy: `POST /api/v1/documents/upload`, `auth: api`, `body_limit` = file cap + 1 MiB (default `101m`), `streaming: true`. Set `request.max_content_length` for this request in the handler (Quart supports a per-request setter; the app-wide `MAX_CONTENT_LENGTH` stays small) and raise `BODY_TIMEOUT` for the route (default 60 s covers parse time of the whole body; 100 MB on a slow link needs minutes). [VERIFIED: quart/wrappers/request.py; `QUART BODY_TIMEOUT` default 60 in quart.app]
2. Authorise (permission `manage_document`, dataset visibility, member-of-tenant) **before** reading the body where possible; Quart parses lazily, so check headers and dataset id first. A `dataset_id` form field or query parameter; for the multipart parse use `await request.files` / `await request.form`. Quart's parser is created with `silent=True`: a malformed multipart returns **empty** files rather than an error, so "no files" must be a 400.
3. Validate every file **before** any write: sanitized-name rules, extension allow-list, declared MIME allow-list, magic bytes for binary types, size (`<= max_file_bytes`; measure by seeking to the end of the spooled file, never trust `Content-Length` of the part), files-per-request, documents-per-dataset (`doc_num + n <= max`), zero-byte files refused. Any failure rejects the whole request with 400 (413 for size) and stores nothing.
4. Stream-hash each spooled file in 1 MiB chunks (`xxhash.xxh64()` + running size + first 16 bytes for magic bytes) without loading 100 MB into memory.
5. Under `DatabaseLock(f"kb-upload:{kb_id}")`: compute auto-rename names (`report.pdf` -> `report(1).pdf`, `(2)`, ... checked against both existing documents and names earlier in the same request; keep the extension; cap total length 255), then per file the dedupe lookup, then `put` of new blobs.
6. One DB transaction: `file` (type, `parent_id`, `tenant_id`, `location`, `size`, `source_type`), `document` (`run='0'`, `progress=0.0`, `suffix`, `type`, `content_hash`, `created_by`, `parser_id`/`parser_config` copied from the dataset (DOC-16)), `file2document`, `knowledgebase.doc_num += n`. On any failure delete the blobs created by this request (not reused ones).
7. Response: list of `{id, name, size, run, progress, ...}` as the docs' example (`data: [{id, name}]`).

**Dedupe (DOC-04, `docs/06-document-processing/upload.md`):** lookup key is `(tenant_id, xxh64 hex, size)` via `document.content_hash` (indexed) joined through `file2document` to `file.tenant_id`. `document` has no `tenant_id` column (D-12 of Phase 2), so the join is mandatory: never dedupe across tenants. On a hit **verify the bytes** (stream-compare the stored blob with the upload) before reusing: xxh64 is not collision resistant and a tenant member can craft a colliding file to be linked to another member's private blob and read it. The verify only costs on duplicate uploads. On a verified hit reuse the existing `file` row (docs: "Reuse File Record & Link to Document") and add a new `document` + `file2document`.

**Allowed extensions (D-12), the union of what the docs name** [CITED: docs/06-document-processing/upload.md flow, docs/21-end-to-end-flows/upload-document.md, docs/02-frontend/document-upload-ui.md, docs/05-rag-pipeline/parsing.md, docs/06-document-processing/parsers.md]:

`pdf, docx, pptx, xlsx, txt, md, markdown, csv, json, html, htm, epub, jpg, jpeg, png, mp3, wav`

Legacy `doc`, `ppt`, `xls` are *not* named by any doc (only parser module names hint at them); exclude them and note it. Other image types the docs only call "images" (`gif`, `bmp`, `tif`, `tiff`, `webp`) are optional additions; the planner should decide with the user whether "images" means those (default: no). Make the list configuration with this as the default. MIME: accept the extension's expected types plus `application/octet-stream` and empty (browsers vary: `.md` arrives as `text/markdown` or octet-stream; `.csv` on Windows arrives as `application/vnd.ms-excel`), so build a per-extension allowed-MIME set generously, and rely on magic bytes (`%PDF-`, `PK\x03\x04` for docx/pptx/xlsx/epub, PNG/JPEG signatures, `RIFF....WAVE`, `ID3`/MPEG sync for mp3) for the binary families. Text families (txt, md, csv, json, html) get a "no NUL bytes in the first 8 KiB" check. [ASSUMED design; record]

**Filename rules (success criterion 4 says reject, not sanitise):** NFC-normalise; strip surrounding whitespace; reject (400) if empty, longer than 255, equal to `.`/`..`, containing `/`, `\`, NUL, other control characters, or a Windows drive prefix; the final component must carry an allowed extension (case-insensitive; `a.pdf.exe` has extension `exe`; `.pdf` alone has no stem and is rejected). The name is metadata only: it never reaches a path or object key, and the SPA renders it as text.

**Configuration defaults (D-13, record):** `UPLOAD_MAX_FILE_BYTES=104857600`, `UPLOAD_MAX_FILES_PER_REQUEST=20`, `DATASET_MAX_DOCUMENTS=10000`, `UPLOAD_BODY_TIMEOUT_SECONDS=600`, request body cap = file cap + 1 MiB. Nginx's `client_max_body_size` is the only layer that can cap the *request*; it cannot cap a single part, so the server enforces the per-file number and the request total is bounded at roughly one maximal file. The SPA therefore sends **one POST per file** (also what gives per-file progress bars). [ASSUMED; record]

### Pattern 10: Document delete and GC (DOC-14, DOC-15)

`DELETE /api/v1/datasets/{id}/documents` body `{"ids":[...]}`: authorise all, then (1) `DocStoreConnection.delete({"doc_id": ids}, index, dataset_id)` (chunks; must be a real call even though Phase 3 has none, DOC-14), (2) one transaction: lock each affected `file` row (`SELECT ... FOR UPDATE`), delete `task`, `file2document`, `document` rows, count remaining `file2document` per `file_id`; for zero remaining delete the `file` row and queue its blob key; decrement `doc_num`; (3) after commit `rm` the queued blobs. The dedupe path locks the same `file` row before linking, so a delete racing an upload either sees the new link (blob kept) or commits first (the upload finds no `file` row and stores a fresh blob). Blob removal failure is logged and left for a reconciliation sweep (note as a known orphan class, harmless and unreachable); never roll back the DB for it.

### Anti-Patterns to Avoid

- **`allowed(principal.role, ...)` for token principals** (Pitfall 6).
- **Returning provider 401/403 as our 401**: the SPA purges the session on any 401 or `code 401` envelope (`web/src/services/http.ts` line 237).
- **Reading the whole upload into `bytes`** (`await file.read()` on 100 MB multiplied by concurrent requests exhausts the 8 GB container budget).
- **Using the loop default executor for Peewee/ES/MinIO calls**: use a dedicated bounded executor (R-133 lesson); every blocking call gets a timeout.
- **Echoing provider response bodies or SDK exception strings** to the client or the log without redaction (SSRF body exfiltration, key fragments in messages).
- **Making dataset search "filter optional"** in the port.
- **A second component system or a drag-and-drop dependency** in the SPA.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chat provider routing, streaming, usage | A per-provider HTTP client | `litellm.acompletion` with `openai/` + `api_base` | Docs-mandated; handles SSE framing, usage chunks, provider quirks |
| Embedding HTTP calls | Raw httpx to `/embeddings` | `openai` SDK (`OpenAIEmbed`), `ollama` SDK | Index re-ordering, retries, base64 decoding handled |
| Authenticated encryption | XOR/Fernet clones, homemade padding | AES-GCM from pycryptodome with AAD | Nonce misuse and tag checks are easy to get wrong |
| Non-cryptographic content hash | A Python-loop hash | `xxhash.xxh64` | Docs-mandated, C speed |
| Multipart parsing | A manual boundary parser | Quart `request.files` (werkzeug parser, spools to temp files > 500 KB) | Edge cases in boundaries and headers |
| Dataset-name serialisation | Python locks or sleep loops | `api.db.database.DatabaseLock` (MySQL `GET_LOCK` on its own connection) | Works across workers and processes |
| Vector index lifecycle | Hand-built `curl` mappings in handlers | `DocStoreConnection.create_idx` adapter | Keeps Infinity possible later (v1 scope) |
| Presigned URLs | Self-signed URLs | `Minio.presigned_get_object` | SigV4 details |
| Route/registry/permission tables | Hard-coded role checks | `conf/routes.yaml` + `conf/permissions.yaml` -> `scripts/gen_routes.py` | D-19; drift gate and oracle tests exist |
| Log redaction | New regexes in feature code | Extend `common/log_utils.py` + the Go logger + Nginx map with shared vectors | One place, linear-time design from Phase 2 |
| Cross-tenant tests | Bespoke per-route tests only | Registry-driven matrix (`_matrix_fixtures.py`) | A route without a fixture fails the suite |

**Key insight:** every piece here has a documented or already-present building block. The work is wiring them with the safety rules above (tenant filter mandatory, secrets never echoed, blob lifecycle under a lock), not inventing components.

## Runtime State Inventory

Not a rename/refactor phase; omitted. One related fact: Phase 2 registration already writes `tenant_llm` rows (lower-case `chat/embedding/rerank`, no key) when `DEFAULT_*` model variables are set. Phase 3 code must read those rows without assuming a key is present, and must pick one case convention for `model_type` (docs write upper-case `CHAT`, `EMBEDDING`; the existing Go writer and its tests use lower-case): keep lower-case in `tenant_llm` to avoid touching Phase 2, upper-case never stored. [VERIFIED: internal/dao/tenant_llm.go]

## Common Pitfalls

### Pitfall 1: Dedupe link to a blob that is being garbage-collected
**What goes wrong:** Upload B finds the existing `file` row and links to it while delete A commits and removes the blob; B's document points at nothing.
**Why:** Reference count (`file2document`) and blob removal are two systems.
**How to avoid:** `SELECT ... FOR UPDATE` the `file` row in both paths; delete the blob only after the transaction that removed the last link committed and the `file` row is gone; the dedupe path re-checks the row inside its transaction. Add a concurrent live test (two threads, delete vs duplicate upload).
**Warning signs:** `get` of a document's `location` returns NoSuchKey.

### Pitfall 2: xxh64 collision gives one member another member's file
**What goes wrong:** Crafted collision -> new upload is linked to a victim's blob in a private (`me`) dataset.
**How to avoid:** key on hash + size and byte-compare the stored blob before reuse (Pattern 9). Test with two different files forced to the same lookup key (insert a `document` row with a chosen `content_hash`/size in the test, or monkeypatch only the hash function in a unit test).

### Pitfall 3: Validation after the write
**What goes wrong:** Blob stored, then the extension check fails, leaving an orphan; or file 3 of 5 fails after 1-2 are committed.
**How to avoid:** validate the whole request first; blobs created in this request are compensated on any later failure; one DB transaction per request. Success criterion 4 is "nothing is stored": the live test lists the MinIO prefix before and after.

### Pitfall 4: Dataset delete leaves chunks or half-deletes
**What goes wrong:** ES unreachable -> rows gone but chunks remain (invisible but orphaned), or the reverse.
**How to avoid:** ES delete first and fail the request if it fails; DB transaction second; blobs last. Re-running the same request must be safe (idempotent `delete_by_query`).

### Pitfall 5: Quart silently turns a malformed multipart into "no files"
**What goes wrong:** `request.files` is empty for a bad boundary; code treats it as success with 0 documents.
**How to avoid:** zero files is a 400; test a truncated body and a body without boundary. [VERIFIED: `FormDataParser(silent=True)` in quart/formparser.py]

### Pitfall 6: API-token principals carry the owner's role
**What goes wrong:** `allowed(principal.role, "tenant_settings", "update_llm_keys")` passes for an API token, contradicting the permission table which denies the `api_token` subject.
**How to avoid:** compute the subject from `auth_type` first (Pattern 7), make the key-writing routes `auth: jwt`, and add a matrix test: API token on PUT `/providers` is refused. [VERIFIED: auth_service.py `_principal_for_token`, permissions_gen.py]

### Pitfall 7: Provider 401 ends the user's session
**What goes wrong:** A wrong provider key is returned as HTTP 401 (or envelope code 401); the SPA's response interceptor purges the session and redirects to login.
**How to avoid:** never propagate upstream status codes; use 400 with a sanitized reason for a rejected provider credential. Test in the SPA live suite that a bad key keeps the user signed in. [VERIFIED: web/src/services/http.ts:237]

### Pitfall 8: SPA and Nginx timeouts
**What goes wrong:** The SPA's axios instance has a 10 s timeout (`TIMEOUT_MS`), killing a 100 MB upload and the save-time key test; Quart's `BODY_TIMEOUT` is 60 s; Nginx's `client_body_timeout` is 30 s *between reads* (fine).
**How to avoid:** per-request axios `timeout: 0` (or minutes) for uploads with `onUploadProgress`, 45 s for the provider save; server `BODY_TIMEOUT` raised on the upload route only; server key-test timeout 20 s. [VERIFIED: http.ts line 28; quart.app config]

### Pitfall 9: Retry storms and SDK-level retries
**What goes wrong:** LiteLLM and the OpenAI SDK both retry by default; combined with our own retry the call count multiplies (cost and rate-limit pressure).
**How to avoid:** set `max_retries=0` on SDK clients and `num_retries=0` for LiteLLM and own the single retry loop (LLM-19). Never retry a non-idempotent state change (the key test is idempotent; saving is not).

### Pitfall 10: tiktoken tries to download its vocabulary
**What goes wrong:** First `tiktoken.get_encoding("cl100k_base")` fetches from the internet; fails in the app container / CI.
**How to avoid:** litellm vendors the rank file (`litellm/litellm_core_utils/tokenizers/9b5ad71b...`, the sha1 cache name tiktoken expects); set `TIKTOKEN_CACHE_DIR` to that directory before first use. Provider-reported usage is preferred anyway. [VERIFIED: litellm 1.103.2 wheel contents; the cache-dir mechanism is MEDIUM, confirm in a unit test run with the network blocked]

### Pitfall 11: Embedding request shape differences
**What goes wrong:** The OpenAI SDK requests `encoding_format=base64` by default and decodes; some OpenAI-compatible gateways do not implement it. Order of results can differ from input. Empty strings are rejected (OpenRouter `minLength: 1`). Reasoning models need `max_completion_tokens` and no `temperature` (LLM-18).
**How to avoid:** always pass `encoding_format="float"`; sort by `index` (`_sorted_by_index`); replace empty text with a single space; truncate to the model limit (8192 token ceiling in the docs, but bge-m3 listing says 8194, use the lower).

### Pitfall 12: Embedding model change or dimension mismatch after creation
**What goes wrong:** Changing a dataset's embedding model after chunks exist leaves vectors in a different space (even at the same dimension, `q_{dim}_vec` is shared by dimension, not by model).
**How to avoid:** `embd_id` immutable once `chunk_num > 0 or doc_num > 0`; the dimension recorded in `tenant_model.extra` at registration is the single source; chunks always filter by `kb_id`.

### Pitfall 13: Base URL as an SSRF primitive
**What goes wrong:** An admin enters `http://169.254.169.254/...`, `http://es01:9200`, or `http://minio:9000`; the key test then probes internal services and the "provider's reason" returned to the user leaks their responses. (Also the shape of GHSA-3cv6-jpf6-8222 in LiteLLM's proxy.)
**How to avoid:** `common/net/url_guard.py`: scheme `http|https` only, no userinfo, no fragment; resolve the host and **deny link-local (169.254.0.0/16, fe80::/10), metadata endpoints, and the project's own service hostnames** always; allow loopback/private ranges only when `LLM_ALLOW_PRIVATE_BASE_URLS` is true (needed for a local Ollama; make it default true in the dev compose, false in production) [ASSUMED policy; record]; re-resolve at call time (DNS rebinding) by connecting to the validated address or re-validating; never follow redirects to a different host; return only a parsed provider error message (`error.message`, truncated to 200 characters, redacted), never a raw body.

### Pitfall 14: Keys in logs and messages
**What goes wrong:** Existing redaction is key-name based (`api_key`, `authorization`, `Bearer`), so a key inside a free-form message (an SDK exception text "Incorrect API key provided: sk-or-v1-...") is not masked; Python `logging` at DEBUG by openai/httpx/litellm can print headers or payloads.
**How to avoid:** add shape-based patterns (`sk-or-v1-[A-Za-z0-9]{16,}`, `sk-[A-Za-z0-9_-]{20,}`) to the Python redactor, the Go logger and the Nginx `$loggable_uri` map with entries in `test/fixtures/log_redaction_vectors.json`; set `litellm.suppress_debug_info=True`, `litellm.set_verbose=False`, leave `litellm`, `openai`, `httpx` loggers at WARNING; never `str(exc)` a provider exception into a response; extend the Phase 2 leak sweep (`_leak_sweep.py`) with a sentinel key to every new response and log. A body-size note: the PUT body carries the key, so the request log must not record bodies (it records route templates only today). [VERIFIED: common/log_utils.py SENSITIVE_KEYS]

### Pitfall 15: Matrix and registry drift
**What goes wrong:** New scope-tenant routes without a matrix fixture fail `coverage_problems`; new permission rows without regenerated tables fail the drift gate; Go `permission_cases.json` oracle may need cases for new rows.
**How to avoid:** make the route-registry + permissions + matrix-builder change one task per route family, run `scripts/gen_routes.py` and `--check`, add the Go oracle cases. The `world` fixture needs builders that create a provider/instance (needs a fake or the live provider; use a local fake-provider URL for matrix fixtures since the matrix is about isolation, not provider behaviour) and a dataset + document per tenant.

### Pitfall 16: ES cluster flood-stage watermark on this host
**What goes wrong:** With 97% disk used a stock ES container goes red/read-only (observed in the research probe). The project's compose already sets low dev watermarks (R-56). Live tests that create indices must run against the project stack, not a bare ES. `vm.max_map_count` stays 65530 (B-02, override recorded).

## Code Examples

### Generation parameter whitelist (LLM-17)
```python
# Source: docs/11-llm/llm-architecture.md "Generation Parameter Filtering"
ALLOWED_GEN_CONF_KEYS = frozenset({
    "temperature", "max_completion_tokens", "top_p", "stream", "stream_options", "stop", "n",
    "presence_penalty", "frequency_penalty", "functions", "function_call", "logit_bias", "user",
    "response_format", "seed", "tools", "tool_choice", "logprobs", "top_logprobs", "extra_headers",
})

def sanitize_gen_conf(conf: dict, model_name: str) -> dict:
    out = {k: v for k, v in (conf or {}).items() if k in ALLOWED_GEN_CONF_KEYS}
    if REASONING_MODEL.match(model_name):          # o1 / o3 families (LLM-18)
        out.pop("temperature", None)
        if "max_tokens" in (conf or {}):
            out["max_completion_tokens"] = conf["max_tokens"]
    return out
```
`extra_headers` is on the documented whitelist; treat it as caller-trusted only (never from an HTTP request body) because it can override `Authorization`.

### AES-GCM envelope (SEC-03)
```python
# Source: pycryptodome AES-GCM (pycryptodome.readthedocs.io), envelope layout is this project's decision
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

def seal(key: bytes, kid: str, plaintext: str, aad: str) -> str:
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(aad.encode())
    ct, tag = cipher.encrypt_and_digest(plaintext.encode())
    return f"v1:{kid}:" + base64.urlsafe_b64encode(nonce + ct + tag).decode()

def open_(keys: dict[str, bytes], envelope: str, aad: str) -> str:
    version, kid, blob = envelope.split(":", 2)
    raw = base64.urlsafe_b64decode(blob)
    nonce, ct, tag = raw[:12], raw[12:-16], raw[-16:]
    cipher = AES.new(keys[kid], AES.MODE_GCM, nonce=nonce)
    cipher.update(aad.encode())
    return cipher.decrypt_and_verify(ct, tag).decode()    # raises ValueError on tamper or wrong AAD
```
Test vectors: round trip; wrong AAD fails; wrong key fails; tampered tail fails; two seals of the same plaintext differ; the stored column never contains the plaintext (assert against MySQL).

### Stream-hash one uploaded file without loading it
```python
# Source: xxhash docs (python-xxhash); chunked read of a werkzeug FileStorage spool
def hash_and_measure(stream, chunk=1 << 20):
    h, size, head = xxhash.xxh64(), 0, b""
    stream.seek(0)
    while block := stream.read(chunk):
        if not head: head = block[:16]
        h.update(block); size += len(block)
    stream.seek(0)
    return h.hexdigest(), size, head          # 16 hex chars: fits document.content_hash varchar(32)
```
Run it via the storage thread pool, not on the event loop.

### Mapping the vector field through the Python client
```python
# Source: verified against elasticsearch:8.11.3 on 2026-10-08 (REST); client call shape per elasticsearch-py 8.x
es.indices.put_mapping(index=index_name, properties={
    f"q_{dim}_vec": {"type": "dense_vector", "dims": dim, "index": True, "similarity": "cosine",
                     "index_options": {"type": "hnsw", "m": 16, "ef_construction": 200}}})
info = es.indices.get_field_mapping(index=index_name, fields=f"q_{dim}_vec")
```

### Live OpenRouter calls the live tier makes (tiny, D-05)
```python
# 1 non-stream chat, 1 streamed chat (usage in final chunk), 1 embedding batch of 2 strings, 1 bad-key error case.
# Key comes from the environment of THIS test process only; never logged. Models via env:
#   LIVE_CHAT_MODEL=meta-llama/llama-3.1-8b-instruct   LIVE_EMBED_MODEL=baai/bge-m3   LIVE_EXPECTED_DIM=1024
# The tests drive the PRODUCT API (PUT /providers, PATCH /models/default, then a real call through LLMBundle
# via a test-only service entry or the dataset create path), then read tenant_llm.used_tokens from MySQL.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `elasticsearch-dsl` separate package | `elasticsearch.dsl` bundled in the client (8.18+) | 2025 | Do not add `elasticsearch-dsl`; plain dict DSL is also fine |
| ES `dense_vector` max 1024/2048 dims | 4096 in 8.11 | 8.11 | Covers every OpenRouter embedding model listed; still validate |
| One fixed `*_1024_vec` dynamic template per size (reference) | Explicit per-dataset mapping | this phase | Removes the 4-dimension ceiling; field appears at dataset creation |
| OpenAI SDK 1.x | 2.x (3.x exists but needs `httpx2`) | 2026 | Pin `<3` while litellm requires it |
| litellm 1.84.0 pin (CLAUDE.md) | 1.103.2 (7 days old, 0 advisories) | 2026-10 | Needs user approval; fallback 1.84.0 |

**Deprecated/outdated:** CLAUDE.md package versions for openai (2.41.0), ollama (0.6.1), xxhash and tiktoken are older than current; use the resolved versions above. `minio/minio` image is not used (project already on `pgsty/minio`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | One ES index per tenant (`ragflow_{tenant_id}`) rather than per dataset | Pattern 3 | If the user wants per-dataset indices, dataset delete becomes `drop index`, and Phase 5 searches several indices; port signature is unaffected (it already takes `index_names`) |
| A2 | Ciphertext in `tenant_llm.api_key`, display mask in `tenant_model_instance.api_key`, both in one transaction | Pattern 4 | If the user wants the new `tenant_model_*` entities to be the only store, move the ciphertext there; code localised in one service |
| A3 | Acting-tenant resolution via optional `tenant_id` parameter and resource-derived tenant | Pattern 7 | If the intent is "own workspace only", D-07 for admins of a joined workspace is not deliverable; a UI workspace selector is a UI-contract item |
| A4 | A `me` dataset is invisible to owners/admins of the tenant | Pattern 7 | If owners/admins must see/manage everything, visibility query and 404-vs-403 tests change |
| A5 | Default limits: 20 files/request, 10 000 documents/dataset, 100 MiB file, 600 s upload body timeout | Pattern 9 | Wrong numbers are config changes only |
| A6 | Extension list = union of docs; legacy doc/ppt/xls and extra image types excluded | Pattern 9 | Users cannot upload those until added; one config line |
| A7 | Generous per-extension MIME set + magic bytes for binary families | Pattern 9 | Over-strict -> legitimate files rejected; over-loose -> disguised files accepted |
| A8 | Base-URL guard policy (deny link-local/metadata, private only when configured) | Pitfall 13 | Too strict breaks local Ollama in production; too loose leaves SSRF |
| A9 | `embd_id` immutable once documents exist | Pattern 6 | Reference behaviour; if users expect free switching they must re-embed (Phase 4) |
| A10 | Retry/timeout numbers (60/30/20 s, 3 retries) | Pattern 1 | Tuning only |
| A11 | Live cost per gate run is well under one cent | Summary | Pennies either way (D-05 allows) |
| A12 | litellm 1.103.2 works for the openai-prefix streaming path (only import was tested) | Standard Stack | Fall back to 1.96.2 or 1.84.0 after the live gate |
| A13 | `TIKTOKEN_CACHE_DIR` pointing at litellm's vendored directory makes tiktoken offline | Pitfall 10 | Token estimate falls back to provider-reported counts; add a network-blocked unit test |
| A14 | Presigned URLs not exposed through a route this phase | Pattern 8 | If a download/preview route is wanted now, Nginx must front MinIO or Python must stream |
| A15 | Provider/model_type value case: keep lower-case in `tenant_llm` | Runtime State Inventory | A docs-literal reading (upper-case) needs a Phase 2 writer change |

## Open Questions

1. **Acting tenant for joined workspaces (A3).** What we know: the Python principal has only the own workspace; the SPA has no workspace switcher; D-07, D-09 and success criterion 2 need joined-workspace access. Unclear: whether a workspace selector is in scope for this phase's UI. Recommendation: adopt Pattern 7 (resource-derived tenant for ids, optional `tenant_id` for the rest) and have `/gsd-ui-phase 3` decide the selector; ask the user only if they want the narrower "own workspace only" reading.
2. **Which table is the credential system of record (A2).** Docs name both `tenant_llm` (LLM-16) and `tenant_model_*` (LLM-29). Recommendation in Pattern 4; the planner records it in `DECISIONS.md`.
3. **Can owners/admins see another member's `me` dataset (A4).** D-08 says "only its creator". Recommendation: strictly private; ask if the user expects an admin override.
4. **Variable name for the live key.** The user must add it to `docker/.env`. Recommendation: `OPENROUTER_API_KEY`, with chat/embedding model names in non-secret variables (`LIVE_CHAT_MODEL`, `LIVE_EMBED_MODEL`). The checkpoint text must tell the user the exact name; the agent must not read the value.
5. **Package approval (D-21).** Six packages (five new downloads, 202 MB). A `checkpoint:human-verify` must precede any `uv add`.
6. **Image types beyond jpg/jpeg/png.** D-12 says "images"; the docs name only JPG and PNG explicitly. Default excludes gif/bmp/tiff/webp.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | compose stack, live tiers | yes | 29.1.3 | none |
| Elasticsearch image | doc store | yes (pulled) | 8.11.3 | none |
| MinIO image | storage | yes | `pgsty/minio:RELEASE.2026-03-25...` | none |
| MySQL, Valkey images | metadata, limits | yes | 8.0.40 / 8 | none |
| uv | dependency changes | yes | 0.9.18 | none |
| Python (project venv) | engine, tests | yes | 3.13.11 | none |
| Node / npm | SPA | yes | 22.23.3 | none |
| Go | schema verify, Go tiers | yes | go1.25.5 | none |
| Chrome (CDP browser tests) | upload dialog E2E | yes | 143 | none |
| Network to openrouter.ai | live tier | yes (public endpoints fetched) | n/a | none: gate fails by design (D-04) |
| **OpenRouter API key in `docker/.env`** | live tier, phase exit gate | **unknown / not found under an OPENROUTER or LLM variable name** | n/a | none; user action; the gate fails without it (D-04) |
| Free disk | package install, images, volumes | **tight** | 6.7 GB free of 183 GB (97% used) | none; B-03 open; install adds about 200 MB |
| Free RAM | gate needs 4096 MB available | 6.3 GB available now | n/a | close other workloads (B-14) |
| `vm.max_map_count` | Elasticsearch | 65530 (low) | n/a | `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, recorded (B-02) |
| Ollama | contract tests only | not needed (D-03) | n/a | fake server |

**Missing with no fallback:** the OpenRouter key (user). **Constraint:** disk. A throwaway ES container used for this research was removed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode=auto`, `-p no:anyio`, `filterwarnings=error`), Go `go test` (tiers), vitest 5.0.3 (+ `--project live`), Chrome CDP for browser tests |
| Config file | `pyproject.toml`; `run_tests.py`; `web/vitest` config; `scripts/clean_room.sh` (gate) |
| Quick run command | `uv run python run_tests.py -m unit` |
| Full suite command | `scripts/clean_room.sh --runs 3` (phase exit); live tiers alone: `uv run python run_tests.py -m "integration or e2e"` after `scripts/wait_stack.sh` |

New marker to register in `pyproject.toml` (strict markers): `live_model` (needs the provider key; run as its own gate step that fails, not skips, without the key per D-04). `filterwarnings=error` means every new dependency's import path must be warning-free: verified for litellm/openai/ollama/xxhash/tiktoken at the pinned versions.

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-03 | AES-GCM envelope round trip, AAD binding, tamper, no plaintext in MySQL | unit + integration | `pytest test/unit_test/test_secretbox.py` ; `pytest -m integration test/integration/test_provider_key_at_rest.py` | no, Wave 0 |
| SEC-02, D-17, D-23 | Key never in any response, log, or error; leak sweep with sentinel key | e2e | `pytest -m e2e test/testcases/test_response_leaks.py` (extend) | extend existing |
| LLM-01..05, 17..20 | Drivers vs fake OpenAI/Azure/Ollama servers; error map; retry; whitelist; reasoning; sanitizer | unit (real loopback HTTP) | `pytest test/unit_test/test_llm_drivers.py` | no, Wave 0 |
| LLM-14, 15 | Composite id parsing, bundle credential resolution | unit | `pytest test/unit_test/test_llm_bundle.py` | no |
| LLM-16, 24, 25, 27, 28, 29, TEN-12 | Provider save (test-before-save), list, delete, instances, defaults; masked responses; roles | e2e | `pytest -m e2e test/testcases/test_provider_flow.py` | no |
| LLM-03, 21, 22 (live) | Real chat, streamed chat, embedding batch, bad-key error on OpenRouter; `used_tokens` rises; dimension recorded | live_model | `pytest -m live_model test/testcases/test_live_models.py` | no |
| KB-01..09, TEN-16 | Dataset CRUD, duplicate name (case variant), unknown embedding model, permission default `me`, update, delete | e2e | `pytest -m e2e test/testcases/test_dataset_flow.py` | no |
| IDX-04..06, 08, 09, KB-03, TEST-08 | Contract suite on the real ES: create_idx idempotent, field mapping read back (dims, cosine, hnsw 16/200), conflicting dims error, zero-vector error, insert/get/update/delete/search with kb filter, empty `dataset_ids` refused, index-name validation | integration | `pytest -m integration test/integration/test_doc_store_es.py` | no |
| E2E-03 | Create KB: DB row + ES field mapping for the model's dimension | e2e | `pytest -m e2e test/testcases/test_create_kb_e2e.py` | no |
| STOR-01, 02, 06, 08, 10, 11 | Factory, MinIO put/get/rm, bucket-on-write, presigned URL fetch with 3600 s expiry, local traversal rejection, UUID keys | integration (+unit for local) | `pytest -m integration test/integration/test_storage.py` ; `pytest test/unit_test/test_local_storage.py` | no |
| DOC-01..07, SEC-06, E2E-04 | Upload happy path (blob in MinIO, rows `run=0`, progress 0), reject ext/MIME/size/traversal/inaccessible dataset with nothing stored (MinIO prefix listing + row counts), same content twice shares blob, auto-rename, limits, hash-collision byte-compare, concurrent delete vs duplicate upload | e2e | `pytest -m e2e test/testcases/test_upload_flow.py` | no |
| DOC-08, 14, 15, 16 | List with paging/keywords; delete prunes chunks and GCs blob only at zero refs; per-document parser override | e2e | `pytest -m e2e test/testcases/test_document_flow.py` | no |
| TEN-01, 05, 13, D-20 | Cross-tenant matrix builders for every new scope-tenant registry row; member roles 403/404; API token refused on key routes; second member sees a `team` dataset, not a `me` one | e2e | `pytest -m e2e test/testcases/test_cross_tenant_matrix.py` (extend `_matrix_fixtures.py`) | extend existing |
| Routes/registry | Registry rows, generated Nginx limits (upload 101m, JSON small), drift gate | unit | `uv run python scripts/gen_routes.py --check` ; `pytest test/unit_test/test_gen_routes.py test/unit_test/test_nginx_limits.py` | extend existing |
| Permissions | New permission rows regenerated in Go and Python; oracle cases | unit + Go | `pytest test/unit_test/test_permissions*.py` ; `go test ./internal/common/...` | extend existing |
| Layering | `rag/` and new services respect import rules | unit | `pytest test/unit_test/test_layering.py` | extend existing |
| UI-10, 11, 12, 37 | Components (gallery, dialog, workspace table, status badges, upload dialog validation, masked key form, "configured" state, missing-embedding-default message), i18n key parity en/zh | vitest unit | `cd web && npm run test -- --run` | no |
| UI live | Settings save with the live provider key; create dataset; upload via the real DOM; 100 MB timeout not hit; bad key keeps session | vitest live + Chrome CDP | `cd web && npm run test:live` ; `pytest -m e2e test/testcases/test_spa_browser.py` (extend) | extend existing |
| Go | Schema verify unchanged (no new tables); if a migration is added regenerate `conf/schema.json`/entities | Go integration | `go test -tags=integration ./internal/dao/...` | existing |

### Sampling Rate
- **Per task commit:** `uv run python run_tests.py -m unit` plus the touched module's tests.
- **Per wave merge:** unit + `-m integration` (needs the stack: `make infra-up`) and `npm run test -- --run`.
- **Phase gate:** `scripts/clean_room.sh --runs 3` green with the key present, including a new `live-model` step; web port 8088; at least 4096 MB available RAM.

### Wave 0 Gaps
- [ ] Register `live_model` marker; add the `live-model` step to `scripts/clean_room.sh` (read the key from `docker/.env` inside a subshell export, never print it, fail when absent) and a `scripts/preflight.sh` presence/shape check that prints only "present"/"missing".
- [ ] `test/helpers/fake_provider.py`: loopback OpenAI-compatible, Azure-shaped and Ollama-shaped server fixture recording requests.
- [ ] `test/helpers/` builders for providers/datasets/documents in `_matrix_fixtures.py` (BUILDERS entries for each new scope-tenant row).
- [ ] `test/fixtures/log_redaction_vectors.json` additions for key-shaped strings; Go logger and Nginx map parity.
- [ ] `test/integration/test_doc_store_es.py` written as an engine-agnostic contract class so the Infinity adapter can reuse it later.
- [ ] `docker/.env.example`: `LLM_KEY_ENCRYPTION_KEY` (secret), `UPLOAD_*`, `DATASET_MAX_DOCUMENTS`, `STORAGE_IMPL`, `LLM_ALLOW_PRIVATE_BASE_URLS`, and the live-test variable names (no values); `test_env_catalog.py` expectations.
- [ ] `conf/service_conf.yaml.template`, `scripts/render_conf.py`, `common/settings.py`: new sections.
- [ ] Package approval checkpoint, then `uv add` and `uv.lock` commit.
- [ ] `web`: i18n keys en/zh, `no-hardcoded-copy` test coverage for new pages, `api-routes.generated.json` regeneration (`gen_routes.py`), OpenAPI types (`npm run gen:api`).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | inherited | Phase 2 gate; key-writing routes `auth: jwt` only |
| V3 Session Management | yes | Provider errors must not trigger the SPA 401 purge |
| V4 Access Control | yes | Generated permission table + `tenant_scope` + object rules; 404 for invisible, 403 for lacking role; subject from `auth_type` |
| V5 Input Validation | yes | pydantic/quart-schema request models with `SafeIdentifier`; manual multipart validation; filename/extension/MIME/magic checks; ES index-name regex |
| V6 Cryptography | yes | AES-256-GCM via pycryptodome, dedicated env key, AAD binding, kid rotation; never hand-roll |
| V7 Error Handling and Logging | yes | Sanitized provider errors; shape-based key redaction in Python, Go, Nginx; leak sweep |
| V8 Data Protection | yes | Keys masked (`last4`), never readable; no secrets in responses |
| V12 Files and Resources | yes | Allow-list, size caps, UUID keys, traversal rejection, no execution, byte-compare dedupe |
| V13 API and Web Service | yes | Envelope, small JSON body limits, rate limit on key-test (reuse Phase 2 Valkey limiter, fail closed) |
| SSRF (V12.6 / V5) | yes | `url_guard` on every user-supplied base URL, at save and at call time |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF via provider base URL; response-body exfiltration via "provider's reason" | Information disclosure | URL guard, no redirects, parsed+truncated provider message only |
| Provider key leakage in logs/exceptions/responses | Information disclosure | Envelope encryption, last4-only masking, shape-based redaction, SDK debug off, leak sweep |
| API-token principal using owner role to change keys | Elevation of privilege | Subject by `auth_type`, `auth: jwt` on write routes, matrix test |
| Cross-tenant ES read (empty/foreign `dataset_ids`, wildcard index) | Information disclosure | Required non-empty `dataset_ids`, index-name regex, `kb_id` filter always applied |
| xxh64 collision -> foreign blob link | Information disclosure | Hash+size+byte-compare |
| Path traversal in filename or local storage key | Tampering | Reject at validation; server-generated keys; `resolve()+is_relative_to` in local driver |
| Disguised executable/polyglot upload | Tampering | Extension allow-list + magic bytes + no server-side execution; filenames rendered as text |
| Upload DoS (huge body, slow body, many files, temp-disk exhaustion) | Denial of service | Nginx cap, per-request `max_content_length`, body timeout, files-per-request and documents-per-dataset limits, one file per SPA request |
| Race: duplicate dataset name, rename collision, GC vs link | Tampering / integrity | `DatabaseLock`, row locks, single transaction |
| Mass assignment on dataset create/update (`tenant_id`, `created_by`, counters) | Tampering | Request models list allowed fields; server sets tenant/creator |
| Stored XSS via filename/dataset name/description | Tampering | React text rendering only; no `dangerouslySetInnerHTML` (inherits B-30 rule) |
| Decryption oracle / key swap between rows | Tampering | GCM tag + AAD |

## Sources

### Primary (HIGH confidence)
- OpenRouter official OpenAPI spec `https://openrouter.ai/openapi.json` (fetched 2026-10-08): `/embeddings` request and response schema incl. `usage`; `/embeddings/models`.
- OpenRouter public catalogs `https://openrouter.ai/api/v1/models` and `/api/v1/embeddings/models` (pricing, context, dimensions, expiry).
- OpenRouter docs `https://openrouter.ai/docs/api/reference/overview` (error shape, usage object, streaming usage) and `.../embeddings`.
- Elasticsearch 8.11 `dense_vector` reference `https://www.elastic.co/guide/en/elasticsearch/reference/8.11/dense-vector.html` (dims <= 4096, hnsw m/ef_construction, cosine zero-vector rule).
- Live run against `docker.elastic.co/elasticsearch/elasticsearch:8.11.3` (mapping idempotency, conflict, bounds, zero vector, wrong dims, kNN filter).
- PyPI JSON for litellm, openai, ollama, xxhash, tiktoken, cryptography; `api.osv.dev` per-version advisory queries for litellm (2026-10-08); local `uv pip install --dry-run` and `--target` installs.
- Local source: Quart `wrappers/request.py` and `formparser.py` (per-request `max_content_length`, `silent=True`), litellm 1.103.2 wheel (vendored tokenizers).
- Project files: `docs/11-llm/*`, `docs/09-storage/*`, `docs/06-document-processing/upload.md`, `docs/05-rag-pipeline/indexing.md`, `docs/17-integrations/vector-database-integrations.md`, `docs/21-end-to-end-flows/{create-knowledge-base,upload-document}.md`, `docs/20-security/{secrets,file-security}.md`, `docs/16-auth/{permissions,multi-tenancy}.md`, `docs/04-api/{provider,models,dataset,document}-api.md`, `docs/apikey llm.md`, `api/**`, `common/**`, `conf/**`, `scripts/**`, `test/**`, `web/**` (Phase 2 code).

### Secondary (MEDIUM confidence)
- Reference implementation (read-only): `rag/llm/__init__.py` (prefix table), `common/doc_store/doc_store_base.py`, `es_conn_base.py`, `rag/utils/es_conn.py` (search/delete), `conf/mapping.json`, `api/apps/restful_apis/provider_api.py` routes, `api/utils/file_utils.py` (`filename_type`).
- WebSearch result list on litellm CVEs (older CVEs, all fixed far below the pinned version).

### Tertiary (LOW confidence)
- The `TIKTOKEN_CACHE_DIR` offline mechanism (stated from knowledge of tiktoken's cache naming; confirm by test).
- litellm streaming behaviour through the `openai/` prefix on 1.103.2 (only import verified).
- Real OpenRouter behaviour for `baai/bge-m3` (dimension, index ordering, error bodies) is unverified until the first live run.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM-HIGH. Versions, advisories and resolution verified; litellm functional behaviour on the new version unverified beyond import.
- Architecture: HIGH for ES, storage, upload, layering (verified against code and a live ES); MEDIUM for tenant-scope and credential-table decisions (genuine design choices, flagged).
- Pitfalls: HIGH for the ones tied to code I read (Quart, SPA interceptor, principal role, permissions); MEDIUM for provider-behaviour pitfalls (no live call possible).

**Research date:** 2026-10-08
**Valid until:** 2026-10-15 for litellm/openai version pins (litellm ships daily); 2026-11-07 for the rest.
