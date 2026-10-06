# Frontend Data Flow

## Level 1: End-to-End User Interaction Flow

This document details the lifecycle of data moving through the frontend single-page application—from raw user input down through React components, Zustand state stores, Axios API wrappers, Server-Sent Events (SSE) channels, and back into rendered DOM elements.

---

## Level 2: Comprehensive Interaction Sequence Diagrams

### 1. Document Upload & Chunking Flow

```mermaid
sequenceDiagram
    participant User as User Browser
    participant UploadDialog as Upload Component (file-upload-dialog)
    participant DocHook as Document Hook (use-document-request.ts)
    participant ApiClient as Axios API Client (utils/authorization-util.ts)
    participant GoServer as Go Server (cmd/ragflow_server.go)

    User->>UploadDialog: Drag & Drop PDF File -> Select "General" Parser
    UploadDialog->>DocHook: Call uploadDocument(formData)
    DocHook->>ApiClient: POST /api/v1/documents/upload (Multipart FormData + Bearer Token)
    ApiClient->>GoServer: Process upload
    GoServer-->>ApiClient: HTTP 200 { retcode: 0, data: { doc_id: "xyz" } }
    ApiClient-->>DocHook: Return document ID
    DocHook->>GoServer: POST /api/v1/datasets/<dataset_id>/documents/parse { doc_ids: ["xyz"] }
    DocHook->>User: Update UI table badge to "RUNNING (0%)"
```

### 2. Real-Time Chat SSE Stream Flow

```mermaid
sequenceDiagram
    participant User as User Browser
    participant ChatInput as Message Input (components/message-input)
    participant ChatHook as Chat Hook (use-send-message.ts)
    participant PyServer as Python Server (api/ragflow_server.py)

    User->>ChatInput: Type question -> Press Enter
    ChatInput->>ChatHook: Call sendMessage(prompt)
    ChatHook->>PyServer: POST /api/v1/chat/completions { session_id, message, stream: true }
    
    loop SSE Token Stream
        PyServer-->>ChatHook: data: {"answer": "chunk_text", "reference": {...}}
        ChatHook->>ChatHook: Append token to assistant message string
        ChatHook->>User: Re-render Markdown Component (components/markdown-content)
    end

    PyServer-->>ChatHook: data: [DONE]
    ChatHook->>User: Finalize message state & render citations drawer
```

### Key Source References

- Document Request Hook: [`web/src/hooks/use-document-request.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-document-request.ts)
- SSE Send Message Hook: [`web/src/hooks/use-send-message.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-send-message.ts)
- Authorization Utility: [`web/src/utils/authorization-util.ts`](file:///home/logan78/Desktop/ragflow/web/src/utils/authorization-util.ts)
- Markdown Component: [`web/src/components/markdown-content/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/components/markdown-content)
