# Subpart 04: Result Assembly

## 1. Objective
To merge the results from Vector Search and BM25 Search, deduplicate chunks that were found by both methods, and apply a final ranking algorithm.

## 2. Documentation Basis
*   `docs/07-retrieval/hybrid-search.md`: DOCUMENTED - The merging of multiple retrieval strategies.

## 3. Prerequisites
*   `02-Vector-Search` and `03-BM25-Search` completed.

## 4. Components to Implement
*   **Result Combiner**: Logic to merge two arrays and normalize their scores.

## 5. Detailed Sequential Implementation Steps

### Step 01: Merge and Deduplicate

#### Purpose
Create a unified list of unique chunks.

#### Prerequisites
Both search executors available.

#### Implementation Scope
Write the main `retrieve_documents` function.
1. Call Vector Search and BM25 Search concurrently (or sequentially).
2. Combine the arrays.
3. Iterate through the array. If a chunk's ID appears twice (found by both methods), merge the records.

#### Inputs
Two arrays of results.

#### Outputs
One array of unique results.

#### Proceed When
Deduplication logic is flawless.

### Step 02: Score Normalization (Reciprocal Rank Fusion)

#### Purpose
Rank the final list fairly.

#### Prerequisites
Step 01.

#### Implementation Scope
Because Cosine scores (0.0 to 1.0) and BM25 scores (arbitrary floats) cannot be compared directly, implement Reciprocal Rank Fusion (RRF). 
Rank = `1 / (k + vector_rank) + 1 / (k + bm25_rank)`.
Sort the deduplicated array by this combined rank. Take the top `K` (e.g., 5) chunks to return.

#### Outputs
The final top K chunks.

#### Expected Result
The engine reliably returns the absolute best chunks for a query.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Run a query and verify the returned list is sorted correctly and limited to `top_k`.

#### Proceed When
The retrieval engine API is complete.

