# Subpart 03: Database Connection

## 1. Objective
To establish a connection pool to the relational database using an Object-Relational Mapper (ORM) and verify that both the Python and Go backends can successfully talk to the infrastructure provisioned in Part 01.

## 2. Documentation Basis
*   `docs/08-database/schema.md`: INFERRED - An ORM is required to map the documented schemas to application objects securely without writing raw SQL.
*   The architecture implies a dual-backend setup where both Python and Go must connect to the same central database container using the credentials loaded from the configuration singleton.

## 3. Prerequisites
*   `Part-01-Infrastructure/01-Relational-DB` (The DB container must be running).
*   `Part-02-Core-Backend/02-Configuration-Management` (To provide the DB credentials via the configuration singleton).

## 4. Components to Implement
*   **ORM Initialization (Python)**: Configuring `playhouse.pool.PooledMySQLDatabase` using `api.config.CONF`.
*   **ORM Initialization (Go)**: Configuring `gorm.io/gorm` using `config.CONF`.
*   **Connection Pool**: Establishing persistent connections to MySQL on startup.

## 5. Detailed Sequential Implementation Steps

### Step 01: Configure the ORMs (Dual-Backend)

#### Purpose
Connect both the API backend (Python) and the high-performance API (Go) to the MySQL database.

#### Implementation Scope
**Python:** 
Update `api/db/db_models.py` to use `PooledMySQLDatabase` loaded dynamically:
```python
from peewee import *
from playhouse.pool import PooledMySQLDatabase
import sys
import os

# Import api.config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.config import CONF

mysql_conf = CONF['mysql']
db = PooledMySQLDatabase(
    mysql_conf.get('db', 'rag_flow'),
    max_connections=32,
    stale_timeout=300,
    user=mysql_conf.get('user', 'root'),
    password=mysql_conf['password'],
    host=mysql_conf.get('host', '127.0.0.1'),
    port=int(mysql_conf.get('port', 3306))
)
# ... models remain identical ...
```

**Go:**
Create `internal/dao/database.go` and use `gorm`:
```go
package dao

import (
	"fmt"
	"log"

	"devrag/internal/config"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

var DB *gorm.DB

func InitDB() {
	if config.CONF == nil {
		panic("Config not loaded before initializing DB")
	}

	mysqlConf := config.CONF.MySQL
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True&loc=Local",
		mysqlConf.User, mysqlConf.Password, mysqlConf.Host, mysqlConf.Port, mysqlConf.DB)

	var err error
	DB, err = gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		panic(fmt.Sprintf("Failed to connect to database: %v", err))
	}
	log.Println("Database connection successfully established (Go).")
}
```

---

### Step 02: Update System Health Endpoints

#### Purpose
Allow external monitoring to verify DB health via an API route.

#### Implementation Scope
**Python:**
Update `api/ragflow_server.py` to execute a simple probe query via the Peewee ORM:
```python
from api.db.db_models import db

def check_db():
    try:
        db.execute_sql("SELECT 1")
        return True, {"status": "ok", "elapsed": "0.0"}
    except Exception as e:
        return False, {"status": "nok", "error": str(e)}

@app.route('/api/health', methods=['GET'])
async def api_health():
    is_ok, db_status = check_db()
    return jsonify({
        "status": "ok" if is_ok else "nok",
        "engine": "python",
        "db": db_status
    })
```

**Go:**
Update `cmd/ragflow_server.go` to implement equivalent logic using GORM's `.Raw("SELECT 1")`:
```go
	r.GET("/api/health", func(c *gin.Context) {
		var result int
		err := dao.DB.Raw("SELECT 1").Scan(&result).Error

		dbStatus := gin.H{"status": "ok", "elapsed": "0.0"}
		systemStatus := "ok"

		if err != nil {
			dbStatus["status"] = "nok"
			dbStatus["error"] = err.Error()
			systemStatus = "nok"
		}

		c.JSON(http.StatusOK, gin.H{
			"status": systemStatus,
			"engine": "go",
			"db":     dbStatus,
		})
	})
```

#### Verification
Start the servers:
`PYTHONPATH=. python api/ragflow_server.py`
`go run cmd/ragflow_server.go`

Hit `curl http://localhost:9380/api/health` and `curl http://localhost:9381/api/health`.

#### Acceptance Criteria
* [ ] Both language stacks output `{"db":{"elapsed":"0.0","status":"ok"},"engine":"<lang>","status":"ok"}`.
