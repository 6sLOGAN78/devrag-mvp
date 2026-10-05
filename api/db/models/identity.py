"""Identity tables: user, tenant, user_tenant, invitation_code.

Columns come from the RAGFlow reference model of the same name (docs/08-database/entities.md
lists the entities only); there is no documented DDL for these tables.
"""
from __future__ import annotations

import peewee

from api.db.models.base import BaseModel, LongTextField

_STATUS_HELP = "is it validate(0: wasted, 1: validate)"


class User(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    access_token = peewee.CharField(max_length=255, null=True, index=True)
    nickname = peewee.CharField(max_length=100, null=False, help_text="nicky name", index=True)
    password = peewee.CharField(max_length=255, null=True, help_text="password", index=True)
    email = peewee.CharField(max_length=255, null=False, help_text="email", unique=True)
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    language = peewee.CharField(max_length=32, null=True, help_text="English|Chinese", default="English", index=True)
    color_schema = peewee.CharField(max_length=32, null=True, help_text="Bright|Dark", default="Bright", index=True)
    timezone = peewee.CharField(max_length=64, null=True, help_text="Timezone", default="UTC+8\tAsia/Shanghai", index=True)
    last_login_time = peewee.DateTimeField(null=True, index=True)
    is_authenticated = peewee.CharField(max_length=1, null=False, default="1", index=True)
    is_active = peewee.CharField(max_length=1, null=False, default="1", index=True)
    is_anonymous = peewee.CharField(max_length=1, null=False, default="0", index=True)
    login_channel = peewee.CharField(null=True, help_text="from which user login", index=True)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)
    is_superuser = peewee.BooleanField(null=True, help_text="is root", default=False, index=True)

    class Meta:
        table_name = "user"


class Tenant(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    name = peewee.CharField(max_length=100, null=True, help_text="Tenant name", index=True)
    public_key = peewee.CharField(max_length=255, null=True, index=True)
    llm_id = peewee.CharField(max_length=128, null=False, help_text="default llm ID", index=True)
    tenant_llm_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    embd_id = peewee.CharField(max_length=128, null=False, help_text="default embedding model ID", index=True)
    tenant_embd_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    asr_id = peewee.CharField(max_length=128, null=False, help_text="default ASR model ID", index=True)
    tenant_asr_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    img2txt_id = peewee.CharField(max_length=128, null=False, help_text="default image to text model ID", index=True)
    tenant_img2txt_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    rerank_id = peewee.CharField(max_length=128, null=False, help_text="default rerank model ID", index=True)
    tenant_rerank_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    tts_id = peewee.CharField(max_length=256, null=True, help_text="default tts model ID", index=True)
    tenant_tts_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    ocr_id = peewee.CharField(max_length=256, null=True, help_text="default OCR model ID", index=True)
    tenant_ocr_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    parser_ids = peewee.CharField(max_length=256, null=False, help_text="document processors", index=True)
    credit = peewee.IntegerField(default=512, index=True)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "tenant"


class UserTenant(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    user_id = peewee.CharField(max_length=32, null=False, index=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    role = peewee.CharField(max_length=32, null=False, help_text="UserTenantRole", index=True)
    invited_by = peewee.CharField(max_length=32, null=False, index=True)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "user_tenant"


class InvitationCode(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    code = peewee.CharField(max_length=32, null=False, index=True)
    visit_time = peewee.DateTimeField(null=True, index=True)
    user_id = peewee.CharField(max_length=32, null=True, index=True)
    tenant_id = peewee.CharField(max_length=32, null=True, index=True)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "invitation_code"
