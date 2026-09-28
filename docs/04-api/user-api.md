# user_api.py Endpoints

Source: `api/apps/restful_apis/user_api.py`

## Route: `/auth/login`
- **Methods:** POST
- **Handler Function:** `rollback_user_registration()`

- **Calls Services:**
  - `FileService`
  - `UserTenantService`
  - `TenantService`
  - `UserService`
  - `TenantLLMService`

---

## Route: `/users`
- **Methods:** POST
- **Handler Function:** `_verified_key()`

- **Calls Services:**
  - `UserService`

---
