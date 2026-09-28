# Chat Subsystem Architecture Overview

## Level 1: Conceptual Overview

The **Chat Subsystem** in RAGFlow powers interactive conversational AI assistants equipped with Retrieval-Augmented Generation (RAG). It manages assistant presets (`Dialog`), multi-turn session persistence (`Conversation` / `API4Conversation`), hybrid retrieval against linked Knowledge Bases (`kb_ids`), memory context window management, citation annotation (`##0$$`), and SSE token streaming.

```mermaid
graph TD
    Client[Client App / Web UI / SDK] --> REST[Chat REST APIs (chat_api.py / chat.go)]
    REST --> AuthCheck[User / Tenant Authentication]
    AuthCheck --> DialogSvc[DialogService (dialog_service.py / chat.go)]
    
    DialogSvc --> ConvSvc[ConversationService (conversation_service.py)]
    DialogSvc --> RetrEngine[SearchService / Retrieval Engine]
    
    RetrEngine --> VectorStore[(Elasticsearch / Infinity / OpenSearch)]
    
    DialogSvc --> PromptCompiler[Prompt Generator & Citation Annotator]
    PromptCompiler --> LLMB[LLMBundle (llm_service.py)]
    LLMB --> ModelDriver[Chat Model Driver (chat_model.py)]
    ModelDriver --> StreamingSSE[SSE Token Generator]
    
    StreamingSSE --> DB[(MySQL DB: dialog, conversation, api_4_conversation)]
    StreamingSSE --> Client
```

---

## Level 2: Implementation Details

### Source File Map

| Subsystem Component | Python Path | Go Path | Key Responsibilities |
| :--- | :--- | :--- | :--- |
| **REST API Routes** | [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1) | [chat.go](file:///home/logan78/Desktop/ragflow/internal/handler/chat.go#L32) | HTTP endpoints for dialog CRUD, session completion, mindmap generation |
| **OpenAI Compatibility** | [openai_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/openai_api.py#L1) | [openai_chat.go](file:///home/logan78/Desktop/ragflow/internal/handler/openai_chat.go#L1) | `/v1/chat/completions` proxy routing to RAG flow |

---

### Database Schemas

In [db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py):

#### 1. `Dialog` Model
Stores assistant configuration presets.
- `id`: Primary key `VARCHAR(32)`
- `tenant_id`: FK to tenant `VARCHAR(32)`
- `name`: Assistant title `VARCHAR(255)`
- `kb_ids`: Array of associated knowledge base IDs (`JSON`)
- `llm_id`: Composite LLM selector string (`VARCHAR(255)`)
- `prompt_config`: System prompt templates and generation parameters (`JSON`)

#### 2. `Conversation` Model
Stores session state and full message turn histories.
- `id`: Session ID `VARCHAR(32)`
- `dialog_id`: FK to parent `Dialog` (`VARCHAR(32)`)
- `user_id`: End-user or API client ID (`VARCHAR(32)`)
- `message`: Array of turn objects `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "...", "reference": [...]}]` (`JSON`)
- `reference`: Document chunk attribution metadata (`JSON`)
