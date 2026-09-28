# Subpart 01: KB Model and CRUD APIs

## 1. Objective
To implement the database tables and REST API for Knowledge Base management, ensuring strict tenant isolation.

## 2. Documentation Basis
*   `docs/04-api/knowledge-base.md`: DOCUMENTED - The REST contracts for managing KBs.

## 3. Prerequisites
*   `Part-03-Authentication-Tenancy` completed.

## 4. Components to Implement
*   **KnowledgeBase Model**: The ORM representation.
*   **CRUD API Router**: The HTTP endpoints.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the Model

#### Purpose
Establish the physical table.

#### Prerequisites
ORM initialized.

#### Implementation Scope
Create a `KnowledgeBase` model. Fields: `id` (UUID), `tenant_id` (UUID, Foreign Key), `name` (String), `description` (String), `created_at` (Timestamp). Run the database migration.

#### Inputs
Code definition.

#### Outputs
A new table in the database.

#### Expected Result
Database is ready to store KBs.

#### Proceed When
Migration executes successfully.

### Step 02: Build the Create API

#### Purpose
Allow users to create a KB.

#### Prerequisites
Step 01.

#### Implementation Scope
Implement `POST /api/knowledge-base`. Protect it with the Auth Middleware. Accept `{ name, description }` in the JSON body. Extract `tenant_id` from the middleware context. Insert the new record.

#### Inputs
`POST` request with JSON body.

#### Outputs
`200 OK` with the created KB object (including its generated ID).

#### Expected Result
Users can create KBs.

#### Proceed When
API returns success and DB contains the record.

### Step 03: Build the List API

#### Purpose
Allow users to see their KBs.

#### Prerequisites
Step 02.

#### Implementation Scope
Implement `GET /api/knowledge-base`. Protect it with Auth Middleware. Query the database for all KBs `WHERE tenant_id = <context.tenant_id>`.

#### Outputs
JSON array of KB objects.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Create KBs under two different users. Call the API as User 1. Ensure User 2's KBs are not in the response.

#### Proceed When
Tenant isolation is proven.

### Step 04: Build Delete API

#### Purpose
Allow users to remove KBs.

#### Prerequisites
Step 03.

#### Implementation Scope
Implement `DELETE /api/knowledge-base/{id}`. **CRITICAL**: The DELETE query MUST include `WHERE id = {id} AND tenant_id = <context.tenant_id>`. If no rows are deleted, return 404.

#### Expected Result
Users can delete only their own KBs.

#### Proceed When
API works and prevents deleting other tenants' KBs.

