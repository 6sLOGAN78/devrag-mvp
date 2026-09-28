# Full-Text Search Engine

## Level 1: Conceptual Overview

Full-Text Search matches user query terms against document chunk text fields (`content_ltks`, `title_tks`, `important_kwd`, `question_tks`) using inverse document frequency (IDF) term weighting and field boosting multipliers.

---

## Level 2: Implementation Details

### Query Construction & Term Weighting

Implemented in [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L28-L92):

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

### Mathematical Formula: BM25

Given a document chunk $D$ and query $Q$ with terms $q_1, q_2, \dots, q_n$:

$$\text{Score}_{\text{BM25}}(D, Q) = \sum_{i=1}^{n} \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

$$\text{IDF}(q_i) = \ln\left( \frac{N - n(q_i) + 0.5}{n(q_i) + 0.5} + 1 \right)$$

Parameters: $k_1 = 1.2$, $b = 0.75$.
- $f(q_i, D)$: Term frequency of term $q_i$ in chunk $D$.
- $|D|$: Length of chunk $D$ in words.
- $\text{avgdl}$: Average chunk length across index.
