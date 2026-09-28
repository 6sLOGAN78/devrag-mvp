# End-to-End Complete RAG Execution Flow

## Level 1: Conceptual Overview

The complete RAG flow spans document upload, asynchronous worker queue ingestion, layout recognition, domain-specific chunking, multi-engine vector indexing, hybrid retrieval, neural reranking, context construction, and streaming LLM generation with inline citations.

---

## Level 2: Implementation Details

### Complete End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant WebUI as Web UI / API Gateway
    participant TaskQueue as Redis Task Queue (te.0.common)
    participant Worker as Task Executor (task_executor.py)
    participant DeepDoc as DeepDoc Vision Engine
    participant DocStore as DocStore (ES / Infinity)
    participant LLM as LLM Engine

    User->>WebUI: Upload Document (POST /api/v1/documents/upload)
    WebUI->>TaskQueue: Enqueue Task Payload
    Worker->>TaskQueue: Pop Task (collect)
    Worker->>DeepDoc: DLA + OCR + TSR Processing
    DeepDoc-->>Worker: Layout Boxes & Text Spans
    Worker->>Worker: Apply Domain Chunker (rag/app/)
    Worker->>DocStore: Upsert Chunks & Embeddings
    Worker-->>WebUI: Ingestion Complete (100%)
    
    User->>WebUI: Submit Query (POST /api/v1/agents/chat/completions)
    WebUI->>DocStore: Execute Hybrid Retrieval (Dealer.retrieval)
    DocStore-->>WebUI: Raw Candidates
    WebUI->>WebUI: Execute Cross-Encoder Reranking
    WebUI->>LLM: Send Context & Formatted Prompt
    LLM-->>WebUI: Stream Token Stream
    WebUI->>WebUI: Run insert_citations()
    WebUI-->>User: Final Answer with References
```

### Complete Source Code Map

2. **Task Queue Worker**: [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L220)
3. **DeepDoc Layout Engine**: [deepdoc/vision/layout_recognizer.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L33)
4. **Hybrid Retrieval Dealer**: [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L39)
5. **Full-text Query Builder**: [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L28)
6. **DocStore Connections**: [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py#L40) / [infinity_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/infinity_conn.py#L35)
