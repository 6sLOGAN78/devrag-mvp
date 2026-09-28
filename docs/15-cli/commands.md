# CLI REPL Command Catalog & Argument Specifications

## Level 1: Conceptual Explanation

`ragflow-cli` features a SQL-like domain-specific language (DSL) alongside traditional UNIX shell commands. The grammar is parsed using a hand-written recursive descent parser ([`internal/cli/parser.go`](file:///home/logan78/Desktop/ragflow/internal/cli/parser.go)) and scanner ([`internal/cli/lexer.go`](file:///home/logan78/Desktop/ragflow/internal/cli/lexer.go)). Commands are segregated into **User Operations**, **Virtual Filesystem Navigation**, **Admin Server Management**, and **Meta Controls**.

---

## Level 2: Implementation Details & Command Catalog

### 1. User & Dataset Commands (`internal/cli/user_parser.go` & `user_command.go`)

#### Authentication & Session Management
- **`LOGIN USER '<email>' [PASSWORD '<password>']`**
  - *Description*: Authenticates user against API server (`POST /v1/user/login`) and stores returned JWT access token.
  - *Source Handler*: [`parseAPILoginUser`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L19-L53) -> [`handleAPILoginUser`](file:///home/logan78/Desktop/ragflow/internal/cli/user_command.go#L80)
- **`LOGOUT`**
  - *Description*: Clears current session credentials.
  - *Source Handler*: [`parseAPILogout`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L55-L63)
- **`REGISTER USER '<email>' AS '<nickname>' PASSWORD '<password>'`**
  - *Description*: Registers a new RAGFlow user account (`POST /v1/user/register`).
  - *Source Handler*: [`parseAPIRegister`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L75-L100)

#### Dataset Management
- **`CREATE DATASET '<name>' [WITH EMBEDDING '<model_name>'] [PARSER '<parser_id>']`**
  - *Description*: Creates a knowledge base dataset (`POST /v1/dataset/create`).
  - *Source Handler*: [`parseAPICreateDataset`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L120)
- **`LIST DATASETS [LIMIT <n>]`**
  - *Description*: Returns paginated list of user knowledge bases (`GET /v1/dataset/list`).
- **`DROP DATASET '<name>'`**
  - *Description*: Deletes a specified knowledge base (`POST /v1/dataset/rm`).
- **`SHOW DATASET '<name>'`**
  - *Description*: Fetches dataset metadata and configuration (`GET /v1/dataset/detail`).

#### Document & Chunk Operations
- **`IMPORT FILE '<path>' INTO DATASET '<dataset_name>' [PARSER '<parser_type>']`**
  - *Description*: Uploads local document file into target dataset (`POST /api/v1/documents/upload`).
- **`PARSE DOCUMENT '<doc_id>' IN DATASET '<dataset_name>'`**
  - *Description*: Triggers async chunking and embedding execution task (`POST /api/v1/datasets/<dataset_id>/documents/parse`).
- **`LIST DOCUMENTS IN DATASET '<dataset_name>'`**
  - *Description*: Lists documents inside a dataset (`POST /api/v1/datasets/<dataset_id>/documents`).
- **`LIST CHUNKS OF DOCUMENT '<doc_id>' IN DATASET '<dataset_name>'`**
  - *Description*: Displays chunked text segments and vector index status (`POST /v1/chunk/list`).

#### Retrieval & Search Engine DSL
- **`SEARCH '<query>' ON DATASETS '<ds1>' ['<ds2>'] [WITH top_k <k> similarity_threshold <t> vector_similarity_weight <w> keyword <bool>]`**
  - *Description*: Executes hybrid semantic vector + keyword search over specified datasets (`POST /v1/api/retrieval`).
  - *Source Handler*: [`parseAPISearch`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L1200)

#### Model Provider Settings
- **`SET DEFAULT LLM '<model_name>'`** / **`RESET DEFAULT LLM`**
  - *Description*: Sets or resets default LLM provider configuration (`POST /v1/user/set_tenant_info`).
- **`SET DEFAULT EMBEDDING '<model_name>'`** / **`RESET DEFAULT EMBEDDING`**
  - *Description*: Sets or resets default vector embedding model.

---

### 2. Virtual Filesystem (VFS) Commands (`internal/cli/filesystem/*`)

The Virtual Filesystem maps REST endpoints into UNIX directory operations:

| VFS Command | Syntax & Options | Description | Backend Endpoint | Source Link |
| :--- | :--- | :--- | :--- | :--- |
| `ls` | `ls [path] [-n limit]` | List datasets (`/datasets`) or document files (`/datasets/{name}`) | `GET /v1/dataset/list` | [`dataset.go:L50`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/dataset.go#L50) |
| `cat` | `cat <path>` | Display raw text content of file node | `GET /api/v1/documents/<doc_id>/preview` | [`file.go:L80`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/file.go#L80) |
| `mkdir` | `mkdir <dataset_name>` | Create new dataset directory | `POST /v1/dataset/create` | [`dataset.go:L120`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/dataset.go#L120) |
| `rm` | `rm <path>` | Delete dataset directory or document file | `POST /v1/dataset/rm` | [`dataset.go:L180`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/dataset.go#L180) |
| `search` | `search "<query>" [path]` | Perform vector retrieval on path context | `POST /v1/api/retrieval` | [`engine.go:L110`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/engine.go#L110) |
| `skill` | `skill install/uninstall <id>` | Manage agent tool skill packages | `/v1/skill/*` | [`skill.go:L40`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/skill.go#L40) |

---

### 3. Administrative Commands (`internal/cli/admin_parser.go` & `admin_command.go`)

Operates under `--admin` CLI flag:

- **`LOGIN ADMIN '<email>' [PASSWORD '<password>']`**: Admin authentication (`POST /v1/admin/login`).
- **`LIST SERVICES`**: Queries status of backend server microservices (`GET /v1/admin/services`).
- **`SHOW SERVICE <service_id>`**: Returns detailed node health, PID, host IP, and memory stats.
- **`STARTUP SERVICE <service_id>`** / **`SHUTDOWN SERVICE <service_id>`** / **`RESTART SERVICE <service_id>`**: Controls backend daemon lifecycle.
- **`PING [STORE|ENGINE|MQ|CACHE]`**: Tests connectivity and latency to MySQL/MinIO (`STORE`), Elasticsearch/Infinity (`ENGINE`), NATS (`MQ`), or Redis (`CACHE`).
- **`LIST USERS`** / **`SHOW USER '<email>'`** / **`DROP USER '<email>'`**: Global user administration across multi-tenant workspaces.
- **`CREATE ROLE <name> DESCRIPTION '<desc>'`**: Security RBAC role management.
- **`GRANT <permission> ON <resource> TO ROLE <role_name>`**: Grants resource access privileges.

---

### 4. REPL Meta Commands (`internal/cli/parser.go`)

Meta commands start with a backslash (`\`) and control local REPL session parameters:

- **`\h`** or **`\help`**: Displays CLI command help and grammar reference.
- **`\q`** or **`\quit`**: Gracefully terminates REPL shell session.
- **`\c`** or **`\connect <host:port>`**: Switches target API server host connection.
- **`\mode <api|admin>`**: Toggles active CLI mode between User (`api`) and Admin (`admin`).
- **`\output <table|plain|json>`**: Toggles response renderer output format.

---

## References & Source Links

- [`internal/cli/user_parser.go:L1-L200`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go#L1-L200) - User SQL-like command parsers.
- [`internal/cli/user_command.go:L1-L300`](file:///home/logan78/Desktop/ragflow/internal/cli/user_command.go#L1-L300) - User command execution logic.
- [`internal/cli/admin_parser.go:L1-L150`](file:///home/logan78/Desktop/ragflow/internal/cli/admin_parser.go#L1-L150) - Admin command parsers.
- [`internal/cli/admin_command.go:L1-L200`](file:///home/logan78/Desktop/ragflow/internal/cli/admin_command.go#L1-L200) - Admin command execution logic.
- [`internal/cli/filesystem/engine.go:L1-L200`](file:///home/logan78/Desktop/ragflow/internal/cli/filesystem/engine.go#L1-L200) - Virtual Filesystem Engine execution.
