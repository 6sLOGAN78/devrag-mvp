# Database Indexes & Performance Optimization

## Level 1: Conceptual Overview

Relational database indexes in RAGFlow are placed on high-cardinality foreign keys (`tenant_id`, `kb_id`, `doc_id`) and status filter columns (`status`, `run`, `progress`) to ensure fast JOIN operations and rapid status filtering.

---

## Level 2: Implementation Details

### Database Index Specifications

Defined in [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py):

| Table | Index Field | Index Type | Purpose |
| :--- | :--- | :--- | :--- |
| `document` | `kb_id` | B-Tree | Fast lookup of all documents in a dataset |
| `document` | `parser_id` | B-Tree | Filtering documents by chunking parser type |
| `document` | `status` | B-Tree | Excluding deleted (`status='0'`) documents |
| `task` | `doc_id` | B-Tree | Worker progress lookups for a target document |
| `task` | `progress` | B-Tree | Querying active or uncompleted background tasks |
| `knowledgebase` | `tenant_id` | B-Tree | Isolating dataset queries per tenant |
| `file` | `parent_id` | B-Tree | Directory hierarchy navigation in file manager |
