# Database Schema & Tables Specification

## Level 1: Conceptual Overview

The Database Schema defines all core tables, column types, primary keys, nullability constraints, defaults, and foreign key relations across MySQL, OceanBase, and PostgreSQL database engines.

---

## Level 2: Implementation Details

### Table Specifications

#### 1. `document` Table
Peewee model: [Document](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L894) | Go struct: `entity.Document`

```sql
CREATE TABLE `document` (
  `id` varchar(32) NOT NULL PRIMARY KEY,
  `thumbnail` longtext,
  `kb_id` varchar(256) NOT NULL,
  `parser_id` varchar(32) NOT NULL,
  `pipeline_id` varchar(32),
  `parser_config` longtext NOT NULL,
  `source_type` varchar(128) NOT NULL DEFAULT 'local',
  `type` varchar(32) NOT NULL,
  `created_by` varchar(32) NOT NULL,
  `name` varchar(255),
  `location` varchar(255),
  `size` bigint NOT NULL DEFAULT 0,
  `token_num` int NOT NULL DEFAULT 0,
  `chunk_num` int NOT NULL DEFAULT 0,
  `progress` float NOT NULL DEFAULT 0,
  `progress_msg` longtext,
  `process_begin_at` datetime,
  `process_duration` float NOT NULL DEFAULT 0,
  `suffix` varchar(32) NOT NULL,
  `content_hash` varchar(32) DEFAULT '',
  `run` varchar(1) DEFAULT '0',
  `status` varchar(1) DEFAULT '1',
  `create_time` bigint,
  `update_time` bigint,
  INDEX `idx_doc_kb_id` (`kb_id`),
  INDEX `idx_doc_parser_id` (`parser_id`),
  INDEX `idx_doc_status` (`status`)
);
```

#### 2. `task` Table
Peewee model: [Task](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L1002) | Go DAO: [IngestionTaskDAO](file:///home/logan78/Desktop/ragflow/internal/dao/ingestion.go#L30)

```sql
CREATE TABLE `task` (
  `id` varchar(32) NOT NULL PRIMARY KEY,
  `doc_id` varchar(32) NOT NULL,
  `from_page` int NOT NULL DEFAULT 0,
  `to_page` int NOT NULL DEFAULT 1000000,
  `task_type` varchar(32) NOT NULL DEFAULT '',
  `priority` int NOT NULL DEFAULT 0,
  `begin_at` datetime,
  `process_duration` float NOT NULL DEFAULT 0,
  `progress` float NOT NULL DEFAULT 0,
  `progress_msg` longtext,
  `retry_count` int NOT NULL DEFAULT 0,
  `digest` longtext,
  `chunk_ids` longtext,
  `create_time` bigint,
  `update_time` bigint,
  INDEX `idx_task_doc_id` (`doc_id`),
  INDEX `idx_task_progress` (`progress`)
);
```

#### 3. `knowledgebase` Table
Peewee model: [Knowledgebase](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L837) | Go DAO: [KnowledgebaseDAO](file:///home/logan78/Desktop/ragflow/internal/dao/kb.go#L30)

```sql
CREATE TABLE `knowledgebase` (
  `id` varchar(32) NOT NULL PRIMARY KEY,
  `avatar` longtext,
  `tenant_id` varchar(32) NOT NULL,
  `name` varchar(128) NOT NULL,
  `language` varchar(32) DEFAULT 'English',
  `description` longtext,
  `embd_id` varchar(128) NOT NULL,
  `parser_id` varchar(32) NOT NULL DEFAULT 'naive',
  `parser_config` longtext NOT NULL,
  `status` varchar(1) DEFAULT '1',
  INDEX `idx_kb_tenant_id` (`tenant_id`),
  INDEX `idx_kb_name` (`name`)
);
```
