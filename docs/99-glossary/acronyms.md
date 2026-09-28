# RAGFlow Technical Acronyms Reference

| Acronym | Full Form | System Description |
|---|---|---|
| **API** | Application Programming Interface | REST/HTTP endpoints in `api/apps/restful_apis/` and `internal/handler/` |
| **BM25** | Best Matching 25 | Probabilistic term frequency / inverse document frequency ranking algorithm used for sparse text retrieval in [rag/nlp/query.py](file:///home/logan78/Desktop/ragflow/rag/nlp/query.py) |
| **DAG** | Directed Acyclic Graph | Execution model for Agent Canvas workflows in [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49) |
| **DSL** | Domain-Specific Language | JSON schema defining Agent Canvas nodes, edges, and parameters |
| **ES** | Elasticsearch | Distributed vector and full-text search engine in [rag/utils/es_conn.py](file:///home/logan78/Desktop/ragflow/rag/utils/es_conn.py) |
| **GMM** | Gaussian Mixture Model | Clustering algorithm used in RAPTOR tree building |
| **KB** | Knowledge Base | Dataset entity storing documents, vector index schema, and embedding settings |
| **LLM** | Large Language Model | Generative AI models wrapped via `LLMBundle` in [api/db/services/llm_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/llm_service.py) |
| **RAG** | Retrieval-Augmented Generation | Combining database retrieval with LLM generation |
| **RAPTOR** | Recursive Abstractive Processing for Tree-Organized Retrieval | Hierarchical chunk summarization algorithm in [rag/utils/raptor_utils.py](file:///home/logan78/Desktop/ragflow/rag/utils/raptor_utils.py) |
| **RBAC** | Role-Based Access Control | Permission management mapped via `user_tenant` table (`owner`, `admin`, `normal`) |
| **RRF** | Reciprocal Rank Fusion | Rank aggregation algorithm for combining sparse and dense search results |
| **SSE** | Server-Sent Events | Real-time HTTP token streaming protocol (`text/event-stream`) |
| **TTS** | Text-to-Speech | Audio synthesis service for chat responses |
| **YOLO** | You Only Look Once | Real-time object detection model used in DeepDoc layout analysis |
