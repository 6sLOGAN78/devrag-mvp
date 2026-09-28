# Storage Operational Flow

## Level 1: Conceptual Overview

The Storage Operational Flow governs blob creation, key generation, bucket verification, binary streaming, and deletion workflows across the application lifecycle.

---

## Level 2: Implementation Details

### Binary Read & Write Flow

```mermaid
sequenceDiagram
    autonumber
    participant App as Document Service / Worker
    participant Storage as Storage Engine (MinIO / S3)
    
    App->>Storage: bucket_exists(bucket_name)
    alt Bucket missing
        Storage->>Storage: create_bucket(bucket_name)
    end
    App->>Storage: put(bucket_name, key, binary_data)
    Storage-->>App: Return Object ETag / Key
    
    App->>Storage: get(bucket_name, key)
    Storage-->>App: Return Byte Stream
    
    App->>Storage: rm(bucket_name, key)
    Storage-->>App: Acknowledge Deletion
```

Key Generation Pattern:
- Source Files: `bucket: ragflow`, `key: {tenant_id}/{doc_id}`
- Image Thumbnails: `bucket: ragflow`, `key: {tenant_id}/{doc_id}/{img_id}.png`
