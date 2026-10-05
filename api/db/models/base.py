"""Base model and field helpers shared by every table (D-10: Peewee models own the schema)."""
from __future__ import annotations

import datetime
import json
import time
from typing import Any

import peewee

from api.db.database import DB


def current_timestamp_ms() -> int:
    """Unix time in milliseconds (13 digits), the ``*_time`` column convention."""
    return int(time.time() * 1000)


def timestamp_to_date(timestamp_ms: int) -> datetime.datetime:
    """Naive UTC datetime, second precision, for the ``*_date`` columns."""
    return datetime.datetime.fromtimestamp(timestamp_ms / 1000, datetime.UTC).replace(tzinfo=None, microsecond=0)


class LongTextField(peewee.TextField):
    field_type = "LONGTEXT"


class JSONField(LongTextField):
    """JSON document stored as LONGTEXT (the reference storage format); json only, never pickle."""

    def db_value(self, value: Any) -> str | None:
        return None if value is None else json.dumps(value, ensure_ascii=False)

    def python_value(self, value: str | None) -> Any:
        return None if value is None else json.loads(value)


class BaseModel(peewee.Model):
    create_time = peewee.BigIntegerField(null=True, index=True)
    create_date = peewee.DateTimeField(null=True, index=True)
    update_time = peewee.BigIntegerField(null=True, index=True)
    update_date = peewee.DateTimeField(null=True, index=True)

    class Meta:
        database = DB

    def save(self, *args: Any, **kwargs: Any) -> Any:
        now = current_timestamp_ms()
        if self.create_time is None:
            self.create_time = now
            self.create_date = timestamp_to_date(now)
        self.update_time = now
        self.update_date = timestamp_to_date(now)
        return super().save(*args, **kwargs)
