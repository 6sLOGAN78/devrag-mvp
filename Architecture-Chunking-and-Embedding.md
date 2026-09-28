# Codebase Architecture: Chunking & Embedding

This document provides a deep dive into the exact codebase architecture and execution flow for how **Chunking** and **Embedding** are handled in the main RAGFlow repository.

---

## 1. The Orchestration Layer
**File:** `rag/svr/task_executor.py`

The entire ingestion pipeline is governed by the `do_handle_task()` function inside the worker. It enforces a strict, synchronous pipeline for a single document task:

1. **`build_chunks()`**: Converts raw file bytes into an array of chunk dictionaries.
2. **`embedding()`**: Converts chunk text into mathematical vectors using an LLM.
3. **`insert_chunks()`**: Bulk inserts the vectors into the database.

### The FACTORY Pattern
RAGFlow supports over 14 distinct chunking strategies (e.g., *Laws*, *Resume*, *Q&A*, *Table*). To manage this without massive `if/else` statements, it uses a Python `FACTORY` dictionary.
```python
# snippet from rag/svr/task_executor.py
FACTORY = {
    "naive": naive,
    "paper": paper,
    "resume": resume,
    "table": table,
    # ...
}
chunker = FACTORY[task["parser_id"].lower()]
cks = await thread_pool_exec(chunker.chunk, ...)
```

---

## 2. The Chunking Layer
**File:** `rag/app/naive.py` (and others in `rag/app/`)

Every chunker module (like `naive.py`) must expose a `def chunk(...)` method. This method executes a two-phase process: **Extraction** and **Merging**.

### Phase 1: DeepDoc Extraction
RAGFlow heavily utilizes its custom `deepdoc` package to understand file structure:
*   If the file is a PDF, it uses `PdfParser` (which can invoke layout recognition via OCR models like PaddleOCR or Docling) to extract blocks of text, images, and tables alongside their positional bounding boxes.
*   If it's an Excel file, it uses `ExcelParser`.

### Phase 2: NLP Merging
Once the raw text is extracted, it must be split into token-limited semantic chunks. 
RAGFlow uses algorithms located in `rag/nlp/` (e.g., `naive_merge`).
1.  **Splitting**: It splits massive strings using defined delimiters (`\n`, `!`, `?`, `。`).
2.  **Aggregation**: It iterates through the pieces and continuously concatenates them together until the token count (calculated via `tiktoken`) reaches the `chunk_token_num` limit (default 128 or 512).
3.  **Overlap**: It ensures a sliding window overlap (e.g., 10%) so context isn't lost at chunk boundaries.

---

## 3. The Embedding Layer
**Files:** `rag/svr/task_executor.py` (Line 710) & `rag/llm/embedding_model.py`

RAGFlow does much more than just firing strings at an API. Its embedding logic is highly optimized for production Retrieval-Augmented Generation.

### A. The LLMBundle Abstraction
Instead of writing explicit `requests.post()` calls for OpenAI, Azure, or Ollama, RAGFlow routes everything through the `LLMBundle` class (`api/db/services/llm_service.py`), which abstracts away the specific provider SDKs and token-counting limits.

### B. Batching
Sending 5,000 chunks to an API sequentially would take hours. RAGFlow chunks the chunks. It slices the array using `settings.EMBEDDING_BATCH_SIZE` and utilizes `thread_pool_exec` to make parallel API calls while strictly adhering to rate limiters (`embed_limiter`).

### C. Advanced Vector Mixing (Title + Content)
RAGFlow tackles a major RAG flaw: chunks losing global context (e.g., a chunk on page 50 loses the context of the book's title).
1.  It embeds the document's Title (`tts`).
2.  It embeds the chunk's Content (`cnts`).
3.  It mathematically mixes the vectors using numpy based on a configurable weight (`filename_embd_weight`, default 10% title, 90% content).
```python
# snippet from rag/svr/task_executor.py
title_w = float(filename_embd_weight)
vects = title_w * tts + (1 - title_w) * cnts
```
The resulting vector is then dynamically stored back onto the chunk dictionary using the exact dimensions returned by the model (e.g., `d["q_1536_vec"] = v`).

---

## 4. The Vector Store Layer
**File:** `common/doc_store/` & `rag/svr/task_executor.py`

### Abstraction
Because RAGFlow supports Elasticsearch, Infinity, OceanBase, and OpenSearch, it uses a generic `settings.docStoreConn.insert()` interface. The underlying driver (e.g., `es_conn_base.py`) translates the chunk dictionaries into the specific database's bulk insert schema.

### Zero-Trust Multitenancy
When inserting, RAGFlow does not dump all vectors into a single global index. It passes `search.index_name(task_tenant_id)` as the target index.
*   **Result**: Every organization (tenant) gets their own completely isolated index table in the vector database. A bug or prompt injection cannot accidentally retrieve chunks belonging to a different tenant because the query is physically restricted to that tenant's index.

### Mother Chunks
For advanced hierarchical retrieval (e.g., pulling a parent section if a child chunk matches), the `insert_chunks` function extracts `mom_with_weight` fields, generates a deterministic `xxhash` ID for the mother node, and inserts them alongside the standard chunks.
