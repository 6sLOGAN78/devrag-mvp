# Subpart 02: Auth APIs

## 1. Objective
To implement the REST endpoints required for a user to create an account and authenticate themselves, yielding a JSON Web Token (JWT).

## 2. Documentation Basis
*   `docs/16-auth/authentication.md`: DOCUMENTED - Basic auth flows.

## 3. Prerequisites
*   `01-User-Tenant-Models` completed (Tables exist).

## 4. Components to Implement
*   **Password Hasher**: Utility to hash and verify passwords using `bcrypt` or `argon2`.
*   **JWT Service**: Utility to sign and decode JWTs.
*   **Registration API**: `POST /api/register`
*   **Login API**: `POST /api/login`

## 5. Detailed Sequential Implementation Steps

### Step 01: Build Utilities

#### Purpose
Implement security primitives.

#### Prerequisites
None.

#### Implementation Scope
Write helper functions to hash a password, verify a password, and generate a JWT using a secret key defined in your `.env`.

#### Inputs
Plaintext password, User ID, Tenant ID.

#### Outputs
Hashed string, Signed JWT string.

#### Expected Result
Helper functions are ready for use in APIs.

#### Proceed When
Unit tests for the helpers pass.

### Step 02: Registration Endpoint

#### Purpose
Allow users to create accounts.

#### Prerequisites
Step 01.

#### Implementation Scope
Implement `POST /api/register`. It should accept `{ email, password, tenant_name }`. 
1. Hash the password.
2. Create a new `Tenant` record.
3. Create a new `User` record linked to the tenant.
4. Return 200 OK.

#### Expected Result
User can register.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Send a POST request via Postman. Check the database to see the inserted rows.

#### Proceed When
Registration works end-to-end.

### Step 03: Login Endpoint

#### Purpose
Issue authentication tokens.

#### Prerequisites
Step 02.

#### Implementation Scope
Implement `POST /api/login`. Accept `{ email, password }`.
1. Find user by email. Return 401 if not found.
2. Verify password hash. Return 401 if invalid.
3. Generate JWT containing `user_id` and `tenant_id` in the payload.
4. Return `{ token: "..." }`.

#### Expected Result
User can retrieve a JWT.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Send a POST request via Postman. Decode the resulting JWT (e.g., at jwt.io) to ensure the payload contains the `tenant_id`.

#### Proceed When
Login returns a valid token.

