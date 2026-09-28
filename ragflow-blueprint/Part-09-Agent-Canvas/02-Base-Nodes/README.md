# Subpart 02: Base Nodes

## 1. Objective
To implement the specific executable blocks that plug into the DAG Engine, wrapping your existing RAG capabilities.

## 2. Documentation Basis
*   `ragflow-docs/13-agents/canvas.md`: DOCUMENTED - Built-in nodes like LLM and Retrieval.

## 3. Prerequisites
*   `01-DAG-Engine` completed.
*   Retrieval Engine and LLM Client (Parts 06, 07).

## 4. Components to Implement
*   **Start Node**: Ingests user variables.
*   **LLM Node**: Calls the LLM.
*   **Retrieval Node**: Calls Vector DB.
*   **End Node**: Returns final response.

## 5. Detailed Sequential Implementation Steps

### Step 01: Implement Nodes

#### Purpose
Bridge the DAG to your RAG logic.

#### Prerequisites
DAG Engine ready.

#### Implementation Scope
Create a `Node` base class. 
Implement `StartNode` -> saves `user_query` to state.
Implement `RetrievalNode` -> reads `user_query`, calls `retrieve_documents()` from Part 06, saves `chunks` to state.
Implement `LLMNode` -> reads `user_query` and `chunks`, calls LLM Client, saves `answer` to state.
Implement `EndNode` -> yields `answer`.

#### Proceed When
Nodes are registered with the DAG Engine.

