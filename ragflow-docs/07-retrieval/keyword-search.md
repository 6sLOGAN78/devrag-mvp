# Keyword & Synonym Search

## Level 1: Conceptual Overview

Keyword & Synonym Search expands raw user query strings by identifying key phrases, generating synonym alternatives, and applying fine-grained tokenization to maximize retrieval recall.

---

## Level 2: Implementation Details

### Synonym Lookup & Term Expansion

Implemented in [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L31-L75) and `rag/nlp/synonym.py`:

```python
self.syn = synonym.Dealer(redis=REDIS_CONN.REDIS if REDIS_CONN.is_alive() else None)
```

1. **Redis Cache Lookup**: Checks Redis key store for pre-compiled synonym pairs (e.g. `LLM` -> `Large Language Model`).
2. **Term Weighting**: Assigns higher boost to rare technical keywords using `term_weight.Dealer()` in [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py#L30).
3. **Infinity Escapable Sanitization**: Strips Infinity parser break characters `[\x20()^"'~*?:\\]` to prevent lexer syntax errors.
