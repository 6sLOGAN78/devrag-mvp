"""Helpers for upload tests (plan 03-16): what a tenant holds in MinIO and in the dataset tables, and small valid file bodies.

Listings and counts use the exact tenant id as a parameter or as an object prefix, never a pattern, so a test only ever looks at
the objects and rows of the accounts it registered.
"""
from __future__ import annotations

import uuid
from typing import Any

from minio import Minio

from test.conftest import stack_env
from test.helpers.db import root_connection

BUCKET = "ragflow"
PDF_HEAD = b"%PDF-1.4\n"


def pdf_bytes(tag: str = "", size: int = 300) -> bytes:
    """A small file that passes the PDF magic rule and is unique per call (a fresh uuid inside)."""
    body = f"{tag}-{uuid.uuid4().hex}-".encode()
    return PDF_HEAD + (body * (size // len(body) + 1))[:size]


def text_bytes(tag: str = "", size: int = 300) -> bytes:
    body = f"{tag} {uuid.uuid4().hex} lorem ipsum\n".encode()
    return (body * (size // len(body) + 1))[:size]


def minio_client() -> Minio:
    env = stack_env()
    return Minio(f"127.0.0.1:{env.get('MINIO_PORT', '9000')}", access_key=env.get("MINIO_USER", "rag_flow"), secret_key=env["MINIO_PASSWORD"], secure=False)


def tenant_object_keys(tenant_id: str) -> list[str]:
    """Every object key under ``{tenant_id}/`` in the storage bucket, sorted."""
    if len(tenant_id) != 32 or any(ch not in "0123456789abcdef" for ch in tenant_id):
        raise ValueError("tenant id must be 32 lowercase hex characters")
    client = minio_client()
    if not client.bucket_exists(BUCKET):
        return []
    return sorted(item.object_name for item in client.list_objects(BUCKET, prefix=f"{tenant_id}/", recursive=True))


def object_bytes(key: str) -> bytes:
    response = minio_client().get_object(BUCKET, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def sql(query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(query, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def tenant_row_counts(tenant_id: str) -> dict[str, int]:
    """Rows the upload path writes for one tenant: file, document, file2document, plus the summed doc_num of its datasets."""
    one = tenant_id
    files = sql("SELECT COUNT(*) FROM `file` WHERE `tenant_id` = %s", (one,))[0][0]
    docs = sql("SELECT COUNT(*) FROM `document` WHERE `kb_id` IN (SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s)", (one,))[0][0]
    links = sql("SELECT COUNT(*) FROM `file2document` WHERE `file_id` IN (SELECT `id` FROM `file` WHERE `tenant_id` = %s)", (one,))[0][0]
    counted = sql("SELECT COALESCE(SUM(`doc_num`), 0) FROM `knowledgebase` WHERE `tenant_id` = %s", (one,))[0][0]
    return {"file": int(files), "document": int(docs), "file2document": int(links), "doc_num": int(counted)}


def snapshot(tenant_id: str) -> tuple[list[str], dict[str, int]]:
    """Objects and row counts together, for a before and after comparison around a refused request."""
    return tenant_object_keys(tenant_id), tenant_row_counts(tenant_id)
