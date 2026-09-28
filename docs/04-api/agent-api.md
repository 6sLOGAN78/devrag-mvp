# agent_api.py Endpoints

Source: `api/apps/restful_apis/agent_api.py`

## Route: `/agents/<agent_id>/sessions`
- **Methods:** GET
- **Handler Function:** `list_agent_sessions()`

- **Calls Services:**
  - `API4ConversationService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/sessions`
- **Methods:** POST
- **Handler Function:** `get_agent_session()`

- **Calls Services:**
  - `API4ConversationService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/sessions/<session_id>`
- **Methods:** DELETE
- **Handler Function:** `delete_agent_session_item()`

- **Calls Services:**
  - `API4ConversationService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/sessions`
- **Methods:** DELETE
- **Handler Function:** `list_agent_template()`

- **Calls Services:**
  - `CanvasTemplateService`
  - `TenantService`
  - `UserCanvasService`

---

## Route: `/agents/prompts`
- **Methods:** GET
- **Handler Function:** `prompts()`

- **Calls Services:**
  - `TenantService`
  - `UserCanvasService`

---

## Route: `/agents`
- **Methods:** GET
- **Handler Function:** `list_agents()`

- **Calls Services:**
  - `TenantService`
  - `UserCanvasService`

---

## Route: `/agents/tags`
- **Methods:** GET
- **Handler Function:** `list_agent_tags()`

- **Calls Services:**
  - `TenantService`
  - `UserCanvasService`

---

## Route: `/agents/<canvas_id>/tags`
- **Methods:** PUT
- **Handler Function:** `get_agent_component_input_form()`

- **Calls Services:**
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/components/<component_id>/debug`
- **Methods:** POST
- **Handler Function:** `get_agent()`

- **Calls Services:**
  - `KnowledgebaseService`
  - `CanvasReplicaService`
  - `UserCanvasVersionService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/versions`
- **Methods:** GET
- **Handler Function:** `list_agent_versions()`

- **Calls Services:**
  - `UserCanvasVersionService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/versions/<version_id>`
- **Methods:** GET
- **Handler Function:** `get_agent_version()`

- **Calls Services:**
  - `UserCanvasVersionService`
  - `CanvasReplicaService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>/logs/<message_id>`
- **Methods:** GET
- **Handler Function:** `delete_agent()`

- **Calls Services:**
  - `CanvasReplicaService`
  - `UserCanvasVersionService`
  - `UserCanvasService`

---

## Route: `/agents/<agent_id>`
- **Methods:** PUT
- **Handler Function:** `_attachment_request_metadata()`

- **Calls Services:** None directly detected.

---
