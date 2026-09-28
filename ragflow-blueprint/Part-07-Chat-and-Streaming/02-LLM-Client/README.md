# Subpart 02: LLM Chat Client

## 1. Objective
To integrate with an LLM provider and handle the Server-Sent Events (SSE) stream returned by the provider, converting it into a local generator/iterator.

## 2. Documentation Basis
*   `ragflow-docs/11-llm/integration.md`: INFERRED - Standard OpenAI-compatible API interaction with `stream=True`.

## 3. Prerequisites
*   LLM API key in `.env`.

## 4. Components to Implement
*   **Streaming Chat Client**: An HTTP wrapper around the provider's API.

## 5. Detailed Sequential Implementation Steps

### Step 01: Implement Streaming Generator

#### Purpose
Fetch tokens in real-time.

#### Prerequisites
LLM API Key.

#### Implementation Scope
Write `stream_chat(messages: list) -> Generator`.
Use your language's HTTP client or the official SDK (e.g., `openai` Python package).
Call the chat completion endpoint with `stream=True`.
Yield each text token as it arrives.

#### Outputs
A generator/iterator of string tokens.

#### Expected Result
You can iterate over the LLM's response before it finishes generating.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Write a quick script to test the function in the terminal: `for token in stream_chat(msg): print(token, end="")`. You should see the text appear letter by letter.

#### Proceed When
Terminal streaming works.

