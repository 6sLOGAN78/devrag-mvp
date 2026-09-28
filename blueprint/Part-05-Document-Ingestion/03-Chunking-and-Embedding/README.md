# Subpart 03: Chunking & Embedding

## 1. Objective
To implement the actual data transformation: downloading the raw text, splitting it into semantic chunks, generating vector embeddings, and inserting them into the Vector DB.

---

## 2. RAGFlow Architecture Breakdown

In the main RAGFlow repository, this subpart is highly sophisticated and handles multiple parser types, mixed embeddings, and hierarchical chunking.

The entire process is orchestrated inside `rag/svr/task_executor.py` through the `do_handle_task()` function, which delegates to three primary steps:

### Step 01: Chunking (`build_chunks`)
RAGFlow supports 14+ different parsers (Naive, Resume, Laws, Q&A, Table, etc.). 
1. **S3 Fetch**: It uses `File2DocumentService.get_storage_address()` to find the file in MinIO and downloads the raw bytes into memory.
2. **Dynamic Parser**: It uses a `FACTORY` dictionary to map the `parser_id` to the correct Python module (e.g., `rag.app.naive`).
3. **Execution**: The parser runs inside a `thread_pool_exec` to avoid blocking the event loop. The parser returns an array of chunk dictionaries. These dictionaries contain text content, bounding boxes (if it was a PDF with layout analysis), and token counts.

### Step 02: Embedding (`embedding`)
RAGFlow's embedding strategy is incredibly advanced compared to a simple API call.
1. **Title vs. Content**: For every chunk, it extracts both the content and the document's title.
2. **Batch Encoding**: It sends the text to the LLM (e.g., Infinity, OpenAI) in configurable batches (`settings.EMBEDDING_BATCH_SIZE`).
3. **Mixed Embeddings**: It generates vectors for BOTH the title and the content. It then performs vector math to mix them based on a `filename_embd_weight` (default 10% title, 90% content):
   ```python
   # Mixes the title and content embeddings mathematically
   vects = title_w * tts + (1 - title_w) * cnts
   ```
4. **Vector Field**: It dynamically assigns the vector back into the chunk dictionary as `q_{vector_size}_vec` (e.g., `q_1536_vec`).

### Step 03: Vector Database Insertion (`insert_chunks`)
RAGFlow abstracts the database layer via `docStoreConn` (which resolves to Elasticsearch, Infinity, etc.).
1. **Mother Chunks**: If a parser outputs hierarchical nodes (a "mother" node with child nodes), it hashes the mother's content using `xxhash` and isolates them to ensure relational integrity.
2. **Tenant Isolation**: It executes a bulk insert to the Vector DB. Crucially, the target index name is generated via `search.index_name(task_tenant_id)`. This means **every tenant gets their own isolated physical or logical index** in the Vector database, guaranteeing data segregation.

---

## 3. How to Implement this in devRag_@ MVP

To build this in your MVP without getting bogged down by 14 different specialized parsers, here is the updated approach:

### Step 01: Fetch and Split Text
*   **Action**: Inside your worker, fetch the bytes from MinIO/S3 using the path saved in the database.
*   **MVP Scope**: Do not build the `FACTORY` architecture yet. Hardcode a single "Naive" chunker. Use a Recursive Character Text Splitter (e.g., from LangChain) to split the decoded UTF-8 string into chunks of ~500 tokens with a 50-token overlap.

### Step 02: Generate Embeddings
*   **Action**: Iterate over your string chunks and call your embedding model (e.g., OpenAI `text-embedding-3-small`).
*   **MVP Scope**: Skip the advanced vector mixing (Title * 0.1 + Content * 0.9). Just embed the chunk content directly. Append the resulting float array to your chunk object as the vector.

### Step 03: Insert into Vector DB
*   **Action**: Connect to Elasticsearch (or your chosen Vector DB).
*   **MVP Scope**: Do not implement hierarchical "Mother" chunks yet. Simply take your flat array of chunks and bulk insert them. 
*   **CRITICAL**: You MUST enforce RAGFlow's multitenancy approach. Ensure every inserted record contains `tenant_id`, `kb_id`, and `doc_id`. Ideally, insert them into an index named after the `tenant_id` to mimic RAGFlow's exact zero-trust architecture.
