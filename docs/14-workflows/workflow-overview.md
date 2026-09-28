# Workflow Subsystem Overview & Visual Canvas

## Level 1: Conceptual Overview

The **Workflow Subsystem** in RAGFlow allows developers to construct complex, multi-step LLM application graphs via a visual canvas editor. Workflows process incoming queries, execute conditional branching, iterate over datasets, invoke external tools/APIs, and generate structured output streams.

```mermaid
graph TD
    DSL[User Canvas DSL JSON] --> EngineSelector{Engine Target}
    
    EngineSelector -->|Python Graph Runner| PyRunner[agent/canvas.py (Graph Engine)]
    EngineSelector -->|Go Eino DAG Engine| GoRunner[internal/agent/canvas (Compile & Runner)]
    
    subgraph Core Graph Execution
        PyRunner --> NodeExec[Node Component Dispatch]
        GoRunner --> EinoGraph[Eino ComposeGraph DAG]
        
        NodeExec --> BeginNode[Begin Node (Inputs)]
        NodeExec --> LLMNode[Generate / LLM Node]
        NodeExec --> RetrievalNode[Retrieval / KB Search]
        NodeExec --> SwitchNode[Switch / Categorize Node]
        NodeExec --> SubgraphNode[Loop / Iteration Node]
        NodeExec --> ToolNode[Tool / Code Sandbox Node]
    end

    NodeExec --> StateStore[CanvasState & Checkpoint Persistence]
    StateStore --> SSEOutput[SSE Event Stream (workflow_started, node_started, message, done)]
```

### Key Architectural Highlights
1. **Dual Execution Engine**: Supports legacy Python graph traversal ([agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49)) and high-performance Go Eino DAG execution ([canvas.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/canvas.go#L47)).
2. **DSL Format Integrity**: Workflows are serialized as standardized JSON DSL schemas (`components`, `history`, `retrieval`, `globals`, `path`).
3. **Subgraphs & Control Flow**: Advanced control structures including `Loop` subgraphs ([loop_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/loop_subgraph.go)), `Parallel` branching ([parallel_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/parallel_subgraph.go)), and `Switch` conditionals.
4. **State Checkpointing & Interrupts**: Interactive human-in-the-loop pause and resume via `checkpoint_store.go` and `interrupt_resume.go`.

---

## Level 2: Implementation Details

### Source File Map

| Component | Python Path | Go Path | Primary Function |
| :--- | :--- | :--- | :--- |
| **Canvas Engine Driver** | [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49) | [canvas.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/canvas.go#L47) | Graph DSL parsing, node loading, graph execution loop |
| **DAG Compiler** | — | [compile.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/compile.go#L1) | Translates JSON DSL into executable ByteDance Eino `ComposeGraph` |
| **Runtime Runner** | — | [runner.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/runner.go#L1) | Drives invocation, handles `waiting_for_user` interrupts, outputs SSE frames |
| **Checkpoint Persistence** | — | [checkpoint_store.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/checkpoint_store.go#L1) | Persists canvas execution state snapshots to Redis/MySQL |
| **Loop Subgraphs** | — | [loop_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/loop_subgraph.go#L1) | Compiles inner subgraphs for repetitive node execution |
| **Parallel Subgraphs** | — | [parallel_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/parallel_subgraph.go#L1) | Executes concurrent branch graphs |
