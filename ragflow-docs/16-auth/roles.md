# User Roles & System Privileges

## Level 1: Role Definitions

RAGFlow defines three system roles for users within organization tenant workspaces:

1. **`owner` (Workspace Owner)**:
   - Creator of the tenant workspace.
   - Holds full administrative privileges, including team member management, workspace billing/plan configuration, API provider key management, and deletion of the workspace.
2. **`admin` (Workspace Administrator)**:
   - Appointed by the owner to manage tenant resources.
   - Can manage LLM provider credentials, update dataset settings, and view enterprise monitoring metrics.
3. **`normal` (Standard User Member)**:
   - Standard workspace member.
   - Can create datasets, upload files, build canvas workflows, test chat dialogues, and execute search bots.

---

## Level 2: Database Schema & Source Implementation

### User Tenant Role Model (`UserTenantRole` / `UserTenant`)

```python
# api/db/db_models.py
class UserTenant(DataBaseModel):
    id = StringField(max_length=32, primary_key=True)
    user_id = StringField(max_length=32, index=True)
    tenant_id = StringField(max_length=32, index=True)
    role = StringField(max_length=32)  # 'owner', 'admin', 'normal'
```

### Source References

- DB Models: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- User Service Role Methods: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33)
- Go User Tenant DAO: [`internal/dao/user_tenant.go`](file:///home/logan78/Desktop/ragflow/internal/dao/user_tenant.go)
