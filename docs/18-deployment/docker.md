# Docker Build & Images

## Level 1: Conceptual Explanation

RAGFlow leverages containerization to bundle Python runtime dependencies, compiled Go binaries (`ragflow_server`), native C++ libraries (DeepDoc, PDFium, OfficeOxide), and deep learning model weights. 

The image build system consists of:
- **`Dockerfile`**: Production multi-stage build image bundling the Web server, Task Executor, Go API binary, Nginx, and Python virtual environment (`uv`).
- **`Dockerfile_base`**: Base image pre-compiling native C/C++ bindings (PDFium static libraries, Rust OfficeOxide, PCRE2) and downloading core PyTorch models.
- **`Dockerfile_deepdoc_oss`**: Standalone image for the DeepDoc layout parser daemon (`deepdoc`).
- **`Dockerfile_tei`**: Container configuration for HuggingFace Text Embeddings Inference (TEI) model server.

---

## Level 2: Implementation Details

### Production `Dockerfile` Analysis

Located in [`Dockerfile`](file:///home/logan78/Desktop/ragflow/Dockerfile):

1. **Base Stage (`builder`)**: Uses Python 3.10 slim base, installs system build dependencies (`gcc`, `g++`, `cmake`, `git`, `libssl-dev`, `libpcre2-dev`).
2. **Go Binary Compilation**: Executes [`build.sh`](file:///home/logan78/Desktop/ragflow/build.sh) to produce CGO-linked binaries `bin/ragflow_server` and `bin/ragflow-cli`.
3. **Python Virtualenv Setup**: Uses `uv` package manager to build wheels and install dependencies defined in `pyproject.toml`.

### Container Entrypoint Execution (`entrypoint.sh`)

Located in [`docker/entrypoint.sh`](file:///home/logan78/Desktop/ragflow/docker/entrypoint.sh):
2. **Nginx Startup**: Starts local Nginx reverse proxy daemon (`nginx`).
4. **Python Web API Startup**: Launches Python Flask application server with Gunicorn or standard WSGI runner (`python3 api/ragflow_server.py`).

---

## Docker Image Matrix

| Image Name | Purpose / Description | Dockerfile Target | Base OS |
| :--- | :--- | :--- | :--- |
| `infiniflow/ragflow:nightly` | Main RAGFlow application image (CPU/GPU) | [`Dockerfile`](file:///home/logan78/Desktop/ragflow/Dockerfile) | Ubuntu 22.04 / Python 3.10 |
| `infiniflow/ragflow_base:latest` | Pre-built C++ native dependencies | [`Dockerfile_base`](file:///home/logan78/Desktop/ragflow/Dockerfile_base) | Ubuntu 22.04 |
| `deepdoc_oss:latest` | DeepDoc layout parsing microservice | [`Dockerfile_deepdoc_oss`](file:///home/logan78/Desktop/ragflow/Dockerfile_deepdoc_oss) | Python 3.10 slim |
| `infiniflow/tei:latest` | Local embedding & reranking model server | [`Dockerfile_tei`](file:///home/logan78/Desktop/ragflow/Dockerfile_tei) | HuggingFace TEI |
| `infiniflow/sandbox-executor-manager` | Code execution sandbox manager | `agent/sandbox/.../Dockerfile` | Alpine / Linux |

---

## References & Source Links

- [`Dockerfile:L1-L120`](file:///home/logan78/Desktop/ragflow/Dockerfile#L1-L120) - Main multi-stage Docker build file.
- [`Dockerfile_base:L1-L80`](file:///home/logan78/Desktop/ragflow/Dockerfile_base#L1-L80) - Base image definition.
- [`build.sh:L1-L200`](file:///home/logan78/Desktop/ragflow/build.sh#L1-L200) - Go binary and CGO linkage build script.
