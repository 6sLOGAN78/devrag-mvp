"""Elasticsearch 8 adapter for the document-store port (plan 03-08, IDX-04, IDX-05, IDX-08, IDX-09).

One shared index ``ragflow_{tenant_id}`` holds every dataset of a tenant; rows carry ``kb_id`` (the dataset id) and every query,
update and delete is AND-ed with a ``kb_id`` filter. A dataset's embedding field ``q_{dim}_vec`` is mapped explicitly and on demand.

The adapter is synchronous and every request has an explicit timeout; callers run it in a bounded executor. Engine response
objects never leave this module, and error messages name the operation only (never a host, credential or response body).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from elasticsearch import ApiError, BadRequestError, Elasticsearch, NotFoundError, TransportError

from common.doc_store.doc_store_base import (
    DimensionConflict,
    DocStoreConnection,
    DocStoreError,
    require_dataset_id,
    validate_single_index,
    vector_field,
)
from common.settings import Settings
from rag.utils.es_mapping import INDEX_MAPPINGS, INDEX_SETTINGS, vector_mapping

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
ENGINE_TYPE = "elasticsearch"
_VECTOR_COMPARED_KEYS = ("type", "dims", "index", "similarity")


@contextmanager
def _guard(operation: str) -> Iterator[None]:
    """Translate any engine failure into a :class:`DocStoreError` that names the operation and nothing else."""
    try:
        yield
    except DocStoreError:
        raise
    except (TransportError, ApiError) as exc:
        logger.warning("document store request failed", extra={"operation": operation, "error_type": type(exc).__name__})
        raise DocStoreError(f"document store {operation} failed") from None


def _same_vector_mapping(existing: dict[str, Any], wanted: dict[str, Any]) -> bool:
    if any(existing.get(key) != wanted.get(key) for key in _VECTOR_COMPARED_KEYS):
        return False
    return (existing.get("index_options") or {}) == wanted["index_options"]


class ESConnection(DocStoreConnection):
    def __init__(self, settings: Settings) -> None:
        es = settings.es
        self._client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)

    def db_type(self) -> str:
        return ENGINE_TYPE

    def health(self) -> dict:
        try:
            self._client.info()
        except (TransportError, ApiError) as exc:
            logger.debug("document store health check failed", extra={"error_type": type(exc).__name__})
            return {"status": "error", "type": ENGINE_TYPE}
        return {"status": "ok", "type": ENGINE_TYPE}

    # --- index lifecycle -------------------------------------------------------------------------------------------
    def create_idx(self, index_name: str, dataset_id: str, vector_size: int, parser_id: str | None = None) -> bool:
        index = validate_single_index(index_name)
        require_dataset_id(dataset_id)
        field = vector_field(vector_size)
        wanted = vector_mapping(vector_size)
        with _guard("create index"):
            if not self._client.indices.exists(index=index).body:
                try:
                    self._client.indices.create(index=index, settings=INDEX_SETTINGS, mappings=INDEX_MAPPINGS)
                except BadRequestError as exc:
                    if "resource_already_exists_exception" not in str(exc.body):
                        raise
            existing = self._field_mapping(index, field)
            if existing is None:
                try:
                    self._client.indices.put_mapping(index=index, properties={field: wanted})
                except BadRequestError:
                    existing = self._field_mapping(index, field)
                    if existing is None or not _same_vector_mapping(existing, wanted):
                        raise DimensionConflict(f"vector field {field} already exists with different options") from None
            elif not _same_vector_mapping(existing, wanted):
                raise DimensionConflict(f"vector field {field} already exists with different options")
        return True

    def _field_mapping(self, index: str, field: str) -> dict[str, Any] | None:
        body = self._client.indices.get_field_mapping(index=index, fields=field).body
        found = body.get(index, {}).get("mappings", {})
        if field not in found:
            return None
        return found[field]["mapping"][field]

    def delete_idx(self, index_name: str, dataset_id: str) -> None:
        index = validate_single_index(index_name)
        require_dataset_id(dataset_id)
        with _guard("delete dataset rows"):
            try:
                self._client.delete_by_query(index=index, query={"term": {"kb_id": dataset_id}}, refresh=True, conflicts="proceed")
            except NotFoundError:
                return

    def index_exist(self, index_name: str, dataset_id: str | None = None) -> bool:
        index = validate_single_index(index_name)
        if dataset_id is not None:
            require_dataset_id(dataset_id)
        with _guard("check index"):
            return bool(self._client.indices.exists(index=index).body)


_instances: dict[str, ESConnection] = {}
_instances_lock = threading.Lock()


def get_doc_store(settings: Settings) -> ESConnection:
    """One shared connection per hosts string; the client is thread-safe."""
    key = settings.es.hosts
    with _instances_lock:
        if key not in _instances:
            _instances[key] = ESConnection(settings)
        return _instances[key]
