# Documentation Gaps

This document identifies areas where the original `docs` do not provide sufficient detail to create an exact replica. These gaps require either source-code investigation or architectural decisions during implementation.

## GAP-01: Internal API Contracts
*   **Area**: Core Backend
*   **Description**: The exact JSON schemas for internal API requests (e.g., creating a Knowledge Base, updating a document status) are not exhaustively documented in `docs/04-api/`.
*   **Impact**: Frontend and Backend cannot communicate without a defined contract.
*   **Suggested Investigation**: You must define these REST contracts yourself (`PROPOSED`) based on the required ORM models, or inspect network requests on a live RAGFlow instance.

## GAP-02: Chunking Algorithm Nuances
*   **Area**: Document Ingestion
*   **Description**: The documentation mentions 14 specific chunkers (`docs/06-document-processing/chunking.md`) but does not provide the algorithmic logic for how the "Paper" chunker differs from the "Resume" chunker.
*   **Impact**: Exact parity with RAGFlow's chunking quality is impossible from docs alone.
*   **Suggested Investigation**: Build a generic Recursive Character Splitter for the MVP. Advanced heuristics require source code reading of the DeepDoc module.

## GAP-03: Hybrid Search Weighting Math
*   **Area**: Retrieval Engine
*   **Description**: When merging Dense Vector results and BM25 Sparse results, the exact mathematical weighting (Alpha) used before sending the list to the Cross-Encoder is `UNKNOWN`.
*   **Impact**: Search rankings may differ from original RAGFlow.
*   **Suggested Investigation**: Implement Reciprocal Rank Fusion (RRF) as a standard industry fallback (`PROPOSED`).

## GAP-04: Agent Canvas JSON Schema
*   **Area**: Agent Canvas
*   **Description**: The exact JSON schema representing the Directed Acyclic Graph (DAG) is `UNKNOWN`.
*   **Impact**: The frontend DAG builder and backend DAG engine cannot sync.
*   **Suggested Investigation**: Design a standard Node/Edge JSON schema (similar to React Flow's output) and implement it strictly across both stacks (`PROPOSED`).

## GAP-05: Frontend Component Library
*   **Area**: Frontend UI
*   **Description**: The source documentation provides architectural diagrams but does not specify the exact CSS framework or component library used for the UI.
*   **Impact**: Visual parity relies on developer choices.
*   **Suggested Investigation**: Select a comprehensive component library (e.g., MUI, Tailwind UI, Shadcn) that supports complex DataGrids and Drawers (`PROPOSED`).
