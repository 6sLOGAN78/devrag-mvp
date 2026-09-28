# Ingestion & Parsing Call Chain Tracing

## Level 1: Conceptual Overview

The ingestion call chain encompasses document parsing, layout recognition, OCR, tokenization, chunking, vector embedding, and index insertion.

---

## Level 2: Complete Code Call Chain

```
[React Parse Trigger]
       │
       ▼ (HTTP POST /api/v1/datasets/<dataset_id>/documents/parse)
[api/apps/restful_apis/document_api.py:parse_documents()] [L1552]
       │
       ├─► Update Document Status in MySQL: DocumentService.update_by_id(doc_id, {"run": "1"})
       ├─► Create Task Entries: TaskService.create_task() [api/db/services/task_service.py]
       └─► Queue Product: REDIS_CONN.queue_product("ragflow_TASK_EXE_QUEUE", task_dict)
       │
       ▼ (Asynchronous Redis Dispatch)
[rag/svr/task_executor.py:main()] [L1904]
       │
       ├─► Pop task from Redis: REDIS_CONN.queue_consumer("ragflow_TASK_EXE_QUEUE")
       ├─► Download Binary Stream: FileService.get_file(doc.location) [api/db/services/file_service.py]
       │
       ├─► Execute DeepDoc Parser Engine (based on parser_id):
       │     ├─► PDF Parser: deepdoc/parser/pdf_parser.py:PdfParser()
       │     │     ├─► Layout Recognition: deepdoc/vision/layout_recognizer.py (YOLO / PP-YOLO)
       │     │     ├─► OCR Recognition: deepdoc/vision/ocr_recognizer.py (PaddleOCR)
       │     │     └─► Table Extraction: deepdoc/vision/table_structure_recognizer.py
       │     ├─► DOCX Parser: deepdoc/parser/docx_parser.py:DocxParser()
       │     └─► Excel / Table Parser: deepdoc/parser/excel_parser.py
       │
       ├─► Text Tokenization & Chunking:
       │     └─► rag/nlp/chunk_tokenizer.py:ChunkTokenizer.tokenize()
       │
       ├─► Generate Dense Embeddings:
       │     └─► api/db/services/llm_service.py:LLMBundle.encode(chunk_texts)
       │
       ├─► Insert Chunks into Vector Store:
       │     ├─► Elasticsearch: rag/utils/es_conn.py:ESConnection.insert_chunks()
       │     └─► Infinity: rag/utils/infinity_conn.py:InfinityConnection.insert()
       │
       └─► Update MySQL Document Progress:
             └─► DocumentService.update_by_id(doc_id, {"progress": 1.0, "status": "FINISHED"})
```

---

## Exact Source Code References

- **Parse API Route**: `parse_documents()` in [api/apps/restful_apis/document_api.py:L1552](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/document_api.py#L1552)
- **Task Dispatcher Service**: `TaskService` in [api/db/services/task_service.py:L40](file:///home/logan78/Desktop/ragflow/api/db/services/task_service.py#L40)
- **Worker Main Loop**: `main()` in [rag/svr/task_executor.py:L1904](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L1904)
- **DeepDoc PDF Parser**: [deepdoc/parser/pdf_parser.py:L50](file:///home/logan78/Desktop/ragflow/deepdoc/parser/pdf_parser.py#L50)
- **DeepDoc Layout Recognizer**: [deepdoc/vision/layout_recognizer.py:L30](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L30)
- **Elasticsearch Storage Engine**: [rag/utils/es_conn.py:L150](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py#L150)
- **Infinity Storage Engine**: [rag/utils/infinity_conn.py:L120](file:///home/logan78/Desktop/ragflow/rag/utils/infinity_conn.py#L120)
