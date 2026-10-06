# Agent Call Chain Tracing

## Level 1: Conceptual Overview

The agent call chain traces execution through the Agent Canvas engine. A visual agent DSL is compiled into a graph DAG of component objects, which are executed asynchronously with state isolation.

---

## Level 2: Complete Code Call Chain

```
[React UI Agent Canvas / Chat Input]
       │
       ▼ (HTTP POST /api/v1/agents/chat/completions)
[api/apps/restful_apis/agent_api.py:agent_chat_completion()] [L1447]
       │
       ├─► 1. Access Check & DSL Lookup:
       │     └─► Fetch agent canvas DSL from MySQL table `canvas`
       │
       ├─► 2. Graph Initialization:
       │     └─► agent/canvas.py:Graph(canvas_dsl) [L49]
       │
       ├─► 3. Graph Execution Loop:
       │     └─► agent/canvas.py:Graph.run() [L440]
       │           │
       │           ├─► Node 1: agent/component/begin.py:Begin.run()
       │           │     └─► Read query inputs & request variables
       │           │
       │           ├─► Node 2: agent/component/retrieval.py:Retrieval.run()
       │           │     └─► rag/nlp/search.py:Dealer.search() -> Multi-KB Hybrid Search
       │           │
       │           ├─► Node 3: agent/component/categorize.py:Categorize.run()
       │           │     └─► Intent classification & path branching
       │           │
       │           ├─► Node 4: agent/component/llm.py:LLM.run()
       │           │     └─► api/db/services/llm_service.py:LLMBundle.chat()
       │           │
       │           └─► Node 5: agent/component/answer.py:Answer.run()
       │                 └─► Format final SSE output stream
       │
       └─► 4. Session Persistence:
             └─► AgentSessionService.save() -> INSERT INTO `agent_session` in MySQL
```

---

## Component Registry Mapping (`agent/component/__init__.py`)

| Component Name | Class Name | Source File |
|---|---|---|
| Begin | `Begin` | [agent/component/begin.py:L30](file:///home/logan78/Desktop/ragflow/agent/component/begin.py#L30) |
| LLM | `LLM` | [agent/component/llm.py:L40](file:///home/logan78/Desktop/ragflow/agent/component/llm.py#L40) |
| Categorize | `Categorize` | [agent/component/categorize.py:L35](file:///home/logan78/Desktop/ragflow/agent/component/categorize.py#L35) |
| Switch | `Switch` | [agent/component/switch.py:L35](file:///home/logan78/Desktop/ragflow/agent/component/switch.py#L35) |

---

## Exact Source Code References

- **Agent REST Controller**: `agent_chat_completion()` in [api/apps/restful_apis/agent_api.py:L1447](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py#L1447)
- **Canvas Graph Engine**: `Graph` class in [agent/canvas.py:L49](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L49)
- **Canvas Run Method**: `Graph.run()` in [agent/canvas.py:L440](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L440)
- **Base Component Class**: `ComponentBase` in [agent/component/base.py:L30](file:///home/logan78/Desktop/ragflow/agent/component/base.py#L30)
- **Go Canvas Implementation**: [internal/agent/canvas/canvas.go:L80](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/canvas.go#L80)
