# Object Storage Integration (MinIO / S3 / GCS / OSS)

## Level 1: Conceptual Overview

Object Storage integration provides high-scalability, durable storage for binary assets using MinIO, AWS S3, Google Cloud Storage, or Alibaba Cloud OSS.

---

## Level 2: Implementation Details

### Configuration Settings

Configured via environment variables in `common/settings.py` ([common/settings.py](file:///home/logan78/Desktop/ragflow/common/settings.py#L135)) and Go server config:
- `STORAGE_IMPL`: `MINIO`, `S3`, `GCS`, `OSS`, `LOCAL`
- `MINIO_ENDPOINT`: Host and port (e.g. `minio:9000`)
- `MINIO_ACCESS_KEY` & `MINIO_SECRET_KEY`
- `S3_REGION` & `S3_BUCKET`

### Go MinIO Storage Implementation

In [internal/storage/minio.go](file:///home/logan78/Desktop/ragflow/internal/storage/minio.go#L25):

```go
type MinioStorage struct {
	client *minio.Client
	bucket string
}

func (s *MinioStorage) Put(ctx context.Context, key string, data []byte) error {
	_, err := s.client.PutObject(ctx, s.bucket, key, bytes.NewReader(data), int64(len(data)), minio.PutObjectOptions{})
	return err
}
```
