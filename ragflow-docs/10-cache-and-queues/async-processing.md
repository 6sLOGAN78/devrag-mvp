# Asynchronous Processing Engine

## Level 1: Conceptual Overview

The Asynchronous Processing Engine uses `asyncio` event loops paired with thread-pool executors to run non-blocking network I/O alongside heavy blocking compute workloads (C++ tokenizers, ONNX vision models).

---

## Level 2: Implementation Details

### Thread Pool Offloading (`thread_pool_exec`)

Implemented in `common/misc_utils.py` and heavily used in [rag/nlp/search.py](file:///home/logan78/Desktop/ragflow/rag/nlp/search.py#L32):

```python
from common.misc_utils import thread_pool_exec

# Offloading blocking GPU/CPU embedding encoding
qv, _ = await thread_pool_exec(emb_mdl.encode_queries, txt)

# Offloading blocking DocStore database search
res = await thread_pool_exec(self.dataStore.search, src, ...)
```

This prevents blocking Python `asyncio` main loops during heavy embedding calculations or database roundtrips.
