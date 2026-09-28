# Subpart 01: DAG Execution Engine

## 1. Objective
To build a programmatic state machine that can parse a JSON graph (nodes and edges), topologically sort it, and execute nodes in the correct order, passing variables between them.

## 2. Documentation Basis
*   `docs/14-workflows/execution.md`: DOCUMENTED - Node execution lifecycle.

## 3. Prerequisites
*   None.

## 4. Components to Implement
*   **Graph Parser**: Validates JSON.
*   **Execution Loop**: State machine traversing edges.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define JSON Schema and Parser

#### Purpose
Establish the data contract for workflows.

#### Prerequisites
None.

#### Implementation Scope
Define a schema:
```json
{
  "nodes": [{"id": "n1", "type": "Start"}, {"id": "n2", "type": "End"}],
  "edges": [{"source": "n1", "target": "n2"}]
}
```
Write a `DAGEngine` class that accepts this JSON, validates it (no cycles), and prepares a state dictionary to hold variables.

#### Proceed When
The engine can detect cycles and topological sorting works.

### Step 02: Implement Execution Loop

#### Purpose
Traverse the graph.

#### Prerequisites
Step 01.

#### Implementation Scope
Write a `run(initial_input)` method. Find the `Start` node. Execute its logic (mock it for now). Find its outgoing edges. Pass the output to the target node. Repeat until reaching an `End` node.

#### Outputs
Final state dictionary.

#### Proceed When
The engine traverses a mock graph successfully.

