# Attack Surface Analysis

## Level 1: Conceptual Explanation

An attack surface analysis evaluates potential vulnerability entry points across exposed network ports, external API routes, C/C++ native shared libraries, file upload handlers, and LLM prompt injection vectors.

---

## Level 2: Implementation Details

### Threat Vector & Mitigation Matrix

| Vector Domain | Threat Description | Attack Vector | Code Mitigation | Source Reference |
| :--- | :--- | :--- | :--- | :--- |
| **Deserialization** | Arbitrary Code Execution via Python `pickle` payloads | Malicious Base64 strings sent to API | Restricted class loading in `RestrictedUnpickler` (`safe_module = {"numpy", "rag_flow"}`) | [`configs.py:L25`](file:///home/logan78/Desktop/ragflow/api/utils/configs.py#L25) |
| **Code Execution** | Arbitrary code execution via agent Python/Node.js steps | LLM generated code execution | Spawns isolated Docker containers with memory limits (`256m`), timeouts (`10s`), and no new privileges | `docker-compose-base.yml:L180` |
| **Authentication** | Access token brute forcing or forgery | Forged Bearer headers | HMAC SHA256 secret key validation and expiration checks in `_load_user()` | [`api/apps/__init__.py:L144`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L144) |
| **Multi-Tenancy** | Cross-tenant data retrieval leakage | Querying other tenant's dataset or document ID | Mandatory `tenant_id` filtering in all database service layer methods | `api/db/services/*` |
| **Native C++ Memory** | Buffer overflow or memory corruption in C++ parser libraries | Crafted malicious PDF / DOCX binary files | Sandboxed execution in `deepdoc` container process | [`Dockerfile_deepdoc_oss`](file:///home/logan78/Desktop/ragflow/Dockerfile_deepdoc_oss) |

---

## References & Source Links

- [`SECURITY.md:L1-L75`](file:///home/logan78/Desktop/ragflow/SECURITY.md#L1-L75) - Unpickling attack PoC and mitigation policy.
- [`api/utils/configs.py:L22-L52`](file:///home/logan78/Desktop/ragflow/api/utils/configs.py#L22-L52) - `RestrictedUnpickler` code.
- [`api/apps/__init__.py:L144-L280`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L144-L280) - Auth enforcement logic.
