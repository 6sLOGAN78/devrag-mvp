# Hybrid Retrieval Subsystem

## Level 1: Conceptual Overview

Hybrid Retrieval combines dense vector similarity search with sparse BM25 full-text keyword retrieval, ensuring both high semantic recall and high exact term precision.

---

## Level 2: Implementation Details

### Fusion Expressions & Score Merging

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L210):

```python
fusionExpr = FusionExpr("weighted_sum", topk, {"weights": "0.001,1"})
matchExprs = [matchText, matchDense, fusionExpr]
```

### Mathematical Formulas

#### 1. Weighted Hybrid Combination Formula
$$S_{\text{hybrid}} = w_{\text{term}} \cdot S_{\text{term}} + w_{\text{vector}} \cdot S_{\text{vector}} + S_{\text{rank\_feature}}$$

Where $w_{\text{term}} + w_{\text{vector}} = 1.0$.

#### 2. Reciprocal Rank Fusion (RRF) Formula
When merging rank positions across separate search passes $M$:

$$\text{RRF\_Score}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$

Where $k = 60$ is the RRF rank constant, and $r_m(d)$ is the 1-based rank position of chunk $d$ in system $m$.
