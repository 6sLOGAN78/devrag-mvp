# connector_api.py Endpoints

Source: `api/apps/restful_apis/connector_api.py`

## Route: `/connectors/<connector_id>`
- **Methods:** PATCH
- **Handler Function:** `list_connector()`

- **Calls Services:**
  - `SyncLogsService`
  - `ConnectorService`

---

## Route: `/connectors/<connector_id>`
- **Methods:** GET
- **Handler Function:** `get_connector()`

- **Calls Services:**
  - `SyncLogsService`
  - `ConnectorService`

---

## Route: `/connectors/<connector_id>/logs`
- **Methods:** GET
- **Handler Function:** `list_logs()`

- **Calls Services:**
  - `SyncLogsService`
  - `ConnectorService`

---

## Route: `/connectors/<connector_id>/rebuild`
- **Methods:** POST
- **Handler Function:** `rm_connector()`

- **Calls Services:**
  - `ConnectorService`

---

## Route: `/connectors/<connector_id>/test`
- **Methods:** POST
- **Handler Function:** `_web_state_cache_key()`

- **Calls Services:** None directly detected.

---
