# tenant_api.py Endpoints

Source: `api/apps/restful_apis/tenant_api.py`

## Route: `/tenants/<tenant_id>/users`
- **Methods:** GET
- **Handler Function:** `user_list()`

- **Calls Services:**
  - `UserTenantService`
  - `UserService`

---

## Route: `/tenants/<tenant_id>/users`
- **Methods:** POST
- **Handler Function:** `tenant_list()`

- **Calls Services:**
  - `UserTenantService`

---

## Route: `/tenants/<tenant_id>`
- **Methods:** PATCH
- **Handler Function:** `agree()`

- **Calls Services:**
  - `UserTenantService`

---
