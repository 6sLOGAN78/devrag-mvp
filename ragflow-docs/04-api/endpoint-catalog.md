# Master API Endpoint Catalog

## Level 1: Endpoint Catalog Overview

This document presents the complete API Endpoint Catalog for RAGFlow, listing endpoints across both the **Go Gin Engine** and the **Python Quart ASGI Engine**, annotated with HTTP methods, route paths, underlying controllers/handlers, required parameters, authentication levels, and functional descriptions.

---

## Level 2: Comprehensive API Endpoint Table

### 1. System & Authentication APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Go | `systemHandler.Health` | None | None | System health status check. |
| `GET` | `/api/v1/system/ping` | Go | `systemHandler.Ping` | None | None | Basic server ping test. |
| `GET` | `/api/v1/system/config` | Go | `systemHandler.GetConfig` | None | None | Returns public system configurations. |
| `GET` | `/api/v1/system/version` | Go | `systemHandler.GetVersion` | None | None | Returns RAGFlow version string. |
| `GET` | `/api/v1/language` | Go | `systemHandler.Language` | None | None | Runtime language detection (`go` vs `python`). |
| `POST` | `/api/v1/auth/login` | Go | `userHandler.LoginByEmail` | None | JSON: `email`, `password` | Authenticate user by email & password. |
| `POST` | `/api/v1/users` | Go | `userHandler.Register` | None | JSON: `email`, `password`, `nickname` | Register a new user account. |
| `POST` | `/api/v1/auth/password/forgot/otp` | Go | `userHandler.ForgotSendOTP` | None | JSON: `email` | Send OTP for password reset. |
| `POST` | `/api/v1/auth/password/reset` | Go | `userHandler.ForgotResetPassword` | None | JSON: `email`, `otp`, `new_password` | Reset forgotten password. |
| `GET` | `/v1/user/info` | Go | `userHandler.Info` | JWT / Session | Header: `Authorization` | Retrieve current user profile & role. |
| `GET` | `/v1/user/tenant_info` | Go | `tenantHandler.TenantInfo` | JWT / Session | Header: `Authorization` | Retrieve tenant workspace details. |
| `GET` | `/v1/tenant/list` | Go | `tenantHandler.TenantList` | JWT / Session | Header: `Authorization` | List accessible tenant workspaces. |
| `POST` | `/v1/user/setting` | Go | `userHandler.Setting` | JWT / Session | JSON: `nickname`, `avatar`, `language` | Update user settings. |
| `POST` | `/v1/user/setting/password` | Go | `userHandler.ChangePassword` | JWT / Session | JSON: `old_password`, `new_password` | Change user password. |

---

### 2. Knowledge Base (Dataset) & Document APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/datasets` | Python | `dataset_api.create` | JWT / API Key | JSON: `name`, `parser_id`, `embd_id` | Create a new dataset. |
| `PUT` | `/api/v1/datasets/<dataset_id>` | Python | `dataset_api.update` | JWT / API Key | JSON: `name`, `parser_id` | Update dataset configurations. |
| `DELETE` | `/api/v1/datasets` | Python | `dataset_api.delete` | JWT / API Key | JSON: `dataset_id` | Delete a dataset and its document index. |
| `GET` | `/api/v1/datasets` | Python | `dataset_api.list_datasets` | JWT / API Key | Query: `page`, `page_size`, `keywords` | List datasets for the current tenant. |
| `POST` | `/api/v1/documents/upload` | Python / Go | `document_api.upload_info` | JWT / API Key | Multipart: `file`, `dataset_id` | Upload a document file to a dataset. |
| `POST` | `/api/v1/datasets/<dataset_id>/documents/parse` | Python | `document_api.run` | JWT / API Key | JSON: `doc_ids`, `run` | Trigger parsing & chunking execution tasks. |
| `POST` | `/api/v1/datasets/<dataset_id>/documents/batch-update-status` | Python | `document_api.change_status` | JWT / API Key | JSON: `doc_id`, `status` | Enable or disable document chunks in search. |
| `DELETE` | `/api/v1/datasets/<dataset_id>/documents` | Python | `document_api.delete` | JWT / API Key | JSON: `doc_id` | Delete document and remove vector chunks. |
| `GET` | `/api/v1/datasets/<dataset_id>/documents` | Python | `document_api.list_docs` | JWT / API Key | Query: `dataset_id`, `page`, `keywords` | List documents inside a dataset. |
| `GET` | `/api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks` | Python | `chunk_api.list_chunks` | JWT / API Key | Query: `doc_id`, `page`, `keywords` | Retrieve chunk text list and status. |
| `POST` | `/api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks` | Python | `chunk_api.create` | JWT / API Key | JSON: `doc_id`, `content_with_weight` | Create a manual chunk. |

---

### 3. Agent & Canvas Workflow APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/agents` | Python | `agent_api.create` | JWT / API Key | JSON: `title`, `description` | Create agent canvas flow graph. |
| `GET` | `/api/v1/agents/<agent_id>` | Python | `agent_api.get` | JWT / API Key | Path: `agent_id` | Get agent canvas DSL topology. |
| `POST` | `/api/v1/agents/chat/completions` | Python | `agent_api.agent_chat_completion` | JWT / API Key | JSON: `agent_id`, `message`, `stream` | Execute agent graph flow with streaming. |
| `GET` | `/api/v1/agents` | Python | `agent_api.list_agents` | JWT / API Key | Query: `page`, `keywords` | List user agents. |
| `DELETE` | `/api/v1/agents/<agent_id>` | Python | `agent_api.delete` | JWT / API Key | Path: `agent_id` | Delete an agent canvas workflow. |

---

### 4. Chat & Dialogue Playground APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/chats` | Python | `chat_api.create` | JWT / API Key | JSON: `name`, `dataset_ids`, `llm_id` | Create a chat dialogue configuration. |
| `GET` | `/api/v1/chats` | Python | `chat_api.list_chats` | JWT / API Key | Query: `page`, `keywords` | List active chat assistants. |
| `DELETE` | `/api/v1/chats/<chat_id>` | Python | `chat_api.delete_chat` | JWT / API Key | Path: `chat_id` | Remove a chat assistant. |
| `POST` | `/api/v1/chat/completions` | Python | `chat_api.session_completion` | JWT / API Key | JSON: `session_id`, `message`, `stream` | Stream RAG chat completion tokens (SSE). |
| `GET` | `/api/v1/chats/<chat_id>/sessions` | Python | `chat_api.list_sessions` | JWT / API Key | Query: `chat_id` | List sessions under a chat assistant. |

---

### 5. Search Bots & MCP Server APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/searchbots/ask` | Go | `searchBotHandler.Ask` | Beta Auth | JSON: `question`, `kb_ids` | High-performance search bot query. |
| `POST` | `/api/v1/searchbots/retrieval_test`| Go | `searchBotHandler.RetrievalTest`| Beta Auth | JSON: `question`, `kb_ids` | Retrieval accuracy testing endpoint. |
| `POST` | `/api/v1/mcp` | Go | `mcpServerHandler.HandleMCP` | Beta Auth | JSON: MCP JSON-RPC protocol body | Model Context Protocol server endpoint. |

### Core Source References

- Go Router Setup: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Restful APIs Directory: [`api/apps/restful_apis/`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis)
- Python App Registration: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
