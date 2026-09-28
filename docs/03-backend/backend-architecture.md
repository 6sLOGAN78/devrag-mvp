# Backend System Architecture

## Level 1: Architectural Patterns

The RAGFlow backend is architected around four core software design patterns:

1. **Dual-Stack Gateway Strategy**: Requests entering the system pass through Nginx to either the Go Gin server (for user/tenant/auth/sync handlers) or the Python Quart server (for heavy ML/agent execution). The Go server attaches `X-API-Source: go` to HTTP responses ([`internal/router/router.go:L146`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L146)).
2. **Layered Service-DAO Pattern**: Clean isolation between the Handler/Controller layer (`api/apps/restful_apis/` or `internal/handler/`), Service layer (`api/db/services/` or `internal/service/`), and Data Access Object (DAO) layer (`api/db/db_models.py` or `internal/dao/`).
3. **Distributed Lock Coordination**: Background document chunking status updaters and task ingestion queues synchronize using Redis distributed locks (`RedisDistributedLock`) ([`api/ragflow_server.py:L56`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L56)).
4. **Pluggable Vector Storage Abstraction**: Vector database interactions pass through a unified DocStore interface ([`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils)), decoupling business logic from underlying search engines (Infinity, ES, OceanBase, Qdrant, Milvus).

---

## Level 2: Detailed Architectural Diagrams & Code Map

```mermaid
graph TB
    subgraph Client_Requests ["Client Ingress"]
        REST_Req["REST API Request"]
        SSE_Req["SSE Chat Stream Request"]
    end

    subgraph Go_Stack ["Go Backend Engine (cmd/ragflow_server.go)"]
        Gin_Engine["Gin Engine Router (internal/router/router.go)"]
        Go_Auth["Auth Middleware (internal/handler/auth.go)"]
        Go_Handler["Gin Handlers (internal/handler/)"]
        Go_Service["Go Service Layer (internal/service/)"]
        Go_DAO["Go DAO Layer (internal/dao/)"]

        Gin_Engine --> Go_Auth --> Go_Handler --> Go_Service --> Go_DAO
    end

    subgraph Py_Stack ["Python Backend Engine (api/ragflow_server.py)"]
        Quart_Engine["Quart App Router (api/apps/__init__.py)"]
        Py_Auth["login_required Decorator"]
        Py_API["RESTful APIs (api/apps/restful_apis/)"]
        Py_Service["Python Services (api/db/services/)"]
        Peewee_DB["Peewee DB Models (api/db/db_models.py)"]

        Quart_Engine --> Py_Auth --> Py_API --> Py_Service --> Peewee_DB
    end

    subgraph Subsystems ["Engine Execution Subsystems"]
        Agent_Engine["Agent Canvas Runtime (agent/component/)"]
        DeepDoc_Engine["DeepDoc OCR & TSR (deepdoc/vision/)"]
        DocStore_Adapter["DocStore Vector Adapter (rag/utils/)"]

        Py_Service --> Agent_Engine & DeepDoc_Engine & DocStore_Adapter
    end

    REST_Req -->|Go Routes| Gin_Engine
    REST_Req -->|Python Routes| Quart_Engine
    SSE_Req --> Quart_Engine

    Go_DAO --> MySQL[("MySQL DB")]
    Peewee_DB --> MySQL
    Go_DAO --> Redis[("Redis Cache")]
    DocStore_Adapter --> VectorDB[("Vector Engine")]
```

### Primary Code References

- Go Main Entry: [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)
- Go Router: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Server Entry: [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)
- Python App Setup: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
- Database Models: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- DocStore Interface: [`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils)
