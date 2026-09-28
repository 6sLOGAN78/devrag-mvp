# Workflow Call Chain Tracing

## Level 1: Conceptual Overview

The workflow call chain orchestrates multi-step, production-grade automation workflows triggered asynchronously via HTTP Webhooks or REST API calls.

---

## Level 2: Complete Code Call Chain

```
[Webhook Request / API Trigger]
       │
       ▼ (HTTP POST /v1/agent/<agent_id>/webhook)
[api/apps/restful_apis/agent_api.py:webhook()] [L1830]
       │
       ├─► 1. Security Authorization:
       │     └─► validate_webhook_security(security_cfg) [L1883]
       │
       ├─► 2. Invoke Workflow Session Runner:
       │     └─► _run_workflow_session(agent_id, req) [L232]
       │           │
       │           ├─► Commit Runtime Replica Snapshot:
       │           │     └─► api/apps/services/canvas_replica_service.py:commit_runtime_replica()
       │           │           └─► Freeze canvas DSL state in MySQL
       │           │
       │           ├─► Set Request Context:
       │           │     └─► common/llm_request_context.py:set_llm_request_context()
       │           │
       │           ├─► Execute Graph Engine:
       │           │     └─► agent/canvas.py:Graph.run() [L440]
       │           │           └─► Node-by-node execution loop
       │           │
       │           └─► Persist Session Metrics:
       │                 └─► persist_workflow_session() [L291]
       │                       └─► Write execution log, node states, and token counts to `agent_session`
       │
       ▼
[HTTP 200 OK Response] -> {code: 0, data: {outputs: {...}, session_id: "sess_123"}}
```

---

## Exact Source Code References

- **Webhook Handler**: `webhook()` in [api/apps/restful_apis/agent_api.py:L1830](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py#L1830)
- **Workflow Session Runner**: `_run_workflow_session()` in [api/apps/restful_apis/agent_api.py:L232](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py#L232)
- **Session Persistence**: `persist_workflow_session()` in [api/apps/restful_apis/agent_api.py:L291](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py#L291)
- **Canvas Replica Snapshot Service**: [api/apps/services/canvas_replica_service.py:L30](file:///home/logan78/Desktop/ragflow/api/apps/services/canvas_replica_service.py#L30)
- **LLM Request Context**: [common/llm_request_context.py:L20](file:///home/logan78/Desktop/ragflow/common/llm_request_context.py#L20)
