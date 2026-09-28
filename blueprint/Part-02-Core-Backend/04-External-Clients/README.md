# Subpart 04: External Clients

## 1. Objective
To initialize singleton client objects for communicating with Redis (for caching and task queues) and MinIO (for blob storage). This officially completes the Core Backend scaffolding for both Python and Go engines.

## 2. Documentation Basis
*   `docs/09-storage/s3.md`
*   `docs/10-cache-and-queues/redis.md`
*   RAGFlow Architecture: Dual-backend deployment requires both Go and Python to securely connect to the singletons on boot.

## 3. Prerequisites
*   `Part-01-Infrastructure` (Redis and MinIO containers running).
*   `Part-02/02-Configuration-Management` (Credentials injected into configuration singletons).

## 4. Components to Implement
*   **Redis Client**: A singleton connection manager for Redis.
*   **S3/MinIO Client**: An initialized MinIO SDK client configured for local path-style addressing without SSL.

## 5. Detailed Sequential Implementation Steps

### Step 01: Configure External Clients (Python Backend)

#### Implementation Scope
1. Install dependencies: `pip install redis minio`.
2. Create `api/utils/redis_conn.py` to instantiate the Redis connection.
3. Create `api/utils/storage_client.py` to instantiate the MinIO connection.

#### Inputs
**`api/utils/redis_conn.py`**:
```python
import redis
from api.config import CONF

redis_conf = CONF['redis']
REDIS_CLIENT = redis.Redis.from_url(redis_conf['url'], decode_responses=True)

try:
    REDIS_CLIENT.ping()
    print("Redis connected successfully (Python).")
except Exception as e:
    raise RuntimeError(f"Failed to connect to Redis: {e}")
```

**`api/utils/storage_client.py`**:
```python
from minio import Minio
from api.config import CONF

minio_conf = CONF['minio']
STORAGE_CLIENT = Minio(
    minio_conf['endpoint'],
    access_key=minio_conf['user'],
    secret_key=minio_conf['password'],
    secure=False # CRITICAL for local MinIO
)

try:
    STORAGE_CLIENT.list_buckets()
    print("MinIO connected successfully and authenticated (Python).")
except Exception as e:
    raise RuntimeError(f"Failed to connect to MinIO: {e}")
```

Update `api/ragflow_server.py` to import these utilities so they execute on startup.

---

### Step 02: Configure External Clients (Go Backend)

#### Implementation Scope
1. Install dependencies: `go get github.com/redis/go-redis/v9 github.com/minio/minio-go/v7`.
2. Create `internal/engine/redis/redis.go` to instantiate the Redis pool.
3. Create `internal/engine/storage/storage.go` to instantiate the MinIO connection.

#### Inputs
**`internal/engine/redis/redis.go`**:
```go
package redis

import (
	"context"
	"devrag/internal/config"
	goredis "github.com/redis/go-redis/v9"
)

var Client *goredis.Client

func InitRedis() {
	opt, _ := goredis.ParseURL(config.CONF.Redis.URL)
	Client = goredis.NewClient(opt)
	if err := Client.Ping(context.Background()).Err(); err != nil {
		panic(err)
	}
}
```

**`internal/engine/storage/storage.go`**:
```go
package storage

import (
	"context"
	"devrag/internal/config"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

var Client *minio.Client

func InitStorage() {
	minioConf := config.CONF.Minio
	var err error
	Client, err = minio.New(minioConf.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(minioConf.User, minioConf.Password, ""),
		Secure: false,
	})
	if err != nil {
		panic(err)
	}
	_, err = Client.ListBuckets(context.Background())
	if err != nil {
		panic(err)
	}
}
```

Update `cmd/ragflow_server.go` to call `InitRedis()` and `InitStorage()` on startup.

#### Expected Result
Both backend stacks boot, authenticate natively with the infrastructure, print success logs, and then mount the HTTP server. If Redis or MinIO goes down, the servers will safely fail-fast and crash during boot.

#### Acceptance Criteria
* [ ] Verifies correctly.
Starting `python api/ragflow_server.py` and `go run cmd/ragflow_server.go` outputs successful Redis and MinIO connection logs.
