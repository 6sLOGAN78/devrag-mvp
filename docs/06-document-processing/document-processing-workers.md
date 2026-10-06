# Document Processing Workers Architecture

## Level 1: Conceptual Overview

Document Processing Workers are asynchronous background execution units that poll Redis queues, deserialize document task messages, invoke DeepDoc vision models and domain chunkers, encode vector embeddings, and write results to DocStore database engines.

---

## Level 2: Implementation Details

### Worker Process Loop & Concurrency Limiters

Worker entry point: [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L220).

```mermaid
flowchart TD
    Worker[Task Executor Worker Instance] --> PollLoop[collect Loop]
    PollLoop --> Redis[Redis Queue te.1.common / te.0.common]
    Redis --> TaskMsg[Pop Task Payload]
    
    TaskMsg --> Lock[Acquire Redis Distributed Lock]
    Lock --> Limiter{Apply Rate & Task Limiters}
    
    Limiter --> TaskLimiter[task_limiter / Max Concurrent Tasks]
    Limiter --> ChunkLimiter[chunk_limiter / Token Limiters]
    Limiter --> EmbedLimiter[embed_limiter / API Concurrency]
    
    TaskLimiter & ChunkLimiter & EmbedLimiter --> Exec[Run Pipeline Task]
    Exec --> Progress[Update Task & Document DB Progress]
    Progress --> Ack[Ack Redis Stream Message]
```

### Rate & Concurrency Limiters

Imported in [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L92-L98) from `rag/svr/task_executor_limiter.py`:
- `task_limiter`: Controls maximum parallel parsing tasks per node.
- `chunk_limiter`: Throttles text chunking buffer allocations.
- `embed_limiter`: Controls max simultaneous requests to remote Embedding API endpoints.
- `minio_limiter`: Limits concurrent S3/MinIO binary download operations.
- `kg_limiter`: Throttles Knowledge Graph extraction tasks.
