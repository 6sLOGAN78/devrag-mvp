# Chat & Dialogue Assistant API

## Level 1: Endpoint Specification Overview

The Chat & Dialogue Assistant APIs provide conversational RAG endpoints supporting multi-session dialogues and Server-Sent Events (SSE) streaming token output.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. Create / Update Dialogue Configuration
- **Endpoint**: `POST /v1/api/dialog/set`
- **Engine**: Python Quart (`api/apps/restful_apis/chat_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "name": "Customer Support Assistant",
    "kb_ids": ["kb-10020304"],
    "llm_id": "deepseek-chat",
    "prompt_config": {
      "system": "You are a helpful customer support bot grounded in the provided documents.",
      "parameters": [
        {"key": "knowledge", "optional": false}
      ]
    }
  }
  ```

---

### 2. Stream Chat Completion (SSE Token Output)
- **Endpoint**: `POST /api/v1/chat/completions`
- **Engine**: Python Quart (`api/apps/restful_apis/chat_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "session_id": "sess-887766",
    "dialog_id": "dlg-112233",
    "message": "What is the Q3 net revenue?",
    "stream": true
  }
  ```
- **SSE Response Stream Format**:
  ```http
  HTTP/1.1 200 OK
  Content-Type: text/event-stream

  data: {"code": 0, "message": "", "data": {"answer": "The Q3 net revenue ", "reference": {}}}
  data: {"code": 0, "message": "", "data": {"answer": "was $45.2M.", "reference": {"chunks": [...]}}}
  data: [DONE]
  ```

---

### 3. Public Bot Completion Endpoint
- **Endpoint**: `POST /api/v1/chatbots/:dialog_id/completions`
- **Engine**: Go Gin (`cmd/ragflow_server.go:L212` & `internal/handler/bot.go`)
- **Auth Level**: Beta Token (`BetaAuthMiddleware`)

### Source File References

- Python Chat API Blueprint: [`api/apps/restful_apis/chat_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py)
- Go Bot Handler: [`internal/handler/bot.go`](file:///home/logan78/Desktop/ragflow/internal/handler/bot.go)
- Dialog Service: [`api/db/services/dialog_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py)
