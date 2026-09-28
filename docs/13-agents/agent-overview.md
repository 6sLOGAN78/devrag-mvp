# Agent Subsystem Overview & Capability Architecture

## Level 1: Conceptual Overview

The **Agent Subsystem** in RAGFlow provides autonomous problem-solving capabilities by combining Large Language Models, tool execution loops (ReAct/Function Calling), Model Context Protocol (MCP) integrations, sandboxed code execution, and multi-agent delegation.

```mermaid
graph TD
    Canvas[Canvas Workflow Engine] --> AgentComp[Agent Component (agent_with_tools.py)]
    AgentComp --> ReActLoop[ReAct Autonomous Execution Loop]
    
    subgraph Tool Ecosystem
        ReActLoop --> NativeTools[Native Python Tools (agent/tools/*)]
        ReActLoop --> MCPConnector[MCP Server Tools (internal/mcp/*)]
        ReActLoop --> CodeSandbox[Code Execution Sandbox (agent/sandbox/*)]
        ReActLoop --> RAGTool[Knowledge Base Retrieval Tool]
    end

    ReActLoop --> MultiTurnMemory[Agent Step History & Canvas State]
    ReActLoop --> LLMBundle[LLMBundle / Provider API]
    LLMBundle --> FinalAnswer[Final Output / Artifact Stream]
```

### Core Features
1. **Tool-Enabled ReAct Execution**: Autonomously select tools, run iterations, evaluate tool output observations, and determine when task completion goals are satisfied.
2. **MCP Integration**: Native client support for Model Context Protocol (MCP) servers, discovering remote tools dynamically over SSE or stdio transports.
3. **Sandboxed Code Execution**: Run Python and SQL scripts in isolated Docker/Wasm sandboxes with strict memory and CPU resource limits.
4. **Dual Engine Runtime**: Execute agent workflows in Python ([agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L74)) or compiled Go Eino runtimes ([agent.go](file:///home/logan78/Desktop/ragflow/internal/agent/component/agent.go#L1)).

---

## Level 2: Implementation Details

### Source File Map

| Component | Python Path | Go Path | Key Responsibilities |
| :--- | :--- | :--- | :--- |
| **Agent Component Driver** | [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L74) | [agent.go](file:///home/logan78/Desktop/ragflow/internal/agent/component/agent.go#L1) | Autonomous tool execution loop, tool indexed binding, max_rounds control |
| **MCP Connectors** | [mcp_tool_call_conn.py](file:///home/logan78/Desktop/ragflow/common/mcp_tool_call_conn.py) | [connector.go](file:///home/logan78/Desktop/ragflow/internal/mcp/connector.go#L28) | MCP server protocol binding, tool discovery, schema translation |
