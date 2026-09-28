# Environment Variables Reference

## Level 1: Conceptual Explanation

Environment variables control RAGFlow container configuration, network port bindings, database credentials, resource limits, vector engine selection, and security settings. Environment variables are defined in the `.env` file mounted into Docker Compose or passed directly into container runtimes.

---

## Level 2: Implementation Details

### Environment Variable Catalog

Extracted from [`docker/docker-compose.yml`](file:///home/logan78/Desktop/ragflow/docker/docker-compose.yml), [`docker/docker-compose-base.yml`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml), and [`conf/service_conf.yaml`](file:///home/logan78/Desktop/ragflow/conf/service_conf.yaml):

| Variable Name | Default / Example | Purpose / Description | Affects Component |
| :--- | :--- | :--- | :--- |
| `RAGFLOW_IMAGE` | `infiniflow/ragflow:nightly` | Docker image tag for RAGFlow CPU/GPU container | `ragflow-cpu`, `ragflow-gpu` |
| `DEEPDOC_IMAGE` | `deepdoc_oss:latest` | Docker image tag for DeepDoc layout parser | `deepdoc` |
| `SVR_WEB_HTTP_PORT` | `80` | Host port mapped to Nginx HTTP port 80 | `ragflow-cpu` |
| `SVR_WEB_HTTPS_PORT` | `443` | Host port mapped to Nginx HTTPS port 443 | `ragflow-cpu` |
| `SVR_HTTP_PORT` | `9380` | Host port mapped to Python Web API port 9380 | `ragflow-cpu` |
| `ADMIN_SVR_HTTP_PORT` | `9381` | Host port mapped to Python Admin API port 9381 | `ragflow-cpu` |
| `SVR_MCP_PORT` | `9382` | Host port mapped to MCP Server port 9382 | `ragflow-cpu` |
| `GO_HTTP_PORT` | `9384` | Host port mapped to Go HTTP API port 9384 | `ragflow-cpu` |
| `GO_ADMIN_PORT` | `9383` | Host port mapped to Go Admin port 9383 | `ragflow-cpu` |
| `MYSQL_PASSWORD` | `infini_rag_flow` | Root password for MySQL relational database | `mysql`, `ragflow-cpu` |
| `EXPOSE_MYSQL_PORT` | `3306` | Host port mapped to MySQL 3306 | `mysql` |
| `MINIO_USER` | `rag_flow` | Root access key for MinIO object storage | `minio`, `ragflow-cpu` |
| `MINIO_PASSWORD` | `infini_rag_flow` | Root secret key for MinIO object storage | `minio`, `ragflow-cpu` |
| `MINIO_PORT` | `9000` | Host S3 API port for MinIO | `minio` |
| `MINIO_CONSOLE_PORT` | `9001` | Host Console UI port for MinIO | `minio` |
| `REDIS_PASSWORD` | `infini_rag_flow` | Authentication password for Valkey/Redis | `redis`, `ragflow-cpu` |
| `REDIS_PORT` | `6379` | Host port for Redis | `redis` |
| `NATS_PORT` | `4222` | Host client port for NATS JetStream | `nats`, `ragflow-cpu` |
| `STACK_VERSION` | `8.11.3` | Version tag for Elasticsearch/Kibana | `es01`, `kibana` |
| `ELASTIC_PASSWORD` | `infini_rag_flow` | Authentication password for Elasticsearch | `es01` |
| `ES_PORT` | `9200` | Host HTTP port for Elasticsearch | `es01` |
| `OPENSEARCH_PASSWORD` | `infini_rag_flow_OS_01` | Password for OpenSearch | `opensearch01` |
| `OS_PORT` | `9201` | Host HTTP port for OpenSearch | `opensearch01` |
| `INFINITY_THRIFT_PORT` | `23817` | RPC Thrift port for Infinity Vector DB | `infinity` |
| `INFINITY_HTTP_PORT` | `23820` | HTTP REST Admin port for Infinity | `infinity` |
| `INFINITY_PSQL_PORT` | `5432` | PostgreSQL protocol port for Infinity | `infinity` |
| `CLICKHOUSE_USER` | `ragflow` | Username for ClickHouse DB | `clickhouse` |
| `CLICKHOUSE_PASSWORD` | `infini_rag_flow` | Password for ClickHouse DB | `clickhouse` |
| `CLICKHOUSE_TCP_PORT` | `9900` | Native TCP client port for ClickHouse | `clickhouse` |
| `CLICKHOUSE_HTTP_PORT` | `8123` | HTTP REST port for ClickHouse | `clickhouse` |
| `SANDBOX_EXECUTOR_MANAGER_PORT` | `9385` | Host HTTP port for code sandbox manager | `sandbox-executor-manager` |
| `SANDBOX_EXECUTOR_MANAGER_POOL_SIZE` | `3` | Number of pre-warmed sandbox execution containers | `sandbox-executor-manager` |
| `SANDBOX_MAX_MEMORY` | `256m` | Maximum memory limit per sandbox container | `sandbox-executor-manager` |
| `SANDBOX_TIMEOUT` | `10s` | Execution timeout limit for sandbox jobs | `sandbox-executor-manager` |
| `MEM_LIMIT` | `8g` | Maximum memory ceiling per engine container | `es01`, `infinity`, etc. |

---

## References & Source Links

- [`docker/docker-compose.yml:L1-L152`](file:///home/logan78/Desktop/ragflow/docker/docker-compose.yml#L1-L152) - Environment variables in compose orchestrator.
- [`docker/docker-compose-base.yml:L1-L428`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml#L1-L428) - Environment variables in base infrastructure.
- [`conf/service_conf.yaml:L1-L191`](file:///home/logan78/Desktop/ragflow/conf/service_conf.yaml#L1-L191) - Runtime configuration mappings.
