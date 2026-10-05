"""Knowledge tables.

``knowledgebase``, ``document`` and ``task`` follow the DDL in docs/08-database/schema.md exactly
(name, type, nullability, DB-level default, named secondary indexes; D-11). Columns the docs omit
are supplemental from the reference models (R-60) and are marked below. ``document`` and ``task``
carry no ``tenant_id`` (D-12): tenant isolation is transitive through ``knowledgebase.tenant_id``.
``pipeline_operation_log`` is reference-only (docs list the entity).
"""
from __future__ import annotations

from typing import Any

import peewee

from api.db.models.base import BaseModel, JSONField, LongTextField, db_default

_STATUS_HELP = "is it validate(0: wasted, 1: validate)"
MAXIMUM_TASK_PAGE_NUMBER = 1_000_000


def default_parser_config() -> dict[str, Any]:
    return {"pages": [[1, 1000000]], "table_context_size": 0, "image_context_size": 0}


class Knowledgebase(BaseModel):
    # documented columns
    id = peewee.CharField(max_length=32, primary_key=True)
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    tenant_id = peewee.CharField(max_length=32, null=False)
    name = peewee.CharField(max_length=128, null=False, help_text="KB name")
    language = peewee.CharField(max_length=32, null=True, default="English", constraints=db_default("English"), help_text="English|Chinese", index=True)
    description = LongTextField(null=True, help_text="KB description")
    embd_id = peewee.CharField(max_length=128, null=False, help_text="default embedding model ID", index=True)
    parser_id = peewee.CharField(max_length=32, null=False, default="naive", constraints=db_default("naive"), help_text="default parser ID", index=True)
    parser_config = JSONField(null=False, default=default_parser_config)
    status = peewee.CharField(max_length=1, null=True, default="1", constraints=db_default("1"), help_text=_STATUS_HELP, index=True)
    # supplemental from reference (R-60)
    tenant_embd_id = peewee.CharField(max_length=32, null=True, help_text="id in tenant_model", index=True)
    permission = peewee.CharField(max_length=16, null=False, help_text="me|team", default="me", index=True)
    created_by = peewee.CharField(max_length=32, null=False, index=True)
    doc_num = peewee.IntegerField(default=0, index=True)
    token_num = peewee.IntegerField(default=0, index=True)
    chunk_num = peewee.IntegerField(default=0, index=True)
    similarity_threshold = peewee.FloatField(default=0.2, index=True)
    vector_similarity_weight = peewee.FloatField(default=0.3, index=True)
    pipeline_id = peewee.CharField(max_length=32, null=True, help_text="Pipeline ID", index=True)
    pagerank = peewee.IntegerField(default=0, index=False)
    graphrag_task_id = peewee.CharField(max_length=32, null=True, help_text="Graph RAG task ID", index=True)
    graphrag_task_finish_at = peewee.DateTimeField(null=True)
    raptor_task_id = peewee.CharField(max_length=32, null=True, help_text="RAPTOR task ID", index=True)
    raptor_task_finish_at = peewee.DateTimeField(null=True)
    mindmap_task_id = peewee.CharField(max_length=32, null=True, help_text="Mindmap task ID", index=True)
    mindmap_task_finish_at = peewee.DateTimeField(null=True)
    wiki_task_id = peewee.CharField(max_length=32, null=True, help_text="Artifact compilation task ID", index=True)
    wiki_task_finish_at = peewee.DateTimeField(null=True)
    skill_task_id = peewee.CharField(max_length=32, null=True, help_text="Skill generation task ID", index=True)
    skill_task_finish_at = peewee.DateTimeField(null=True)
    structure_graph_task_id = peewee.CharField(max_length=32, null=True, help_text="Structure graph merge task ID", index=True)
    structure_graph_task_finish_at = peewee.DateTimeField(null=True)
    structure_mindmap_task_id = peewee.CharField(max_length=32, null=True, help_text="Structure mindmap merge task ID", index=True)
    structure_mindmap_task_finish_at = peewee.DateTimeField(null=True)
    timeline_task_id = peewee.CharField(max_length=32, null=True, help_text="Timeline merge task ID", index=True)
    timeline_task_finish_at = peewee.DateTimeField(null=True)
    session_graph_task_id = peewee.CharField(max_length=32, null=True, help_text="Session graph merge task ID", index=True)
    session_graph_task_finish_at = peewee.DateTimeField(null=True)
    session_essence_task_id = peewee.CharField(max_length=32, null=True, help_text="Session essence merge task ID", index=True)
    session_essence_task_finish_at = peewee.DateTimeField(null=True)
    structure_task_id = peewee.CharField(max_length=32, null=True, help_text="Structure merge-all task ID", index=True)
    structure_task_finish_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "knowledgebase"


Knowledgebase.add_index(Knowledgebase.tenant_id, name="idx_kb_tenant_id")
Knowledgebase.add_index(Knowledgebase.name, name="idx_kb_name")


class Document(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    thumbnail = LongTextField(null=True, help_text="thumbnail base64 string")
    kb_id = peewee.CharField(max_length=256, null=False)
    parser_id = peewee.CharField(max_length=32, null=False, help_text="default parser ID")
    pipeline_id = peewee.CharField(max_length=32, null=True, help_text="pipeline ID", index=True)
    parser_config = JSONField(null=False, default=default_parser_config)
    source_type = peewee.CharField(max_length=128, null=False, default="local", constraints=db_default("local"), help_text="where dose this document come from", index=True)
    type = peewee.CharField(max_length=32, null=False, help_text="file extension", index=True)
    created_by = peewee.CharField(max_length=32, null=False, help_text="who created it", index=True)
    name = peewee.CharField(max_length=255, null=True, help_text="file name", index=True)
    location = peewee.CharField(max_length=255, null=True, help_text="where dose it store", index=True)
    size = peewee.BigIntegerField(default=0, constraints=db_default(0), index=True)
    token_num = peewee.IntegerField(default=0, constraints=db_default(0), index=True)
    chunk_num = peewee.IntegerField(default=0, constraints=db_default(0), index=True)
    progress = peewee.FloatField(default=0, constraints=db_default(0), index=True)
    progress_msg = LongTextField(null=True, help_text="process message", default="")
    process_begin_at = peewee.DateTimeField(null=True, index=True)
    process_duration = peewee.FloatField(default=0, constraints=db_default(0))
    suffix = peewee.CharField(max_length=32, null=False, help_text="The real file extension suffix", index=True)
    content_hash = peewee.CharField(max_length=32, null=True, default="", constraints=db_default(""), help_text="xxhash128 of document content for change detection", index=True)
    run = peewee.CharField(max_length=1, null=True, default="0", constraints=db_default("0"), help_text="start to run processing or cancel.(1: run it; 2: cancel)", index=True)
    status = peewee.CharField(max_length=1, null=True, default="1", constraints=db_default("1"), help_text=_STATUS_HELP)

    class Meta:
        table_name = "document"


Document.add_index(Document.kb_id, name="idx_doc_kb_id")
Document.add_index(Document.parser_id, name="idx_doc_parser_id")
Document.add_index(Document.status, name="idx_doc_status")


class Task(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    doc_id = peewee.CharField(max_length=32, null=False)
    from_page = peewee.IntegerField(default=0, constraints=db_default(0))
    to_page = peewee.IntegerField(default=MAXIMUM_TASK_PAGE_NUMBER, constraints=db_default(MAXIMUM_TASK_PAGE_NUMBER))
    task_type = peewee.CharField(max_length=32, null=False, default="", constraints=db_default(""))
    priority = peewee.IntegerField(default=0, constraints=db_default(0))
    begin_at = peewee.DateTimeField(null=True, index=True)
    process_duration = peewee.FloatField(default=0, constraints=db_default(0))
    progress = peewee.FloatField(default=0, constraints=db_default(0))
    progress_msg = LongTextField(null=True, help_text="process message", default="")
    retry_count = peewee.IntegerField(default=0, constraints=db_default(0))
    digest = LongTextField(null=True, help_text="task digest", default="")
    chunk_ids = LongTextField(null=True, help_text="chunk ids", default="")

    class Meta:
        table_name = "task"


Task.add_index(Task.doc_id, name="idx_task_doc_id")
Task.add_index(Task.progress, name="idx_task_progress")


class PipelineOperationLog(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    document_id = peewee.CharField(max_length=32, index=True)
    tenant_id = peewee.CharField(max_length=32, null=False, index=True)
    kb_id = peewee.CharField(max_length=32, null=False, index=True)
    pipeline_id = peewee.CharField(max_length=32, null=True, help_text="Pipeline ID", index=True)
    pipeline_title = peewee.CharField(max_length=32, null=True, help_text="Pipeline title", index=True)
    parser_id = peewee.CharField(max_length=32, null=False, help_text="Parser ID", index=True)
    document_name = peewee.CharField(max_length=255, null=False, help_text="File name")
    document_suffix = peewee.CharField(max_length=255, null=False, help_text="File suffix")
    document_type = peewee.CharField(max_length=255, null=False, help_text="Document type")
    source_from = peewee.CharField(max_length=255, null=False, help_text="Source")
    progress = peewee.FloatField(default=0, index=True)
    progress_msg = LongTextField(null=True, help_text="process message", default="")
    process_begin_at = peewee.DateTimeField(null=True, index=True)
    process_duration = peewee.FloatField(default=0)
    dsl = JSONField(null=True, default=dict)
    task_type = peewee.CharField(max_length=32, null=False, default="")
    operation_status = peewee.CharField(max_length=32, null=False, help_text="Operation status")
    avatar = LongTextField(null=True, help_text="avatar base64 string")
    status = peewee.CharField(max_length=1, null=True, help_text=_STATUS_HELP, default="1", index=True)

    class Meta:
        table_name = "pipeline_operation_log"
