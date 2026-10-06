# Volume Management & Data Persistence

## Level 1: Conceptual Explanation

Data persistence in RAGFlow is configured to prevent loss of relational state, uploaded document binaries, vector index structures, message queues, and execution logs across container restarts. Persistence uses named Docker volumes managed by standard storage drivers alongside host bind mounts for logs and configuration overrides.

---

## Level 2: Implementation Details

### Volume Declarations & Binding Table

Defined in [`docker/docker-compose-base.yml#L397-L424`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml#L397-L424) and [`docker/docker-compose.yml#L56-L63`](file:///home/logan78/Desktop/ragflow/docker/docker-compose.yml#L56-L63):

| Volume Name / Mount Source | Mount Destination Path | Managed Data Type | Driver |
| :--- | :--- | :--- | :--- |
| `mysql_data` | `/var/lib/mysql` | Relational tables, user records, metadata | `local` |
| `minio_data` | `/data` | Raw uploaded files, PDF chunks, layout images | `local` |
| `redis_data` | `/data` | Session cache, task status keys | `local` |
| `nats_data` | `/data` | NATS JetStream persistent message queues | `local` |
| `infinity_data` | `/var/infinity` | Infinity vector indices, scalar attributes | `local` |
| `esdata01` | `/usr/share/elasticsearch/data` | Elasticsearch inverse index & vector embeddings | `local` |
| `osdata01` | `/usr/share/opensearch/data` | OpenSearch index segments | `local` |
| `clickhouse_data` | `/var/lib/clickhouse` | ClickHouse analytical tables & logs | `local` |
| `serenedb_data` | `/var/lib/serenedb` | SereneDB database files | `local` |
| `./ragflow-logs` (Host bind) | `/ragflow/logs` | Gunicorn, Go server, and Python task logs | Bind Mount |
| `./service_conf.yaml.template` | `/ragflow/conf/service_conf.yaml.template` | Dynamic environment configuration template | Bind Mount |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker daemon socket for sandbox manager | Bind Mount |

---

## References & Source Links

- [`docker/docker-compose-base.yml:L397-L424`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml#L397-L424) - Named volume definitions.
- [`docker/docker-compose.yml:L56-L63`](file:///home/logan78/Desktop/ragflow/docker/docker-compose.yml#L56-L63) - Host bind mounts.
