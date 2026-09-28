# Subpart 02: Task Workers

## 1. Objective
To build the background worker process that consumes ingestion tasks from Redis, manages the Document's state machine (`UNSTART` -> `RUNNING` -> `DONE`/`FAILED`), and orchestrates the processing logic.

## 2. Documentation Basis
*   `docs/10-cache-and-queues/workers.md`: DOCUMENTED - The worker polling mechanism.

## 3. Prerequisites
*   `Part-05/01-Upload-API` completed. Redis must contain tasks.

## 4. Components to Implement
*   **Worker Daemon**: A script running in an infinite loop, distinct from the HTTP API server.
*   **State Manager**: Logic to update the RDBMS.

## 5. Detailed Sequential Implementation Steps

### Step 01: Create the Worker Loop

#### Purpose
Establish the background consumer.

#### Prerequisites
Redis connection code.

#### Implementation Scope
Create a new entrypoint script (e.g., `worker.py` or `worker.js`). Initialize the ORM and Redis clients. Write an infinite `while` loop that calls a blocking pop (`BRPOP ragflow_TASK_EXE_QUEUE 0`) on the Redis queue.

#### Inputs
Tasks pushed by the Upload API.

#### Outputs
Task JSON string popped from the queue.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Run the worker script. Upload a file via the API. The worker terminal should print the JSON payload.

#### Proceed When
The worker successfully pops tasks.

### Step 02: Implement State Transitions

#### Purpose
Track processing progress in the DB.

#### Prerequisites
Step 01.

#### Implementation Scope
Upon popping a task, extract the `document_id`. 
1. Query the DB for the Document. If not found, skip.
2. Update the Document `status` to `RUNNING`.
3. Wrap the actual processing call (to be built in subpart 03) in a `try/catch` block.
4. On success, update `status` to `DONE`. On exception, update to `FAILED`.

#### Expected Result
The database reflects the lifecycle of the document accurately.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Upload a file. Since processing is just a placeholder, the status should instantly jump from `UNSTART` to `RUNNING` to `DONE`.

#### Proceed When
State transitions are robust.

