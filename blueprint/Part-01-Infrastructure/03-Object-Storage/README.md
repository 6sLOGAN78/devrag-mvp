# Subpart 03: Object Storage Setup

## 1. Objective
To provision an S3-compatible object storage service (MinIO) to securely store raw user document uploads (PDFs, PPTs) and intermediate generated images.

## 2. Documentation Basis
*   `docs/09-storage/object-storage.md`: Documents the requirement for blob storage to hold raw files before processing.
*   **DOCUMENTED**: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` are used by the Storage Factory.

## 3. Prerequisites
*   Docker and Docker Compose installed.

## 4. Components to Implement
*   **MinIO Docker Service**: Addition to `docker-compose-base.yml`.
*   **Bucket Initialization**: Script to create the `ragflow-raw-documents` bucket.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the MinIO Container

#### Purpose
Start the S3-compatible server.

#### Implementation Scope
Append the following to your `docker/.env` file:
```ini
MINIO_CONSOLE_PORT=9001
MINIO_PORT=9000
MINIO_USER=rag_flow
MINIO_PASSWORD=infini_rag_flow
```

Append the following `minio` service to your `docker/docker-compose-base.yml`:
```yaml
  minio:
    image: minio/minio:RELEASE.2023-11-20T22-40-07Z
    container_name: ragflow-minio
    command: server --console-address ":9001" /data
    ports:
      - "${MINIO_PORT}:9000"
      - "${MINIO_CONSOLE_PORT}:9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
```
*(Also add `minio_data:` to the `volumes:` block).*

#### Verification
Run `docker compose up -d minio`.

---

### Step 02: Initialize Buckets

#### Purpose
Create the logical containers for file storage.

#### Implementation Scope
You can use a Python script to automatically provision the bucket. Create `init_minio.py`:

```python
from minio import Minio

client = Minio(
    "127.0.0.1:9000",
    access_key="rag_flow",
    secret_key="infini_rag_flow",
    secure=False
)

if not client.bucket_exists("ragflow-raw-documents"):
    client.make_bucket("ragflow-raw-documents")
    print("Bucket created!")
```

#### Verification
Run `python init_minio.py` and ensure it outputs "Bucket created!".
