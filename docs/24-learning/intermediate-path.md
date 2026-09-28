# Intermediate Path: DeepDoc Parsing & Retrieval Pipeline

## Target Audience
Backend engineers, AI developers, and RAG specialists who want to understand document ingestion, DeepDoc parsing, hybrid search retrieval algorithms, and LLM integrations.

---

## Learning Objectives
1. Deep-dive into asynchronous task processing via Redis and `rag/svr/task_executor.py`.
2. Understand vision layout analysis (YOLOv10 / PP-YOLO) and PaddleOCR text extraction in `deepdoc/`.
3. Master hybrid retrieval mechanics (BM25 keyword search + dense vector search) in `rag/nlp/search.py`.
4. Understand cross-encoder reranking and reciprocal rank fusion.
5. Learn how `LLMBundle` handles multi-provider LLM integrations.

---

## Primary Reading List

1. **Document Processing**: Read [21-end-to-end-flows/document-processing.md](../21-end-to-end-flows/document-processing.md) and inspect `main()` in [rag/svr/task_executor.py:L1904](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L1904).
2. **DeepDoc Parser Implementation**: Inspect PDF parser in [deepdoc/parser/pdf_parser.py:L50](file:///home/logan78/Desktop/ragflow/deepdoc/parser/pdf_parser.py#L50).
3. **Indexing Pipeline**: Read [21-end-to-end-flows/indexing.md](../21-end-to-end-flows/indexing.md) and inspect [rag/utils/es_conn.py:L150](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py#L150).
4. **Hybrid Retrieval**: Read [21-end-to-end-flows/ask-question.md](../21-end-to-end-flows/ask-question.md) and inspect `Dealer.search()` in [rag/nlp/search.py:L134](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L134).
5. **Chat Token Streaming**: Read [21-end-to-end-flows/chat-streaming.md](../21-end-to-end-flows/chat-streaming.md) and inspect [api/db/services/llm_service.py:L220](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L220).

---

## Hands-On Milestones

- **Milestone 1**: Trace a document through parsing: upload PDF -> inspect Redis queue -> breakpoint in `pdf_parser.py` -> verify chunk insertion into Elasticsearch.
- **Milestone 3**: Add a custom LLM provider class into `rag/llm/` and connect it via `LLMBundle`.
