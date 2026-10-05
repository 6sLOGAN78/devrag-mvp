"""Schema exporter: determinism, table set, --check (DATA-06)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.db.models import ALL_MODELS, Document, Task
from scripts import export_schema

pytestmark = pytest.mark.unit

EXPECTED_TABLES = {
    "system_settings", "user", "tenant", "user_tenant", "invitation_code",
    "llm_factories", "llm", "tenant_llm", "tenant_langfuse",
    "tenant_model_provider", "tenant_model_instance", "tenant_model", "tenant_model_group", "tenant_model_group_mapping",
    "knowledgebase", "document", "task", "pipeline_operation_log",
    "file", "file2document", "file_commit", "file_commit_item",
    "dialog", "conversation", "api_token", "api_4_conversation", "search",
    "user_canvas", "canvas_template", "user_canvas_version", "mcp_server", "compilation_template", "compilation_template_group",
    "connector", "connector2kb", "chat_channel", "sync_logs", "memory",
}  # fmt: skip


def test_table_set_is_the_38_documented_tables() -> None:
    names = [m._meta.table_name for m in ALL_MODELS]
    assert len(names) == 38
    assert set(names) == EXPECTED_TABLES


def test_export_is_deterministic() -> None:
    assert export_schema.render() == export_schema.render()
    data = json.loads(export_schema.render())
    assert [t["name"] for t in data["tables"]] == sorted(EXPECTED_TABLES)
    for table in data["tables"]:
        assert [c["name"] for c in table["columns"]] == sorted(c["name"] for c in table["columns"])


def test_no_tenant_id_on_document_or_task() -> None:
    assert "tenant_id" not in Document._meta.fields
    assert "tenant_id" not in Task._meta.fields


def test_documented_indexes_are_named() -> None:
    data = {t["name"]: t for t in json.loads(export_schema.render())["tables"]}
    names = {t: {i["name"] for i in data[t]["indexes"]} for t in ("document", "task", "knowledgebase")}
    assert {"idx_doc_kb_id", "idx_doc_parser_id", "idx_doc_status"} <= names["document"]
    assert {"idx_task_doc_id", "idx_task_progress"} <= names["task"]
    assert {"idx_kb_tenant_id", "idx_kb_name"} <= names["knowledgebase"]


def test_check_passes_on_committed_file_and_fails_on_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert export_schema.main(["--check"]) == 0
    stale = tmp_path / "schema.json"
    stale.write_text("{}\n", encoding="utf-8")
    assert export_schema.main(["--check", "--out", str(stale)]) == 1
    assert "stale" in capsys.readouterr().err
    export_schema.main(["--out", str(stale)])
    assert export_schema.main(["--check", "--out", str(stale)]) == 0


def test_db_default_parsed_from_constraint() -> None:
    assert export_schema.db_default(Document.source_type) == "local"
    assert export_schema.db_default(Document.size) == "0"
    assert export_schema.db_default(Document.content_hash) == ""
    assert export_schema.db_default(Document.name) is None
