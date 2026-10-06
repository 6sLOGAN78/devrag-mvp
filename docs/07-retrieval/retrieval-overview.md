# Retrieval Subsystem Overview

## Level 1: Conceptual Overview

The Retrieval Subsystem in RAGFlow searches knowledge bases for relevant document chunks given a user prompt. It executes a hybrid search architecture combining vector KNN dense retrieval, full-text term matching (BM25), metadata filtering, PageRank weighting, and cross-encoder re-ranking.

```mermaid
flowchart TD
    Query[User Query String] --> Dealer[Dealer / rag/nlp/search.py]
    
    Dealer --> VectorPath[Vector Search Path / MatchDenseExpr]
    Dealer --> FulltextPath[Full-Text Search Path / MatchTextExpr]
    
    VectorPath --> KNN[Vector KNN Search / Cosine Similarity]
    FulltextPath --> BM25[Full-Text Search / BM25 Term Weighting]
    
    KNN & BM25 --> HybridFusion[Hybrid Score Fusion / FusionExpr]
    HybridFusion --> Pruning[Dealer._prune_deleted_chunks]
    Pruning --> Rerank{Reranker Enabled?}
    
    Rerank -->|Yes| CrossEncoder[Neural Reranker / rerank_by_model]
    Rerank -->|No| HeuristicRerank[KNN + Term Heuristic / rerank_with_knn]
    
    CrossEncoder & HeuristicRerank --> Threshold[Similarity Threshold Filter]
    Threshold --> Result[Filtered & Ordered Reference Chunks]
```

---

## Level 2: Implementation Details

### System Component Map

| Component | File Path | Primary Function |
| :--- | :--- | :--- |
| **Search Dealer** | [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L39) | Central retrieval engine `Dealer` class, `retrieval()` and `search()` methods |
| **Fulltext Queryer** | [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L28) | `FulltextQueryer` class, query normalization, synonym lookup |
| **NLP Tokenizer** | [rag/nlp/rag_tokenizer.py](file:///home/logan78/Desktop/ragflow/rag/nlp/rag_tokenizer.py#L20) | Word segmentation, traditional/simplified Chinese conversion |
| **DocStore Engine** | [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py#L40), [infinity_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/infinity_conn.py#L35) | DB adapters translating `MatchTextExpr` and `MatchDenseExpr` into backend queries |
| **Go Engine** | [internal/engine/elasticsearch/chunk.go](file:///home/logan78/Desktop/ragflow/internal/engine/elasticsearch/chunk.go#L30) | High-performance Go retrieval driver |
