# 05-Chat-Interface

## 1. Objective
To build the conversational interface where users can ask questions against a selected Knowledge Base and receive streaming, cited answers from the LLM. This completes the end-to-end devRAG user experience.

## 2. Documentation Basis
*   `ragflow-docs/12-chat/ui-integration.md`: DOCUMENTED - The frontend must consume Server-Sent Events (SSE).
*   `ragflow-docs/05-rag-pipeline/prompt-engineering.md`: DOCUMENTED - The UI must parse `##0$$` markers into clickable citations.

## 3. Prerequisites
*   `01-Frontend-Core` (App Shell).
*   Backend Part 07 (SSE Chat API must be fully functional).

## 4. Components to Implement
*   **Chat Page**: Route `/chat`.
*   **Message List**: Renders the conversation.
*   **Chat Input**: Text area for user queries.
*   **Markdown Renderer**: Parses the stream.

---

## Page: Chat Interface

### 1. Page Purpose
The primary interactive query interface for the RAG system.

### 2. Route
`/chat`

### 3. Access Requirements
*   Valid JWT. Renders inside `AppShell`.

### 4. Page Layout
*   **Sidebar Extension (Optional)**: A list of chat sessions (History).
*   **Main Region**: A flex column. 
    *   Top: A dropdown to select which Knowledge Base to chat with.
    *   Middle: The scrollable message history.
    *   Bottom: A fixed input bar.

### 5. Visual Components
*   **KBSelector**: `<select>` dropdown populated with user's KBs.
*   **MessageBubble**: Differentiates between "User" and "AI".
*   **MarkdownContent**: Parses Markdown into HTML.
*   **CitationBadge**: A superscript `[1]` that appears inline.
*   **ChatInput**: Expanding `<textarea>` with a "Send" icon.

### 6. Component Hierarchy
`PROPOSED`:
```text
ChatView
├── TopBar
│   └── KBSelector
├── MessageContainer (Scrollable)
│   ├── UserMessage
│   └── AIMessage
│       └── MarkdownRenderer
└── InputArea
    ├── TextArea
    └── SendButton
```

### 7. User Interactions
*   User selects a KB.
*   User types "Hello" and presses Enter.
*   Message is appended to UI as "User".
*   An empty "AI" message is appended.
*   SSE stream begins -> text streams into the empty "AI" message.
*   Scrollbar automatically pins to the bottom.

### 8. Frontend State
*   `selectedKb`: String (ID).
*   `messages`: Array `[{ role: 'user'|'ai', content: '...' }]`.
*   `isStreaming`: Boolean (disables input while generating).

### 9. API Contract
*   **Endpoint**: `POST /api/chat`
*   **Request**: `{"query": "...", "kb_ids": ["..."]}`
*   **Response**: `Content-Type: text/event-stream`. Data chunks: `data: {"chunk": "..."}`.

### 10. Expected UI States
*   **Ready**: Input is focused.
*   **Generating**: Input is disabled, text is animating into the AI bubble.

### 11. Responsive Behavior
*   Input area sticks to the bottom of the viewport on mobile devices (handling keyboard popups).

### 12. Accessibility
*   Textarea should support `Cmd/Ctrl + Enter` to submit if multiline.
*   Aria-live region for the streaming text is not recommended due to screen reader spam, but a "Generating answer..." status should be announced.

### 13. Verification
1.  Navigate to `/chat`.
2.  Select the KB containing the test file from Part 04.
3.  Ask a question.
4.  Verify the answer streams smoothly without flickering.
5.  Verify citations render as superscripts instead of literal `##0$$` strings.

### 14. Acceptance Criteria
*   [ ] Streaming parses SSE correctly.
*   [ ] Markdown renders code blocks and lists.
*   [ ] Citations are transformed visually.

---

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Chat Layout and State

#### What I Implement
Create `src/pages/Chat.tsx`. Implement the Flexbox layout ensuring the `MessageContainer` is `flex-1` and `overflow-y-auto`. Fetch the user's KBs on mount to populate the `KBSelector`. Create the `messages` array state.

#### What the User Sees
An empty chat window with a dropdown at the top and an input box at the bottom.

#### What the Frontend Receives
User keystrokes.

#### What the Frontend Does
Updates the local `messages` state array with the user's text when they press Send.

#### What the User Can Do
Type fake messages to themselves to test the scroll behavior.

#### What the Backend Must Provide
N/A.

#### Expected Output
A static, scrollable chat interface.

#### Verification
Add 20 mock messages to state and ensure the window scrolls correctly.

---

### Step 02: Implement SSE Consumption

#### What I Implement
Inside the form submit handler:
1. Append the User message to state.
2. Append an empty AI message to state. Set `isStreaming(true)`.
3. Use the native `fetch` API to POST to `/api/chat`.
4. Process the stream using a `ReadableStreamDefaultReader`:
   ```javascript
   const response = await fetch('/api/chat', { ... });
   const reader = response.body.getReader();
   const decoder = new TextDecoder();
   while (true) {
     const { done, value } = await reader.read();
     if (done) break;
     const chunk = decoder.decode(value);
     // parse the SSE 'data: {...}' format
     // append the parsed text to the last message in state
   }
   ```

#### What the User Sees
After sending a message, characters begin appearing one by one in the AI's chat bubble in real-time.

#### What the Frontend Receives
A raw HTTP socket stream.

#### What the Frontend Does
Decodes binary chunks into strings, strips the `data: ` prefix, parses the JSON, extracts the token, and appends it to the React state.

#### What the User Can Do
Read the answer as it is generated, identical to the ChatGPT experience.

#### What the Backend Must Provide
`POST /api/chat` (Part 07) returning `text/event-stream`.

#### Expected Output
A fully functional streaming pipeline.

#### Verification
Ensure the backend is running. Ask a question. Confirm text streams without buffering in large chunks.

---

### Step 03: Implement Markdown and Citations

#### What I Implement
Install `react-markdown`. Wrap the AI message content in this component.
Write a regex replacement function that runs *before* passing the text to `react-markdown`.
Regex: `/##(\d+)\$\$/g`
Replacement: `<sup>[$1]</sup>` (or a custom React component if you want click handlers).

#### What the User Sees
The raw streaming text is instantly formatted. Bolding applies, code blocks get syntax highlighting, and ugly `##0$$` markers turn into neat superscript `[0]` citations.

#### What the Frontend Receives
The same raw text string from state.

#### What the Frontend Does
Re-evaluates the Regex and Markdown parsing on every single React render loop as new tokens arrive.

#### What the User Can Do
Read beautifully formatted text.

#### What the Backend Must Provide
Backend Prompt Assembly (Part 07.01) must ensure the LLM outputs the exact `##0$$` format.

#### Expected Output
A polished, production-ready interface.

#### Verification
Ask the LLM a question that forces a citation based on your uploaded document. Verify the UI renders it nicely.
