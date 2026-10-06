# Agent Architecture & Class Structure

## Level 1: Conceptual Overview

The **Agent Architecture** builds upon `LLM` and `ToolBase` superclasses. An Agent component wraps a dedicated LLM instance (`chat_mdl`), a map of indexed tool bindings (`tools`), an optional array of MCP server connections (`mcp`), and loop control constraints (`max_rounds`).

---

## Level 2: Implementation Details

### Class Hierarchy & Method Signatures

In [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L40-L100):

```python
class AgentParam(LLMParam, ToolParamBase):
    """Configuration parameters for Agent components."""
    def __init__(self):
        super().__init__()
        self.function_name = "agent"
        self.tools = []          # List of native tool component definitions
        self.mcp = []            # List of MCP server IDs
        self.max_rounds = 5      # Maximum ReAct iterations allowed
        self.description = ""

class Agent(LLM, ToolBase):
    component_name = "Agent"

    def __init__(self, canvas, id, param: LLMParam):
        LLM.__init__(self, canvas, id, param)
        self.tools = {}
        # Indexed tool mapping to prevent name collisions
        for idx, cpn in enumerate(self._param.tools):
            cpn = self._load_tool_obj(cpn)
            original_name = cpn.get_meta()["function"]["name"]
            indexed_name = f"{original_name}_{idx}"
            self.tools[indexed_name] = cpn

    def _run(self, history, **kwargs):
        """Executes the autonomous tool calling loop up to max_rounds."""
        ...
```

---

### Tool Indexing & Name Collision Prevention

When binding multiple tool components to an agent (e.g. two separate `Google` search tools with different API keys), the agent assigns unique indexed function keys ([agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L80-L100)):

```
Tool 0 (Google)  -> Function Name: google_search_0
Tool 1 (Google)  -> Function Name: google_search_1
Tool 2 (ArXiv)   -> Function Name: arxiv_search_2
```
