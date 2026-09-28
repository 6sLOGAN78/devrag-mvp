# search_api.py Endpoints

Source: `api/apps/restful_apis/search_api.py`

## Route: `/searches`
- **Methods:** POST
- **Handler Function:** `list_searches()`

- **Calls Services:**
  - `UserTenantService`
  - `SearchService`

---

## Route: `/searches/<search_id>`
- **Methods:** GET
- **Handler Function:** `detail()`

- **Calls Services:**
  - `UserTenantService`
  - `SearchService`
  - `TenantService`

---

## Route: `/searches/<search_id>`
- **Methods:** PUT
- **Handler Function:** `delete_search()`

- **Calls Services:**
  - `KnowledgebaseService`
  - `SearchService`

---
