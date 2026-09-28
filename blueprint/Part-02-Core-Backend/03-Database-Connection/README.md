# Subpart 03: Database Connection

## 1. Objective
To establish a connection pool to the relational database using an Object-Relational Mapper (ORM) and verify that the backend can successfully talk to the infrastructure provisioned in Part 01.

## 2. Documentation Basis
*   `docs/08-database/schema.md`: INFERRED - An ORM is required to map the documented schemas to application objects securely without writing raw SQL.

## 3. Prerequisites
*   `Part-01-Infrastructure/01-Relational-DB` (The DB container must be running).
*   `Part-02-Core-Backend/02-Configuration-Management` (To provide the DB credentials).

## 4. Components to Implement
*   **ORM Initialization**: Installing and configuring the ORM library (e.g., SQLAlchemy, TypeORM, GORM).
*   **Connection Pool**: Establishing a persistent connection pool to the database.

## 5. Detailed Sequential Implementation Steps

### Step 01: Configure the ORM

#### Purpose
Connect the backend to the database.

#### Prerequisites
DB credentials loaded in config.

#### Implementation Scope
Install the ORM. Create a `database` module. Initialize the connection pool using the credentials from the config manager (`DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `DB_NAME`).

#### Inputs
Database credentials.

#### Processing and Behavior
The ORM attempts to negotiate a TCP connection with the running database container.

#### Outputs
An active connection pool object.

#### Dependencies
MySQL/Postgres container running on localhost.

#### Expected Result
The backend establishes a persistent connection to the database on startup.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Add a log statement upon successful connection. Start the application. Observe the logs.

#### Proceed When
The logs confirm a successful database connection.

### Step 02: Update Health Endpoint

#### Purpose
Allow external monitoring to verify DB health.

#### Prerequisites
Step 01.

#### Implementation Scope
Modify the `/health` endpoint created in Subpart 01. It should now execute a simple `SELECT 1` query via the ORM. If the query succeeds, return 200 OK. If it throws an exception, return 500 Internal Server Error.

#### Inputs
`GET /health`

#### Outputs
`{"status": "ok", "db": "connected"}`

#### Expected Result
The health endpoint truly reflects the state of the infrastructure.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Stop the database container (`docker stop <db_container>`). Hit `/health`. It should return 500. Start the container. Hit `/health`. It should return 200.

#### Proceed When
The health endpoint accurately reflects the database state.

