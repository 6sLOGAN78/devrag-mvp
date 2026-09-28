# Global Dependencies

## System Dependencies

This document outlines the strict dependencies between the implementation parts of the devRAG recreation project. You must not attempt to build a dependent part before its prerequisites are fully verified.

### Core Component Dependency Graph

```mermaid
flowchart TD
    %% Infrastructure Layer
    subgraph Part-01-Infrastructure
        NGX[NGINX Reverse Proxy]
        RDB[(Relational DB)]
        RED[(Redis)]
        OBJ[(Object Storage)]
        VDB[(Vector DB)]
    end

    %% Core Backend Layer
    subgraph Part-02-Core-Backend
        API[API Server & Configuration]
        ORM[Database ORM]
    end

    %% Security Layer
    subgraph Part-03-Authentication
        Auth[Auth APIs]
        MT[Multi-Tenancy Middleware]
    end

    %% Business Logic Layer
    subgraph Part-04-KnowledgeBase
        KB[KB CRUD APIs]
    end

    %% Ingestion Layer
    subgraph Part-05-Ingestion
        Upload[Upload API]
        Worker[Background Worker]
        Chunk[Chunking & Embedding]
    end

    %% Retrieval Layer
    subgraph Part-06-Retrieval
        Search[Hybrid Search Engine]
    end

    %% Chat Layer
    subgraph Part-07-Chat
        Prompt[Prompt Assembly]
        Stream[SSE Chat API]
    end

    %% Advanced Layers
    subgraph Part-08-Advanced-DeepDoc
        Vision[YOLO & OCR Pipeline]
    end
    
    subgraph Part-09-Agent-Canvas
        DAG[DAG Execution Engine]
    end

    %% Frontend Layer
    subgraph Part-10-Frontend
        UI_Shell[UI App Shell]
        UI_Auth[UI Auth]
        UI_Dash[UI KB Dashboard]
        UI_Chat[UI Chat]
        UI_Agent[UI Agent Canvas]
    end
    
    %% Edge Routing
    User((User Browser)) --> NGX
    NGX -->|Serves Static Files| UI_Shell
    NGX -->|Routes /api/*| API

    %% Backend Dependencies
    RDB --> ORM
    RED --> Worker
    OBJ --> Upload
    VDB --> Chunk
    VDB --> Search

    API --> Auth
    ORM --> Auth
    Auth --> MT

    MT --> KB
    KB --> Upload

    Upload --> Worker
    Worker --> Chunk
    
    Chunk --> Search
    Search --> Prompt
    Prompt --> Stream

    Chunk -.-> Vision
    Stream -.-> DAG

    %% Frontend to Backend Connections
    Auth --> UI_Auth
    KB --> UI_Dash
    Stream --> UI_Chat
    DAG --> UI_Agent
    
    UI_Shell --> UI_Auth
    UI_Auth --> UI_Dash
    UI_Dash --> UI_Chat
```

## Dependency Rules

1. **Infrastructure First (DOCUMENTED)**: Application code cannot run without state stores and the edge proxy. (`Part-01` must be verified before `Part-02`).
2. **Security Before Data (DOCUMENTED)**: RAGFlow relies on strict data isolation (`tenant_id`). You cannot create Knowledge Bases or Documents until the Multi-Tenancy interceptor is active. (`Part-03` before `Part-04`).
3. **Ingestion Before Retrieval (INFERRED)**: You cannot search a Vector DB that has no data. (`Part-05` before `Part-06`).
4. **Retrieval Before Chat (DOCUMENTED)**: The LLM needs context to answer questions. (`Part-06` before `Part-07`).
5. **Frontend Trails Backend (PROPOSED)**: While UI mocks can be built concurrently, the actual Frontend logic requires stable API contracts routed through NGINX. `Part-10` subparts should be built immediately after their corresponding backend parts are verified.
6. **Advanced Features Last (PROPOSED)**: DeepDoc (Vision) and Agent Canvas (DAGs) are extremely complex. They should only be attempted after the core text-based Q&A loop is functional. (`Part-08` and `Part-09` at the end).
