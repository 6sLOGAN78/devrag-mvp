"""Chat tables: dialog, conversation, api_token, api_4_conversation, search (reference columns; docs list entities)."""
from __future__ import annotations

from typing import Any

import peewee

from api.db.models.base import BaseModel, JSONField, LongTextField

_STATUS_HELP = "is it validate(0: wasted, 1: validate)"


def _llm_setting() -> dict[str, Any]:
    return {"temperature": 0.1, "top_p": 0.3, "frequency_penalty": 0.7, "presence_penalty": 0.4, "max_tokens": 512}


def _prompt_config() -> dict[str, Any]:
    return {
        "system": "",
        "prologue": "Hi! I'm your assistant. What can I do for you?",
        "parameters": [],
        "empty_response": "Sorry! No relevant content was found in the knowledge base!",
    }


def _search_config() -> dict[str, Any]:
    return {
        "kb_ids": [],
        "doc_ids": [],
        "similarity_threshold": 0.2,
        "vector_similarity_weight": 0.3,
        "use_kg": False,
        "rerank_id": "",
        "top_k": 1024,
        "summary": False,
        "chat_id": "",
        "llm_setting": {
            "temperature": 0.1,
            "top_p": 0.3,
            "frequency_penalty": 0.7,
            "presence_penalty": 0.4,
            "temperature_enabled": True,
            "top_p_enabled": True,
            "frequency_penalty_enabled": True,
            "presence_penalty_enabled": True,
        },
        "chat_settingcross_languages": [],
        "highlight": False,
        "keyword": False,
        "web_search": False,
        "related_search": False,
        "query_mindmap": False,
    }


class Dialog(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=255, null=True, help_text="dialog application name", index=True)
    description = LongTextField(null=True, help_text="Dialog description")
    icon = LongTextField(null=True, help_text="icon base64 string")
    language = peewee.CharField(max_length=32, null=True, default="English", help_text="English|Chinese", index=True)
    llm_id = peewee.CharField(max_length=128, null=False, help_text="default llm ID")
    tenant_llm_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    llm_setting = JSONField(null=False, default=_llm_setting)
    prompt_type = peewee.CharField(max_length=16, null=False, default="simple", help_text="simple|advanced", index=True)
    prompt_config = JSONField(null=False, default=_prompt_config)
    meta_data_filter = JSONField(null=True, default=dict)
    similarity_threshold = peewee.FloatField(default=0.2)
    vector_similarity_weight = peewee.FloatField(default=0.3)
    top_n = peewee.IntegerField(default=6)
    top_k = peewee.IntegerField(default=1024)
    do_refer = peewee.CharField(max_length=1, null=False, default="1", help_text="it needs to insert reference index into answer or not")
    rerank_id = peewee.CharField(max_length=128, null=False, help_text="default rerank model ID")
    tenant_rerank_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    kb_ids = JSONField(null=False, default=list)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "dialog"


class Conversation(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    dialog_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=255, null=True, help_text="conversation name", index=True)
    message = JSONField(null=True)
    reference = JSONField(null=True, default=list)
    user_id = peewee.CharField(max_length=255, null=True, help_text="user_id", index=True)

    class Meta:
        table_name = "conversation"


class APIToken(BaseModel):
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    token = peewee.CharField(max_length=255, null=False, index=True)
    dialog_id = peewee.CharField(max_length=32, null=True, index=True)
    source = peewee.CharField(max_length=16, null=True, help_text="none|agent|dialog", index=True)
    beta = peewee.CharField(max_length=255, null=True, index=True)

    class Meta:
        table_name = "api_token"
        primary_key = peewee.CompositeKey("tenant_id", "token")


class API4Conversation(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    name = peewee.CharField(max_length=255, null=True, help_text="conversation name", index=False)
    dialog_id = peewee.CharField(max_length=32, null=False, index=True)
    user_id = peewee.CharField(max_length=255, null=False, help_text="user_id", index=True)
    exp_user_id = peewee.CharField(max_length=255, null=True, help_text="exp_user_id", index=True)
    message = JSONField(null=True)
    reference = JSONField(null=True, default=list)
    tokens = peewee.IntegerField(default=0)
    source = peewee.CharField(max_length=16, null=True, help_text="none|agent|dialog", index=True)
    dsl = JSONField(null=True, default=dict)
    duration = peewee.FloatField(default=0, index=True)
    round = peewee.IntegerField(default=0, index=True)
    thumb_up = peewee.IntegerField(default=0, index=True)
    errors = LongTextField(null=True, help_text="errors")
    version_title = peewee.CharField(max_length=255, null=True, help_text="canvas version title when session created", index=False)

    class Meta:
        table_name = "api_4_conversation"


class Search(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=128, null=False, help_text="Search name", index=True)
    description = LongTextField(null=True, help_text="KB description")
    created_by = peewee.CharField(max_length=32, null=False, index=True)
    search_config = JSONField(null=False, default=_search_config)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "search"
