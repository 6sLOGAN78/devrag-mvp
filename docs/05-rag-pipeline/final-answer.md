# Final Answer Post-Processing

## Level 1: Conceptual Overview

Final Answer Post-Processing evaluates LLM output, verifies factual alignment against retrieved groundings, injects clickable inline citation badges, formats markdown/LaTeX formulas, and logs audit metrics.

---

## Level 2: Implementation Details

### Citation Matching Algorithm (`insert_citations`)

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L252-L310):

1. **Sentence Splitting**: Splitting generated text by sentence boundary regex (`[；。？!！\n]`).
2. **Embedding Encoding**: Encodes candidate sentences with `embd_mdl.encode()`.
3. **Similarity Computation**: Computes cosine similarity between output sentences and retrieved chunks.
4. **Badge Insertion**: Inserts citation indices `[1]`, `[2]` when similarity exceeds threshold.

```python
ans_v, _ = embd_mdl.encode(pieces_)
# Sentence-chunk similarity scoring
```

### Response Payload Structure

```json
{
  "code": 0,
  "data": {
    "answer": "RAGFlow uses a hybrid dual-engine architecture [1].",
    "reference": {
      "chunks": [
        {
          "id": "chunk_001",
          "doc_name": "RAGFlow_Architecture.pdf",
          "content": "RAGFlow combines a Go core engine with Python processing workers...",
          "dataset_id": "kb_123",
          "page_number": 2,
          "positions": [[2, 100, 150, 400, 200]]
        }
      ]
    }
  }
}
```
