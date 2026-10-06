# Agent Tool Execution & Sandboxed Environments

## Level 1: Conceptual Overview

**Tool Execution** handles native tool invocations (web scrapers, financial APIs, scientific databases), MCP tool requests, and custom code execution (Python/SQL). Custom user code runs inside isolated sandboxes (`agent/sandbox/*`) to prevent host compromise or unauthorized system access.

---

## Level 2: Implementation Details

### Source File Map
- **Native Tool Base**: [agent/tools/base.py](file:///home/logan78/Desktop/ragflow/agent/tools/base.py#L1)
- **Code Execution Tool**: [agent/tools/code_exec.py](file:///home/logan78/Desktop/ragflow/agent/tools/code_exec.py#L1)
- **Sandbox Client**: [agent/sandbox/client.py](file:///home/logan78/Desktop/ragflow/agent/sandbox/client.py#L1)
- **Executor Manager**: [agent/sandbox/executor_manager/main.py](file:///home/logan78/Desktop/ragflow/agent/sandbox/executor_manager/main.py#L1)

---

### Python Code Sandbox Execution Flow

```
[Agent Component / CodeExec Tool]
   │
   ▼
[Sandbox Client (agent/sandbox/client.py)]
   │
   ▼  HTTP POST /execute (JSON payload: {code, timeout, env})
[Executor Manager (agent/sandbox/executor_manager)]
   │
   ▼  Spawn isolated Docker/Container subprocess
[Code Execution Engine (Restricted Environment)]
   │
   ▼  Capture stdout, stderr, execution result dict
[Sandbox Client]
   │
   ▼  Return Observation to Agent ReAct Loop
```

In [agent/tools/code_exec.py](file:///home/logan78/Desktop/ragflow/agent/tools/code_exec.py#L1):
Custom Python code provided by the LLM is sent to the sandbox executor manager with CPU time limits (`timeout=10s`) and restricted memory allocation (`max_memory_mb=512`).
