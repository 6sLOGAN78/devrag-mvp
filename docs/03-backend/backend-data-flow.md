# Backend Data Flow Architecture

## Level 1: End-to-End Data Processing Pipeline

This document details how data flows through the backend system, from HTTP request entry to database transaction execution, vector store indexing, and response rendering.

---

## Level 2: Comprehensive Execution Sequence Diagrams

### 1. Document Chunking & Indexing Flow

```mermaid
sequenceDiagram
    participant Client as Frontend SPA / API Client
    participant Router as Go Gin Gateway (cmd/ragflow_server.go)
    participant PyApp as Python ASGI (api/ragflow_server.py)
    participant Service as DocumentService (api/db/services)
    participant DeepDoc as DeepDoc Parser (deepdoc/vision)
    participant DocStore as Vector Store (rag/utils)

    Client->>Router: POST /api/v1/documents/upload (PDF File)
    Router->>Service: Save raw PDF file to MinIO Object Store
    Service-->>Router: Document Record Created (status=UNSTART)
    Client->>PyApp: POST /api/v1/datasets/<dataset_id>/documents/parse { doc_ids: ["..."] }
    PyApp->>Service: Launch task execution job
    
    loop Chunking & Indexing Execution
        Service->>DeepDoc: Parse layout, OCR, TSR table matrices
        DeepDoc-->>Service: Extracted Text Blocks & HTML Tables
        Service->>Service: Calculate Dense Vector Embeddings
        Service->>DocStore: Insert Chunks & Vectors (tenant_id scoped)
    end

    Service-->>PyApp: Update Document Status to SUCCESS
    PyApp-->>Client: HTTP 200 { retcode: 0, status: "SUCCESS" }
```

### 2. Conversational RAG Chat Stream Flow

```mermaid
sequenceDiagram
    participant Client as Frontend SPA
    participant PyApp as Quart App (api/apps/restful_apis/chat_api.py)
    participant RAG as RAG Retrieval Engine (rag/nlp)
    participant LLM as LiteLLM Model Bridge
    participant DocStore as Vector Engine (rag/utils)

    Client->>PyApp: POST /api/v1/chat/completions { session_id, message }
    PyApp->>RAG: Hybrid Search (Dense Vectors + BM25 Keywords)
    RAG->>DocStore: Retrieve Hit Chunks (filtered by tenant_id)
    DocStore-->>RAG: Top-K Grounding Chunks
    RAG-->>PyApp: Context-Augmented Prompt
    PyApp->>LLM: Stream Chat Completion (LiteLLM)
    
    loop Token Stream
        LLM-->>PyApp: Token Chunk
        PyApp-->>Client: SSE Event (data: {"answer": "token"})
    end
```

### Key Source Links

- Document Upload Handler: [`internal/handler/document.go`](file:///home/logan78/Desktop/ragflow/internal/handler/document.go)
- Document Service: [`api/db/services/document_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/document_service.py)
- Chat REST API: [`api/apps/restful_apis/chat_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py)
- RAG Retrieval Engine: [`rag/nlp/`](file:///home/logan78/Desktop/ragflow/rag)
- DocStore Connector: [`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils)
