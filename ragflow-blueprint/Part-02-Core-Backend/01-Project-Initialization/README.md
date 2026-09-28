# Subpart 01: Project Initialization

## 1. Objective
To scaffold the basic directory structure of the backend application and expose a minimal web server that can accept HTTP requests.

## 2. Documentation Basis
*   `ragflow-docs/03-backend/architecture.md`: IMPLEMENTATION DECISION - RAGFlow uses Go and Python. You are initializing a unified backend project here using **both** languages (Python with Quart and Go with Gin, just like the original codebase).

## 3. Prerequisites
*   Python 3.x and Go 1.20+ installed locally.

## 4. Components to Implement
*   **Dependency Manager**: `requirements.txt` (Python) and `go.mod` (Go).
*   **Web Framework Entrypoints**: Main scripts (`api/ragflow_server.py` and `cmd/ragflow_server.go`).
*   **Health Route**: A basic GET handler in both frameworks.

## 5. Detailed Sequential Implementation Steps

### Step 01: Initialize the Python Backend

#### Purpose
Establish the Python machine learning and API backend.

#### Implementation Scope
Initialize the dependency manager and install the web framework (Quart) alongside essential adapters.

#### Inputs
Create a `requirements.txt` file in the root:
```txt
quart
peewee
pymysql
minio
```
Run `pip install -r requirements.txt`.

#### Outputs
A configured Python environment.

---

### Step 02: Initialize the Go Backend

#### Purpose
Establish the high-performance Go API backend.

#### Implementation Scope
Initialize the Go module and install the `gin` web framework (used in the original source code).

#### Inputs
Run `go mod init devrag`.
Run `go get github.com/gin-gonic/gin`.

#### Outputs
A configured `go.mod` file.

---

### Step 03: Build the Health Endpoints

#### Purpose
Prove the HTTP servers can boot and accept requests.

#### Implementation Scope
Write the entrypoint scripts. Add a route for `GET /health` that returns a simple JSON object: `{"status": "ok"}`. 
We will configure Python to run on port `9380` and Go to run on port `9381`.

#### Inputs (Python)
Create `api/ragflow_server.py`:
```python
from quart import Quart, jsonify

app = Quart(__name__)

@app.route('/health', methods=['GET'])
async def health():
    return jsonify({"status": "ok", "engine": "python"})

@app.route('/api/health', methods=['GET'])
async def api_health():
    return jsonify({"status": "ok", "engine": "python"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9380)
```

#### Inputs (Go)
Create `cmd/ragflow_server.go`:
```go
package main

import (
	"net/http"
	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "engine": "go"})
	})

	r.GET("/api/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "engine": "go"})
	})

	r.Run("0.0.0.0:9381")
}
```

#### Verification
Start both servers: 
1. `python api/ragflow_server.py`
2. `go run cmd/ragflow_server.go`

Run `curl http://localhost:9380/health` (Python) and `curl http://localhost:9381/health` (Go).

#### Acceptance Criteria
* [ ] You receive the JSON response `{"status": "ok", "engine": "python"}` and `{"status": "ok", "engine": "go"}`.
