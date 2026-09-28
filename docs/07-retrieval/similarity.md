# Similarity Metrics Reference

## Level 1: Conceptual Overview

RAGFlow leverages multiple mathematical similarity metrics across vector space distance, term frequency overlap, and tag feature similarity.

---

## Level 2: Implementation Details

### Mathematical Formulas

#### 1. Cosine Vector Similarity
$$\text{Cosine}(A, B) = \frac{\sum_{i=1}^{d} A_i B_i}{\sqrt{\sum_{i=1}^{d} A_i^2} \sqrt{\sum_{i=1}^{d} B_i^2}}$$

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L62):
Used as standard vector space similarity metric in `MatchDenseExpr`.

#### 2. Token Overlap Similarity (`token_similarity`)
In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L455):

$$\text{Sim}_{\text{token}}(Q_{\text{kw}}, D_{\text{tks}}) = \frac{|Q_{\text{kw}} \cap D_{\text{tks}}|}{|Q_{\text{kw}}|}$$

#### 3. Tag & PageRank Score Combination
In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L350-L362):

$$S_{\text{tag}} = \frac{\sum_{t \in T} W_{\text{query}}(t) \cdot S(t)}{\sqrt{\sum_{t \in T} S(t)^2} \cdot Q_{\text{denor}}}$$

$$S_{\text{rank\_feature}} = 10.0 \cdot S_{\text{tag}} + \text{PageRank}$$
