# Subpart 02: Vector Search

## 1. Objective
To query the Vector Database using the query embedding to find the most semantically similar text chunks, while strictly enforcing multi-tenancy.

## 2. Documentation Basis
*   `docs/07-retrieval/hybrid-search.md`: DOCUMENTED - Cosine similarity search.

## 3. Prerequisites
*   `01-Query-Processing` (The query vector).
*   Vector DB populated with chunks from Part 05.

## 4. Components to Implement
*   **Dense Search Executor**: Function to build and execute the Vector DB query payload.

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Search Query

#### Purpose
Construct a secure vector search payload.

#### Prerequisites
Vector DB Client initialized.

#### Implementation Scope
Write a function `execute_vector_search(query_vector: list, kb_ids: list, tenant_id: str, top_k: int = 10)`. 
Construct the JSON payload specific to your Vector DB (e.g., Elasticsearch `knn` query). 
**CRITICAL SECURITY ENFORCEMENT**: The query MUST contain a hard filter: `tenant_id == tenant_id` AND `kb_id IN kb_ids`. Without this, users can search other people's data.

#### Inputs
Vector array, tenant constraints.

#### Processing and Behavior
Database calculates cosine distance between the query vector and all chunks matching the filters.

#### Outputs
A list of documents with their similarity scores.

#### Expected Result
The database returns the most relevant chunks.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Upload a test document with the phrase "The secret password is XYZZY". Query the vector search function with "What is the secret?". It should return the chunk containing the password. Run the same query passing a different `tenant_id` - it MUST return 0 results.

#### Proceed When
Both semantic accuracy and security filtering are verified.

