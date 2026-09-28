# system_api.py Endpoints

Source: `api/apps/restful_apis/system_api.py`

## Route: `/system/ping`
- **Methods:** GET
- **Handler Function:** `version()`

- **Calls Services:** None directly detected.

---

## Route: `/language`
- **Methods:** GET
- **Handler Function:** `language()`

- **Calls Services:**
  - `KnowledgebaseService`

---

## Route: `/system/status`
- **Methods:** GET
- **Handler Function:** `status()`

- **Calls Services:**
  - `KnowledgebaseService`

---

## Route: `/system/oceanbase/status`
- **Methods:** GET
- **Handler Function:** `oceanbase_status()`

- **Calls Services:** None directly detected.

---

## Route: `/system/config`
- **Methods:** GET
- **Handler Function:** `get_config()`

- **Calls Services:**
  - `APITokenService`
  - `UserTenantService`

---

## Route: `/system/healthz`
- **Methods:** GET
- **Handler Function:** `healthz()`

- **Calls Services:**
  - `APITokenService`
  - `UserTenantService`

---

## Route: `/system/tokens`
- **Methods:** GET
- **Handler Function:** `token_list()`

- **Calls Services:**
  - `APITokenService`
  - `UserTenantService`

---

## Route: `/system/tokens`
- **Methods:** POST
- **Handler Function:** `new_token()`

- **Calls Services:**
  - `APITokenService`
  - `UserTenantService`

---

## Route: `/system/tokens/<token>`
- **Methods:** DELETE
- **Handler Function:** `rm()`

- **Calls Services:**
  - `APITokenService`
  - `UserTenantService`

---
