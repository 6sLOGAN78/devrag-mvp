# Subpart 02: Task Workers

## 1. Objective
To build the background worker process that consumes ingestion tasks from Redis, manages the Document's state machine (`UNSTART` -> `RUNNING` -> `DONE`/`FAILED`), and orchestrates the processing logic.

---

## 2. RAGFlow Architecture Breakdown

In the main RAGFlow repository, this subpart is **highly decoupled**. It does not use a single monolithic worker to both execute the task and update the parent document state. 

Instead, it splits the logic into three distinct systems:

1. **The Task Executor Daemon** (`rag/svr/task_executor.py`)
2. **The Distributed Heartbeat Manager** (Redis ZSETs)
3. **The State Aggregator Thread** (`api/ragflow_server.py`)

Here is exactly how these three components work together to fulfill the objective.

### Step 01: The Worker Loop (Task Executor)
**Location**: `rag/svr/task_executor.py`

RAGFlow runs a completely separate Python entrypoint (`task_executor.py`) configured via Docker. 
*   **The Loop**: It spins up an infinite `async` loop (`while True`) that calls `REDIS_CONN.queue_consumer()` (a wrapper around Redis `XREADGROUP` / Streams) to pop tasks off the queue.
*   **Execution**: When a task is popped, it extracts the `task_type` and routes it to `do_handle_task()`.
*   **Isolation**: The worker wraps the entire parsing logic in a `try...except` block. If parsing succeeds, it updates the `Task` to `1` (100%). If it throws an exception, it catches it and updates the `Task` to `-1` (Failed) with the stack trace.

```python
# Pseudo-code of RAGFlow's handle_task
try:
    await do_handle_task(task)  # Performs OCR, NLP chunking, etc.
    set_progress(task_id, prog=1.0)
except Exception as e:
    set_progress(task_id, prog=-1, msg=f"[Exception]: {str(e)}")
finally:
    redis_msg.ack() # Acknowledge completion to Redis Stream
```

### Step 02: Distributed Heartbeat Manager
**Location**: `rag/svr/task_executor.py` (`report_status`)

Because parsing PDFs is CPU intensive and prone to OOM (Out of Memory) crashes, RAGFlow assumes workers might die silently.
*   Alongside the main loop, the executor runs a concurrent `report_status()` thread.
*   Every 30 seconds, it pushes a JSON heartbeat (containing its `pid`, `ip_address`, and current `pending` tasks) to a Redis Sorted Set (`TASKEXE`).
*   This allows the system to detect zombies and re-queue tasks if a worker crashes midway.

### Step 03: The State Manager (Progress Aggregator)
**Location**: `api/ragflow_server.py` -> `DocumentService.update_progress()`

**Crucial Design Choice**: The worker *does not* update the parent `Document` state machine to `DONE`. If you have a 100-page PDF split into 10 tasks, having 10 concurrent workers trying to update the same Document row to `DONE` causes race conditions.

Instead, RAGFlow uses an asynchronous aggregation strategy:
1.  When the API server starts (`ragflow_server.py`), it spins up a background thread that loops every 6 seconds.
2.  The thread acquires a Redis Distributed Lock (`redis_lock.acquire()`) so that if you run 5 API servers, only 1 performs the aggregation.
3.  It fetches all `Document`s in the MySQL database where `status == RUNNING`.
4.  For each Document, it queries all child `Task`s. It calculates the average progress: `progress_percentage = sum(task.progress) / len(tasks)`.
5.  If `progress_percentage == 1.0`, it transitions the `Document` state to `DONE`. If any task failed, it transitions to `FAILED`.

```python
# Inside api/ragflow_server.py
def update_progress():
    redis_lock = RedisDistributedLock("update_progress", timeout=60)
    while True:
        if redis_lock.acquire():
            # Scans unfinished docs and computes average child task progress
            DocumentService.update_progress()
            redis_lock.release()
        time.sleep(6)
```

## 3. How to Implement this in devRag_@
To build this in your MVP without over-engineering:

1.  **Create `worker.py`**: Write a simple script that connects to MySQL and Redis.
2.  **The Consumer Loop**: Use `redis_client.brpop('task_queue')` inside a `while True` loop.
3.  **Atomic State Management**: Since you aren't splitting a single file into dozens of sub-tasks yet, you *can* safely have your worker update the `Document` state directly. 
    *   *Start*: `UPDATE document SET status = 'RUNNING' WHERE id = ?`
    *   *End*: `UPDATE document SET status = 'DONE' WHERE id = ?`
4.  **Try/Catch**: Wrap your placeholder parsing logic so any failure executes `UPDATE document SET status = 'FAILED'`. 

Once your MVP scales to support splitting a single document across multiple workers, you should pivot to RAGFlow's aggregation thread pattern.
