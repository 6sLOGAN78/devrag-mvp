"""Peewee models. Every model is the schema source of truth (D-10)."""
from api.db.database import DB
from api.db.models.base import BaseModel, JSONField, LongTextField
from api.db.models.canvas import CanvasTemplate, CompilationTemplate, CompilationTemplateGroup, MCPServer, UserCanvas, UserCanvasVersion
from api.db.models.chat import API4Conversation, APIToken, Conversation, Dialog, Search
from api.db.models.files import File, File2Document, FileCommit, FileCommitItem
from api.db.models.identity import InvitationCode, Tenant, User, UserTenant
from api.db.models.integrations import ChatChannel, Connector, Connector2Kb, Memory, SyncLogs
from api.db.models.knowledge import Document, Knowledgebase, PipelineOperationLog, Task
from api.db.models.llm import (
    LLM,
    LLMFactories,
    TenantLangfuse,
    TenantLLM,
    TenantModel,
    TenantModelGroup,
    TenantModelGroupMapping,
    TenantModelInstance,
    TenantModelProvider,
)
from api.db.models.system import SCHEMA_VERSION_KEY, SystemSettings, get_setting, upsert_setting

# Every table, SystemSettings first (created by migration 0001, bootstrap), then by domain.
ALL_MODELS: list[type[BaseModel]] = [
    SystemSettings,
    User, Tenant, UserTenant, InvitationCode,
    LLMFactories, LLM, TenantLLM, TenantLangfuse,
    TenantModelProvider, TenantModelInstance, TenantModel, TenantModelGroup, TenantModelGroupMapping,
    Knowledgebase, Document, Task, PipelineOperationLog,
    File, File2Document, FileCommit, FileCommitItem,
    Dialog, Conversation, APIToken, API4Conversation, Search,
    UserCanvas, CanvasTemplate, UserCanvasVersion, MCPServer, CompilationTemplate, CompilationTemplateGroup,
    Connector, Connector2Kb, ChatChannel, SyncLogs, Memory,
]  # fmt: skip

__all__ = [
    "ALL_MODELS", "DB", "SCHEMA_VERSION_KEY", "BaseModel", "JSONField", "LongTextField",
    "get_setting", "upsert_setting",
    *[m.__name__ for m in ALL_MODELS],
]  # fmt: skip
