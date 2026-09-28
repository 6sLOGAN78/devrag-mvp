# Subpart 03: Chunking & Embedding

## 1. Objective
To implement the actual data transformation: downloading the raw text, splitting it into semantic chunks, generating vector embeddings, and inserting them into the Vector DB.

## 2. Documentation Basis
*   `ragflow-docs/06-document-processing/chunking.md`: IMPLEMENTATION DECISION - Using a generic text chunker instead of 14 specialized ones for MVP.
*   `ragflow-docs/05-rag-pipeline/ingestion-pipeline.md`: DOCUMENTED - The Embedding and VDB insertion flow.

## 3. Prerequisites
*   `Part-05/02-Task-Workers` completed (Worker state machine is ready).
*   Vector DB running (Part 01.04).

## 4. Components to Implement
*   **S3 Fetcher**: Downloads the file.
*   **Text Splitter**: Chunks the string.
*   **Embedding Client**: Calls an LLM.
*   **Vector DB Client**: Inserts the chunks.

## 5. Detailed Sequential Implementation Steps

### Step 01: Fetch and Split Text

#### Purpose
Prepare the raw text for the LLM.

#### Prerequisites
None.

#### Implementation Scope
Inside the worker's `try` block: Use the S3 client to download the file bytes using `Document.s3_path`. Decode to UTF-8. Implement a Recursive Character Text Splitter (e.g., via LangChain or custom script) that splits the string into chunks of ~500 tokens with 50-token overlap.

#### Outputs
An array of string chunks.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Log the array length. A large file should produce dozens of chunks.

#### Proceed When
Text splitting works correctly.

### Step 02: Generate Embeddings

#### Purpose
Convert text semantics to math.

#### Prerequisites
Step 01.

#### Implementation Scope
Initialize an HTTP client to your chosen embedding provider (e.g., OpenAI API). Send the array of strings. Receive an array of vector embeddings (arrays of floats, e.g., length 1536).

#### Inputs
Array of strings.

#### Outputs
Array of float arrays.

#### Proceed When
You successfully retrieve embeddings from the provider.

### Step 03: Insert into Vector DB

#### Purpose
Persist the searchable data.

#### Prerequisites
Step 02.

#### Implementation Scope
Initialize the Vector DB client. Map the strings and vectors into the required insertion payload. **CRITICAL**: Every inserted record MUST include the `tenant_id`, `knowledgebase_id`, and `document_id` as metadata fields for filtering. Execute a bulk insert.

#### Outputs
HTTP 200 OK from the Vector DB.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Query the Vector DB directly (via cURL or GUI) to ensure the records exist and metadata is attached.

#### Proceed When
The data is safely in the Vector DB.

