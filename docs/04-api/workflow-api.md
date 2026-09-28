# Pipeline & Workflow API

## Level 1: Endpoint Specification Overview

The Pipeline & Workflow APIs provide public static metadata templates, pipeline operator definitions, and task status query capabilities.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. List Built-in Ingestion Pipelines
- **Endpoint**: `GET /api/v1/pipelines`
- **Engine**: Go Gin ([`internal/router/router.go:L170`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L170))
- **Auth Level**: Unauthenticated (Public static binary data)
- **Query Parameter**: `type=builtin`
- **Response Payload**: List of built-in parser templates shipped with the binary.

---

### 2. Get Pipeline Specification by ID
- **Endpoint**: `GET /api/v1/pipelines/:id`
- **Engine**: Go Gin (`internal/handler/pipeline.go`)
- **Auth Level**: Unauthenticated
- **Path Parameter**: `id` (e.g. `naive`, `paper`, `table`, `qa`, `laws`)

---

### 3. Task Execution Status Query
- **Endpoint**: `GET /v1/task/status/:task_id`
- **Engine**: Python Quart (`api/apps/restful_apis/task_api.py`)
- **Auth Level**: JWT / API Key

### Source File References

- Go Router Pipeline Registrations: [`internal/router/router.go:L170`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L170)
- Go Pipeline Handler: [`internal/handler/pipeline.go`](file:///home/logan78/Desktop/ragflow/internal/handler/pipeline.go)
- Python Task API Blueprint: [`api/apps/restful_apis/task_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/task_api.py)
