# Retrieval Call Chain Tracing

## Level 1: Conceptual Overview

The retrieval call chain spans from query submission down to multi-index vector search, hybrid candidate collection, cross-encoder reranking, and citation marker format assembly.

---

## Level 2: Complete Code Call Chain

```
[User Search Query / Chat Request]
       │
       ▼ (HTTP POST /v1/session/completion or /v1/search)
[api/apps/restful_apis/chat_api.py:session_completion()] [L1230]
  or  [api/apps/restful_apis/search_api.py:search()]
       │
       ├─► Tokenize Query String:
       │     └─► rag/nlp/rag_tokenizer.py:tokenize(query_text)
       │
       ├─► Generate Query Embedding Vector:
       │     └─► api/db/services/llm_service.py:LLMBundle.encode_queries(query_text)
       │
       ├─► Execute Search Engine:
       │     └─► rag/nlp/search.py:Dealer.search(req, idx_names, kb_ids, emb_mdl) [L134]
       │           │
       │           ├─► Sparse BM25 Keyword Search:
       │           │     └─► rag/nlp/query.py:FulltextQueryer.query() -> Match keywords in `content_ltks`
       │           │
       │           ├─► Dense Vector Cosine Similarity Search:
       │           │     └─► MatchDenseExpr(vector_column_name, query_vector, similarity)
       │           │
       │           └─► Vector Store Connection Query:
       │                 ├─► Elasticsearch: rag/utils/es_conn.py:ESConnection.search()
       │                 └─► Infinity: rag/utils/infinity_conn.py:InfinityConnection.search()
       │
       ├─► Top-K Cross-Encoder Reranking:
       │     └─► rag/nlp/search.py:Dealer.rerank(sres, rerank_mdl, topk, similarity) [L200]
       │           └─► rerank_model.py:RerankModel.similarity()
       │
       └─► Format Context for Prompt Generator:
             └─► rag/prompts/generator.py:chunks_format(chunks) [L100]
                   └─► Insert citation markers: "##0$$ Chunk text... ##0$$"
```

---

## Exact Source Code References

- **Chat REST Endpoint**: `session_completion()` in [api/apps/restful_apis/chat_api.py:L1230](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L1230)
- **Search REST Endpoint**: `search()` in [api/apps/restful_apis/search_api.py:L40](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/search_api.py#L40)
- **Search Engine Dealer**: `Dealer.search()` in [rag/nlp/search.py:L134](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L134)
- **Dealer Reranker**: `Dealer.rerank()` in [rag/nlp/search.py:L200](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L200)
- **Query Term Tokenizer**: [rag/nlp/rag_tokenizer.py:L35](file:///home/logan78/Desktop/ragflow/rag/nlp/rag_tokenizer.py#L35)
- **Fulltext Queryer**: [rag/nlp/query.py:L40](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L40)
- **Context Chunk Formatter**: `chunks_format()` in [rag/prompts/generator.py:L100](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py#L100)
