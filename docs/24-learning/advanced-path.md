# Advanced Path: Agent Canvas Engine & Multi-Service Architecture

## Target Audience
Senior software architects, AI system developers, and open-source contributors extending RAGFlow's Agent Canvas, workflow engine, or Go backend service microarchitecture.

---

## Learning Objectives
1. Reverse-engineer the Agent Canvas Graph execution engine (`agent/canvas.py` and `internal/agent/canvas/`).
2. Learn how to write custom Agent Canvas nodes by extending `ComponentBase` in `agent/component/`.
3. Understand RAPTOR hierarchical clustering and graph-based retrieval.
4. Master Go microservice migration patterns (`internal/server/`, `internal/handler/`, `internal/service/`).
5. Design asynchronous webhook and API automation workflows.

---

## Primary Reading List

1. **Agent Canvas Engine**: Read [21-end-to-end-flows/agent-execution.md](../21-end-to-end-flows/agent-execution.md) and inspect `Graph.run()` in [agent/canvas.py:L440](file:///home/logan78/Desktop/ragflow/agent/canvas.py#L440).
2. **Workflow Execution**: Read [21-end-to-end-flows/workflow-execution.md](../21-end-to-end-flows/workflow-execution.md) and inspect `_run_workflow_session()` in [api/apps/restful_apis/agent_api.py:L232](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py#L232).
3. **Component Architecture**: Inspect `ComponentBase` in [agent/component/base.py:L30](file:///home/logan78/Desktop/ragflow/agent/component/base.py#L30) and node implementations (Retrieval, LLM, Categorize, Switch, ExeSQL).
4. **RAPTOR Implementation**: Inspect `RAPTOR_TREE_BUILDER` in [rag/utils/raptor_utils.py:L48](file:///home/logan78/Desktop/ragflow/rag/utils/raptor_utils.py#L48).

---

## Hands-On Milestones

- **Milestone 2**: Configure a RAPTOR-enabled Knowledge Base and trace tree summary generation in `task_executor.py`.
- **Milestone 3**: Trace a webhook execution flow: trigger `POST /v1/agent/<id>/webhook` -> verify replica snapshot -> trace execution log in `agent_session`.
