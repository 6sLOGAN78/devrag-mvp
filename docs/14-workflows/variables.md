# Canvas State & Variable Resolution Engine

## Level 1: Conceptual Overview

The **Variable Resolution Engine** provides global scope state (`Graph.globals`) and node-local output references across the workflow graph. Variables are referenced in node parameters using standard template syntax: `{component_id.field_name}` or `{sys.user_id}`.

---

## Level 2: Implementation Details

### Source File Map
- **Go Canvas State**: [state.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/state.go#L1)
- **Python Canvas**: [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L81-L88)
- **Variable Aggregator**: [variable_aggregator.py](file:///home/logan78/Desktop/ragflow/agent/component/variable_aggregator.py#L54)
- **Variable Assigner**: [variable_assigner.py](file:///home/logan78/Desktop/ragflow/agent/component/variable_assigner.py#L39)

---

### System & Custom Variable Namespace

In [agent/canvas.py](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L81-L88):

#### 1. System Reserved Namespace (`sys.*`)
- `sys.query`: Initial prompt text passed to `Begin` node
- `sys.user_id`: Tenant/user identifier string
- `sys.conversation_turns`: Turn iteration count
- `sys.files`: Uploaded document attachments array

#### 2. Component Output Namespace (`{node_id}.*`)
- `{retrieval_0.chunks}`: Array of retrieved document chunks
- `{generate_0.content}`: Text output emitted by LLM generate node
- `{browser_0.html}`: HTML content scraped by browser component

---

### Variable Interpolation Algorithm

Node parameters evaluate variable template strings dynamically before component execution:

```python
def getValue(self, cpn_id, var_name):
    """Resolve variable value from globals or component outputs."""
    if var_name.startswith("sys."):
        return self.globals.get(var_name)
    component_output = self.components.get(cpn_id, {}).get("output", {})
    return component_output.get(var_name)
```
