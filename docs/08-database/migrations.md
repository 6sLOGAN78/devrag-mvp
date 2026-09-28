# Database Migrations

## Level 1: Conceptual Overview

Schema migrations manage database DDL evolution across versions without data loss, executing column additions, type alterations, and index creation across MySQL, OceanBase, and PostgreSQL.

---

## Level 2: Implementation Details

### Database Migrator Enums

In [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L464-L468) and Go migration driver [internal/dao/migration.go](file:///home/logan78/Desktop/ragflow/internal/dao/migration.go#L20):

```python
class DatabaseMigrator(Enum):
    MYSQL = MySQLMigrator
    OCEANBASE = MySQLMigrator
    POSTGRES = PostgresqlMigrator
```

Example migration execution in Python:
```python
migrator = DatabaseMigrator[settings.DATABASE_TYPE.upper()].value(db)
migrate(
    migrator.add_column('document', 'content_hash', CharField(max_length=32, default='')),
)
```
