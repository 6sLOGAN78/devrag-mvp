"""System-level tables."""
from __future__ import annotations

import peewee

from api.db.models.base import BaseModel, current_timestamp_ms, timestamp_to_date

SCHEMA_VERSION_KEY = "schema.version"


class SystemSettings(BaseModel):
    name = peewee.CharField(max_length=128, primary_key=True)
    source = peewee.CharField(max_length=32, null=False, index=False)
    data_type = peewee.CharField(max_length=32, null=False, index=False)
    value = peewee.CharField(max_length=1024, null=False)

    class Meta:
        table_name = "system_settings"


def upsert_setting(name: str, value: str, source: str = "system", data_type: str = "string") -> None:
    """Insert or update one setting with a single parameterised INSERT ... ON DUPLICATE KEY UPDATE."""
    now = current_timestamp_ms()
    date = timestamp_to_date(now)
    (
        SystemSettings.insert(
            name=name, source=source, data_type=data_type, value=value,
            create_time=now, create_date=date, update_time=now, update_date=date,
        )
        .on_conflict(preserve=[SystemSettings.source, SystemSettings.data_type, SystemSettings.value, SystemSettings.update_time, SystemSettings.update_date])
        .execute()
    )


def get_setting(name: str) -> str | None:
    row = SystemSettings.select(SystemSettings.value).where(SystemSettings.name == name).tuples().first()
    return row[0] if row else None
