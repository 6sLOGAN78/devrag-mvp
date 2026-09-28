# Hybrid Search & Score Fusion

## Level 1: Conceptual Overview

Hybrid Search in RAGFlow merges exact keyword full-text search (BM25) with semantic dense vector search (KNN Cosine Similarity). This hybrid approach guarantees high precision for rare domain terminology, codes, and exact names, while maintaining semantic recall for conceptual queries.

---

## Level 2: Implementation Details

### Hybrid Score Fusion Equation

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L434-L460):

$$S_{\text{hybrid}} = w_{\text{term}} \cdot S_{\text{term}} + w_{\text{vector}} \cdot S_{\text{vector}} + S_{\text{rank\_feature}}$$

Where:
- $w_{\text{vector}} = \text{vector\_similarity\_weight}$ (configured per query or dialog, e.g. 0.3)
- $w_{\text{term}} = 1 - w_{\text{vector}}$ (e.g. 0.7)
- $S_{\text{term}}$: Normalized token match score computed by `qryr.token_similarity()`
- $S_{\text{vector}}$: Cosine similarity between query vector and chunk vector
- $S_{\text{rank\_feature}}$: Tag feature score + PageRank weight computed by `_rank_feature_scores()`

---

### Mathematical Formulas

#### 1. BM25 Term Weighting Formula
Given document chunk $D$ and query $Q$ with terms $q_1, q_2, \dots, q_n$:

$$\text{Score}_{\text{BM25}}(D, Q) = \sum_{i=1}^{n} \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

$$\text{IDF}(q_i) = \ln\left( \frac{N - n(q_i) + 0.5}{n(q_i) + 0.5} + 1 \right)$$

Where $k_1 = 1.2$, $b = 0.75$, $|D|$ is chunk length, and $\text{avgdl}$ is average chunk length.

#### 2. Reciprocal Rank Fusion (RRF) Formula
When merging rank lists from distinct retrieval engines $M$ (e.g. vector rank and BM25 rank):

$$\text{RRF\_Score}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$

Where $k = 60$ is the smoothing constant, and $r_m(d)$ is the 1-based rank position of document chunk $d$ in result set $m$.

#### 3. Field Boost Weights in Fulltext Querying
Defined in [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L32-L40):
```python
self.query_fields = [
    "title_tks^10",
    "title_sm_tks^5",
    "important_kwd^30",
    "important_tks^20",
    "question_tks^20",
    "content_ltks^2",
    "content_sm_ltks",
]
```
- Keywords (`important_kwd`): 30x multiplier
- Questions (`question_tks`): 20x multiplier
- Section Titles (`title_tks`): 10x multiplier
- Chunk Content (`content_ltks`): 2x multiplier
