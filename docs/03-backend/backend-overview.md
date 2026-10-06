# Backend Architecture Overview

## Level 1: Conceptual Overview & Dual-Stack Architecture

RAGFlow employs a modern, production-grade **dual-stack backend architecture**:

1. **Go Backend Server (Gin Framework)** ([`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)):
   Designed for high concurrency, memory efficiency, and rapid network I/O. Hosts user authentication handlers, tenant management APIs, task ingestion pipelines, background syncers, admin endpoints, and Model Context Protocol (MCP) server integration.
2. **Python Backend Server (Quart ASGI Framework)** ([`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)):
   Designed for machine learning, natural language processing, complex agent workflow execution, computer vision document parsing (DeepDoc), and legacy REST API endpoints. Uses async Quart ASGI with Peewee ORM.

```
+-----------------------------------------------------------------------------------+
| RAGFLOW DUAL-STACK BACKEND SYSTEM                                                 |
+-----------------------------------------------------------------------------------+
                                         |
                       +-----------------+-----------------+
                       |                                   |
                       v                                   v
+------------------------------------+   +------------------------------------+
| GO ENGINE (cmd/ragflow_server.go)  |   | PYTHON ENGINE (api/ragflow_server) |
|  * Gin Web Framework               |   |  * Quart ASGI Async Framework      |
|  * GORM / Custom DAO               |   |  * Peewee ORM DB Models            |
|  * High-Throughput Routing         |   |  * Agent Workflow Engine (agent/)  |
|  * Ingestion Syncer (syncer/)      |   |  * DeepDoc Vision Engine (deepdoc/)|
|  * MCP Server Middleware           |   |  * Vector Store Engine (rag/)      |
+------------------------------------+   +------------------------------------+
                       |                                   |
                       +-----------------+-----------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| PERSISTENCE & INFRASTRUCTURE LAYER                                                |
| MySQL / OceanBase DB | Redis Distributed Cache & Lock | MinIO S3 | Vector DBs      |
+-----------------------------------------------------------------------------------+
```

---

## Level 2: Component & File Reference Matrix

| Architectural Layer | Python Implementation | Go Implementation | Responsibilities |
| :--- | :--- | :--- | :--- |
| **Entry Point** | [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90) | [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81) | Initialization, CLI flag parsing, DB setup, thread dispatch. |
| **Routing Layer** | [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61) | [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141) | Request matching, URL parameters, CORS, header injection. |
| **Auth Middleware**| `login_required` ([`api/apps/__init__.py:L144`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L144)) | `AuthMiddleware()` ([`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go)) | Token decoding, session lookup, permission validation. |
| **Service Layer** | [`api/db/services/`](file:///home/logan78/Desktop/ragflow/api/db/services) | [`internal/service/`](file:///home/logan78/Desktop/ragflow/internal/service) | Domain logic, dataset management, document chunking. |
| **DAO / Models** | [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py) | [`internal/dao/`](file:///home/logan78/Desktop/ragflow/internal/dao) | Relational SQL schema, queries, migrations. |
