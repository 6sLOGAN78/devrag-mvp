# Permission Matrix & Capabilities

## Level 1: Permission Management Overview

Permissions in RAGFlow dictate which operations users and API keys can execute across datasets, documents, canvas workflows, system settings, and model providers.

---

## Level 2: Role Permission Matrix

| Functional Area | Action / Endpoint | `owner` | `admin` | `normal` | Beta Token | API Token |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Datasets** | Create / Edit / Delete Dataset | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Datasets** | Upload / Chunk / Delete Document | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Datasets** | Run Retrieval Testing | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Agent Canvas** | Create / Save / Delete Flow | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Agent Canvas** | Stream Agent Completion | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Search Bots** | Ask Search Bot (`/searchbots/ask`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **MCP Server** | Handle MCP Tool Calls (`/mcp`)| ✅ | ✅ | ✅ | ✅ | ✅ |
| **Tenant Settings**| Update LLM Provider Keys | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Team Admin** | Invite Member / Change Role | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Enterprise Admin**| View System Health Metrics | ✅ | ✅ | ❌ | ❌ | ❌ |

### Source References

- User Role Definitions: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- Python REST API Permissions: [`api/apps/restful_apis/`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis)
- Go Router Auth Rules: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
