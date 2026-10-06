# File Storage Abstraction

## Level 1: Conceptual Overview

The File Storage abstraction encapsulates underlying cloud and local blob storage engines behind a uniform key-value interface (`get`, `put`, `rm`, `bucket_exists`). This isolates document parsing and embedding workers from specific cloud providers (MinIO, AWS S3, Google Cloud Storage, Alibaba Cloud OSS, local filesystem).

---

## Level 2: Implementation Details

### Storage Interface & Factory

Implemented in Python (`rag/utils/storage_factory.py`, `minio_conn.py`, `s3_conn.py`) and Go (`internal/storage/storage_factory.go`, `minio.go`, `s3.go`, `gcs.go`, `oss.go`).

Go Factory Dispatcher in [internal/storage/storage_factory.go](file:///home/logan78/Desktop/ragflow/internal/storage/storage_factory.go#L70-L84):

```go
func (f *Factory) initStorage(ctx context.Context) error {
	globalConfig := server.GetConfig()
	switch globalConfig.StorageEngineType() {
	case "minio":
		return f.initMinio()
	case "s3":
		return f.initS3(ctx)
	case "oss":
		return f.initOSS(ctx)
	case "gcs":
		return f.initGCS(ctx)
	default:
		return fmt.Errorf("unsupported storage type: %s", globalConfig.StorageEngineType())
	}
}
```

### Bucket & Path Structure

Files are organized in storage buckets using tenant and document UUID prefixes:
- Document Source Files: `{tenant_id}/{doc_id}`
- Extracted Visual Images: `{tenant_id}/{doc_id}/{img_id}.png`
- Cropped Table Screenshots: `{tenant_id}/{doc_id}/tables/{table_id}.png`
