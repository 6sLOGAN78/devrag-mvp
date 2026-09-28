# Streaming Token Protocol (SSE)

## Level 1: Conceptual Overview

The **Streaming Engine** delivers real-time token outputs from the LLM provider to front-end clients via HTTP Server-Sent Events (SSE). This reduces perceived latency (Time-To-First-Token) and provides smooth user experience during document answer synthesis.

---

## Level 2: Implementation Details

### Source File Map
- **Quart SSE Controller**: [chat_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/chat_api.py#L60-L90)
- **Go Gin SSE Controller**: [openai_chat.go](file:///home/logan78/Desktop/ragflow/internal/handler/openai_chat.go#L1)

---

### Wire Format & Frame Envelope

Each frame sent over the SSE connection is formatted with `data: <JSON>\n\n`.

#### 1. Intermediate Token Chunk Frame
```json
data: {
  "code": 0,
  "message": "",
  "data": {
    "answer": "The quarterly project deliverables ",
    "reference": null,
    "session_id": "conv_998811"
  }
}
```

#### 2. Final Answer & Reference Attribution Frame
When generation completes, the final frame includes source document chunk references:
```json
data: {
  "code": 0,
  "message": "",
  "data": {
    "answer": "The quarterly project deliverables ##0$$ include software specifications.",
    "reference": {
      "chunks": [
        {
          "id": "c100",
          "doc_name": "Specs.pdf",
          "doc_id": "d10",
          "content": "Software specifications outline system design..."
        }
      ]
    },
    "session_id": "conv_998811"
  }
}
```

#### 3. SSE Stream Termination Frame
```
data: [DONE]
```
