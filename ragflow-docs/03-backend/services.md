# Backend Services Catalog

## Level 1: Service Layer Responsibilities

The service layer contains domain-specific business logic, orchestrating database transactions, external LLM calls, document parsing workers, and search index updates.

---

## Level 2: Comprehensive Service Matrix & Source Map

### 1. Python Service Layer ([`api/db/services/`](file:///home/logan78/Desktop/ragflow/api/db/services))

| Service Class | File Path | Responsibilities & Methods |
| :--- | :--- | :--- |
| `UserService` | [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33) | User registration, authentication, password verification, access token queries (`query()`), tenant ownership. |
| `DocumentService` | [`api/db/services/document_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/document_service.py) | Document CRUD, chunking task creation, update progress loop (`update_progress()`), status updates. |
| `KnowledgebaseService` | [`api/db/services/knowledgebase_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/knowledgebase_service.py) | Dataset creation, parsing configuration, document counting, vector store index creation. |
| `TaskService` | [`api/db/services/task_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/task_service.py) | Task queuing, task execution status tracking, error trace updates. |
| `ConversationService` | [`api/db/services/conversation_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/conversation_service.py) | Dialogue session creation, chat message history persistence, reference link storage. |
| `LLMService` | [`api/db/services/llm_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py) | Tenant LLM provider credentials lookup, model instance binding. |
| `TenantLLMService` | [`api/db/services/tenant_llm_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/tenant_llm_service.py) | Multi-tenant LLM provider API key configuration and model parameters. |

---

### 2. Go Service Layer ([`internal/service/`](file:///home/logan78/Desktop/ragflow/internal/service))

| Go Package / Service | Directory Path | Responsibilities |
| :--- | :--- | :--- |
| `tenant` | [`internal/service/tenant.go`](file:///home/logan78/Desktop/ragflow/internal/service/tenant.go) | Tenant retrieval, multi-tenant workspace list, user-tenant mapping. |
| `document` | [`internal/service/document/`](file:///home/logan78/Desktop/ragflow/internal/service/document) | Document status querying, file metadata operations, chunking job dispatch. |
| `dataset` | [`internal/service/dataset/`](file:///home/logan78/Desktop/ragflow/internal/service/dataset) | Dataset listing, search configuration, knowledge base retrieval bridging. |
| `chunk` | [`internal/service/chunk/`](file:///home/logan78/Desktop/ragflow/internal/service/chunk) | Chunk representation querying and status update logic. |
| `ingestion` | [`internal/ingestion/service/`](file:///home/logan78/Desktop/ragflow/internal/ingestion/service) | High-speed document ingestion service. |

### Source Links

- Python Services Directory: [`api/db/services/`](file:///home/logan78/Desktop/ragflow/api/db/services)
- Go Services Directory: [`internal/service/`](file:///home/logan78/Desktop/ragflow/internal/service)
- User Service Source: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33)
- Document Service Source: [`api/db/services/document_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/document_service.py)
