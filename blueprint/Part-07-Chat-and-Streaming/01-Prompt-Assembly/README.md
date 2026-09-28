# Subpart 01: Prompt Assembly

## 1. Objective
To concatenate the raw text chunks retrieved from the database into a single cohesive string, injecting specific citation markers so the LLM knows how to reference them.

## 2. Documentation Basis
*   `docs/05-rag-pipeline/prompt-engineering.md`: DOCUMENTED - RAGFlow uses specific markers (like `##0$$`) to teach the LLM to cite its sources.

## 3. Prerequisites
*   `Part-06` completed (Retrieval engine returns chunks).

## 4. Components to Implement
*   **Prompt Builder**: A string formatting function.

## 5. Detailed Sequential Implementation Steps

### Step 01: Inject Citations

#### Purpose
Format the context.

#### Prerequisites
Array of retrieved chunks.

#### Implementation Scope
Write `build_prompt(query: str, chunks: list) -> str`.
Iterate over the chunks. Prepend a marker to each chunk's text: `[Context {index}]: {text}` or RAGFlow's native `##{index}$$`.
Concatenate all chunks into one large `context_string`.

#### Outputs
A single string containing all context.

#### Proceed When
String concatenation logic works perfectly.

### Step 02: Construct System Prompt

#### Purpose
Instruct the LLM on behavior.

#### Prerequisites
Step 01.

#### Implementation Scope
Create a system instruction string: "You are a helpful assistant. Use the following context to answer the user's question. If the answer is not in the context, say 'I don't know'. You must cite your sources using the marker format provided."
Combine the system instruction, the `context_string`, and the user's `query` into the final LLM payload format (e.g., OpenAI's `messages` array).

#### Outputs
Array of message objects `[{"role": "system", "content": "..."}, {"role": "user", "content": query}]`.

#### Proceed When
The message array is correctly formatted.

