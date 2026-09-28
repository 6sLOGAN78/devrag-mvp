# Subpart 03: Multi-Tenancy Middleware

## 1. Objective
To build the most critical security boundary in the application. This middleware intercepts incoming API requests, validates the JWT, extracts the `tenant_id`, and ensures that all subsequent database operations are strictly scoped to that tenant.

## 2. Documentation Basis
*   `ragflow-docs/16-auth/multi-tenancy.md`: DOCUMENTED - Strict data isolation is mandatory in RAGFlow.

## 3. Prerequisites
*   `02-Auth-APIs` (You need a JWT to test this).

## 4. Components to Implement
*   **Auth Middleware**: HTTP request interceptor.
*   **Tenant Context Context/Scoped Session**: A mechanism to pass the `tenant_id` down to the ORM layer safely.

## 5. Detailed Sequential Implementation Steps

### Step 01: Implement Auth Interceptor

#### Purpose
Block unauthenticated requests.

#### Prerequisites
JWT utilities.

#### Implementation Scope
Write an HTTP middleware function. It should read the `Authorization: Bearer <token>` header. If missing, return 401. If invalid/expired, return 401. If valid, decode it and attach the `user_id` and `tenant_id` to the request object (or thread-local context).

#### Inputs
HTTP Headers.

#### Outputs
Mutated Request object or Context.

#### Expected Result
Protected routes are inaccessible without a token.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Create a dummy protected route `GET /api/me`. Test it with and without a token.

#### Proceed When
Authentication enforcement works perfectly.

### Step 02: Implement ORM Tenancy Scoping

#### Purpose
Prevent cross-tenant data access automatically.

#### Prerequisites
Step 01.

#### Implementation Scope
This depends heavily on your chosen framework. 
*   *Option A*: Write a global ORM interceptor that automatically appends `WHERE tenant_id = ?` to every SELECT/UPDATE/DELETE query based on the context.
*   *Option B*: If Option A is too complex in your framework, establish a strict pattern where the API route extracts the `tenant_id` from the request and manually passes it into every repository/database call.

*IMPLEMENTATION DECISION*: Option B is often safer and easier to debug for manual MVP creation, though Option A is more robust against developer error.

#### Expected Result
It is impossible to query another tenant's data.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Register two different users (User A, User B). Create a dummy record tied to User A's tenant. Attempt to fetch it using User B's token.

#### Proceed When
The system returns a 404 or empty list when User B queries User A's data.

