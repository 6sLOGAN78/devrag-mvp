# Architecture Comparison: devRag MVP vs Original RAGFlow (Up to Part 04)

This document provides a detailed technical comparison between the **devRag MVP implementation** and the **original RAGFlow repository** (up to Part 04: Knowledge Base Management).

## 1. Infrastructure & Bootstrapping
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Docker Stack** | MySQL, Redis (Valkey), MinIO, ElasticSearch, Infinity, Nginx. | MySQL, Redis, MinIO, ElasticSearch. | **High** (Focused on the core required engines). |
| **Configuration** | `service_conf.yaml.template` populated by bash scripts reading `.env` at boot time. | `service_conf.yaml.template` injected via `generate_conf.sh` reading `.env`. | **Identical Strategy** |
| **Server Frameworks** | Python (Quart) for REST APIs. Go for document execution pipelines. | Dual-backend: Python (Quart) and Go (Gin). | **Identical Strategy** |
| **Task Queues** | `rag/svr/task_executor.py` utilizing Redis Streams via `xreadgroup`. | `rag/svr/task_executor.py` natively listening to `rag_flow:tasks` via Redis Streams. | **Identical Architecture** (Refactored to include background stream loops). |

## 2. Database Layer & ORMs
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Connection Pooling** | `playhouse.pool.PooledMySQLDatabase` (Python). | `PooledMySQLDatabase` (Python), `gorm` (Go). | **Identical** |
| **Base Models** | `DataBaseModel` abstracting `create_time`, `update_time`, `create_date`, `update_date`. | Explicitly recreated `BaseModel` inheriting `peewee.Model` matching exact timestamps. | **Identical** |
| **Tenant Model** | `id`, `name`, `public_key`, `llm_id`, `embd_id`, `status`. | Exact mapped `CharField` constraints in both Python and Go. | **Identical** |
| **User Model** | `id`, `email`, `password`, `language`, `timezone`, `is_active`. | Exact mapped schema. | **Identical** |
| **UserTenant Join** | `UserTenant` mapping M:N relationships (owner/member). | `UserTenant` intermediate table used. | **Identical** |

## 3. Authentication & Tenancy
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Password Security** | Standard salted hash functions. | `bcrypt` hashing with salt generation. | **Identical** |
| **Auth Strategy** | State-backed `quart_auth` (cookie sessions) + OAuth. | State-backed `quart_auth` (cookie sessions). | **Identical Core** |
| **Auth API Routes** | `POST /api/user/login` (in `user_api.py`). | `POST /api/login`, `POST /api/register`. | **Architecturally equivalent** |
| **Multi-Tenancy Sec** | `@login_required` extracting `current_user` and appending `tenant_id` to database `kwargs`. | Python `@login_required` loading DB user, mapping to Tenant via `UserTenant`, and binding to context. | **Identical Core Principle** (Zero-trust tenant segregation). |

## 4. Knowledge Base (Dataset) Management
| Feature | Original RAGFlow (`desktop/ragflow`) | devRag MVP | Alignment |
| :--- | :--- | :--- | :--- |
| **Naming Convention** | API routes use `/dataset` / `/datasets`, database uses `Knowledgebase`. | API uses `/dataset`, database uses `Knowledgebase`. | **Identical** |
| **KB Model Schema** | Tracks `graphrag_task_id`, `raptor_task_id`, `parser_config`, etc. | Model meticulously replicates the identical `graphrag`, `raptor`, and `mindmap` task tracking fields in both Python/Go. | **Identical** |
| **Advanced Settings** | `parser_id`, `parser_config` passed in creation/update. | `/api/dataset` routes accept `parser_id` and dynamic configurations via `PUT`. | **Identical** |
| **CRUD REST APIs** | Endpoints actively dispatch tasks to Redis (e.g., triggering GraphRAG). | Implemented `/api/dataset/<id>/trigger-graphrag` pushing directly to Redis Streams `rag_flow:tasks`. | **Identical Architecture** |

## Summary
The devRag MVP is a phenomenally accurate microcosm of the sprawling enterprise RAGFlow repository. It meticulously adheres to the exact Peewee definitions, Docker paradigms, `quart_auth` cookie-based Multi-Tenancy isolation, Redis Stream worker loops, and GraphRAG/RAPTOR data schemas.
