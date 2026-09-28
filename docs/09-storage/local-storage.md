# Local File Storage Driver

## Level 1: Conceptual Overview

The Local File Storage driver persists binary assets directly to the host filesystem, providing single-node file storage without external cloud object dependencies.

---

## Level 2: Implementation Details

### Path Sanitization & Security

Implemented in [api/utils/file_utils.py](file:///home/logan78/Desktop/ragflow/api/utils/file_utils.py#L20) (`sanitize_path`):

```python
def sanitize_path(path_str):
    # Prevents directory traversal vulnerabilities (e.g. ../../etc/passwd)
    clean_path = Path(path_str).resolve()
    assert clean_path.is_relative_to(BASE_DIR)
    return str(clean_path)
```

Base Directory: Defaults to `/home/logan78/Desktop/ragflow/rag/res/` or host environment data path.
