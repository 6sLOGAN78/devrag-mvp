# Cross-Encoder Reranking

## Level 1: Conceptual Overview

Cross-Encoder Reranking evaluates candidate chunk relevance by feeding full query-document pairs into cross-attention transformer layers, producing a unified relevance score.

---

## Level 2: Implementation Details

### Implementation in `Dealer.rerank_by_model`

In [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L494-L519):

```python
def rerank_by_model(self, rerank_mdl, sres, query, tkweight=0.3, vtweight=0.7, cfield="content_ltks", rank_feature=None):
    _, keywords = self.qryr.question(query)
    docs = [remove_redundant_spaces(" ".join(tks)) for tks in ins_tw]
    tksim = self.qryr.token_similarity(keywords, ins_tw)
    vtsim, _ = rerank_mdl.similarity(query, docs)
    rank_fea = self._rank_feature_scores(rank_feature, sres)
    return tkweight * np.array(tksim) + vtweight * vtsim + rank_fea, tksim, vtsim
```

Supported Reranker Providers in `api/db/services/llm_service.py`:
- BGE-Reranker (Large/Base/v2)
- BCEmbedding Reranker
- Cohere Rerank v3
- Jina Reranker v2
- Voyage AI Reranker
