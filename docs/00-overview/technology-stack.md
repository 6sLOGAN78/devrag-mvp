# Technology Stack

## Level 1: Stack Inventory & Layering

RAGFlow integrates modern web standards, concurrent systems programming in Go, AI data processing in Python, machine learning vision models, and enterprise database technologies into a scalable topology.

```
+-----------------------------------------------------------------------------------+
| FRONTEND SPA: React 18, TypeScript, Vite/UmiJS, TailwindCSS, Zustand, React Router 7 |
+-----------------------------------------------------------------------------------+
                                         |
                                    HTTP / REST / SSE
                                         |
+-----------------------------------------------------------------------------------+
| DUAL-STACK BACKEND ENGINE                                                         |
|  * Go Engine: Go 1.22+, Gin Framework, GORM, Uber Zap, Go-Redis                 |
|  * Python Engine: Python 3.10+, Quart (ASGI), Peewee ORM, PyTorch, LiteLLM        |
+-----------------------------------------------------------------------------------+
                                         |
                                  Storage & AI Engines
                                         |
+-----------------------------------------------------------------------------------+
| INFRASTRUCTURE & VECTOR STORES                                                    |
|  * MySQL 8.0 / OceanBase (Relational Metadata & Multi-Tenant Data)                |
|  * Redis 7.0 (Session Cache, Rate Limiting, Distributed Locking)                  |
|  * MinIO / AWS S3 (Object Store for Raw Documents & Images)                       |
|  * Infinity / Elasticsearch / OpenSearch / Qdrant / Milvus / PGVector (Vector Store)|
+-----------------------------------------------------------------------------------+
```

---

## Level 2: Component Tech Stack Catalog

### 1. Frontend Web Client Stack (`web/`)

- **Framework**: React 18 + TypeScript
- **Router**: React Router 7 (`react-router`) with lazy component code-splitting ([`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L23))
- **State Management**: Zustand stores ([`web/src/hooks/`](file:///home/logan78/Desktop/ragflow/web/src/hooks))
- **Styling**: TailwindCSS + Shadcn/ui + Ant Design components
- **Canvas Visual Flow Editor**: `@xyflow/react` (React Flow v12) ([`web/src/pages/agent/canvas/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/canvas/index.tsx))
- **Markdown & Code Rendering**: `react-markdown`, `remark-gfm`, `rehype-katex`, `highlight.js`
- **Internationalization**: `i18next` + `react-i18next` ([`web/src/locales/`](file:///home/logan78/Desktop/ragflow/web/src/locales))

### 2. Go Backend Stack (`cmd/` & `internal/`)

- **Runtime**: Go (1.22+)
- **HTTP Framework**: Gin Gonic (`github.com/gin-gonic/gin`) ([`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L54))
- **Logging**: Uber Zap (`go.uber.org/zap`)
- **Database Access**: GORM & Custom DAO layer ([`internal/dao/`](file:///home/logan78/Desktop/ragflow/internal/dao))
- **Caching & Locks**: Go-Redis with distributed mutex locking

### 3. Python Backend & AI Stack (`api/`, `agent/`, `deepdoc/`, `rag/`)

- **Runtime**: Python 3.10+
- **ASGI Web Framework**: Quart (Async Flask-compatible microframework) ([`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61))
- **Schema & Validation**: `quart_schema` (OpenAPI OpenAPI v3 generation)
- **ORM**: Peewee ORM ([`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py))
- **LLM Abstraction**: LiteLLM + direct provider integrations (OpenAI, Anthropic, Ollama, DeepSeek, Qwen, HuggingFace)
- **Computer Vision / OCR**: PyTorch, OpenCV, YOLOv8, PaddleOCR ([`deepdoc/vision/`](file:///home/logan78/Desktop/ragflow/deepdoc/vision))
- **Tokenizer & NLP**: HuggingFace Transformers, NLTK, Jieba, HanLP

### 4. Persistence & Search Engines

- **MySQL / OceanBase**: Relational DB storing system users, tenants, configuration, chat dialogues, agent canvas definitions.
- **Redis**: Distributed session storage, API key caching, execution locks.
- **MinIO / AWS S3**: File object storage for raw PDFs, Word files, images, OCR output crops.
- **Vector Engines**: Pluggable support for Infinity, Elasticsearch, OpenSearch, OceanBase, Qdrant, Milvus, PostgreSQL (PGVector), and Tantivy ([`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils)).
