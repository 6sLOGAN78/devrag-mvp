# Subpart 04: Vector Database Setup

## 1. Objective
To provision a Vector Database capable of storing high-dimensional embeddings and performing both dense vector similarity search and sparse keyword (BM25) search. This is the heart of the retrieval engine.

## 2. Documentation Basis
*   `ragflow-docs/08-database/vector-db.md`: Documents the necessity of a database supporting Hybrid Search. Infinity and Elasticsearch are explicitly mentioned.

## 3. Prerequisites
*   Docker and Docker Compose installed.

## 4. Components to Implement
*   **Vector DB Docker Service**: Addition to `docker-compose.yml`.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the Vector Database Container

#### Purpose
Start the Vector Database.

#### Prerequisites
`docker-compose.yml` exists.

#### Implementation Scope
Add an `elasticsearch` (or `infinity`) service to the compose file. If using Elasticsearch, you must ensure it includes the plugins for vector fields (`dense_vector`) and BM25 tokenization. Define a persistent volume.

#### Inputs
JVM memory limits and cluster configuration environment variables.

#### Processing and Behavior
Docker pulls the image and starts the database engine.

#### Outputs
A running HTTP API on port 9200 (for Elasticsearch).

#### Dependencies
Docker.

#### Expected Result
The Vector DB is up and accepting REST requests.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Run `curl http://localhost:9200`.

#### Proceed When
You receive a JSON response containing the cluster name, version, and a tagline (e.g., "You Know, for Search").

