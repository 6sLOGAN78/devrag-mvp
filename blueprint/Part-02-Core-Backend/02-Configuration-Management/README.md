# Subpart 02: Configuration Management

## 1. Objective
To implement a secure, central mechanism for the application to load environment variables (like database passwords and API keys) rather than hardcoding them in the source code.

## 2. Documentation Basis
*   `ragflow-docs/03-backend/architecture.md`: INFERRED - Standard backend security practice. RAGFlow relies on a three-step Template Replacement Mechanism during startup to resolve `.env` variables into a literal YAML file that the backends parse.

## 3. Prerequisites
*   `Part-02-Core-Backend/01-Project-Initialization` completed.

## 4. Components to Implement
*   **Template Config**: `conf/service_conf.yaml.template` referencing env vars.
*   **Env Loader Script**: `generate_conf.sh` to inject `.env` into the template.
*   **Config Singleton (Python & Go)**: A centralized configuration object that parses the YAML and fails fast.

## 5. Detailed Sequential Implementation Steps

### Step 01: Implement the Config Loader Mechanism

#### Purpose
Centralize credential management into a single resolved YAML file without hardcoding.

#### Implementation Scope
1. Make sure your `docker/.env` has all necessary variables (`MYSQL_HOST=127.0.0.1`, `REDIS_PORT=6379`, etc).
2. Create `conf/service_conf.yaml.template` using bash variable syntax.
3. Create an execution script `generate_conf.sh` that sources `.env` and runs `envsubst`.

#### Inputs
Create `conf/service_conf.yaml.template`:
```yaml
mysql:
  host: ${MYSQL_HOST}
  port: ${MYSQL_PORT}
  user: root
  password: ${MYSQL_PASSWORD}
  db: ${MYSQL_DBNAME}

redis:
  url: redis://:${REDIS_PASSWORD}@127.0.0.1:${REDIS_PORT}/0

minio:
  endpoint: 127.0.0.1:${MINIO_PORT}
  user: ${MINIO_USER}
  password: ${MINIO_PASSWORD}
```

Create `generate_conf.sh`:
```bash
#!/bin/bash
set -a
source docker/.env
set +a
envsubst < conf/service_conf.yaml.template > conf/service_conf.yaml
```
Run `chmod +x generate_conf.sh` and execute it.

#### Outputs
A literal `conf/service_conf.yaml` file containing the injected secrets.

---

### Step 02: Implement Python Configuration Singleton

#### Implementation Scope
Create `api/config.py` that parses the generated YAML file.

#### Inputs
```python
import yaml
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '../conf/service_conf.yaml')

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("Configuration file not found. Please run generate_conf.sh first.")
        
    with open(CONFIG_PATH, 'r') as file:
        config = yaml.safe_load(file)
        
    # Fail-Fast Validation
    if not config.get('mysql', {}).get('password'):
        raise ValueError("CRITICAL: mysql.password is missing in configuration! Refusing to start.")
        
    return config

# Singleton instance
CONF = load_config()
```

---

### Step 03: Implement Go Configuration Singleton

#### Implementation Scope
Create `cmd/config.go` that parses the generated YAML file.

#### Inputs
```go
package main

import (
	"fmt"
	"os"
	"gopkg.in/yaml.v3"
)

type Config struct {
	MySQL struct {
		Host     string `yaml:"host"`
		Port     string `yaml:"port"`
		User     string `yaml:"user"`
		Password string `yaml:"password"`
		DB       string `yaml:"db"`
	} `yaml:"mysql"`
    // ... Redis and Minio structs
}

var CONF *Config

func LoadConfig() {
	path := "conf/service_conf.yaml"
	data, err := os.ReadFile(path)
	if err != nil {
		panic("Configuration file not found. Please run generate_conf.sh first.")
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		panic(err)
	}

	// Fail-Fast Validation
	if config.MySQL.Password == "" {
		panic("CRITICAL: mysql.password is missing in configuration! Refusing to start.")
	}

	CONF = &config
}
```

#### Expected Result
Both backend layers can securely parse the generated YAML config and refuse to run in an invalid state.

#### Verification
Rename your `.env` file or remove a password from `service_conf.yaml` and test the fail-fast validation in both languages. They should crash immediately.
