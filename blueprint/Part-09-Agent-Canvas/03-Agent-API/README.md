# Subpart 03: Agent API

## 1. Objective
To expose the DAG Engine via a REST endpoint that accepts streaming connections.

## 2. Documentation Basis
*   `docs/14-workflows/execution.md`: DOCUMENTED.

## 3. Prerequisites
*   `02-Base-Nodes` completed.

## 4. Components to Implement
*   **Agent Execution API**: `POST /api/agent/run`.

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Endpoint

#### Purpose
Expose workflows.

#### Prerequisites
DAG Engine ready.

#### Implementation Scope
Implement `POST /api/agent/run`. Protect with Auth Middleware. Accept `{ graph_json, inputs }`. 
Initialize the `DAGEngine`. Call `run(inputs)`.
Stream the output of the `EndNode` back to the client using Server-Sent Events (SSE).

#### Proceed When
The endpoint streams text.

