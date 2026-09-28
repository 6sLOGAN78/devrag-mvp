# Multi-Tenancy Architecture

## Level 1: Conceptual Multi-Tenancy Design

RAGFlow provides strict multi-tenancy isolation for enterprise deployments. A tenant represents an organization or isolated team workspace.

### Key Characteristics

1. **Workspace Multi-Tenancy**: Multiple users can belong to a single tenant workspace, sharing datasets, documents, models, and agent workflows.
2. **Tenant ID Scoping**: Every database entity (`Knowledgebase`, `Document`, `Task`, `Dialog`, `Canvas`) references a `tenant_id` string foreign key.
3. **Search Engine Scoping**: DocStore vector indexes (Infinity, Elasticsearch, OpenSearch, OceanBase, Qdrant, Milvus) index chunks with `tenant_id` fields, guaranteeing that vector search queries never leak data across tenants.

---

## Level 2: Database Schema & Source Implementation

```mermaid
erDiagram
    TENANT ||--o{ USER_TENANT : owns
    USER ||--o{ USER_TENANT : belongs_to
    TENANT ||--o{ KNOWLEDGEBASE : contains
    TENANT ||--o{ DIALOG : contains
    TENANT ||--o{ CANVAS : contains

    TENANT {
        string id PK
        string name
        string llm_id
        string embd_id
        string status
    }

    USER {
        string id PK
        string email
        string password
        string access_token
    }

    USER_TENANT {
        string id PK
        string user_id FK
        string tenant_id FK
        string role
    }

    KNOWLEDGEBASE {
        string id PK
        string tenant_id FK
        string name
    }
```

### Source File References

- User & Tenant Database Models: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- User Tenant Association Service: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33)
- Go Tenant DAO: [`internal/dao/tenant.go`](file:///home/logan78/Desktop/ragflow/internal/dao/tenant.go)
- Go Tenant Service: [`internal/service/tenant.go`](file:///home/logan78/Desktop/ragflow/internal/service/tenant.go)
- DocStore Scoping Adapter: [`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils)
