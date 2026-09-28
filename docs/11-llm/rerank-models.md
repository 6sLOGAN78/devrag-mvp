# Cross-Encoder Rerank Models

## Level 1: Conceptual Overview

**Rerank Models** act as a second-stage cross-encoder ranker in RAGFlow's hybrid retrieval pipeline. Unlike bi-encoder embeddings that compute vector cosine similarity independently, cross-encoders accept query-document pairs simultaneously to score contextual relevance.

The rerank engine guarantees score normalization to $[0.0, 1.0]$ across all providers (Cohere, Jina, BAAI/SiliconFlow, NVIDIA, Voyage, LocalAI), ensuring hybrid blend formulas ($w_{vec} \cdot S_{vec} + w_{rerank} \cdot S_{rerank}$) operate on calibrated scales.

---

## Level 2: Implementation Details

### Source File References
- **Rerank Module**: [rag/llm/rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L32)

---

### Score Normalization Algorithm (`_normalize_rank`)

In [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L69-L94):

```python
@staticmethod
def _normalize_rank(rank: np.ndarray) -> np.ndarray:
    """Guarantee scores land in [0, 1] for hybrid retrieval blending.
    
    Providers emitting calibrated scores in [0, 1] (Cohere, Jina, Voyage) pass through.
    Out-of-range outputs (e.g. NVIDIA's unbounded negative logits) are min-max rescaled.
    """
    if rank.size == 0:
        return rank
    min_rank = float(np.min(rank))
    max_rank = float(np.max(rank))

    if min_rank >= 0.0 and max_rank <= 1.0:
        return rank
    span = max_rank - min_rank
    if span < 1e-3:
        return np.clip(rank, 0.0, 1.0)
    return (rank - min_rank) / span
```

---

### Core Driver Classes

#### 1. Jina Rerank (`JinaRerank`)
In [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L96-L118):
Target model: `jina-reranker-v2-base-multilingual`. Calls HTTP endpoint `https://api.jina.ai/v1/rerank`.

#### 2. Cohere Rerank (`CoHereRerank`)
In [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L290-L323):
Uses Cohere SDK `v2/rerank` to evaluate relevance scores.

#### 3. NVIDIA Rerank (`NvidiaRerank`)
In [rerank_model.py](file:///home/logan78/Desktop/ragflow/rag/llm/rerank_model.py#L197-L244):
Outputs raw logit scores which are rescaled to $[0, 1]$ by `_normalize_rank`.
