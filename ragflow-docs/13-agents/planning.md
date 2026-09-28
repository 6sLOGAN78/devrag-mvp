# Agent Planning & Reasoning Mechanics

## Level 1: Conceptual Overview

**Agent Planning** involves task decomposition, tool selection, and supervisor delegation. RAGFlow supports supervisor reasoning prompts (`reasoning`, `context`, `user_prompt`), structured output format enforcement (JSON schema parsing via `json_repair`), and ReAct mode switching (`function_call` vs `react`).

---

## Level 2: Implementation Details

### Source File Map
- **Agent Component**: [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L40-L75)
- **Categorize Component**: [categorize.py](file:///home/logan78/Desktop/ragflow/agent/component/categorize.py#L30)
- **Switch Component**: [switch.py](file:///home/logan78/Desktop/ragflow/agent/component/switch.py#L25)

---

### Planning Parameters & Schema Injection

In [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L46-L64):

The `AgentParam` schema injects supervisor fields into prompt templates:
- `user_prompt`: The specific goal or command assigned to the agent.
- `reasoning`: The supervisor's rationale for picking this agent.
- `context`: Comprehensive background information and state needed to complete the task.

```python
meta = {
    "name": "agent",
    "description": "This is an agent for a specific task.",
    "parameters": {
        "user_prompt": {"type": "string", "description": "Order for the agent.", "required": True},
        "reasoning": {"type": "string", "description": "Reason for invoking agent.", "required": True},
        "context": {"type": "string", "description": "Background state and facts.", "required": True}
    }
}
```
