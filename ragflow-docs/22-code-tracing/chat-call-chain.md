# Chat Call Chain Tracing

## Level 1: Conceptual Overview

The chat call chain traces the full flow of conversation management, prompt construction, hybrid search invocation, LLM generation streaming, and chat dialog history persistence.

---

## Level 2: Complete Code Call Chain

```
[React UI Next-Chats Component] (web/src/pages/next-chats/chat)
       │
       ▼ (HTTP POST /v1/session/completion)
[api/apps/restful_apis/chat_api.py:session_completion()] [L1230]
       │
       ├─► 1. Ensure Owned Chat Session:
       │     └─► _ensure_owned_chat(chat_id) [L189]
       │           └─► DialogService.get_by_id(chat_id) [api/db/services/dialog_service.py]
       │
       ├─► 2. Execute Hybrid Vector Search:
       │     └─► rag/nlp/search.py:Dealer.search()
       │           └─► Returns candidate chunk set
       │
       ├─► 3. Execute Top-K Reranking:
       │     └─► rag/nlp/search.py:Dealer.rerank()
       │
       ├─► 4. Format Prompt Context & Citations:
       │     └─► rag/prompts/generator.py:chunks_format()
       │
       ├─► 5. Stream Tokens via Server-Sent Events (SSE):
       │     └─► Inner async generator: stream() [L1328]
       │           ├─► Yield chunk reference metadata JSON
       │           └─► Loop delta in LLMBundle.chat_streamly():
       │                 └─► Yield SSE data line: `data: {"code": 0, "data": {"answer": delta}}\n\n`
       │
       └─► 6. Save Session Dialogue Audit Record:
             └─► ConversationService.save_session()
                   └─► INSERT INTO `chat_session` & `chat_dialog` in MySQL
```

---

## Exact Source Code References

- **Completion Endpoint**: `session_completion()` in [api/apps/restful_apis/chat_api.py:L1230](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1230)
- **Inner SSE Generator**: `stream()` in [api/apps/restful_apis/chat_api.py:L1328](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1328)
- **Session Creator Endpoint**: `create_session()` in [api/apps/restful_apis/chat_api.py:L824](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L824)
- **Go Chat Handler**: `Completion()` in [internal/handler/chat.go:L110](file:///home/logan78/Desktop/ragflow/internal/handler/chat.go#L110)
- **Dialog Service**: [api/db/services/dialog_service.py:L45](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L45)
- **Conversation Service**: [api/db/services/conversation_service.py:L35](file:///home/logan78/Desktop/ragflow/api/db/services/conversation_service.py#L35)
