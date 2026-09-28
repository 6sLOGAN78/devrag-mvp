# Repository Map

## Level 1: Monorepo Organization

RAGFlow is organized as a unified monorepo accommodating the frontend web application, dual-stack Go and Python backend servers, AI/ML deep document parsing engines, multi-tenant databases, CLI tools, deployment manifests, and integration test suites.

```
/home/logan78/Desktop/ragflow/
├── admin/                    # Admin service and Web UI dashboard
├── agent/                    # Python Agent Execution Engine & Component Nodes
├── api/                      # Python Quart ASGI API Server, Routes, Models & Services
├── bin/                      # Compiled binary utilities and launch scripts
├── cmd/                      # Go Executable Entry Points (ragflow_server.go, ragflow-cli.go)
├── common/                   # Shared Python utilities, DB connectors, DocStores, settings
├── conf/                     # System configuration files (service_conf.yaml, model configs)
├── deepdoc/                  # Deep Document Parsing Engine (OCR, Layout Recognition, TSR)
├── docker/                   # Dockerfiles, docker-compose profiles, Nginx configs
├── docs/                     # Documentation sources
├── example/                  # Code examples, SDK scripts, HTTP demos
├── helm/                     # Helm chart templates for Kubernetes deployment
├── internal/                 # Go backend code (routers, handlers, services, DAOs, ingestion)
├── rag/                      # Core RAG retrieval engine (hybrid search, embeddings, reranking)
├── ragflow-docs/ # Reverse-engineered technical documentation suite
└── web/                      # React SPA Frontend (TypeScript, Tailwind, Zustand, React Router 7)
```

---

## Level 2: Top-Level Module Reference Matrix

| Directory | Language / Stack | Primary Purpose | Key Source Files |
| :--- | :--- | :--- | :--- |
| **`agent/`** | Python | Agent flow graph executor, custom node handlers | [`agent/component/`](file:///home/logan78/Desktop/ragflow/agent/component) |
| **`api/`** | Python (Quart) | REST API endpoints, Peewee DB models & services | [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90), [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61) |
| **`cmd/`** | Go | Entry points for Go API server & CLI | [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81), [`cmd/ragflow-cli.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow-cli.go) |
| **`common/`** | Python | Vector store adapters, constants, logging, settings | [`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils), [`common/settings.py`](file:///home/logan78/Desktop/ragflow/common/settings.py) |
| **`deepdoc/`** | Python (PyTorch/OCR)| Layout recognition, Table OCR, PDF chunking | [`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py) |
| **`internal/`** | Go (Gin) | Routers, Handlers, Services, DAOs, Ingestion syncer| [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141), [`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go) |
| **`rag/`** | Python | Hybrid retrieval, NLP tokenizers, re-ranking models| [`rag/nlp/`](file:///home/logan78/Desktop/ragflow/rag) |
| **`web/`** | TS / React | Single-page Web UI application | [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28), [`web/src/app.tsx`](file:///home/logan78/Desktop/ragflow/web/src/app.tsx#L1) |
