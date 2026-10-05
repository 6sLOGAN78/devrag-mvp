"""Connector, chat-channel, sync-log and memory tables (reference columns; docs list the entities)."""
from __future__ import annotations

import datetime

import peewee

from api.db.models.base import BaseModel, JSONField, LongTextField


class DateTimeTzField(peewee.CharField):
    """Timezone-aware datetime stored as an ISO-8601 string; naive values are taken as UTC."""

    field_type = "VARCHAR"

    def db_value(self, value: datetime.datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.UTC)
        return value.isoformat()

    def python_value(self, value: str | None) -> datetime.datetime | None:
        if value is None:
            return None
        parsed = datetime.datetime.fromisoformat(value)
        return parsed.replace(tzinfo=datetime.UTC) if parsed.tzinfo is None else parsed


class Connector(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=128, null=False, help_text="Search name", index=False)
    source = peewee.CharField(max_length=128, null=False, help_text="Data source", index=True)
    input_type = peewee.CharField(max_length=128, null=False, help_text="poll/event/..", index=True)
    config = JSONField(null=False, default=dict)
    refresh_freq = peewee.IntegerField(default=0, index=False)
    prune_freq = peewee.IntegerField(default=0, index=False)
    timeout_secs = peewee.IntegerField(default=3600, index=False)
    indexing_start = peewee.DateTimeField(null=True, index=True)
    status = peewee.CharField(max_length=16, null=True, help_text="schedule", default="schedule", index=True)

    class Meta:
        table_name = "connector"


class Connector2Kb(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    connector_id = peewee.CharField(max_length=32, null=False, index=True)
    kb_id = peewee.CharField(max_length=32, null=False, index=True)
    auto_parse = peewee.CharField(max_length=1, null=False, default="1", index=False)

    class Meta:
        table_name = "connector2kb"


class ChatChannel(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=128, null=False, help_text="Bot name", index=False)
    channel = peewee.CharField(max_length=128, null=False, help_text="Chat channel type", index=True)
    config = JSONField(null=False, default=dict, help_text="Channel credential & settings")
    chat_id = peewee.CharField(max_length=32, null=True, default=None, help_text="connected chat id", index=True)
    status = peewee.IntegerField(default=1, index=True)

    class Meta:
        table_name = "chat_channel"


class SyncLogs(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    connector_id = peewee.CharField(max_length=32, index=True)
    task_type = peewee.CharField(max_length=32, null=False, default="sync", index=True)
    status = peewee.CharField(max_length=128, null=False, help_text="Processing status", index=True)
    from_beginning = peewee.CharField(max_length=1, null=True, help_text="", default="0", index=False)
    new_docs_indexed = peewee.IntegerField(default=0, index=False)
    total_docs_indexed = peewee.IntegerField(default=0, index=False)
    docs_removed_from_index = peewee.IntegerField(default=0, index=False)
    error_msg = LongTextField(null=False, help_text="process message", default="")
    error_count = peewee.IntegerField(default=0, index=False)
    full_exception_trace = LongTextField(null=True, help_text="process message", default="")
    time_started = peewee.DateTimeField(null=True, index=True)
    poll_range_start = DateTimeTzField(max_length=255, null=True, index=True)
    poll_range_end = DateTimeTzField(max_length=255, null=True, index=True)
    kb_id = peewee.CharField(max_length=32, null=False, index=True)

    class Meta:
        table_name = "sync_logs"


class Memory(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    name = peewee.CharField(max_length=128, null=False, index=False, help_text="Memory name")
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    memory_type = peewee.IntegerField(null=False, default=1, index=True, help_text="Bit flags (LSB->MSB): 1=raw, 2=semantic, 4=episodic, 8=procedural")
    storage_type = peewee.CharField(max_length=32, default="table", null=False, index=True, help_text="table|graph")
    embd_id = peewee.CharField(max_length=128, null=False, index=False, help_text="embedding model ID")
    tenant_embd_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    llm_id = peewee.CharField(max_length=128, null=False, index=False, help_text="chat model ID")
    tenant_llm_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    permissions = peewee.CharField(max_length=16, null=False, index=True, help_text="me|team", default="me")
    description = LongTextField(null=True, help_text="description")
    memory_size = peewee.IntegerField(default=5242880, null=False, index=False)
    forgetting_policy = peewee.CharField(max_length=32, null=False, default="FIFO", index=False, help_text="LRU|FIFO")
    temperature = peewee.FloatField(default=0.5, index=False)
    system_prompt = LongTextField(null=True, help_text="system prompt", index=False)
    user_prompt = LongTextField(null=True, help_text="user prompt", index=False)

    class Meta:
        table_name = "memory"
