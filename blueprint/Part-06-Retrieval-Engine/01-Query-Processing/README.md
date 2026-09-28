# Subpart 01: Query Processing

## 1. Objective
To convert the user's natural language string into a vector embedding so it can be mathematically compared against the chunks in the database.

## 2. Documentation Basis
*   `docs/07-retrieval/hybrid-search.md`: INFERRED - Standard dense retrieval requirement.

## 3. Prerequisites
*   LLM Embedding Client (Built in Part 05.03).

## 4. Components to Implement
*   **Query Embedder**: A wrapper function calling the Embedding API.

## 5. Detailed Sequential Implementation Steps

### Step 01: Embed the Query

#### Purpose
Translate text to math.

#### Prerequisites
None.

#### Implementation Scope
Create a `retrieval_service` module. Write a function `process_query(query: str) -> list[float]`. This function simply calls the exact same LLM Embedding API used in Part 05.03.

#### Inputs
"What is the company leave policy?"

#### Outputs
`[0.012, -0.045, ...]`

#### Dependencies
External LLM provider.

#### Expected Result
The query is vectorized.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Unit test the function to ensure it returns an array of floats.

#### Proceed When
The function reliably returns a vector of the correct dimensionality.

