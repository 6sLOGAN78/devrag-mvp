# Document Ingestion Flow: Upload to Queue

This document explains exactly how the main RAGFlow repository handles the lifecycle of a document from the moment an HTTP upload request is received, up until the background task is queued in Redis for processing.

---

## 1. The Upload Endpoint (API Routing)

**Location**: `api/apps/restful_apis/document_api.py`

When a user uploads a file, it hits the `POST /datasets/<dataset_id>/documents` endpoint. 

RAGFlow implements this using a `Quart` route protected by strict multi-tenancy middleware:
```python
@manager.route("/datasets/<dataset_id>/documents", methods=["POST"])
@login_required
@add_tenant_id_to_kwargs
async def upload_document(dataset_id, tenant_id):
    upload_type = (request.args.get("type") or "local").lower()
    
    # 1. Security Check: Verify KB ownership
    e, kb = KnowledgebaseService.get_by_id(dataset_id)
    if not check_kb_team_permission(kb, tenant_id):
        return get_error_data_result(message="no authorization")

    # 2. Redirect to Local Handler
    if upload_type == "local":
        return await _upload_local_documents(kb, tenant_id)
```

The `_upload_local_documents` function extracts the file parts from the `multipart/form-data` request and delegates the heavy lifting to `FileService.upload_document` inside an asynchronous thread pool to prevent blocking the main event loop.

---

## 2. Safe Storage & Database Registration

**Location**: `api/db/services/file_service.py`

Inside `FileService.upload_document`, RAGFlow performs physical storage and database registration.

### A. Deduplication and Hashing
Before saving, RAGFlow reads the file into memory and computes an `xxhash` to uniquely identify the content and prevent duplicate processing:
```python
blob = file.read()
new_hash = xxhash.xxh128(blob).hexdigest()
```

### B. MinIO / S3 Storage Abstraction
RAGFlow **never** saves uploaded files permanently to the local disk of the API server. Instead, it pushes the `blob` directly to the `STORAGE_IMPL` (which defaults to MinIO/S3):
```python
# 'location' is the unique filename generated, e.g., 'my_doc.pdf'
settings.STORAGE_IMPL.put(kb.id, location, blob)
```

### C. Database Registration
Once the file is safely in MinIO, a `Document` record is created in MySQL via Peewee ORM to track its state. Notice that the initial `status` is just tracked, but parsing hasn't started yet:
```python
doc = {
    "id": doc_id,
    "kb_id": kb.id,
    "parser_id": self.get_parser(filetype, filename, kb.parser_id),
    "created_by": user_id,
    "type": filetype,
    "name": filename,
    "location": location,
    "size": len(blob),
    "content_hash": new_hash,
}
DocumentService.insert(doc)
```

---

## 3. Triggering the Parse Action

**Location**: `api/apps/restful_apis/document_api.py`

A critical architectural design in RAGFlow is that **uploading a file does not immediately start the ingestion process**. 

To begin processing, the frontend makes a secondary call to `POST /datasets/<dataset_id>/documents/parse` passing an array of `document_ids`.

```python
@manager.route("/datasets/<dataset_id>/documents/parse", methods=["POST"])
async def parse_documents(tenant_id, dataset_id):
    # Extracts document_ids from the request
    # ...
    
    # Iterates over each document and triggers the run command
    for doc_id in valid_doc_ids:
        e, doc = DocumentService.get_by_id(doc_id)
        
        # Updates the DB state to RUNNING
        info = {"run": str(TaskStatus.RUNNING.value), "progress": 0}
        DocumentService.update_by_id(doc_id, info)
        
        # Triggers the task distribution
        DocumentService.run(tenant_id, doc.to_dict(), kb_table_num_map)
```

---

## 4. Workload Splitting & Redis Delegation

**Location**: `api/db/services/task_service.py` (`queue_tasks`)

This is the core of the ingestion engine. When `DocumentService.run` is called, it triggers `queue_tasks`. 

Since parsing a 500-page PDF in one go would crash a worker, RAGFlow pulls the file from MinIO, calculates its length, and splits the work into bite-sized tasks.

### A. Task Chunking
```python
if doc["type"] == FileType.PDF.value:
    # 1. Pull from MinIO
    file_bin = settings.STORAGE_IMPL.get(bucket, name)
    # 2. Count total pages
    pages = PdfParser.total_page_number(doc["name"], file_bin)
    
    # 3. Create a task for every 12 pages
    page_size = doc["parser_config"].get("task_page_size") or 12
    for p in range(0, pages, page_size):
        task = {
            "id": get_uuid(),
            "doc_id": doc["id"],
            "from_page": p,
            "to_page": min(p + page_size, pages),
            "progress": 0.0
        }
        parse_task_array.append(task)
```

### B. Task Hashing (Reuse Optimization)
Every task generates a `digest` hash based on its `parser_config` and page ranges. If a user re-runs parsing, tasks that haven't changed configuration will be skipped (saving immense compute time).

### C. Redis Queueing
Finally, the tasks are saved to MySQL and immediately pushed to **Redis Streams**.

```python
# 1. Save all sub-tasks to the Database
bulk_insert_into_db(Task, parse_task_array, True)

# 2. Push unfinished tasks to the Redis Queue
for unfinished_task in unfinished_task_array:
    REDIS_CONN.queue_product(
        queue_name=settings.get_svr_queue_name(priority, suffix), 
        message=unfinished_task
    )
```

At this point, the API server returns `200 OK`. The actual OCR, Layout Analysis, and embedding generation will be picked up asynchronously by the background `task_executor.py` workers listening to that Redis queue.
