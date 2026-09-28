# Complete Chat Call Flow & Execution Sequence

## Level 1: Conceptual Overview

The complete chat execution flow traces a user query from HTTP request arrival to final SSE response termination. It handles dialog resolution, session retrieval, optional web search / knowledge base retrieval, reranking, prompt compilation, LLM streaming, citation parsing (`##0$$`), and database persistence.

---

## Level 2: Implementation Details

### Execution Step Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Client as User / Web Client
    participant API as Chat REST API (chat_api.py)
    participant DialogSvc as DialogService (dialog_service.py)
    participant Search as SearchService (search_service.py)
    participant LLM as LLMBundle (llm_service.py)
    participant DB as MySQL DB

    Client->>API: POST /v1/api/completion (dialog_id, session_id, message)
    API->>DialogSvc: async_chat(dialog, messages, stream=True)
    alt kb_ids or web_search present
        DialogSvc->>Search: hybrid_retrieval(query, kb_ids)
        Search-->>DialogSvc: Retrieved Chunks & Similarity Scores
        DialogSvc->>DialogSvc: Rerank & Assemble Prompt Context
    else No retrieval required
        DialogSvc->>DialogSvc: Route to async_chat_solo
    end
    DialogSvc->>LLM: chat_streamly(system, history, gen_conf)
    loop Token Streaming
        LLM-->>API: Yield Token Delta
        API-->>Client: Send SSE JSON frame
    end
    API->>DB: Append user query + assistant answer to Conversation.message
    API-->>Client: Send SSE [DONE] Frame
```

---

### Key Code Entry Points

1. **REST API Endpoint**: `completion()` in [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1)
2. **Dialog Execution Engine**: `async_chat()` in [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L580)
3. **Solo Chat Fallback**: `async_chat_solo()` in [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L292)
4. **Mindmap Generator**: `gen_mindmap()` in [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L1200)

---

### Data Sanitization (`_sanitize_json_floats`)

In [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L62-L91):
Retrieval scores (`similarity`, `vector_similarity`) can compute to `NaN` when aggregations evaluate over empty chunk sets. `_sanitize_json_floats(obj)` replaces `NaN`/`Infinity` floats with `None` before emitting SSE frames, preventing client JSON parsing errors.
