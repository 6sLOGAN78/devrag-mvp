"""Baseline schema: the 37 tables beyond ``system_settings`` (DATA-01, D-10, D-11).

Idempotent (R-75): MySQL commits DDL implicitly, so a rerun after a partial failure must skip
what exists. A missing table is created whole (columns and indexes). A table that exists but
lacks an index (interrupted run) gets the missing index added by column coverage.
"""
from __future__ import annotations

from api.db.migrations.runner import add_index_if_missing
from api.db.models import ALL_MODELS, SystemSettings
from api.db.models.base import index_specs

VERSION = "0002"

MODELS = [m for m in ALL_MODELS if m is not SystemSettings]


def upgrade(db) -> None:
    with db.bind_ctx(MODELS):
        # db.table_exists never opens a second connection: the runner holds the connection context.
        missing = [m for m in MODELS if not db.table_exists(m._meta.table_name)]
        if missing:
            db.create_tables(missing, safe=True)
        for model in MODELS:
            if model in missing:
                continue
            for _name, columns, unique in index_specs(model):
                add_index_if_missing(db, model._meta.table_name, columns, unique)
