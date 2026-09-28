# document_api.py Endpoints

Source: `api/apps/restful_apis/document_api.py`

## Route: `/documents/upload`
- **Methods:** POST
- **Handler Function:** `list_docs()`

- **Calls Services:** None directly detected.

---

## Route: `/datasets/<dataset_id>/documents`
- **Methods:** DELETE
- **Handler Function:** `list_thumbnails()`

- **Calls Services:**
  - `DocumentService`

---

## Route: `/datasets/<dataset_id>/documents/metadatas`
- **Methods:** PATCH
- **Handler Function:** `_run_sync()`

- **Calls Services:**
  - `TaskService`
  - `DocumentService`

---

## Route: `/datasets/<dataset_id>/documents/parse`
- **Methods:** POST
- **Handler Function:** `_parse_document_image_id()`

- **Calls Services:** None directly detected.

---

## Route: `/documents/images/<image_id>`
- **Methods:** GET
- **Handler Function:** `_sandbox_artifact_dialog_ids_for_user()`

- **Calls Services:**
  - `UserCanvasService`

---

## Route: `/documents/artifact/<filename>`
- **Methods:** GET
- **Handler Function:** `_mimetype_for_document()`

- **Calls Services:**
  - `KnowledgebaseService`
  - `File2DocumentService`
  - `DocumentService`

---
