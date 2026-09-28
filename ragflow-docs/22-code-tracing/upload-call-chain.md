# Upload Call Chain Tracing

## Level 1: Conceptual Overview

The document upload call chain handles multipart form parsing, file format validation, content hashing, storage persistence to MinIO or S3, and database row insertion.

---

## Level 2: Complete Code Call Chain

### Call Chain Diagram

```
[React Upload Component]
       │
       ▼ (HTTP POST /api/v1/documents/upload)
[api/apps/restful_apis/document_api.py:upload_document()] [L452]
       │
       ├─► Request Validation & Knowledge Base Fetch:
       │     └─► KnowledgebaseService.get_by_id(dataset_id) [api/db/services/knowledgebase_service.py]
       │
       ├─► Local File Upload Processor:
       │     └─► api/apps/restful_apis/document_api.py:_upload_local_documents(kb, tenant_id) [L658]
       │           │
       │           ├─► Compute xxhash Checksum on File Stream
       │           ├─► File Storage Persistence:
       │           │     └─► api/db/services/file_service.py:FileService.save_file(file_name, file_bytes, bucket)
       │           │           └─► Object Storage Write (MinIO / S3 / Local Disk)
       │           │
       │           └─► MySQL Document Record Creation:
       │                 └─► api/db/services/document_service.py:DocumentService.insert(doc_payload)
       │                       └─► Set `run` = '0' (UNSTART), `progress` = 0.0
       │
       ▼
[HTTP 200 OK JSON Result] -> [{id: "doc_123", name: "manual.pdf", size: 1048576, ...}]
```

### Go Call Chain Equivalent
```
[React Upload Component]
       │
       ▼ (HTTP POST /api/v1/datasets/:id/documents/upload)
[internal/handler/document.go:Upload()] [L75]
       │
       ├─► internal/service/document.go:DocumentService.Upload()
       ├─► internal/storage/storage.go:Storage.PutObject() -> MinIO / S3 Write
       └─► internal/dao/document.go:DocumentDAO.Create() -> MySQL `document` Insert
```

---

## Exact Source Code References

- **Python Route Decorator**: `@manager.route("/upload", methods=["POST"])` in [api/apps/restful_apis/document_api.py:L452](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/document_api.py#L452)
- **Python Upload Impl**: `_upload_local_documents()` in [api/apps/restful_apis/document_api.py:L658](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/document_api.py#L658)
- **Python File Storage Service**: `FileService.save_file()` in [api/db/services/file_service.py:L40](file:///home/logan78/Desktop/ragflow/api/db/services/file_service.py#L40)
- **Python Document Service**: `DocumentService.insert()` in [api/db/services/document_service.py:L80](file:///home/logan78/Desktop/ragflow/api/db/services/document_service.py#L80)
- **Go Document Handler**: `Upload()` in [internal/handler/document.go:L75](file:///home/logan78/Desktop/ragflow/internal/handler/document.go#L75)
