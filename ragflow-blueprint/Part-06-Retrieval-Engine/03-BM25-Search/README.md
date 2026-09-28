# Subpart 03: BM25 Search (Sparse)

## 1. Objective
To query the Vector Database using the raw text string to find exact keyword matches. This complements semantic search (e.g., finding exact ID numbers or names).

## 2. Documentation Basis
*   `ragflow-docs/07-retrieval/hybrid-search.md`: DOCUMENTED - RAGFlow uses BM25 alongside Vector Search.

## 3. Prerequisites
*   Vector DB populated with chunks from Part 05.

## 4. Components to Implement
*   **Sparse Search Executor**: Function to build and execute the keyword query.

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Keyword Query

#### Purpose
Construct a secure text search payload.

#### Prerequisites
Vector DB Client initialized.

#### Implementation Scope
Write `execute_bm25_search(query_text: str, kb_ids: list, tenant_id: str, top_k: int = 10)`.
Construct the JSON payload for a standard BM25 match (e.g., Elasticsearch `match` query).
Apply the exact same strict `tenant_id` and `kb_id` filters used in Vector Search.

#### Inputs
Raw string query, tenant constraints.

#### Outputs
A list of documents with their BM25 scores.

#### Expected Result
The database returns exact keyword matches.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Query for a specific unique word (e.g., "XYZ999"). It should return the chunk containing it.

#### Proceed When
Keyword search works and respects tenant isolation.

