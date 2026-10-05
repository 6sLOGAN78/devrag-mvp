"""Agent canvas and MCP tables (reference columns; docs list the entities)."""
from __future__ import annotations

import peewee

from api.db.models.base import BaseModel, JSONField, LongTextField

_STATUS_HELP = "is it validate(0: wasted, 1: validate)"


class UserCanvas(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    user_id = peewee.CharField(max_length=255, null=False, help_text="user_id", index=True)
    title = peewee.CharField(max_length=255, null=True, help_text="Canvas title")
    permission = peewee.CharField(max_length=16, null=False, help_text="me|team", default="me", index=True)
    release = peewee.BooleanField(null=False, help_text="is released", default=False, index=True)
    description = LongTextField(null=True, help_text="Canvas description")
    canvas_type = peewee.CharField(max_length=32, null=True, help_text="Canvas type", index=True)
    canvas_category = peewee.CharField(max_length=32, null=False, default="agent_canvas", help_text="Canvas category: agent_canvas|dataflow_canvas", index=True)
    tags = peewee.CharField(max_length=512, null=False, default="", help_text="Comma-separated tags for organizing agents", index=True)
    dsl = JSONField(null=True, default=dict)

    class Meta:
        table_name = "user_canvas"


class CanvasTemplate(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    title = JSONField(null=True, default=dict, help_text="Canvas title")
    description = JSONField(null=True, default=dict, help_text="Canvas description")
    canvas_type = peewee.CharField(max_length=32, null=True, help_text="Canvas type", index=True)
    canvas_types = JSONField(null=True, default=list, help_text="Canvas types")
    canvas_category = peewee.CharField(max_length=32, null=False, default="agent_canvas", help_text="Canvas category: agent_canvas|dataflow_canvas", index=True)
    dsl = JSONField(null=True, default=dict)

    class Meta:
        table_name = "canvas_template"


class UserCanvasVersion(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    user_canvas_id = peewee.CharField(max_length=255, null=False, help_text="user_canvas_id", index=True)
    title = peewee.CharField(max_length=255, null=True, help_text="Canvas title")
    description = LongTextField(null=True, help_text="Canvas description")
    release = peewee.BooleanField(null=False, help_text="is released", default=False, index=True)
    dsl = JSONField(null=True, default=dict)

    class Meta:
        table_name = "user_canvas_version"


class MCPServer(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    name = peewee.CharField(max_length=255, null=False, help_text="MCP Server name")
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    url = peewee.CharField(max_length=2048, null=False, help_text="MCP Server URL")
    server_type = peewee.CharField(max_length=32, null=False, help_text="MCP Server type")
    description = LongTextField(null=True, help_text="MCP Server description")
    variables = JSONField(null=True, default=dict, help_text="MCP Server variables")
    headers = JSONField(null=True, default=dict, help_text="MCP Server additional request headers")

    class Meta:
        table_name = "mcp_server"


class CompilationTemplate(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    tenant_id = peewee.CharField(max_length=32, null=True, index=True)
    group_id = peewee.CharField(max_length=32, null=True, index=True)
    name = peewee.CharField(max_length=128, null=False, index=True)
    description = LongTextField(null=True, default="")
    kind = peewee.CharField(max_length=64, null=False, index=True)
    config = JSONField(null=False, default=dict)
    is_builtin = peewee.BooleanField(null=False, default=False, index=True)
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "compilation_template"
        indexes = ((("tenant_id", "group_id", "name", "is_builtin", "status"), True),)


class CompilationTemplateGroup(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    name = peewee.CharField(max_length=128, null=False, index=True)
    description = LongTextField(null=True, default="")
    scope = peewee.CharField(max_length=16, null=False, index=True, help_text="file | dataset")
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "compilation_template_group"
