# Architecture Decisions

This document records the architectural choices made for devRAG, differentiating between what is strictly documented in the original RAGFlow source and what is proposed for this manual implementation.

## 1. Backend Language and Framework
*   **Original RAGFlow (DOCUMENTED)**: Uses Go (Gin) for high-throughput API routing and Python (Quart) for heavy ML processing. Communication happens via HTTP and Redis. NGINX acts as the edge router to split traffic between the two.
*   **devRAG (PROPOSED)**: The blueprint is framework-agnostic but strongly recommends a unified language (e.g., Python FastAPI or Node.js) for the MVP. This reduces inter-process communication overhead. However, NGINX is retained as the edge reverse-proxy to serve frontend static files and route `/api` traffic to the unified backend.

## 2. Ingestion Complexity (DeepDoc)
*   **Original RAGFlow (DOCUMENTED)**: Relies heavily on YOLO, PaddleOCR, and 14 specialized chunkers for all PDF processing.
*   **devRAG (PROPOSED)**: Part 05 (Ingestion MVP) deliberately uses a generic text chunker. YOLO/OCR are deferred to Part 08. **Reason**: Ensure the core database and vector search logic works before debugging complex computer vision ML models.

## 3. Retrieval Reranking
*   **Original RAGFlow (DOCUMENTED)**: Mandates a cross-encoder reranking step after merging dense and sparse search results.
*   **devRAG (PROPOSED)**: Part 06 uses Reciprocal Rank Fusion (RRF) but defers the heavy Cross-Encoder ML model to an optional optimization phase. **Reason**: Reduces initial compute requirements and development friction.

## 4. Agent Sandboxing
*   **Original RAGFlow (DOCUMENTED)**: Uses Docker to sandbox user-provided Python code in the Agent Canvas.
*   **devRAG (PROPOSED)**: Part 09 ignores Docker sandboxing. **Reason**: Implementing secure dynamic Docker virtualization is too complex for an initial recreation. Do not run untrusted code in this recreation.

## 5. Frontend State Management
*   **Original RAGFlow (UNKNOWN)**: Specific frontend state libraries are not explicitly detailed in the docs.
*   **devRAG (PROPOSED)**: Use a standard global state store (e.g., Redux for React, Pinia for Vue) combined with React Query/SWR for server state to handle the complex background processing polling required by the Document Ingestion pipeline.
