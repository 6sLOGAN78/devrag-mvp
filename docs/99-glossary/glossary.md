# RAGFlow Comprehensive Technical Glossary

## Glossary Definitions

### Agent Canvas
The visual drag-and-drop workflow designer in RAGFlow that compiles graphical component nodes into an executable Directed Acyclic Graph (`Graph` in [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49)).

### Bounding Box
Coordinates `[x0, y0, x1, y1]` extracted by DeepDoc layout analysis models (`layout_recognizer.py`) indicating the exact spatial region of a paragraph, table, or figure on a scanned PDF page.

### Chunk
A contiguous segment of text split from a document, associated with dense vector embeddings (`q_{dim}_vec`), keyword tokens (`content_ltks`), metadata attributes, and citation markers (`##0$$`).

### DeepDoc
RAGFlow's proprietary vision-based document parsing engine located in `deepdoc/`. It combines layout recognition models (YOLO), OCR (PaddleOCR), and table structure extraction.

### Hybrid Search
A search strategy that executes both **Sparse BM25 term matching** and **Dense Vector Cosine Similarity search** concurrently in Elasticsearch or Infinity via `Dealer.search()` in [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L134).

### Knowledge Base (Dataset)
The top-level organizational container (`knowledgebase` MySQL table) that encapsulates document collections, embedding model choices, chunking parser templates, and vector store indices.

### LLMBundle
The unified python wrapper class in [api/db/services/llm_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py#L35) that abstracts chat generation, token streaming, and embedding calls across cloud and local LLM providers.

### RAPTOR
Recursive Abstractive Processing for Tree-Organized Retrieval. A hierarchical summarization algorithm in [rag/utils/raptor_utils.py](file:///home/logan78/Desktop/ragflow/rag/utils/raptor_utils.py#L48) that clusters text chunks and builds summary trees for macro-level retrieval.

### Reranker
A cross-encoder model (e.g. `bge-reranker-large`) that re-evaluates candidate chunks returned by hybrid search to calculate fine-grained relevance scores before prompt assembly.

### Server-Sent Events (SSE)
An HTTP streaming standard (`Content-Type: text/event-stream`) used by RAGFlow's chat and agent completion endpoints to stream response tokens and node states to the UI in real time.

### Tenant
An isolated workspace environment associated with a user or organization (`tenant` and `user_tenant` tables), ensuring complete data and model key segregation.
