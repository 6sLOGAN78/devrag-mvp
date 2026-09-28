# Retrieval Metadata Filters

## Level 1: Conceptual Overview

Metadata Filters restrict candidate retrieval scope using pre-search Boolean filtering conditions, ensuring chunks match dataset boundaries, document IDs, active availability flags, or metadata tag conditions.

---

## Level 2: Implementation Details

### Filter Construction Logic

Implemented in `Dealer.get_filters()` in [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L121-L133):

```python
def get_filters(self, req):
    condition = dict()
    for key, field in {"kb_ids": "kb_id", "doc_ids": "doc_id"}.items():
        if key in req and req[key] is not None:
            condition[field] = req[key]
    for key in ["id", "knowledge_graph_kwd", "available_int", "entity_kwd", "from_entity_kwd", "to_entity_kwd", "removed_kwd"]:
        if key in req and req[key] is not None:
            condition[key] = req[key]
    if isinstance(req.get("must_not"), dict):
        condition["must_not"] = req["must_not"]
    return condition
```

### Go Metadata Filter Translator
Go implementation in [internal/engine/elasticsearch/meta_filter.go](file:///home/logan78/Desktop/ragflow/internal/engine/elasticsearch/meta_filter.go#L25) and [internal/engine/infinity/meta_filter.go](file:///home/logan78/Desktop/ragflow/internal/engine/infinity/meta_filter.go#L25).
Translates dictionary key-values into Elasticsearch `bool.must` and `bool.must_not` clauses or Infinity SQL `WHERE` expressions.
