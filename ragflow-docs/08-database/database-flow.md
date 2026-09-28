# Database Operational Flow

## Level 1: Conceptual Overview

The Database Operational Flow outlines transaction boundaries, thread-local connection contexts, lazy initialization, and high-concurrency connection lifecycle management across API request handlers and background worker tasks.

---

## Level 2: Implementation Details

### Connection Lifecycle Management

In [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L470-L485):

```python
@singleton
class BaseDataBase:
    def __init__(self):
        database_config = settings.DATABASE.copy()
        db_name = database_config.pop("name")
        pool_config = {"max_retries": 5, "retry_delay": 1}
        database_config.update(pool_config)
        self.database_connection = PooledDatabase[settings.DATABASE_TYPE.upper()].value(db_name, **database_config)
```

### Context Decorators & Connection Safety

All Peewee service calls wrap database operations using `@DB.connection_context()` decorator to ensure connections are acquired from the pool and cleanly released to prevent leaks:

```python
@classmethod
@DB.connection_context()
def get_by_id(cls, id):
    return cls.model.get_or_none(cls.model.id == id)
```

Worker tasks invoke `close_connection()` in [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L208) inside exception blocks to close connection handles prior to long-running vision model inference.
