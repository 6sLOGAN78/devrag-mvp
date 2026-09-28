# Network Topology & Communications

## Level 1: Conceptual Explanation

RAGFlow uses a single isolated Docker bridge network named `ragflow` (`driver: bridge`). All microservices communicate across this overlay network using DNS container aliases (`mysql`, `redis`, `minio`, `nats`, `infinity`, `es01`, `sandbox-executor-manager`). External access is restricted strictly to designated ingress ports exposed to the host machine.

---

## Level 2: Implementation Details

### Network Bridge Specification

Defined in [`docker/docker-compose-base.yml#L425-L428`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml#L425-L428):
```yaml
networks:
  ragflow:
    driver: bridge
```

### Internal Port Mapping Matrix

```
[ Host Interface ]
  │
  ├── 80  / 443  ──> ragflow-cpu:80 / 443 (Nginx Web UI)
  ├── 9380       ──> ragflow-cpu:9380 (Python REST API)
  ├── 9381       ──> ragflow-cpu:9381 (Python Admin API)
  ├── 9382       ──> ragflow-cpu:9382 (MCP Gateway)
  ├── 9383       ──> ragflow-cpu:9383 (Go Admin Control)
  ├── 9384       ──> ragflow-cpu:9384 (Go Server API)
  │
  ├── 3306       ──> mysql:3306 (MySQL DB)
  ├── 6379       ──> redis:6379 (Valkey Cache)
  ├── 9000/9001  ──> minio:9000 / 9001 (S3 API / Console)
  ├── 4222       ──> nats:4222 (NATS JetStream)
  ├── 23817      ──> infinity:23817 (Infinity Thrift)
  ├── 9200       ──> es01:9200 (Elasticsearch)
  └── 9385       ──> sandbox-executor-manager:9385 (Code Sandbox)
```

---

## References & Source Links

- [`docker/docker-compose-base.yml:L425-L428`](file:///home/logan78/Desktop/ragflow/docker/docker-compose-base.yml#L425-L428) - Docker bridge network definition.
- [`docker/docker-compose.yml:L48-L55`](file:///home/logan78/Desktop/ragflow/docker/docker-compose.yml#L48-L55) - Application port exposures.
