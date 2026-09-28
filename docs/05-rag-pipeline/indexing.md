# Indexing & Storage Engine Integration

## Level 1: Conceptual Overview

Indexing converts extracted chunks, tokenized terms, metadata tags, and dense vector embeddings into structured database records in vector and full-text search engines. RAGFlow abstracts storage engines under a unified `DocStoreConnection` interface, allowing seamless deployment across **Infinity**, **Elasticsearch**, **OceanBase**, **ClickHouse**, and **SereneDB**.

---

## Level 2: Implementation Details

### Tenant Index Isolation Scheme

Indices are isolated per tenant ID using the naming formula in [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L35):

```python
def index_name(uid):
    return f"ragflow_{uid}"
```

### Schema & Mapping Fields

| Field Name | Type | Purpose |
| :--- | :--- | :--- |
| `id` | Keyword / String | Unique chunk ID (`doc_id + "_" + chunk_order`) |
| `doc_id` | Keyword / String | Parent document ID |
| `kb_id` | Keyword / String | Parent Knowledge Base ID |
| `content_ltks` | Text (Analyzed) | Fine-grained tokenized chunk content for BM25 search |
| `title_tks` | Text (Analyzed) | Document/section title tokens (Boost factor 10x) |
| `important_kwd` | Keyword List | Key phrase keywords (Boost factor 30x) |
| `question_tks` | Text (Analyzed) | Generated or parsed Q&A question tokens (Boost factor 20x) |
| `position_int` | Integer Array | `[page_num, x0, top, x1, bottom]` coordinates |
| `q_{dim}_vec` | Dense Vector | HNSW / IVFFlat indexed vector array |
| `available_int` | Integer | Status flag (`1` = active/searchable, `0` = disabled) |

### Engine Implementations

1. **Elasticsearch Connection**:
   - Python Adapter: [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py#L40)
   - Go Driver: [internal/engine/elasticsearch/chunk.go](file:///home/logan78/Desktop/ragflow/internal/engine/elasticsearch/chunk.go#L30)
   - Vector Index Type: `dense_vector` with `hnsw` similarity `cosine`.

2. **Infinity Connection (Default Vector DB)**:
   - Python Adapter: [rag/utils/infinity_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/infinity_conn.py#L35)
   - Go Driver: [internal/engine/infinity/chunk.go](file:///home/logan78/Desktop/ragflow/internal/engine/infinity/chunk.go#L25)
   - Multi-vector indexing and native hybrid fusion.

3. **OceanBase Engine**:
   - Go Driver: [internal/engine/oceanbase/document.go](file:///home/logan78/Desktop/ragflow/internal/engine/oceanbase/document.go#L30)
