# Integration Tests

## Level 1: Conceptual Explanation

Integration tests verify component interactions across process boundaries. They validate communication between the Go server, Python Web API, MySQL database, Redis cache, NATS message queue, vector engines (Infinity, Elasticsearch), and native C++ shared libraries.

---

## Level 2: Implementation Details

### Integration Test Scenarios & Files

#### 1. Native C++ Binding Integration Tests (CGO)
Located in [`internal/deepdoc/parser/pdf/inference_client_integration_test.go`](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/inference_client_integration_test.go#L1-L80):
- Verifies CGO interface calls into C++ PDFium static libraries (`libpdfium.a`) and Rust `liboffice_oxide.a`.
- Ensures memory is allocated safely without leaks across Go-C boundary.

#### 2. Vector Engine Integration Tests
Located in `internal/engine/`:
- [`internal/engine/infinity/client_test.go`](file:///home/logan78/Desktop/ragflow/internal/engine/infinity/client_test.go): Connects to live Infinity RPC server (`port 23817`), creates test collection, inserts embeddings, and queries nearest neighbors.
- [`internal/engine/oceanbase/client_test.go`](file:///home/logan78/Desktop/ragflow/internal/engine/oceanbase/client_test.go): Validates OceanBase vector search queries.

#### 3. Sandbox RPC Integration Tests
Located in [`internal/agent/sandbox/manager_client_test.go`](file:///home/logan78/Desktop/ragflow/internal/agent/sandbox/manager_client_test.go#L1-L80):
- Spawns RPC calls to `sandbox-executor-manager` on port 9385, verifies code container creation, execution output capture, and container termination.

---

## References & Source Links

- [`internal/deepdoc/parser/pdf/inference_client_integration_test.go:L1-L80`](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/inference_client_integration_test.go#L1-L80) - CGO integration test.
- [`internal/engine/infinity/client_test.go:L1-L80`](file:///home/logan78/Desktop/ragflow/internal/engine/infinity/client_test.go#L1-L80) - Infinity DB integration test.
- [`internal/agent/sandbox/manager_client_test.go:L1-L80`](file:///home/logan78/Desktop/ragflow/internal/agent/sandbox/manager_client_test.go#L1-L80) - Sandbox RPC integration test.
