# Technical Prerequisites for RAGFlow Engineering

## Overview

To effectively develop, customize, and reverse engineer RAGFlow, engineers should be familiar with the core technological stack, language paradigms, datastores, and Machine Learning / NLP primitives used across the codebase.

---

## 1. Programming Languages & Frameworks

### Python Backend & AI Processing
- **Python 3.10+**: Asynchronous execution (`asyncio`, `contextvars`), type hinting, decorators, dataclasses.
- **Quart / Flask**: Async micro-web framework powering REST endpoints in [api/ragflow_server.py](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L50) and [api/apps/restful_apis/](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/).
- **Peewee ORM / GORM**: Database abstraction layer for MySQL in [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py).

### Go Backend & High-Performance Microservices
- **GORM**: Object Relational Mapping in Go in `internal/dao/`.

### Frontend Stack
- **React 18+ & TypeScript**: Modern functional components, hooks, lazy loading, React Router.
- **Tailwind CSS & Shadcn/Ant Design**: UI design system and canvas node components in `web/src/`.

---

## 2. Infrastructure & Datastores

### Datastores & Storage Engines
- **MySQL 8.0**: Relational database storing tenant configuration, document metadata, prompt templates, user RBAC, and conversation sessions.
- **Elasticsearch 8+ / Infinity**: Vector and full-text search engine handling hybrid retrieval (dense cosine vector similarity + sparse BM25 term matching) in [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py).
- **Redis**: Asynchronous task queue (`ragflow_TASK_EXE_QUEUE`), pub/sub message broker, and TTS caching.
- **MinIO / AWS S3**: S3-compatible object storage storing raw PDF/DOCX binary files and extracted image cropped bounding boxes in [api/db/services/file_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/file_service.py).

---

## 3. Computer Vision & NLP Primitives

### DeepDoc Parsing & Vision Models
- **YOLOv10 / PP-YOLO**: Object detection for document layout recognition (identifying title, paragraph, header, table, image, footer bounding boxes).

### RAG & LLM Concepts
- **Dense Vector Embeddings**: Cosine distance, inner product, L2 distance vector spaces.
- **Sparse BM25 Retrieval**: Inverse Document Frequency (IDF) keyword scoring.
- **Cross-Encoder Reranking**: Re-scoring retrieved chunk pairs for semantic relevance.
- **RAPTOR**: Recursive Abstractive Processing for Tree-Organized Retrieval (clustering and hierarchical summarization).
