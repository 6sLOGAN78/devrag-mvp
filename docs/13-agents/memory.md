# Agent State & Turn Memory

## Level 1: Conceptual Overview

**Agent Memory** tracks multi-turn ReAct observations within an execution step, as well as persistent memory across graph workflow nodes. It maintains local scratchpads (`tool` role messages) during task solving and exposes results back to the canvas variable state (`Graph.globals`).

---

## Level 2: Implementation Details

### Source File Map
- **Canvas State (Go)**: [state.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/state.go#L1)
- **Canvas Graph (Python)**: [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49-L88)
- **Agent Component**: [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L120-L180)

---

### ReAct Observation Scratchpad Format

During tool execution, intermediate tool outputs are appended as structured tool messages:

```json
[
  {
    "role": "user",
    "content": "Find recent research on quantum computing and summarize key findings."
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_9901",
        "type": "function",
        "function": {
          "name": "arxiv_search_0",
          "arguments": "{\"query\": \"quantum computing 2026\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_9901",
    "content": "Paper 1: Topological qubits in 2026... Paper 2: Fault tolerance..."
  },
  {
    "role": "assistant",
    "content": "Based on the recent ArXiv papers..."
  }
]
```

---

### Graph State Variables Integration

In [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L80-L88):
Once the agent finishes execution, its final text output and generated structured data are written to `Graph.globals` under the component node ID (e.g. `globals.agent_0.output`), allowing downstream workflow nodes to access the result.
