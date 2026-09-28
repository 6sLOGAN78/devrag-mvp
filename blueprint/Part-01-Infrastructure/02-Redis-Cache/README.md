# Subpart 02: Redis Cache Setup

## 1. Objective
To provision a Redis container that will act as the message broker for the asynchronous document processing workers and provide distributed locking mechanisms.

## 2. Documentation Basis
*   `ragflow-docs/10-cache-and-queues/redis.md`: Explicitly documents Redis as the backing store for `ragflow_TASK_EXE_QUEUE`.
*   **DOCUMENTED**: Redis is provisioned using the `valkey/valkey:8` image, requires a password, and is capped at 128mb with a `volatile-lru` eviction policy.

## 3. Prerequisites
*   Docker and Docker Compose installed.
*   `docker/docker-compose-base.yml` from `01-Relational-DB`.

## 4. Components to Implement
*   **Redis Docker Service**: Addition to the `docker-compose-base.yml` file configuring the Redis image.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define the Redis Container

#### Purpose
Establish the Redis instance for pub/sub and queue management.

#### Prerequisites
`docker-compose-base.yml` file exists.

#### Implementation Scope
Add a `redis` service block to the compose file. Use the `valkey/valkey:8` image. Set memory limits and configure the password from the `.env` file.

#### Inputs
Append the following variables to your `docker/.env` file:
```ini
REDIS_PORT=6380
REDIS_PASSWORD=infini_rag_flow_redis
```

Append the following `redis` service to your `docker/docker-compose-base.yml`:
```yaml
  redis:
    image: valkey/valkey:8
    container_name: ragflow-redis
    command: valkey-server --requirepass ${REDIS_PASSWORD} --maxmemory 128mb --maxmemory-policy volatile-lru
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```
*(Don't forget to add `redis_data:` to your `volumes:` block at the bottom of the file).*

#### Processing and Behavior
Docker engine starts the Redis server, limiting its memory overhead to ensure cache stability during large ingestions.

#### Outputs
A running container exposing port 6380.

#### Dependencies
Docker.

#### Expected Result
Redis is up and accepting connections.

#### Verification
Run `docker compose up -d redis`.
Run `docker ps` to verify health.

#### Acceptance Criteria
* [ ] Container successfully boots and shows `healthy`.

#### Proceed When
The container is running steadily.
