# 05-Nginx-Proxy

## 1. Objective
To configure an NGINX reverse proxy to act as the edge router for the devRAG application. NGINX will serve the static frontend assets and securely route API traffic to the backend server.

## 2. Documentation Basis
*   `docs/18-deployment/deployment-overview.md`: DOCUMENTED - Nginx Reverse Proxy sits at the edge on ports 80/443.
*   `docs/22-code-tracing/frontend-to-backend.md`: DOCUMENTED - Proxies HTTP / SSE Requests from UI to backend.
*   `docs/03-backend/backend-architecture.md`: INFERRED - Originally used to split traffic between Go and Python. In devRAG, it routes all `/api` to the unified backend.

## 3. Prerequisites
*   Docker and Docker Compose installed.
*   The Application Backend (Part 02) running on an internal Docker network.

## 4. Components to Implement
*   **NGINX Configuration**: `nginx.conf` detailing the `server` block and `location` proxy rules.
*   **Docker Compose Addition**: Add an `nginx` service to `docker-compose-base.yml`.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define NGINX Configuration

#### Purpose
Create the routing rules that dictate how NGINX handles incoming web traffic.

#### Prerequisites
None.

#### Implementation Scope
Create `docker/nginx/nginx.conf`. Define an `events` block and an `http` block containing a `server` listening on port 80.
Define two main `location` blocks:
1. `location /`: Serve frontend static files (from a mounted directory or upstream frontend container).
2. `location /api/`: `proxy_pass` traffic to the backend API container.

Ensure headers like `Host`, `X-Real-IP`, and `X-Forwarded-For` are correctly passed. For SSE (Chat Streaming) support, ensure `proxy_buffering off;` is set in the `/api/` block or globally.

#### Inputs
An NGINX configuration file.

#### Processing and Behavior
When NGINX receives a request, it matches the URI path against the location blocks and forwards it appropriately.

#### Outputs
A `.conf` file ready to be mounted into a Docker container.

#### Dependencies
None.

#### Expected Result
The configuration syntax is valid.

#### Verification
Can be verified when running the container.

#### Acceptance Criteria
* [ ] The config correctly targets `/api` paths and `/` paths separately.
* [ ] Proxy buffering is disabled for Server-Sent Events (SSE) compatibility.

#### Proceed When
The configuration file is written.

---

### Step 02: Add NGINX to Docker Compose

#### Purpose
Launch the NGINX edge router alongside the rest of the devRAG infrastructure.

#### Prerequisites
Step 01.

#### Implementation Scope
Modify `docker/docker-compose-base.yml`. Add a new service named `nginx` using the `nginx:alpine` image.
Mount `docker/nginx/nginx.conf` to `/etc/nginx/nginx.conf` inside the container.
Expose port `80` to the host machine (e.g., `80:80`).
Ensure it joins the `ragflow` Docker network so it can resolve the backend container by name (e.g., `proxy_pass http://api:8000;`).

#### Inputs
Docker Compose YAML modifications.

#### Processing and Behavior
Docker pulls the NGINX image and runs it, exposing port 80 to the host.

#### Outputs
A running NGINX container intercepting host traffic on port 80.

#### Dependencies
Docker Engine.

#### Expected Result
Visiting `http://localhost:80` hits the NGINX container.

#### Verification
Run `docker compose up -d nginx`. 
Execute `curl -I http://localhost` to confirm NGINX is responding (it may return a 502 Bad Gateway if the backend isn't up, which proves NGINX is working).

#### Acceptance Criteria
* [ ] NGINX container starts successfully.
* [ ] Port 80 is accessible from the host.

#### Proceed When
`docker ps` shows the NGINX container is running and healthy.
