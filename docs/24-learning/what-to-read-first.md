# What to Read First in RAGFlow

## Quick Navigation Matrix

If you want to understand... **READ THIS FIRST**:

| Topic / System Area | Starting File | Key Code Source Link |
|---|---|---|
| **Single Request Lifecycle** | [21-end-to-end-flows/ragflow-one-request.md](../21-end-to-end-flows/ragflow-one-request.md) | Entire Pipeline |
| **API Server Routing** | [22-code-tracing/frontend-to-backend.md](../22-code-tracing/frontend-to-backend.md) | [api/ragflow_server.py](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L50) |
| **Document Upload & Storage** | [21-end-to-end-flows/upload-document.md](../21-end-to-end-flows/upload-document.md) | [api/apps/restful_apis/document_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/document_api.py#L452) |
| **Parsing & DeepDoc Worker** | [21-end-to-end-flows/document-processing.md](../21-end-to-end-flows/document-processing.md) | [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L1904) |
| **Hybrid Search & Reranking** | [21-end-to-end-flows/ask-question.md](../21-end-to-end-flows/ask-question.md) | [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L134) |
| **Chat SSE Token Streaming** | [21-end-to-end-flows/chat-streaming.md](../21-end-to-end-flows/chat-streaming.md) | [api/apps/restful_apis/chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1230) |
| **Agent Canvas Graph Engine** | [21-end-to-end-flows/agent-execution.md](../21-end-to-end-flows/agent-execution.md) | [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L440) |
| **Database Models** | [23-diagrams/database.mmd](../23-diagrams/database.mmd) | [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L30) |

---

## Recommended First Reading Session (30 Minutes)

1. Spend 10 minutes reading **[The Ultimate Single-Story Trace](../21-end-to-end-flows/ragflow-one-request.md)** to grasp how all parts connect.
2. Spend 10 minutes inspecting the **[System Architecture Diagram](../23-diagrams/architecture.mmd)**.
3. Spend 10 minutes following **[Retrieval Call Chain](../22-code-tracing/retrieval-call-chain.md)** down into `rag/nlp/search.py`.
