# Architecture Cross-Reference: devRag MVP vs RAGFlow (Part 05)

This document provides a rigorous audit comparing the recently implemented **Part 05: Document Ingestion, Logging, and Task Workers** in the `devRag_@` MVP against the enterprise `desktop/ragflow` repository.

## 1. Dual-Output Logging Strategy
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Python Core** | `common/log_utils.py` using `init_root_logger`. | `common/log_utils.py` using `init_root_logger`. | **Identical** |
| **Python Handlers** | `RotatingFileHandler` (10MB, 5 backups) + `StreamHandler` (stdout). | `RotatingFileHandler` (10MB, 5 backups) + `StreamHandler` (stdout). | **Identical** |
| **Python Filtering** | Parses `LOG_LEVELS` env var (e.g., `root=INFO`). | Parses `LOG_LEVELS` env var. | **Identical** |
| **Go Core** | `internal/common/logger.go` using `zap` + `lumberjack`. | `internal/common/logger.go` using `zap` + `lumberjack.v2`. | **Identical** |
| **Go Formats** | High-performance JSON to file, human-readable to console. | High-performance JSON to file, human-readable to console. | **Identical** |

## 2. Document Schema & Metadata (`db_models.py`)
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Deduplication** | `content_hash` tracking `xxhash.xxh128()`. | `content_hash` tracking `xxhash.xxh128()`. | **Identical Core** (MVP limits char length to 64 vs 32, but logical mechanism identical). |
| **State Tracking** | Uses `run` field (`TaskStatus` enum: 0=UNSTART, 1=RUNNING, 3=DONE, 4=FAIL). Uses `status` for validation (soft delete). | Uses `status` field for execution state (1=UNSTART, 2=RUNNING, 3=DONE, 4=FAILED). | **Architectural Deviation** (MVP simplified execution state tracking to avoid needing a redundant `run` column). |
| **Advanced Configs** | `parser_config` JSON, `pipeline_id`, `process_begin_at`. | Deferred in MVP. | **Pending Extension** |
| **Task Splitting** | Physical `Task` ORM table tracking chunked page ranges (e.g., pages 1-12, 13-24). | Bypasses intermediate `Task` table; dispatches `doc_id` directly to Redis. | **Conscious MVP Simplification** (Adhering to MVP directive: single task per document). |

## 3. Upload & Dispatch APIs (`document_api.py`)
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **File Storage** | Streams to `STORAGE_IMPL` (MinIO) via `api/db/services/file_service.py`. | Streams directly to `STORAGE_CLIENT` (MinIO). | **Identical Storage Paradigm** (Zero local disk usage). |
| **Two-Step Trigger** | `POST /datasets/<id>/documents` (Upload) -> `POST /datasets/<id>/documents/parse` (Trigger). | `POST /api/dataset/<id>/document` (Upload) -> `POST /api/dataset/<id>/document/parse` (Trigger). | **Identical Workflow** |
| **Queue Dispatch** | Redis Stream push (`queue_product` wrapping `XADD`). | Redis Stream push (`REDIS_CLIENT.xadd`). | **Identical Mechanism** |

## 4. Background Task Workers (`task_executor.py`)
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Consumer Loop** | Isolated daemon polling `rag_flow:tasks` via `xreadgroup`. | Isolated daemon polling `rag_flow:tasks` via `xreadgroup`. | **Identical** |
| **State Transitions** | Updates intermediate `Task` state. Background aggregation thread in `ragflow_server.py` updates parent `Document`. | Worker securely catches exceptions and directly transitions `Document.status` to `DONE` or `FAILED`. | **Conscious MVP Simplification** (Direct state update implemented as instructed for single-worker scale). |
| **Zombie Detection** | Concurrent thread pushing heartbeat (`pid`, `status`) to Redis ZSET `TASKEXE`. | Concurrent daemon thread pushing exact heartbeat signature to Redis ZSET `TASKEXE`. | **Identical** |

## Summary
The MVP achieves remarkable adherence to the original RAGFlow infrastructure. We successfully implemented the precise dual-output logging system, the zero-trust MinIO upload abstraction, and the distributed Redis worker loops.

Where the MVP differs (omitting the intermediate `Task` MySQL table and the aggregator thread), it does so deliberately to minimize over-engineering while the system operates in a 1:1 document-to-task paradigm, matching exactly the blueprint directives provided.
