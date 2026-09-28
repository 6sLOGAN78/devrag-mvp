# Agent API

Source: `api/apps/restful_apis/agent_api.py`

This file handles the orchestration of AI agents, canvas configurations, testing, and webhook integration.

## Key Endpoints and Execution Flow

1. **`GET /agents/<agent_id>/sessions`**
   - **Handler:** `list_sessions()`
   - **Services:** `API4ConversationService`, `UserCanvasService`
   - **Flow:** Validates agent existence via `UserCanvasService`, then queries sessions from `API4ConversationService`.

2. **`POST /agents/chat/completions`**
   - **Handler:** `chat_completions()`
   - **Services:** `UserCanvasService`, `API4ConversationService`
   - **Flow:** This is the primary execution endpoint for agents interacting with users. It sets up SSE streaming (`Response(gen(), mimetype="text/event-stream")`), initiates a session, and calls `canvas_service.completion` to run the agent DAG.

3. **`POST /agents/<agent_id>/components/<component_id>/debug`**
   - **Handler:** `debug_component()`
   - **Services:** `TaskService.queue_dataflow()`
   - **Flow:** Triggers a specific node test (e.g. LLM node or Retrieval node) by queuing a `dataflow` task in Redis for the worker to process.
