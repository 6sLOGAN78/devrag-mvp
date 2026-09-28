# Database Transactions & Concurrency

## Level 1: Conceptual Overview

Database transactions guarantee ACID properties across multi-step mutations (e.g. creating a document row, generating task rows, writing file-to-document mappings).

---

## Level 2: Implementation Details

### Transaction Retry Blocks

In [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L301-L318):

```python
def begin(self):
    for attempt in range(self.max_retries + 1):
        try:
            return super().begin()
        except (OperationalError, InterfaceError) as e:
            if should_retry and attempt < self.max_retries:
                self._handle_connection_loss()
                time.sleep(self.retry_delay * (2**attempt))
            else:
                raise
```

Using `@DB.atomic()` context managers:
```python
with DB.atomic():
    doc = Document.create(...)
    Task.create(doc_id=doc.id, ...)
    File2Document.create(...)
```
