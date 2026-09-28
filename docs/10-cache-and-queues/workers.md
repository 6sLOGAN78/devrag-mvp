# Background Worker Processing

## Level 1: Conceptual Overview

Background Workers are autonomous Python and Go processes executing ingestion pipelines. They manage process heartbeats, distributed locking, chunk batching, exception recovery, and Redis stream message acknowledgments (`XACK`).

---

## Level 2: Implementation Details

### Worker Initialization & Heartbeats

Implemented in [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L164-L180):

```python
TASK_TYPE = "common"
TE_IDX = "0"
WORKER_HEARTBEAT_TIMEOUT = int(os.environ.get("WORKER_HEARTBEAT_TIMEOUT", "120"))
```

Heartbeat status is updated in Redis hash keys to report active worker counts and prevent stale task assignments.

### Message Acknowledgment & Error Handling

In [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L240-L248):

```python
if not msg:
    logging.error(f"collect got empty message of {redis_msg.get_msg_id()}")
    redis_msg.ack() # Invokes XACK
```

When a task completes successfully (`progress = 1.0`), the worker sends `redis_msg.ack()` to clear the stream entry. If a worker process crashes, unacked messages are reclaimed by the next consumer via `UNACKED_ITERATOR`.
