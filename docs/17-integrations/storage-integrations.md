# Object Storage Integrations

## Level 1: Conceptual Overview

**Object Storage** manages raw document file persistence, extracted images, OCR parsed page renders, generated report documents (.docx/.pdf), and audio files across S3-compatible storage endpoints (MinIO, AWS S3, Alibaba Cloud OSS, Azure Blob Storage).

---

## Level 2: Implementation Details

### Source File Map
- **File Service**: [api/db/services/file_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/file_service.py#L1)
- **MinIO Storage Client**: [rag/utils/minio_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/minio_conn.py)

---

### File Persistence & Storage Architecture

1. **Bucket Hierarchy**: Documents are stored under tenant-segregated bucket structures (`ragflow-{tenant_id}`).
2. **Pre-signed Access Links**: Temporary download URLs are generated with short-lived expiration tokens (`expires_in=3600s`).
3. **File Chunk Previews**: Extracted document image pages and audio TTS cache files are stored directly in object storage buckets for web rendering.
