# System Architecture Diagram

## Level 1: Visual Overview

This document presents the complete architectural diagram for RAGFlow, illustrating the interactions between the React single-page application, the dual-stack Go/Python API server backends, the DeepDoc multi-modal parser, the background sync worker, and the persistence storage infrastructure.

---

## Level 2: Comprehensive Architecture Diagram (Mermaid)

```mermaid
graph TB
    subgraph Client_Layer["Client Presentation Layer"]
        Browser["User Browser"]
        SDK["Python / HTTP SDK"]
        Browser -->|HTTPS / WSS| WebUI["React SPA (web/src)"]
    end

    subgraph Gateway_Layer["Ingress & Routing Gateway"]
        Nginx["Nginx Reverse Proxy"]
        WebUI --> Nginx
        SDK --> Nginx
    end

    subgraph Go_Backend_Stack["Go Backend Stack (cmd/ragflow_server.go)"]
        GinServer["Gin Router Engine"]
        GoAuthHandler["Auth Handler & JWT Middleware"]
        UserHandler["User & Tenant Handlers"]
        DocHandler["Document Ingestion Handler"]
        MCPServer["MCP Server Handler"]
        GoSyncer["Task Syncer (internal/syncer)"]

        GinServer --> GoAuthHandler
        GoAuthHandler --> UserHandler
        GoAuthHandler --> DocHandler
        GoAuthHandler --> MCPServer
        DocHandler --> GoSyncer
    end

    subgraph Py_Backend_Stack["Python Backend Stack (api/ragflow_server.py)"]
        QuartServer["Quart ASGI Application"]
        PyAuthMiddleware["Login Decorator (api/apps/__init__.py)"]
        AgentEngine["Agent Canvas Flow Runtime (agent/component)"]
        RetrievalEngine["Hybrid Retrieval & Rerank (rag/nlp)"]
        DeepDocEngine["DeepDoc OCR & Vision Parser (deepdoc/vision)"]

        QuartServer --> PyAuthMiddleware
        PyAuthMiddleware --> AgentEngine
        PyAuthMiddleware --> RetrievalEngine
        PyAuthMiddleware --> DeepDocEngine
    end

    subgraph Storage_Layer["Persistence & Indexing Infrastructure"]
        MySQL[("MySQL Database (api/db/db_models.py)")]
        Redis[("Redis Cache / Session Lock")]
        MinIO[("MinIO / S3 File Storage")]
        VectorStore[("Vector Store (Infinity / Elasticsearch / OceanBase / Qdrant / Milvus)")]
    end

    Nginx -->|/api/v1/auth, /users, /sync| GinServer
    Nginx -->|/api/v1/agents, /api/v1/chats, /api/v1/documents| QuartServer

    Go_Backend_Stack --> MySQL
    Go_Backend_Stack --> Redis

    Py_Backend_Stack --> MySQL
    Py_Backend_Stack --> Redis
    Py_Backend_Stack --> MinIO
    Py_Backend_Stack --> VectorStore
```

---

## Component Reference Links

- **Go Entry Point**: [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)
- **Go Router**: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- **Python Entry Point**: [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)
- **Python App Config**: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
- **Frontend App Entry**: [`web/src/app.tsx`](file:///home/logan78/Desktop/ragflow/web/src/app.tsx#L1)
- **Frontend Routes**: [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28)
- **Database Schema**: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- **DeepDoc Parser**: [`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py)
