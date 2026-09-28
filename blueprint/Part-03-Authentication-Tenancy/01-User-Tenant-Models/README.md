# Subpart 01: User & Tenant Models

## 1. Objective
To define the relational database schemas for Users and Tenants using your ORM, and to apply these migrations to the database.

## 2. Documentation Basis
*   `docs/08-database/schema.md`: INFERRED - The basic structural relationship where a User belongs to a Tenant.

## 3. Prerequisites
*   Part 02 completed (ORM connected).

## 4. Components to Implement
*   **Tenant Model**: Represents a workspace.
*   **User Model**: Represents an identity.
*   **Migration Script**: Translates the ORM models into SQL tables.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define Models

#### Purpose
Map the required schema to application objects.

#### Prerequisites
ORM initialized.

#### Implementation Scope
Create a `Tenant` model with fields: `id` (UUID), `name` (String), `created_at` (Timestamp).
Create a `User` model with fields: `id` (UUID), `tenant_id` (UUID, Foreign Key to Tenant), `email` (String, Unique), `password_hash` (String), `created_at` (Timestamp).

#### Inputs
Code definitions.

#### Processing and Behavior
The ORM parses the relationships.

#### Outputs
Model classes.

#### Expected Result
Models compile without syntax errors.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Code linting.

#### Proceed When
Models are defined accurately.

### Step 02: Run Database Migrations

#### Purpose
Create the physical tables in the Relational Database.

#### Prerequisites
Step 01.

#### Implementation Scope
Use your ORM's migration tool (e.g., Alembic for Python, TypeORM CLI for Node) to generate a migration script and apply it to the database.

#### Inputs
Terminal migration commands.

#### Outputs
SQL `CREATE TABLE` execution.

#### Dependencies
Relational DB running.

#### Expected Result
The database now has `users` and `tenants` tables.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Use a GUI client (like DBeaver) to inspect the database. Verify the tables exist and the foreign key relationship is correct.

#### Proceed When
The tables exist in the database.

