# Conversation Session Management

## Level 1: Conceptual Overview

**Conversation Management** maintains state, session titles, and message histories for multi-turn interactions. It supports both Web UI user sessions (`Conversation`) and external API consumer sessions (`API4Conversation`).

---

## Level 2: Implementation Details

### Source File References
- **Conversation Service**: [conversation_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/conversation_service.py#L1)
- **API Conversation Service**: [api_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/api_service.py#L1)
- **REST Endpoints**: [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L100-L300)

---

### Key Data Structures

#### 1. Turn Message Format
In [conversation_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/conversation_service.py#L50):

```json
[
  {
    "role": "user",
    "content": "What are the project deliverables?"
  },
  {
    "role": "assistant",
    "content": "According to the project plan ##0$$, the deliverables are...",
    "reference": [
      {
        "chunks": [{"id": "chunk_102", "content": "Deliverables include..."}],
        "doc_name": "Project_Plan.pdf",
        "doc_id": "doc_99"
      }
    ]
  }
]
```

#### 2. Answer Structuring (`structure_answer`)
In [conversation_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/conversation_service.py#L120):
`structure_answer(answer, reference)` extracts embedded citation markers (`##0$$`, `##1$$`), maps them to document chunk references, and formats clean output objects with source metadata.

---

### Session Lifecycle API Endpoints

- **Create Session**: `POST /v1/api/new_conversation`
- **List Sessions**: `GET /v1/api/conversations`
- **Get Session Details**: `GET /v1/api/conversation/{id}`
- **Delete Session**: `DELETE /v1/api/conversation/{id}`
