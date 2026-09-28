# Retrieval Execution Flow

## Level 1: Conceptual Overview

The Retrieval Execution Flow traces how an incoming search request is converted into structured query expressions, executed against DocStore vector and full-text indices, pruned of deleted documents, fused across candidate sets, score-thresholded, and returned as references.

---

## Level 2: Implementation Details

### Step-by-Step Code Walkthrough

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L549-L700):

```python
async def retrieval(
    self,
    question,
    embd_mdl,
    tenant_ids,
    kb_ids,
    page,
    page_size,
    similarity_threshold=0.2,
    vector_similarity_weight=0.3,
    top=1024,
    doc_ids=None,
    rerank_mdl=None,
):
```

1. **Window Size Calculation**:
   Calculates window limit via `_rerank_window(page_size, top)` to keep pagination blocks aligned.
2. **Search Request Dispatch**:
   Calls `self.search(req, idx_names, kb_ids, embd_mdl)` returning raw `SearchResult` candidates.
3. **Safety Net Chunk Pruning**:
   Executes `self._prune_deleted_chunks(sres)` to ensure stale chunks from deleted documents are removed.
4. **Reranking / Score Merging**:
   - If `rerank_mdl` is active: Calls `self.rerank_by_model()`.
   - If using Elasticsearch: Calls `self._knn_scores()` and `self.rerank_with_knn()`.
   - If using Infinity: Uses normalized direct scores.
5. **Thresholding & Stable Sorting**:
   Applies `sim_np >= post_threshold` and sorts using `np.argsort(sim_np * -1, kind="stable")`.
