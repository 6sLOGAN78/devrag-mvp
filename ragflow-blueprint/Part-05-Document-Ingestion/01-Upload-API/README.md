# Subpart 01: Upload API

## 1. Objective
To build the endpoint that accepts a file, stores it safely in S3, records its initial state in the database, and delegates the processing workload to a Redis queue.

## 2. Documentation Basis
*   `ragflow-docs/06-document-processing/upload.md`: DOCUMENTED - The upload and task delegation flow.

## 3. Prerequisites
*   `Part-04-KnowledgeBase-Management` (KB Model exists).
*   S3 and Redis clients configured (Part 02).

## 4. Components to Implement
*   **Document Model**: ORM representation of a file.
*   **Upload Controller**: `POST /api/document/upload`.
*   **Redis Publisher**: Utility to push JSON strings to a Redis List.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the Document Model

#### Purpose
Track the lifecycle of an uploaded file.

#### Prerequisites
ORM initialized.

#### Implementation Scope
Create a `Document` model. Fields: `id` (UUID), `tenant_id` (UUID), `knowledgebase_id` (UUID), `file_name` (String), `s3_path` (String), `status` (Enum: `UNSTART`, `RUNNING`, `DONE`, `FAILED`), `created_at`. Run migrations.

#### Outputs
A new table in the database.

#### Proceed When
Migration executes successfully.

### Step 02: Build the Upload Endpoint

#### Purpose
Accept the file from the user.

#### Prerequisites
Step 01.

#### Implementation Scope
Implement `POST /api/document/upload`. Accept `multipart/form-data` containing the file and a `kb_id` field. Protect with Auth Middleware. Validate that the user owns the `kb_id`.

#### Inputs
Multipart form data.

#### Processing and Behavior
Stream the file bytes directly to the MinIO client using a unique path (e.g., `tenant_id/kb_id/uuid-filename.txt`).

#### Outputs
File saved in MinIO bucket.

#### Proceed When
The file is verifiable in the MinIO web console.

### Step 03: Database and Queue Integration

#### Purpose
Register the file and delegate processing.

#### Prerequisites
Step 02.

#### Implementation Scope
Inside the upload endpoint (after S3 upload succeeds):
1. Insert a `Document` record with the `s3_path` and status `UNSTART`.
2. Construct a JSON payload: `{"document_id": "...", "tenant_id": "..."}`.
3. Push the payload to Redis: `LPUSH ragflow_TASK_EXE_QUEUE <json>`.
4. Return HTTP 200 OK to the client with the new Document ID.

#### Expected Result
The API responds quickly without waiting for text processing.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Use `redis-cli LRANGE ragflow_TASK_EXE_QUEUE 0 -1` to verify the payload exists.

#### Proceed When
The DB record and Redis task are created successfully.

