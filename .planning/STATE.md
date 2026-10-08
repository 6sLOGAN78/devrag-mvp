---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-11-PLAN.md
last_updated: "2026-10-08T21:50:00.588Z"
last_activity: 2026-10-08
progress:
  total_phases: 8
  completed_phases: 2
  total_plans: 83
  completed_plans: 63
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-05)

**Core value:** A user can upload a document into a knowledge base and get an accurate, cited answer to a question about it, end-to-end through the real pipeline (parse, chunk, embed, index, hybrid retrieve, rerank, generate), with no mocked stages.
**Current focus:** Phase 3 — Models, Knowledge Bases and Upload

## Current Position

Phase: 3 (Models, Knowledge Bases and Upload) — EXECUTING
Plan: 12 of 31
Status: Ready to execute
Last activity: 2026-10-08

Progress: [████████░░] 76%

## Performance Metrics

**Velocity:**

- Total plans completed: 52
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 24 | - | - |
| 2 | 28 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 15min | 2 tasks | 4 files |
| Phase 01 P03 | 30min | 3 tasks | 17 files |
| Phase 02 P12 | ~2h | 3 tasks | 27 files |
| Phase 02 P14 | 40min | 3 tasks | 26 files |
| Phase 02 P28 | 90min | 3 tasks | 13 files |
| Phase 02 P13 | resumed after interruption | 3 tasks | 30 files |
| Phase 02 P16 | one session | 3 tasks | 26 files |
| Phase 02 P20 | single session | 3 tasks | 25 files |
| Phase 02 P22 | single session | 3 tasks | 26 files |
| Phase 02 P21 | single session | 3 tasks | 24 files |
| Phase 02 P25 | single session | 3 tasks | 14 files |
| Phase 03 P01 | 45min | 3 tasks | 22 files |
| Phase 03 P02 | 35min | 3 tasks | 9 files |
| Phase 03 P03 | 11min (closeout) | 3 tasks | 12 files |
| Phase 03 P04 | 25min | 3 tasks | 17 files |
| Phase 03 P05 | 75min | 3 tasks | 11 files |
| Phase 03 P07 | 25min | 3 tasks | 7 files |
| Phase 03 P08 | 50min | 3 tasks | 6 files |
| Phase 03 P06 | 35min | 2 tasks | 4 files |
| Phase 03 P09 | 70min | 3 tasks | 9 files |
| Phase 03 P10 | 45min | 3 tasks | 5 files |
| Phase 03 P11 | 35min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. The full contradiction register (R-01..R-52) is in `.planning/research/SUMMARY.md` and is committed as `.planning/DECISIONS.md` in Phase 1.
Recent decisions affecting current work:

- [User, 2026-10-05]: Go Gin builds only its own routes (auth, user, tenant, system, search bots, MCP, CLI). Python owns all RAG/ML pipelines. Go mirror engines are v2 (recorded deviation from docs).
- [User, 2026-10-05]: Billing (BILL-01..10 from `docs/apis.md`) is in v1 scope (Phase 8).
- [User, 2026-10-05]: Doc stores in v1 are Elasticsearch (default) and Infinity. All others are v2.
- [Roadmap]: Thin real vertical slice first. Phases 2 to 5 reach the Core Value before any breadth; Phase 5 is a hard gate for Phases 6, 7 and 8.
- [Roadmap]: `DocStoreConnection` port and the Elasticsearch adapter land in Phase 3 (not Phase 4) so dataset creation is verified against a real index.
- [Phase 01]: Plan 01-01: only R-03/R-17/R-18/R-48 user-confirmed; register R-01..R-73 in DECISIONS.md
- [Phase 01]: 01-03: pickle gate rejects Unpickler subclasses; gate-ok honoured only in test trees; secrets gate skips docs/, scripts/ci/, .planning/
- [Phase 01]: 01-05: Go exact-only under /api/v1/system/ (R-53); Python catch-alls /api/ and /v1/
- [Phase 01]: 01-11: Go --migrate is verify-only; VerifySchema over SchemaProvider (SELECT-only), type families, scratch DB for drift tests
- [Phase 02]: [02-12] Auth guard decides from stored token plus fetched user; token store is subscribable so a purge re-renders the guard; / registry entry is auth:required
- [Phase 02]: R-117 Python gate details: 5 s lookup timeout, fail-closed 503 on any resolver error, beta rows also accept access and API tokens, resolver seam keyword-only, static_folder=None
- [Phase 02]: [02-16] R-120: avatar re-encoded on a 256x256 canvas, confirmation field on password change, server Dark theme only without a local choice
- [Phase 02]: Plan 02-20 (R-121): API token management is owner-session only; cap 50 and 20 creations/hour per tenant; exact BINARY matching; token principals never superuser; route-template request log
- [Phase 02]: R-123: permission matrix keyed (area, action); invite never membership; one 404 for invisible tenants; owner-only invite rate limited
- [Phase 02]: R-124: API tokens page - tokens.action.* labels, owner-only forbidden state and home card, own 409/429/403 messages, aria-disabled pending, caption focus after delete
- [Phase 02]: R-127: matrix rows generated from routes.yaml with a fixture guard; Nginx access log masks token paths and drops query and Referer; Go and Python loggers mask credential spellings
- [Phase 02]: R-128: gate stack runs the mail profile and exports SERVICE_CONF and MYSQL_ROOT_PASSWORD for host-run tiers; TEN-01, TEN-05, UI-42 left partial (B-18, B-22)
- [Phase 03]: [03-01] Dev override uses DEV_LLM_ALLOW_PRIVATE_BASE_URLS (default true) so the example's false never shadows it; llm encryption key is URL-safe base64 of 32 bytes validated lazily; provider-test limit 10 per 300 s per tenant
- [Phase 03]: [03-02] Nginx key-shape map entry keeps the prefix and drops the key and the rest of the URI; url_guard judges every IP spelling after resolution and always denies link-local, metadata and project service hosts; DNS-rebinding window accepted (T-03-02-02)
- [Phase 03-03]: Workspace selector persists {userId, tenantId} in localStorage devrag.workspace, validated against server memberships; radio menu items hand-written on installed Radix (D-21)
- [Phase 03]: 03-04: gen_routes lets a registry row tighten an api/beta family to jwt (key-writing methods share a path with readable ones)
- [Phase 03]: 03-04: dataset_visible requires workspace membership even for the creator; me datasets have no owner/admin override
- [Phase 03]: 03-05: 402 maps to ERROR_INVALID_REQUEST (provider_status kept); extra_headers dropped unless trust_extra_headers; per-call no-redirect httpx client with captured error body; pytest ignores two third-party pydantic warnings from litellm
- [Phase 03]: 03-07: StorageNotFound added as StorageError subclass; unknown storage.impl raises ConfigError; presigned URLs implemented but not routed in Phase 3 — callers must tell absent objects from failures; matches the settings loader; URL carries internal MinIO endpoint
- [Phase 03]: 03-08: one shared index ragflow_{tenant_id}; search hits carry id and _score; insert refuses a missing index so the engine never auto-creates it unmapped
- [Phase 03]: 03-06: embedding token limit is min(8191, model_meta.max_tokens) for all providers; target validation (incl. Ollama /v1) surfaces as ERROR_INVALID_REQUEST on the first encode(), not in the constructor — uniform input bound; construction stays I/O-free
- [Phase 03]: Composite model ids are bounded at 128 characters in total; save_instance/add_models refuse longer ones with models_invalid (03-09)
- [Phase 03]: save_instance stores api_base/api_version exactly as given; Change key must resend the stored address (03-09)
- [Phase 03]: Existing models keep max_tokens on re-save; embedding models require a recorded dimension (03-09)
- [Phase 03]: 03-10: one limiter hit per provider save or add; address equality treats no address and the documented default as equal; tests overriding Settings must rename service hosts so the fake provider is not on the deny list
- [Phase 03]: LLMBundle usage log fields are usage_in/usage_out/usage_total because the log redactor masks any field name containing 'token'; bundle_error mirrors provider_service._failure; a failed counter write is logged and the answer still returned — 03-11

### Pending Todos

None yet.

### Blockers/Concerns

Host blockers (measured 2026-10-05). Items marked USER ACTION cannot be fixed by agents.

- [Phase 1] Disk: about 6 GB free (97% used); the stack needs tens of GB for images, volumes and models. USER ACTION: free space before Phase 1 execution. Pruning Docker data needs consent.
- [Phase 1] `vm.max_map_count` is 65530; Elasticsearch needs 262144 or higher. USER ACTION: `sudo sysctl -w vm.max_map_count=262144` and persist it.
- [Phase 1] RAM: about 5 GB free of 15 GB; docs assume 8 GB per engine container. Mitigation: dev compose override (ES heap 1 GB, reduced MySQL buffer pool, one worker). User may need to close other workloads.
- [Phase 3] No LLM API key and no Ollama: a real chat model and a real embedding model are required from Phase 3 onward, or the Core Value cannot be verified. USER ACTION: supply an OpenAI-compatible key or approve Ollama in the dev compose (adds several GB of disk).
- [Phase 5, 6] No GPU: CPU-only `onnxruntime`; rerank over 1024 candidates and OCR of long scans are slow. The `gpu` profile (DEPLOY-06) can be built but not verified on this host; record in BLOCKERS.md.

Other concerns:

- [Phase 1] 16 register rows still need user sign-off (R-02, 04, 06, 09, 11, 21, 24, 26, 38, 39, 41, 42, 44, 49, 50, 51); R-03, R-17, R-18 and R-48 are user-confirmed. Mode is yolo, so unresolved rows take the proposed resolution and are recorded as such in DECISIONS.md.
- [Phase 1] `docs/apikey llm.md` is unread (possible credential material). Do not open, commit or rely on it until the user reviews it; never run `git add docs/` wholesale.
- [Phase 1] Project path contains a space and `@`: quote every path and set the compose project `name:` explicitly.
- [Phase 6] DeepDoc ONNX model acquisition, licence and CPU throughput are unverified; highest research risk.
- [Phase 8] ING-20 (NATS JetStream) and DEPLOY-09 (`ragflow-go` profile with NATS) are still v1; confirm with the user or move to v2 before Phase 8 is planned. (IDX-11..13, DEPLOY-05, SYS-08 already moved to v2.)
- [Phase 8] Phase 8 holds 117 requirements across about ten subsystems; consider splitting it when it is planned.
- [Phase 7, 8] Verification needing third-party credentials (Stripe test key, chat-channel bot accounts, OAuth providers, paid search tools) will be "complete with blocker" unless the user supplies them.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-10-08T21:50:00.577Z
Stopped at: Completed 03-11-PLAN.md
Resume file: None
