# Dual-Engine Architecture & Graph Compilation

## Level 1: Conceptual Overview

RAGFlow features a dual-engine architecture for graph workflows:
1. **Python Graph Runner**: Flexible step-by-step path traversal and dynamic component loading.
2. **Go Eino DAG Engine**: High-concurrency compiled graph engine based on ByteDance's Eino framework, providing streaming state channels, automatic subgraph expansion, and strict dependency validation.

---

## Level 2: Implementation Details

### Go Eino Graph Compilation (`compile.go`)

In [internal/agent/canvas/compile.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/compile.go#L30-L100):

```go
func BuildWorkflow(c *Canvas, factory runtime.ComponentFactory) (*eino.ComposeGraph, error) {
    // 1. Validate DSL component mappings and detect cycles
    // 2. Instantiate nodes and subgraphs (Loop, Parallel)
    // 3. Bind upstream and downstream edges
    // 4. Register state store hooks and checkpoint handlers
    ...
}
```

#### Graph Construction Steps
1. **Node Instantiation**: Converts each `CanvasComponent` in `c.Components` into an Eino graph node via `factory.Create(comp.Obj.ComponentName)`.
2. **Subgraph Compilation**:
   - `Loop` nodes compile inner subgraphs ([loop_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/loop_subgraph.go#L1)).
   - `Parallel` nodes compile concurrent branches ([parallel_subgraph.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/parallel_subgraph.go#L1)).
3. **Edge Wireup**: Adds directed edges from `Upstream` to `Downstream` nodes.

---

### Python Graph Engine (`agent/canvas.py`)

In [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49-L150):

```python
class Graph:
    def __init__(self, dsl: str, tenant_id=None, task_id=None):
        self.dsl = normalize_chunker_dsl(json.loads(dsl))
        self.components = {}  # {node_id: component_instance}
        self.load()

    def run(self, stream=False):
        """Step-by-step graph traversal engine."""
        # Start at 'begin' node
        # Execute component._run()
        # Evaluate downstream links and route traversal
```
