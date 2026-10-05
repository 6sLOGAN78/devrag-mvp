"""LLM catalogue and tenant model-configuration tables (reference columns; docs list entities only)."""
from __future__ import annotations

import peewee

from api.db.models.base import BaseModel

_STATUS_HELP = "is it validate(0: wasted, 1: validate)"


class LLMFactories(BaseModel):
    name = peewee.CharField(max_length=128, null=False, help_text="LLM factory name", primary_key=True)
    logo = peewee.TextField(null=True, help_text="llm logo base64")
    tags = peewee.CharField(max_length=255, null=False, help_text="LLM, Text Embedding, Image2Text, ASR", index=True)
    rank = peewee.IntegerField(default=0, index=False)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "llm_factories"


class LLM(BaseModel):
    llm_name = peewee.CharField(max_length=128, null=False, help_text="LLM name", index=True)
    model_type = peewee.CharField(max_length=128, null=False, help_text="LLM, Text Embedding, Image2Text, ASR", index=True)
    fid = peewee.CharField(max_length=128, null=False, help_text="LLM factory id", index=True)
    max_tokens = peewee.IntegerField(default=0)
    tags = peewee.CharField(max_length=255, null=False, help_text="LLM, Text Embedding, Image2Text, Chat, 32k...", index=True)
    is_tools = peewee.BooleanField(null=False, help_text="support tools", default=False)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "llm"
        primary_key = peewee.CompositeKey("fid", "llm_name")


class TenantLLM(BaseModel):
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    llm_factory = peewee.CharField(max_length=128, null=False, help_text="LLM factory name", index=True)
    model_type = peewee.CharField(max_length=128, null=True, help_text="LLM, Text Embedding, Image2Text, ASR", index=True)
    llm_name = peewee.CharField(max_length=128, null=True, help_text="LLM name", default="", index=True)
    api_key = peewee.TextField(null=True, help_text="API KEY")
    api_base = peewee.CharField(max_length=255, null=True, help_text="API Base")
    max_tokens = peewee.IntegerField(default=8192, help_text="Max context token num", index=True)
    used_tokens = peewee.IntegerField(default=0, help_text="Used token num", index=True)
    status = peewee.CharField(max_length=1, null=False, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "tenant_llm"
        indexes = ((("tenant_id", "llm_factory", "llm_name"), True),)


class TenantLangfuse(BaseModel):
    tenant_id = peewee.CharField(max_length=32, null=False, primary_key=True)
    secret_key = peewee.CharField(max_length=2048, null=False, help_text="SECRET KEY")
    public_key = peewee.CharField(max_length=2048, null=False, help_text="PUBLIC KEY")
    host = peewee.CharField(max_length=128, null=False, help_text="HOST")

    class Meta:
        table_name = "tenant_langfuse"


class TenantModelProvider(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    provider_name = peewee.CharField(max_length=128, null=False, index=False, help_text="LLM provider name")
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)

    class Meta:
        table_name = "tenant_model_provider"
        indexes = ((("tenant_id", "provider_name"), True),)


class TenantModelInstance(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    instance_name = peewee.CharField(max_length=128, null=False, index=False, help_text="Model instance name")
    provider_id = peewee.CharField(max_length=32, null=False, index=False)
    api_key = peewee.CharField(max_length=512, null=False, index=False, help_text="API key")
    status = peewee.CharField(max_length=32, default="active", index=False)
    extra = peewee.CharField(max_length=512, default="{}", index=False)

    class Meta:
        table_name = "tenant_model_instance"


class TenantModel(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    model_name = peewee.CharField(max_length=128, null=True, index=False, help_text="Model name")
    provider_id = peewee.CharField(max_length=32, null=False, index=False)
    instance_id = peewee.CharField(max_length=32, null=False, index=True)
    model_type = peewee.IntegerField(null=False, default=1, index=True, help_text="Bit flags (LSB->MSB): 1=chat, 2=embedding, 4=asr, 8=vision, 16=rerank, 32=tts, 64=ocr")
    status = peewee.CharField(max_length=32, default="active", index=False)
    extra = peewee.CharField(max_length=1024, default="{}", index=False)

    class Meta:
        table_name = "tenant_model"


class TenantModelGroup(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    group_type = peewee.CharField(max_length=32, null=False, index=False, help_text="Group type")
    model_name = peewee.CharField(max_length=128, null=True, index=False, help_text="Model name")
    strategy = peewee.CharField(max_length=32, default="weighted", index=False, help_text="Routing strategy")

    class Meta:
        table_name = "tenant_model_group"


class TenantModelGroupMapping(BaseModel):
    group_id = peewee.CharField(max_length=32, null=False, index=True, help_text="Group ID")
    provider_id = peewee.CharField(max_length=32, null=False, index=False)
    instance_id = peewee.CharField(max_length=32, null=False, index=False)
    model_id = peewee.CharField(max_length=32, null=False, index=True)
    weight = peewee.IntegerField(default=100, index=False, help_text="Routing weight")
    status = peewee.CharField(max_length=32, default="active", index=False)

    class Meta:
        table_name = "tenant_model_group_mapping"
        primary_key = peewee.CompositeKey("group_id", "provider_id", "instance_id", "model_id")
