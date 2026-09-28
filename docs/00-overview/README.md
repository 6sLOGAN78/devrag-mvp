# RAGFlow Documentation Master Map: 00-Overview

Welcome to the **00-Overview** module of the reverse-engineered technical documentation for **RAGFlow**. This section lays down the architectural foundation, core design philosophy, dual-stack Python/Go operational paradigm, and complete high-level technology stack.

---

## Level 1: Conceptual Architecture & System Vision

RAGFlow is an open-source Retrieval-Augmented Generation (RAG) engine designed for enterprise applications. It bridges raw un-structured/semi-structured data (PDFs, PPTX, DOCX, images, web pages, audio) and Large Language Models (LLMs) with high precision and zero hallucinations.

Unlike conventional naive RAG engines that perform arbitrary chunking (e.g., character sliding windows), RAGFlow emphasizes **Deep Document Parsing**—understanding document layout, visual tables, headers, footers, charts, and multi-column formats—prior to semantic indexing and graph-based retrieval.

```
+-----------------------------------------------------------------------------------+
|                                  RAGFlow Platform                                 |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  +------------------+   +-------------------+   +------------------------------+  |
|  | Web UI (React)   |   | REST APIs (v1)    |   | SDK / Open APIs              |  |
|  +--------+---------+   +---------+---------+   +--------------+---------------+  |
|           |                       |                            |                  |
|           +-----------------------+----------------------------+                  |
|                                   |                                               |
|  +--------------------------------v--------------------------------------------+  |
|  | Dual-Stack Routing Engine                                                    |  |
|  |  * Go Engine (Gin framework) - High-concurrency routing, ingestion, task sync|  |
|  |  * Python Engine (Quart ASGI) - Async RAG pipelines, LLM bridge, ML workflows|  |
|  +--------------------------------+--------------------------------------------+  |
|                                   |                                               |
|  +--------------------------------v--------------------------------------------+  |
|  | DeepDoc & Execution Services                                                |  |
|  |  * Layout & Vision OCR Parsing Engine                                        |  |
|  |  * Multi-Vector Indexing (Infinity / Elasticsearch / OceanBase / Qdrant)    |  |
|  |  * Agentic Canvas Flow Execution & RAG Hybrid Search                        |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## Documents in this Directory

| Document | Description | Key Topics |
| :--- | :--- | :--- |
| [what-is-ragflow.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/what-is-ragflow.md) | High-level summary of RAGFlow | Core capabilities, vision, multi-modal ingestion, DeepDoc parsing. |
| [why-ragflow-exists.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/why-ragflow-exists.md) | Problem state & motivation | Naive RAG limitations, visual layout understanding, zero-hallucination guarantee. |
| [high-level-architecture.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/high-level-architecture.md) | Layered subsystem breakdown | Presentation, Routing, Core RAG, DeepDoc, Persistence, Engine. |
| [architecture-diagram.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/architecture-diagram.md) | Complete visual architecture | Comprehensive Mermaid diagram of dual-stack services & components. |
| [repository-map.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/repository-map.md) | High-level repository map | Top-level folder structure, python/go backend split, web workspace. |
| [technology-stack.md](file:///home/logan78/Desktop/ragflow/ragflow-docs/00-overview/technology-stack.md) | Tech stack inventory | React 18, Go Gin, Python Quart, Peewee, Redis, MinIO, Vector DBs. |

---

## Level 2: Core Source Code References

- Python ASGI Server Entry Point: [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)
- Python App Initialization & Auth: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
- Go HTTP Engine Entry Point: [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)
- Go Central Router: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Frontend Application Entry Point: [`web/src/app.tsx`](file:///home/logan78/Desktop/ragflow/web/src/app.tsx#L1)
- Frontend Routes & Lazy Loaders: [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L130)
