# dataset_api.py Endpoints

Source: `api/apps/restful_apis/dataset_api.py`

## Route: `/datasets/tags/aggregation`
- **Methods:** GET
- **Handler Function:** `aggregate_tags()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/metadata/flattened`
- **Methods:** GET
- **Handler Function:** `get_flattened_metadata()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets`
- **Methods:** POST
- **Handler Function:** `list_datasets()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>`
- **Methods:** GET
- **Handler Function:** `get_dataset()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/ingestions/summary`
- **Methods:** GET
- **Handler Function:** `get_ingestion_summary()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/tags`
- **Methods:** GET
- **Handler Function:** `list_tags()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/tags`
- **Methods:** DELETE
- **Handler Function:** `delete_dataset_structure()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/artifacts/alteration`
- **Methods:** GET
- **Handler Function:** `trace_index()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/<index_type>`
- **Methods:** DELETE
- **Handler Function:** `delete_index()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/embedding/check`
- **Methods:** POST
- **Handler Function:** `list_ingestion_logs()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/ingestions/<log_id>`
- **Methods:** GET
- **Handler Function:** `get_ingestion_log()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/metadata/config`
- **Methods:** GET
- **Handler Function:** `get_auto_metadata()`

- **Calls Services:** None directly detected.

---
