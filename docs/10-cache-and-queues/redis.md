# Redis Cache & Distributed Lock Infrastructure

## Level 1: Conceptual Overview

Redis acts as a key-value cache, stream message queue broker, distributed lock manager, and synonym dictionary cache in RAGFlow.

---

## Level 2: Implementation Details

### Connection Adapter & Distributed Lock

Implemented in [rag/utils/redis_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/redis_conn.py#L30-L150):

```python
class RedisDistributedLock:
    def __init__(self, lock_key, timeout=60):
        self.lock_key = f"lock:{lock_key}"
        self.timeout = timeout

    def acquire(self):
        # Uses Redis SET key value NX EX timeout
        return REDIS_CONN.set(self.lock_key, "locked", nx=True, ex=self.timeout)

    def release(self):
        REDIS_CONN.delete(self.lock_key)
```

### Primary Redis Key Patterns

- Task Streams: `te.1.common`, `te.0.common`
- Consumer Group Info: `SVR_CONSUMER_GROUP_NAME` (`ragflow_consumer_group`)
- Distributed Task Lock: `lock:task_{task_id}`
- GraphRAG / RAPTOR LLM Caches: `llm_cache_{hash}`
- Term Synonym Lookups: `synonym_{term}`
