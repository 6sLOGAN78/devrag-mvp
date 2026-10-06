# devRag

## What This Is

devRag is a complete, production-quality implementation of the RAG platform described in `docs/` — a reverse-engineered technical specification of RAGFlow. It ingests unstructured and semi-structured documents (PDF, DOCX, PPTX, images, web pages), parses them with layout awareness, chunks/embeds/indexes them into knowledge bases, and serves grounded, cited answers through chat, agents, and workflows behind a multi-tenant web UI and REST API.

It is for teams who need an enterprise RAG engine: knowledge-base management, document ingestion, hybrid retrieval with reranking, streaming chat with citations, and an agentic canvas.

## Core Value

A user can upload a document into a knowledge base and get an accurate, cited answer to a question about it — end-to-end, through the real pipeline (parse → chunk → embed → index → hybrid retrieve → rerank → generate), with no mocked stages.

## Requirements

### Validated

- ✓ Infrastructure layer runs via Docker Compose (MySQL, Valkey, MinIO, Elasticsearch, Nginx) from empty volumes — Phase 1
- ✓ Dual-stack skeleton: Go Gin and Python Quart answer through one Nginx ingress with one response envelope on one shared schema (38 tables, Peewee-owned, Go verify-only) — Phase 1
- ✓ Decision register (87 rows) and blocker log committed; CI gates against placeholders, pickle, fixed sleeps, secrets and generated-file drift — Phase 1
- ✓ SPA shell with lazy routes and HTTP client; live System status page — Phase 1

Phase 1 covers foundations only: no user-facing RAG capability exists yet, and the Core Value is not yet demonstrated.

### Active

- [ ] Infrastructure layer runs via Docker Compose: relational DB (MySQL), Redis, object storage (MinIO), vector/full-text engine (Elasticsearch/Infinity), reverse proxy (`docs/18-deployment/`, `docs/08-database/`, `docs/09-storage/`, `docs/10-cache-and-queues/`)
- [ ] Backend API server with configuration management, middleware, structured errors, logging, health checks (`docs/03-backend/`)
- [ ] Database schema, entities, relationships, indexes, and migrations (`docs/08-database/`)
- [ ] Authentication, sessions, tokens, API keys, roles, permissions, multi-tenancy (`docs/16-auth/`, `docs/20-security/`)
- [ ] Full documented REST API surface: user, tenant, dataset, document, chat, search, models/provider, agent, workflow, bot, connector, MCP, plugin, langfuse, stats, system (`docs/04-api/`, `docs/apis.md`)
- [ ] Knowledge-base (dataset) management: CRUD, parser configuration, retrieval configuration
- [ ] Document upload, file storage, and document lifecycle (`docs/06-document-processing/upload.md`, `docs/09-storage/`)
- [ ] Document processing: parsers for PDF, office documents, images, tables; OCR; layout analysis; chunking strategies (`docs/06-document-processing/`)
- [ ] Background ingestion: queues, task workers, scheduling, progress tracking, retries (`docs/10-cache-and-queues/`)
- [ ] RAG pipeline: preprocessing, chunking, embedding, indexing (`docs/05-rag-pipeline/`)
- [ ] Retrieval: vector search, keyword/full-text search, hybrid retrieval, filters, similarity, reranking (`docs/07-retrieval/`)
- [ ] LLM layer: provider abstraction, OpenAI, Ollama, other providers, embedding models, rerank models, prompt management, per-tenant model/API-key configuration (`docs/11-llm/`)
- [ ] Chat: conversations, messages, context construction, memory, SSE streaming, citations/source tracking (`docs/12-chat/`)
- [ ] Agents: agent architecture, planning, tools, memory, RAG agent, execution (`docs/13-agents/`)
- [ ] Workflows: canvas engine, nodes, edges, variables, tools, execution (`docs/14-workflows/`)
- [ ] CLI: commands, configuration, entry points (`docs/15-cli/`)
- [ ] Integrations: model, search, storage, vector-database, external services (`docs/17-integrations/`)
- [ ] Frontend SPA: auth, knowledge-base UI, document upload UI, chat UI, agent UI, workflow canvas UI, routing, state management, API client, with loading/error/empty states (`docs/02-frontend/`)
- [ ] Testing: unit, integration, API, database, pipeline, and frontend tests (`docs/19-testing/`)
- [ ] Deployment: Docker images, compose profiles, environment variables, networking, volumes, documented setup (`docs/18-deployment/`)
- [ ] All documented end-to-end flows work: registration, login, create knowledge base, upload document, document processing, indexing, ask question, RAG answer, chat streaming, agent execution, workflow execution (`docs/21-end-to-end-flows/`)

### Out of Scope

- Redesigning, simplifying, or replacing documented architecture — `docs/` is authoritative; deviate only on genuine contradiction or implementation blocker, and document it
- Minimal demo / partial prototype — the goal is the complete system
- Placeholder, mocked, or TODO-only implementations presented as complete — blockers must be documented instead
- Blindly copying RAGFlow source or cloning its visual appearance — it is reference only; the frontend must represent this project's own architecture
- Frameworks or patterns adopted purely because RAGFlow uses them, where `docs/` does not call for them

## Context

- **Source of truth**: `docs/` (227 files, ~570 KB, sections `00-overview` through `99-glossary`, plus `apis.md`, `spec.md`). `docs/spec.md` defines the implementation rules. Every phase must read its relevant `docs/` sections before implementing.
- **What the docs are**: a reverse-engineered documentation suite of RAGFlow. They describe six layers — presentation (React SPA), API/routing gateway, core business logic & RAG engine, DeepDoc parsing engine, persistence & storage, background ingestion workers.
- **Documented stack**: React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui + Zustand + React Router 7 + `@xyflow/react`; Python 3.10+ Quart (ASGI) + Peewee + LiteLLM; Go 1.22+ Gin + GORM + Zap + go-redis; MySQL 8, Redis 7, MinIO/S3, and a pluggable vector engine (Infinity / Elasticsearch / OpenSearch / Qdrant / Milvus / PGVector).
- **Reference repository**: `~/desktop x/ragflow` — a local RAGFlow checkout (contains `api/`, `agent/`, `rag/`, `deepdoc/`, `internal/`, `cmd/`, `web/`, `docker/`, ...). Use it for implementation patterns where `docs/` leaves details open. Doc links point at `file:///home/logan78/Desktop/ragflow/...`; the actual path is `~/desktop x/ragflow`.
- **Prior work**: an earlier Python-only attempt (`api/`, `blueprint/`, Parts 01–05: infrastructure, core backend, auth/tenancy, KB management, document ingestion, chunking & embedding, TenantLLM keys, ES mapping) was deliberately removed. It remains in git history at `github.com/6sLOGAN78/devrag-mvp` (`master`, commit `3fe760d`). This is a fresh start, not a continuation.
- **`docs/apikey llm.md`**: withheld from agents during initialization and Phase 1; released by the user on 2026-10-07 (no credentials). It specifies token formats and LLM usage tracking that Phase 1 research never saw (DECISIONS R-49); Phase 2 and Phase 3 must read it.
- **Repository**: pushed to `github.com/6sLOGAN78/devrag-mvp` (public), `master`; the earlier attempt is at branch `archive/mvp-master`. Dev web port on this host is 8088 (R-87).
- **Open from Phase 1**: an unauthenticated CPU denial-of-service in the Python log redactor (CR-02) and smaller hardening items; see `01-VERIFICATION.md` and BLOCKERS B-15. Fix at the start of Phase 2.
- **Environment**: Linux, Node 22 available. No API keys configured in the session.

## Constraints

- **Authority**: `docs/` always wins over `spec.md`, existing code, RAGFlow, and general judgment (in that priority order) — it is the defined architecture
- **Tech stack**: Use the technologies and boundaries defined in `docs/`; do not introduce a new service, database, queue, framework, or abstraction layer without checking it against the docs
- **Completeness**: No critical placeholders; every feature verified by realistic execution, not static inspection
- **Quality**: Backend must be production-oriented — typed interfaces, config/env handling, input validation, structured errors and logging, migrations, transactions, async processing, retries, timeouts, idempotency, health checks; no giant files
- **Testing**: Each phase ends in a working state with passing tests; broken tests only if documented as a blocked dependency
- **Process**: Understand the architecture before writing code; implement incrementally in dependency order; validate each phase before moving on
- **Documentation**: Any decision not covered by `docs/` must be recorded (what, why, how it fits)
- **Unspecified decisions**: Make the smallest reasonable production-quality choice, using RAGFlow as supporting evidence

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| `docs/` is the authoritative spec; RAGFlow repo is reference only | Stated in `docs/spec.md` priority order | — Pending |
| Fresh greenfield start; prior Python-only MVP discarded | User removed all prior code and git history locally | — Pending |
| Scope is the complete documented system, not an MVP | `docs/spec.md` Primary Goal and Completion Criteria | — Pending |
| Dual-stack backend (Go Gin + Python Quart) as documented — which server owns which routes to be resolved in research | `docs/00-overview` describes both engines on `:9380`; exact split needs verification against `docs/03-backend` and `docs/04-api` | — Pending |
| Default vector/full-text engine to be chosen from the documented pluggable set during research | Docs list several engines; one must be the default for compose and tests | — Pending |
| GSD config: YOLO mode, standard granularity, parallel execution, research + plan-check + verifier on | Chosen at initialization | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-07 after Phase 1 completion*
