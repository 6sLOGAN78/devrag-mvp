# Message Persistence & Feedback Analytics

## Level 1: Conceptual Overview

**Message Handling** manages turn-by-turn message creation, document chunk attribution, user feedback (`thumb_up` / `thumb_down`), chunk-level feedback annotations, and message history updates.

---

## Level 2: Implementation Details

### Source File Map
- **Feedback Service**: [chunk_feedback_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/chunk_feedback_service.py#L1)
- **Dialog Service**: [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L1)
- **Chat REST API**: [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L400-L600)

---

### User Feedback & Annotation Schemas

#### 1. Message Turn Feedback (`thumb_up` / `thumb_down`)
Users can submit feedback ratings for assistant generated turns.
API: `POST /v1/api/conversation/feedback`
Body:
```json
{
  "conversation_id": "conv_123",
  "message_id": "msg_456",
  "thumb": "up",
  "feedback": "Helpful response"
}
```

#### 2. Chunk-Level Fine-Grained Feedback (`ChunkFeedback`)
In [chunk_feedback_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/chunk_feedback_service.py#L1):
Allows users to annotate specific retrieved chunks as accurate or inaccurate. Inaccurate chunks can be blacklisted or downweighted in future hybrid retrieval operations.
