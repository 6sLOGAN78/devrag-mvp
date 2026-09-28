# Subpart 04: Vector Database Setup

## 1. Objective
To provision a Vector Database capable of storing high-dimensional embeddings and performing both dense vector similarity search and sparse keyword (BM25) search. This is the heart of the retrieval engine.

## 2. Documentation Basis
*   `ragflow-docs/08-database/vector-db.md`: Documents the necessity of a database supporting Hybrid Search. 
*   **DOCUMENTED**: The original application handles hybrid search via Elasticsearch (configured as `es01` in Docker).

## 3. Prerequisites
*   Docker and Docker Compose installed.

## 4. Components to Implement
*   **Vector DB Docker Service**: Addition to `docker-compose-base.yml`.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the Vector Database Container

#### Purpose
Start the Vector Database.

#### Prerequisites
`docker-compose-base.yml` exists.

#### Implementation Scope
Add an `elasticsearch` service to the compose file.

#### Inputs
Append the following variables to `docker/.env`:
```ini
ES_PORT=9200
ELASTIC_PASSWORD=infini_rag_flow_es
```

Append the following `es01` service block to `docker/docker-compose-base.yml`:
```yaml
  es01:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.3
    container_name: ragflow-es01
    environment:
      - node.name=es01
      - cluster.name=ragflow-cluster
      - discovery.type=single-node
      - ELASTIC_PASSWORD=${ELASTIC_PASSWORD}
      - bootstrap.memory_lock=true
      - xpack.security.enabled=true
      - xpack.security.http.ssl.enabled=false
      - cluster.routing.allocation.disk.watermark.low=5gb
      - cluster.routing.allocation.disk.watermark.high=3gb
      - cluster.routing.allocation.disk.watermark.flood_stage=2gb
      - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
    ulimits:
      memlock:
        soft: -1
        hard: -1
    volumes:
      - esdata01:/usr/share/elasticsearch/data
    ports:
      - "${ES_PORT}:9200"
    healthcheck:
      test: ["CMD-SHELL", "curl -s http://localhost:9200 -u elastic:${ELASTIC_PASSWORD} | grep -q 'You Know, for Search'"]
      interval: 10s
      timeout: 10s
      retries: 12
```
*(Also add `esdata01:` to the `volumes:` block at the bottom).*

#### Processing and Behavior
Docker pulls the image and starts the database engine, provisioning it for single-node development with vector capabilities out of the box.

#### Outputs
A running HTTP API on port 9200 (for Elasticsearch).

#### Dependencies
Docker.

#### Expected Result
The Vector DB is up and accepting REST requests.

#### Verification
Run `docker compose up -d es01`.
Run `docker ps` to verify health.

#### Acceptance Criteria
* [ ] Container starts.
* [ ] `curl -u elastic:infini_rag_flow_es http://localhost:9200` returns the cluster info ("You Know, for Search").

#### Proceed When
You receive a JSON response containing the cluster name, version, and tagline.
