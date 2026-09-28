# Implementation Order

This document dictates the exact implementation sequence required to recreate RAGFlow (devRAG). 

## Foundation Phase
*Builds the base system that can store data and route traffic.*
1. **`Part-01-Infrastructure`**: Sets up Docker Compose for MySQL/Postgres, Redis, MinIO, Elasticsearch/Infinity, and NGINX.
   - `01-Relational-DB`: MySQL setup.
   - `02-Redis-Cache`: Valkey/Redis setup.
   - `03-Object-Storage`: MinIO setup.
   - `04-Vector-DB`: Infinity/Elasticsearch setup.
   - `05-Nginx-Proxy`: Edge router for static files and API traffic.
2. **`Part-02-Core-Backend`**: Scaffolds the API server, env configuration, ORM, and external clients.

## Security Phase
*Ensures strict tenant isolation before user data is accepted.*
3. **`Part-03-Authentication-Tenancy`**: Implements User/Tenant database models, Login APIs, and the Multi-Tenancy Middleware.

## Knowledge Management Phase
*Creates the logical containers for data.*
4. **`Part-04-KnowledgeBase-Management`**: Implements CRUD endpoints for Knowledge Bases.

## Document Ingestion Phase
*Builds the async pipeline to extract and embed text.*
5. **`Part-05-Document-Ingestion`**:
   - `01-Upload-API`: Saves files to MinIO and pushes tasks to Redis.
   - `02-Task-Workers`: Consumes Redis tasks and manages state.
   - `03-Chunking-and-Embedding`: Splits plain text and inserts vectors into the Vector DB.

## Retrieval Phase
*Builds the core search mechanics.*
6. **`Part-06-Retrieval-Engine`**:
   - `01-Query-Processing`: Embeds the user query.
   - `02-Vector-Search`: Dense search.
   - `03-BM25-Search`: Sparse search.
   - `04-Result-Assembly`: Deduplicates and ranks results using RRF.

## Chat Phase
*Completes the core MVP backend loop.*
7. **`Part-07-Chat-and-Streaming`**:
   - `01-Prompt-Assembly`: Injects citation markers.
   - `02-LLM-Client`: Connects to OpenAI/Anthropic.
   - `03-Chat-API`: Returns Server-Sent Events (SSE) to the client.

## Frontend Phase
*Exposes the backend to the user. (Note: These subparts can be built immediately after their respective backend parts).*
8. **`Part-10-Frontend`**:
   - `01-Frontend-Core`: App shell, routing, state.
   - `02-Auth-UI`: Login/Registration screens.
   - `03-KB-Dashboard`: Knowledge Base lists and creation.
   - `04-Document-Management`: Upload interfaces and status polling.
   - `05-Chat-Interface`: Streaming SSE consumer and Markdown/Citation renderer.

## Advanced Capabilities Phase
*Upgrades the MVP to match true RAGFlow capabilities.*
9. **`Part-08-Advanced-DeepDoc`**: Introduces YOLO layout analysis and PaddleOCR to the Document Ingestion workers.
10. **`Part-09-Agent-Canvas`**: Builds a DAG execution engine to replace the hardcoded Chat flow, allowing multi-step LLM reasoning.
11. **`Part-10-Frontend/06-Agent-UI`**: The drag-and-drop workflow builder.
