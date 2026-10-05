#!/usr/bin/env python3
"""Export the Peewee models to conf/schema.json (DATA-06, D-10).

``conf/schema.json`` is the only input to the Go entity generator, so the Go side never reads
the Python source. Output is deterministic: tables and columns sorted by name, fixed key order.
``--check`` exits 1 with a diff when the committed file differs from a fresh export.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import peewee  # noqa: E402

from api.db.models import ALL_MODELS  # noqa: E402
from api.db.models.base import index_specs  # noqa: E402

DEFAULT_OUT = REPO / "conf" / "schema.json"
_DB_DEFAULT = re.compile(r"^DEFAULT\s+(.+)$", re.IGNORECASE)
_SIMPLE = {"INT": "int", "BIGINT": "bigint", "FLOAT": "float", "DATETIME": "datetime", "TEXT": "longtext", "LONGTEXT": "longtext", "BOOL": "tinyint(1)", "AUTO": "int"}


class ExportError(ValueError):
    """A model uses a field type the exporter cannot normalise."""


def mysql_type(field: peewee.Field) -> str:
    """The MySQL ``COLUMN_TYPE`` string Peewee's MySQL driver produces for this field."""
    kind = field.field_type
    if kind == "VARCHAR":
        return "varchar(%d)" % field.max_length
    if kind in _SIMPLE:
        return _SIMPLE[kind]
    raise ExportError("unsupported field type %s on %s.%s" % (kind, field.model.__name__, field.name))


def db_default(field: peewee.Field) -> str | None:
    """The DB-level DEFAULT (from a ``SQL('DEFAULT ...')`` constraint), unquoted; None if absent."""
    for constraint in field.constraints or ():
        match = _DB_DEFAULT.match(str(getattr(constraint, "sql", "")).strip())
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == "'" else value
    return None


def app_default(field: peewee.Field) -> bool | int | float | str | None:
    """The application-side scalar default; callables (JSON documents) are not exported."""
    value = field.default
    return value if isinstance(value, bool | int | float | str) else None


def _primary_key_columns(model: type[peewee.Model]) -> list[str]:
    pk = model._meta.primary_key
    if isinstance(pk, peewee.CompositeKey):
        return [model._meta.fields[name].column_name for name in pk.field_names]
    return [pk.column_name]


def export_table(model: type[peewee.Model]) -> dict[str, Any]:
    pk_columns = set(_primary_key_columns(model))
    columns = []
    for field in model._meta.sorted_fields:
        columns.append(
            {
                "name": field.column_name,
                "type": mysql_type(field),
                "nullable": bool(field.null) and field.column_name not in pk_columns,
                "default": db_default(field),
                "app_default": app_default(field),
                "primary_key": field.column_name in pk_columns,
                "auto_increment": field.field_type == "AUTO",
            }
        )
    indexes = [{"name": name, "columns": list(cols), "unique": unique} for name, cols, unique in index_specs(model)]
    return {"name": model._meta.table_name, "columns": sorted(columns, key=lambda c: c["name"]), "indexes": indexes}


def export_schema() -> dict[str, Any]:
    tables = sorted((export_table(m) for m in ALL_MODELS), key=lambda t: t["name"])
    return {"generated_by": "scripts/export_schema.py", "tables": tables}


def render() -> str:
    return json.dumps(export_schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="fail with a diff if the file differs")
    args = parser.parse_args(argv)
    fresh = render()
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current == fresh:
            return 0
        sys.stderr.write("".join(difflib.unified_diff(current.splitlines(True), fresh.splitlines(True), str(args.out), "fresh export")))
        sys.stderr.write("\nschema.json is stale: run uv run python scripts/export_schema.py\n")
        return 1
    args.out.write_text(fresh, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
