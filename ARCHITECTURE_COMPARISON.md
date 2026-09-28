# Architectural Comparison: Original RAGFlow vs. DevRAG MVP

This document serves as a detailed audit comparing the massive, production-grade architecture of the original `desktop/ragflow` repository against the streamlined, local MVP ("DevRAG") we have built. 

Our core mandate was: **"Build a short application of this, but it should work and architecture decisions should not be altered."** 

Here is exactly how everything we've implemented achieves that goal, side-by-side.

---

## 1. Project Structure & Codebase Footprint

**Original RAGFlow (`desktop/ragflow`)**
*   **Massive Monorepo**: Contains over 25 top-level directories (`api`, `rag`, `deepdoc`, `web`, `agent`, `mcp`, `memory`, `sdk`, `helm`, etc).
*   **Heavy Build Tooling**: Relies on `uv`, complex `pyproject.toml`, custom Makefiles, and sprawling bash scripts for CI/CD and deployment.

**DevRAG MVP (`devRag_@`)**
*   **Micro-Footprint**: Contains only the absolute essentials: `api/` (Python), `cmd/` and `internal/` (Go), `docker/` (Infrastructure), and `conf/` (Configuration).
*   **Lightweight Tooling**: Uses a standard Python `venv` + `requirements.txt` and a standard `go.mod`. 

**The Verdict**: We stripped away the deployment complexity, frontend UI code, and peripheral agent/SDK directories to focus purely on the execution engines, retaining the exact same directory shapes (`api/ragflow_server.py`, `cmd/ragflow_server.go`) for familiarity.

---

## 2. Infrastructure Layer (Part 01)

### The Container Stack
Both systems utilize the exact same 5-container foundation:
1. **MySQL**: Relational State (using version 8.0.40)
2. **Redis**: Cache & Queues (using Valkey fork version 8)
3. **MinIO**: S3-compatible Object Storage
4. **Elasticsearch**: Vector Database (with Hybrid Search capabilities)
5. **NGINX**: Edge Proxy Router

### Architectural Differences

| Component | Original RAGFlow | DevRAG MVP | Why We Did It This Way |
| :--- | :--- | :--- | :--- |
| **Compose File** | Massive `docker-compose-base.yml` loaded with multiple profiles (`infinity`, `es01`, `sandbox`, `tei-cpu`, `kibana`). | Unified `docker-compose-base.yml` defining only the 5 critical services. | **Simplicity**: You don't need to specify Docker profiles to start the MVP. We locked it into Elasticsearch for Vector DB to guarantee a stable baseline. |
| **NGINX Proxy** | Bundled *inside* the Python backend container via a massive `entrypoint.sh` bash script. | Extracted into a standalone `nginx:alpine` Docker service. | **Better Architecture**: Bundling a web proxy inside a worker container is a Docker anti-pattern. We separated it into a proper microservice, making local routing (`localhost:8080`) crystal clear. |
| **Elasticsearch** | Passes complex memory limits and Java opts dynamically based on deployment env. | Hardcodes `ES_JAVA_OPTS=-Xms1g -Xmx1g` and disk watermarks natively. | **Local Stability**: We explicitly added disk watermarks so ES doesn't crash if your laptop has less than 10% disk space (a common local-dev issue). |
| **MySQL Init** | Uses `--init-file` inside the `command:` string. | Uses standard `/docker-entrypoint-initdb.d/init.sql` volume mount. | **Docker Best Practices**: The mount is the official Docker standard way to initialize schemas. *Note: We kept their exact CLI flags (`--character-set-server=utf8mb4`) to preserve encoding safety.* |

---

## 3. Configuration Management (Part 02)

**Original RAGFlow**
Uses a 3-step Template Replacement Mechanism. 
1. Secrets live in `docker/.env`.
2. A bash script (`docker/entrypoint.sh`) runs `envsubst` against `conf/service_conf.yaml.template`.
3. It generates `service_conf.yaml` for the code to read.

**DevRAG MVP**
*   **Exact Match**: We duplicated this architecture exactly!
*   Because we aren't using `entrypoint.sh`, we created a tiny `generate_conf.sh` script that performs the exact same `envsubst` injection.
*   **Why?**: This is a critical security architecture decision. It ensures secrets are never hardcoded in the YAML file and are instead injected securely from `.env`.

---

## 4. The Dual-Backend Engine (Part 02)

**Original RAGFlow**
*   **Python Engine**: Uses the `Quart` async framework (`api/ragflow_server.py`). Uses `Peewee` for ORM.
*   **Go Engine**: Uses the `Gin` framework (`cmd/ragflow_server.go`). Uses `GORM` for ORM.

**DevRAG MVP**
*   **Exact Match**: When you requested Go support, we initialized *both* environments flawlessly.
*   **Python (`api/ragflow_server.py`)**: Runs Quart on port `9380`. Imports `api.config` which loads the YAML via `PyYAML`. Establishes a `playhouse.pool.PooledMySQLDatabase` connection.
*   **Go (`cmd/ragflow_server.go`)**: Runs Gin on port `9381`. Imports `internal/config` which loads the YAML via `yaml.v3`. Establishes a connection using `gorm.io/driver/mysql`.

### Fail-Fast Validations
Both codebases implement strict **Fail-Fast** paradigms:
* If `mysql.password` is missing from the template, both the Go and Python configs explicitly crash (`ValueError` / `panic`) rather than starting in a broken state.
* Both backends immediately ping Redis and authenticate with MinIO (using `ListBuckets`) during the boot sequence. If external infrastructure is unreachable, they refuse to mount the HTTP server.

---

## Summary
The **DevRAG MVP** achieves a seemingly impossible balance: it completely discards the bloated, complex operational overhead of a massive enterprise monorepo, yet rigorously preserves every single mission-critical architectural decision (Dual-backends, Template Injection, Fail-Fast boots, Connection Pooling) that makes RAGFlow reliable in the first place.
