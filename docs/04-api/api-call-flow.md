# End-to-End API Call Flow

## Level 1: System Call Sequence

This document details end-to-end API request lifecycles across the Go Gin gateway and Python Quart ASGI application.

---

## Level 2: Comprehensive Sequence Diagrams

### 1. User Authentication & JWT Issuance Call Flow

```mermaid
sequenceDiagram
    participant Client as Frontend SPA / Client
    participant Gin as Go Gin Engine (cmd/ragflow_server.go)
    participant UserDAO as User DAO (internal/dao/user.go)
    participant DB as MySQL DB

    Client->>Gin: POST /api/v1/auth/login { email, password }
    Gin->>UserDAO: Query user by email
    UserDAO->>DB: SELECT * FROM user WHERE email = ? AND status = 1
    DB-->>UserDAO: User record
    Gin->>Gin: Verify password hash (Bcrypt / PBKDF2)
    Gin->>Gin: Generate signed JWT Access Token
    Gin-->>Client: HTTP 200 { retcode: 0, data: { access_token: "..." } }
```

### 2. Conversational RAG SSE Stream Call Flow

```mermaid
sequenceDiagram
    participant Client as Frontend SPA
    participant Quart as Python Quart ASGI (api/ragflow_server.py)
    participant Auth as Auth Decorator (api/apps/__init__.py)
    participant RAG as RAG Hybrid Search Engine (rag/nlp)
    participant LLM as LiteLLM Model Bridge

    Client->>Quart: POST /api/v1/chat/completions (Header: Authorization)
    Quart->>Auth: Validate JWT / API Key -> Set g.user & g.tenant_id
    Auth-->>Quart: User Authenticated
    Quart->>RAG: Execute Dense Vector + BM25 Hybrid Retrieval
    RAG-->>Quart: Grounding Chunks (filtered by tenant_id)
    Quart->>LLM: Initiate Streaming Completion Call
    
    loop Stream Output
        LLM-->>Quart: Token Chunk
        Quart-->>Client: SSE Event (data: {"answer": "token"})
    end
```

### Key Source Links

- Go Router Setup: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Auth Decorator: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L98-L220)
- Python Chat REST Endpoint: [`api/apps/restful_apis/chat_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py)
- Go User Handler: [`internal/handler/user.go`](file:///home/logan78/Desktop/ragflow/internal/handler/user.go)
