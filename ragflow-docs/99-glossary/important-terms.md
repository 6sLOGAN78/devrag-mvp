# Important RAGFlow Terms & Identifiers

## Key System Identifiers & Constants

### Task Queue Name
- **`ragflow_TASK_EXE_QUEUE`**: Redis list key used for queuing document parsing tasks between API handlers and background workers.
- **Source**: [api/db/services/task_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/task_service.py) & [rag/svr/task_executor.py](file:///home/logan78/Desktop/ragflow/rag/svr/task_executor.py#L1904).

### Document Run Statuses (`document.run`)
- **`0` (`UNSTART`)**: Document uploaded, pending parsing.
- **`1` (`RUNNING`)**: Document enqueued and actively being parsed by worker.
- **`2` (`CANCEL`)**: Document parsing canceled by user.
- **`3` (`FAIL`)**: Document parsing failed due to error.
- **`1.0` (`progress = 1.0`, `status = FINISHED`)**: Parsing and indexing complete.

### Citation Index Pattern
- **`##<N>$$`**: Standard citation marker string injected into system context by `chunks_format()` in [rag/prompts/generator.py](file:///home/logan78/Desktop/ragflow/rag/prompts/generator.py#L100) (e.g. `##0$$`, `##1$$`), allowing frontend UI to render clickable reference cards.

### Index Naming Convention
- **`ragflow_<dataset_id>`**: Standard index name pattern in Elasticsearch or Infinity vector database storing document chunks for a specific Knowledge Base.

### Authentication Cookie Name
- **`ragflow_auth`**: Signed access token cookie set upon successful user login in [internal/handler/user.go:L54](file:///home/logan78/Desktop/ragflow/internal/handler/user.go#L54).
