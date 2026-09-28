# Subpart 03: Chat API

## 1. Objective
To build the HTTP endpoint that wires everything together: Receiving a POST request, calling Retrieval, building the Prompt, calling the LLM, and streaming the response back over HTTP using Server-Sent Events (SSE).

## 2. Documentation Basis
*   `ragflow-docs/12-chat/streaming.md`: DOCUMENTED - The endpoint uses SSE (`Content-Type: text/event-stream`).

## 3. Prerequisites
*   Auth Middleware (Part 03.03).
*   Retrieval Engine (Part 06.04).
*   Prompt Assembly (Part 07.01).
*   LLM Client (Part 07.02).

## 4. Components to Implement
*   **Chat Router**: `POST /api/chat`.
*   **SSE Response Formatter**: HTTP logic to flush chunks to the client.

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Chat Endpoint

#### Purpose
Wire the RAG flow.

#### Prerequisites
All previous dependencies.

#### Implementation Scope
Implement `POST /api/chat`. Protect with Auth Middleware. Accept `{ query, kb_ids }`. Extract `tenant_id`.
1. Call `retrieve_documents(query, kb_ids, tenant_id)`.
2. Call `build_prompt(query, chunks)`.
3. Call `stream_chat(messages)`.

#### Outputs
A reference to the generator.

#### Proceed When
The endpoint compiles and all dependencies are linked.

### Step 02: Implement SSE Streaming

#### Purpose
Return real-time data to the client.

#### Prerequisites
Step 01.

#### Implementation Scope
Configure the HTTP response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`.
Iterate over the generator. For each token, write `data: {"chunk": "token"}\n\n` to the response stream and force a flush to the network socket.

#### Expected Result
Clients receive data in real-time.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Execute a `curl` request to the endpoint:
`curl -N -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"query":"hello", "kb_ids":["..."]}' http://localhost:8000/api/chat`
You should see the `data: ...` lines stream into your terminal.

#### Proceed When
cURL streaming is verified.

