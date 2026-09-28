# Job Scheduling & Task Priorities

## Level 1: Conceptual Overview

Job Scheduling determines priority queuing order, task splitting, and page-range allocation for large multi-page PDF documents.

---

## Level 2: Implementation Details

### Page Range Splitting Algorithm

Implemented in `TaskService.create_task()` in [api/db/services/task_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/task_service.py#L50):

Large multi-page documents (e.g. 500-page PDF) are split into parallel sub-tasks using constant `MAXIMUM_TASK_PAGE_NUMBER = 12`:

```python
for start_page in range(0, total_pages, MAXIMUM_TASK_PAGE_NUMBER):
    end_page = min(start_page + MAXIMUM_TASK_PAGE_NUMBER, total_pages)
    Task.create(
        id=get_uuid(),
        doc_id=doc.id,
        from_page=start_page,
        to_page=end_page,
        priority=priority,
    )
```

Sub-tasks execute independently across worker pods and update completion progress atomically.
