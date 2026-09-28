# chat_channel_api.py Endpoints

Source: `api/apps/restful_apis/chat_channel_api.py`

## Route: `/chat-channels`
- **Methods:** POST
- **Handler Function:** `list_chat_channel()`

- **Calls Services:**
  - `DialogService`
  - `ChatChannelService`

---

## Route: `/chat-channels/<channel_id>`
- **Methods:** GET
- **Handler Function:** `get_chat_channel()`

- **Calls Services:**
  - `DialogService`
  - `ChatChannelService`

---

## Route: `/chat-channels/<channel_id>`
- **Methods:** PATCH
- **Handler Function:** `rm_chat_channel()`

- **Calls Services:**
  - `ChatChannelService`

---

## Route: `/chat-channels/<channel_id>/runtime`
- **Methods:** GET
- **Handler Function:** `get_chat_channel_runtime()`

- **Calls Services:**
  - `ChatChannelService`

---
