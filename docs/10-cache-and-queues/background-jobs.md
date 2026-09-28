# Background Jobs Subsystem

## Level 1: Conceptual Overview

The Background Jobs Subsystem handles long-running async background operations such as RAPTOR summary tree construction, GraphRAG entity-relation extraction, MindMap generation, and memory sync.

---

## Level 2: Implementation Details

### Pipeline Task Mapping

Defined in [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L130-L160):

```python
TASK_TYPE_TO_PIPELINE_TASK_TYPE = {
    "dataflow": PipelineTaskType.PARSE,
    "raptor": PipelineTaskType.RAPTOR,
    "graphrag": PipelineTaskType.GRAPH_RAG,
    "mindmap": PipelineTaskType.MINDMAP,
    "memory": PipelineTaskType.MEMORY,
    "wiki": PipelineTaskType.ARTIFACT,
    "skill": PipelineTaskType.SKILL,
    "structure_graph": PipelineTaskType.STRUCTURE_GRAPH,
    "structure_mindmap": PipelineTaskType.STRUCTURE_MINDMAP,
    "timeline": PipelineTaskType.TIMELINE,
    "session_graph": PipelineTaskType.SESSION_GRAPH,
    "session_essence": PipelineTaskType.SESSION_ESSENCE,
    "structure": PipelineTaskType.STRUCTURE,
}
```

### KB Fan-out Task Types

For dataset-wide operations (`graphrag`, `raptor`, `mindmap`, `wiki`), tasks use sentinel fake document IDs ([rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L148-L160)) and operate on arrays of document IDs (`task["doc_ids"]`).
