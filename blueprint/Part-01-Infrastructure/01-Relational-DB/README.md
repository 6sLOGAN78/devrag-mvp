# Subpart 01: Relational Database Setup

## 1. Objective
To provision a relational database container (MySQL or PostgreSQL) that serves as the central transactional state store for Users, Tenants, Documents, and other entities in the RAGFlow application. This allows the backend to persist the application state securely.

## 2. Documentation Basis
*   `docs/08-database/architecture.md`: Confirms the use of a relational store (MySQL) for metadata.
*   **DOCUMENTED**: Exact Docker compose configuration, `.env` files, and `init.sql`.
*   **DOCUMENTED**: Peewee ORM definitions for User, Tenant, and Document tables.

## 3. Prerequisites
*   Docker and Docker Compose installed locally.
*   Python environment setup for backend development (for ORM models).

## 4. Components to Implement
*   **Docker Service Definition**: A `docker-compose-base.yml` block configuring MySQL 8.0.
*   **Environment Configuration**: A `.env` file containing database credentials.
*   **Initialization Script**: `init.sql` script to create the `rag_flow` database.
*   **ORM Models**: Python file `api/db/db_models.py` defining the Peewee classes.

## 5. Detailed Sequential Implementation Steps

### Step 01: Define Docker Configuration and Environment

#### Purpose
Establish the running instance of the MySQL relational database with the correct configuration and persistent volumes.

#### Prerequisites
Docker installed.

#### Implementation Scope
1.  Create `docker/.env` and add the required `MYSQL_HOST`, `MYSQL_PORT`, `EXPOSE_MYSQL_PORT`, `MYSQL_DBNAME`, and `MYSQL_PASSWORD` variables.
2.  Create `docker/docker-compose-base.yml` and define the `mysql` service using `mysql:8.0.40`. Mount the data volume and init script. Set the healthcheck and configuration flags.

#### Inputs
Environment variables (save as `docker/.env`):
```ini
MYSQL_HOST=mysql
MYSQL_PORT=3306
EXPOSE_MYSQL_PORT=3306
MYSQL_DBNAME=rag_flow
MYSQL_PASSWORD=infini_rag_flow
```

Docker Compose (save as `docker/docker-compose-base.yml`):
```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0.40
    container_name: ragflow-mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DBNAME}
    command:
      --max_connections=1000
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --default-authentication-plugin=mysql_native_password
    ports:
      - "${EXPOSE_MYSQL_PORT}:${MYSQL_PORT}"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  mysql_data:
```

#### Processing and Behavior
Docker engine pulls the image, reads the `.env` file, and initializes the database files on the mounted `mysql_data` volume.

#### Outputs
A running MySQL container exposing port 3306.

#### Dependencies
*   Docker & Docker Compose.

#### Expected Result
The database is up, accepting TCP connections, and successfully passing its healthcheck.

#### Verification
Run `docker ps` to ensure the container is healthy.

#### Acceptance Criteria
* [ ] Container successfully boots without crashing.
* [ ] Healthcheck passes (`healthy` status in `docker ps`).

#### Proceed When
The container is running steadily.

---

### Step 02: Database Initialization

#### Purpose
Ensure the core application database (`rag_flow`) exists upon startup.

#### Prerequisites
Step 01.

#### Implementation Scope
Create `docker/init.sql` and mount it to `/data/application/init.sql` in the container.

#### Inputs
SQL script content:
```sql
CREATE DATABASE IF NOT EXISTS rag_flow;
USE rag_flow;
```

#### Processing and Behavior
The MySQL container executes this script automatically on first initialization to create the database schema.

#### Outputs
An initialized `rag_flow` database within MySQL.

#### Dependencies
MySQL Service.

#### Expected Result
The `rag_flow` database is available for connections.

#### Verification
Connect using `mysql` or `psql` to check database access:
```bash
mysql -h 127.0.0.1 -P 3306 -uroot -pinfini_rag_flow -e "SELECT 1; USE rag_flow;"
```

#### Acceptance Criteria
* [ ] The database `rag_flow` exists and is accessible using the configured root credentials.

#### Proceed When
You can successfully execute the verification query against the database from your host machine.

---

### Step 03: Define ORM Models

#### Purpose
Map the relational database tables to Python classes to enable the backend to persist and read data.

#### Prerequisites
Step 02.

#### Implementation Scope
You will create `api/db/db_models.py`. 
You will initialize a standard Peewee database connection to MySQL. 
You will define the `User`, `Tenant`, and `Document` classes inheriting from a base `DataBaseModel`.

By referencing the original RAGFlow source, here is the simplified, understandable version of the models you need to implement.

#### Inputs
Open your code editor and create `api/db/db_models.py` with this exact code:

```python
from peewee import *

# 1. Initialize the database connection
db = MySQLDatabase(
    'rag_flow',
    user='root',
    password='infini_rag_flow',
    host='127.0.0.1',
    port=3306
)

# 2. Define the Base Model that binds to the database
class DataBaseModel(Model):
    class Meta:
        database = db

# 3. Define the User Model
class User(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    access_token = CharField(max_length=255, null=True, index=True)
    nickname = CharField(max_length=100, null=False, index=True)
    password = CharField(max_length=255, null=True, index=True)
    email = CharField(max_length=255, null=False, unique=True)
    avatar = TextField(null=True)
    language = CharField(max_length=32, null=True, default="English")
    timezone = CharField(max_length=64, null=True, default="UTC+8\tAsia/Shanghai")
    
    class Meta:
        table_name = 'user'

# 4. Define the Tenant Model
class Tenant(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    name = CharField(max_length=100, null=True, index=True)
    public_key = CharField(max_length=255, null=True, index=True)
    llm_id = CharField(max_length=128, null=False, index=True)
    embd_id = CharField(max_length=128, null=False, index=True)
    
    class Meta:
        table_name = 'tenant'

# 5. Define the Document Model
class Document(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    thumbnail = TextField(null=True)
    kb_id = CharField(max_length=256, null=False, index=True)
    parser_id = CharField(max_length=32, null=False, index=True)
    source_type = CharField(max_length=128, null=False, default='local')
    type = CharField(max_length=32, null=False)
    created_by = CharField(max_length=32, null=False)
    name = CharField(max_length=255, null=True)
    location = CharField(max_length=255, null=True)
    size = BigIntegerField(default=0)
    token_num = IntegerField(default=0)
    chunk_num = IntegerField(default=0)
    progress = FloatField(default=0.0)
    progress_msg = TextField(null=True)
    status = CharField(max_length=1, null=True, default='1', index=True)
    
    class Meta:
        table_name = 'document'
```

#### Processing and Behavior
Peewee translates these Python classes into SQL queries. When you call `.create_tables()`, Peewee reads the fields (`CharField`, `TextField`) and executes `CREATE TABLE` commands.

#### Outputs
A python file containing your database models.

#### Dependencies
Run `pip install peewee pymysql` in your virtual environment.

#### Expected Result
The backend can successfully import and interact with these models.

#### Verification
Create a temporary script called `test_db.py` in your project root:
```python
from api.db.db_models import db, User, Tenant, Document

try:
    db.connect()
    db.create_tables([User, Tenant, Document])
    print("Successfully connected and created all tables!")
except Exception as e:
    print(f"Error: {e}")
```
Run `python test_db.py`.

#### Acceptance Criteria
* [ ] Terminal outputs "Successfully connected and created all tables!"
* [ ] Connecting to your MySQL container using a GUI (like DBeaver) or CLI shows the `user`, `tenant`, and `document` tables exist.

#### Proceed When
You have written the Python code, understood the Peewee field mappings, and verified the tables are successfully created in MySQL.
