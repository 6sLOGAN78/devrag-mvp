# Vector Database & Retrieval Engine Integrations

## Level 1: Conceptual Overview

RAGFlow integrates with high-performance vector search engines and hybrid search databases. Primary vector engines include InfiniFlow Infinity, Elasticsearch 8+, OpenSearch, and PostgreSQL (PGVector).

---

## Level 2: Implementation Details

### Source File Map
- **Search Factory**: [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py)
- **Infinity Client**: [rag/utils/infinity_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/infinity_conn.py)
- **Elasticsearch Client**: [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py)

---

### Retrieval Protocol & Hybrid Score Fusion

Hybrid retrieval blends vector dense similarity ($S_{vec}$) and BM25 text keyword similarity ($S_{term}$) using weighted reciprocal rank fusion (RRF) or explicit linear combinations:

$$S_{final} = w_{vec} \cdot S_{vec} + w_{term} \cdot S_{term}$$

The resulting candidate list is subsequently passed to cross-encoder rerank drivers ([rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L32)).
