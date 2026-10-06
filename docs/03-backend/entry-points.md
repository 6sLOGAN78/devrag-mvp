# Backend Entry Points & Initialization

## Level 1: System Boot Sequence

The backend system boots via two main entry points: the **Go Server** (`cmd/ragflow_server.go`) and the **Python Server** (`api/ragflow_server.py`).

---

## Level 2: Comprehensive Boot & Thread Lifecycle

### 1. Go Engine Entry Point ([`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81))

#### Command-Line Flags
- `--api`: Starts the primary Gin API HTTP service.
- `--admin`: Starts the administration server.
- `--ingestor`: Starts the document chunk ingestion service.
- `--syncer`: Starts background synchronization services.
- `--migrate`: Executes database table migrations.

#### Initialization Sequence
```go
// cmd/ragflow_server.go:L141
engine := gin.New()
// 1. Add GinLogger and X-API-Source response headers
engine.Use(func(c *gin.Context) { c.Header("X-API-Source", "go"); c.Next() })
// 2. Setup health, auth, user, tenant, document, and searchbot routes
router.NewRouter(...).Setup(engine)
// 3. Bind HTTP port and start listening
```

---

### 2. Python ASGI Entry Point ([`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90))

#### Initialization Sequence
1. **Logger & Environment Init**:
   - Calls `init_root_logger("ragflow_server")` ([`api/ragflow_server.py:L92`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L92)).
   - Sets `LITELLM_LOCAL_MODEL_COST_MAP=True`.
2. **Database Initialization**:
   - Calls `init_web_db()` ([`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)) to create tables if missing.
   - Calls `init_web_data()` and `init_superuser()` if `--init-superuser` is specified.
3. **Plugin Loading**:
   - Executes `GlobalPluginManager.load_plugins()` ([`agent/plugin/__init__.py`](file:///home/logan78/Desktop/ragflow/agent/plugin)).
4. **Background Daemon Thread Dispatch**:
   - `update_progress` Thread ([`api/ragflow_server.py:L56`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L56)): Uses `RedisDistributedLock("update_progress")` to update document chunking progress across instances.
   - `chat_channels` Thread ([`api/channels/bootstrap.py`](file:///home/logan78/Desktop/ragflow/api/channels/bootstrap.py)): Launches chat channel bridges (DingTalk, Feishu, Telegram, WeChat).
5. **Quart Server Launch**:
   - Starts ASGI server on `settings.HOST_IP:settings.HOST_PORT` (`app.run`).

### Source File References

- Python Main Entry: [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)
- Python App Config: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
- Go Main Entry: [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)
- Go Router: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
