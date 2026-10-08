"""Elasticsearch 8 adapter for the document-store port (plan 03-08, IDX-04, IDX-05, IDX-08, IDX-09).

One shared index ``ragflow_{tenant_id}`` holds every dataset of a tenant; rows carry ``kb_id`` (the dataset id) and every query,
update and delete is AND-ed with a ``kb_id`` filter. A dataset's embedding field ``q_{dim}_vec`` is mapped explicitly and on demand.

The adapter is synchronous and every request has an explicit timeout; callers run it in a bounded executor. Engine response
objects never leave this module, and error messages name the operation only (never a host, credential or response body).
"""
from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from elasticsearch import ApiError, BadRequestError, Elasticsearch, NotFoundError, TransportError, helpers

from common.doc_store.doc_store_base import (
    CONDITION_KEY_RE,
    VECTOR_FIELD_RE,
    DimensionConflict,
    DocStoreConnection,
    DocStoreError,
    FusionExpr,
    InvalidFilter,
    MatchDenseExpr,
    MatchExpr,
    MatchSparseExpr,
    MatchTextExpr,
    NotSupported,
    OrderByExpr,
    SearchResult,
    check_row_vectors,
    check_vector,
    require_condition,
    require_dataset_id,
    require_dataset_ids,
    validate_condition_keys,
    validate_index_names,
    validate_single_index,
    vector_field,
)
from common.settings import Settings
from rag.utils.es_mapping import INDEX_MAPPINGS, INDEX_SETTINGS, vector_mapping

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
ENGINE_TYPE = "elasticsearch"
_VECTOR_COMPARED_KEYS = ("type", "dims", "index", "similarity")
MAX_RESULT_WINDOW = 10000
AVAILABILITY_WAIT_SECONDS = 10
FIELD_RE = CONDITION_KEY_RE
MATCH_FIELD_RE = re.compile(r"[A-Za-z0-9_.]{1,64}(\^[0-9]+(\.[0-9]+)?)?")
RANK_FEATURE_RE = re.compile(r"[A-Za-z0-9_.]{1,128}")
IMMUTABLE_FIELDS = ("id", "kb_id")
UPDATE_SCRIPT = "for (entry in params.fields.entrySet()) { ctx._source[entry.getKey()] = entry.getValue(); }"


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


def _filter_clauses(condition: dict[str, Any], dataset_ids: list[str]) -> list[dict[str, Any]]:
    """The dataset scope first, then one clause per condition key (a list becomes ``terms``, a scalar ``term``)."""
    validate_condition_keys(condition)
    clauses: list[dict[str, Any]] = [{"terms": {"kb_id": list(dataset_ids)}}]
    for key, value in condition.items():
        if isinstance(value, (list, tuple, set)):
            if not all(isinstance(v, (str, int, float, bool)) for v in value):
                raise InvalidFilter("invalid condition value")
            clauses.append({"terms": {key: list(value)}})
        elif isinstance(value, (str, int, float, bool)):
            clauses.append({"term": {key: value}})
        else:
            raise InvalidFilter("invalid condition value")
    return clauses


def _weights(fusion: FusionExpr | None) -> tuple[float, float]:
    """Text and dense boosts. Without a fusion expression both sides count equally."""
    if fusion is None:
        return 1.0, 1.0
    if fusion.method != "weighted_sum":
        raise NotSupported(f"fusion method {fusion.method!r} is not supported by this document store")
    raw = str((fusion.fusion_params or {}).get("weights", "0.5,0.5"))
    try:
        parts = [float(item) for item in raw.split(",")]
    except ValueError:
        raise DocStoreError("fusion weights are not numbers") from None
    if len(parts) != 2 or any(p < 0 for p in parts):
        raise DocStoreError("fusion weights must be two non-negative numbers")
    return parts[0], parts[1]


def _text_query(expr: MatchTextExpr, boost: float) -> dict[str, Any]:
    if not expr.fields or not all(isinstance(f, str) and MATCH_FIELD_RE.fullmatch(f) for f in expr.fields):
        raise InvalidFilter("invalid text match fields")
    if not isinstance(expr.matching_text, str) or not expr.matching_text.strip():
        raise InvalidFilter("empty match text")
    body: dict[str, Any] = {"fields": expr.fields, "query": expr.matching_text, "type": "best_fields", "default_operator": "OR", "lenient": True, "boost": boost}
    minimum = (expr.extra_options or {}).get("minimum_should_match")
    if minimum is not None:
        body["minimum_should_match"] = minimum
    return {"query_string": body}


def _knn(expr: MatchDenseExpr, boost: float, filters: list[dict[str, Any]]) -> dict[str, Any]:
    if VECTOR_FIELD_RE.fullmatch(expr.vector_column_name) is None:
        raise InvalidFilter("invalid vector field")
    check_vector(expr.vector_column_name, list(expr.embedding_data))
    k = max(1, min(int(expr.topn), MAX_RESULT_WINDOW))
    knn: dict[str, Any] = {
        "field": expr.vector_column_name,
        "query_vector": [float(v) for v in expr.embedding_data],
        "k": k,
        "num_candidates": min(2 * k, MAX_RESULT_WINDOW),
        "filter": {"bool": {"filter": filters}},
        "boost": boost,
    }
    similarity = (expr.extra_options or {}).get("similarity")
    if similarity is not None:
        knn["similarity"] = float(similarity)
    return knn


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
                    # Lost a creation race: wait server-side until the winner's index is usable before reading its mapping.
                    self._client.cluster.health(index=index, wait_for_status="yellow", timeout=f"{AVAILABILITY_WAIT_SECONDS}s")
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
        try:
            body = self._client.indices.get_field_mapping(index=index, fields=field).body
        except NotFoundError:
            return None  # the engine answers 404 for a field that no mapping holds yet (also while another caller adds it)
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

    # --- data operations -------------------------------------------------------------------------------------------
    def insert(self, rows: list[dict], index_name: str, dataset_id: str) -> list[str]:
        index = validate_single_index(index_name)
        require_dataset_id(dataset_id)
        prepared: list[dict[str, Any]] = []
        for original in rows:
            if not isinstance(original, dict) or not isinstance(original.get("id"), str) or not original["id"]:
                raise InvalidFilter("every row needs a string id")
            if original.get("kb_id", dataset_id) != dataset_id:
                raise InvalidFilter("row belongs to another dataset")
            prepared.append({**original, "kb_id": dataset_id})
        if not prepared:
            return []
        check_row_vectors(prepared)
        with _guard("insert"):
            if not self._client.indices.exists(index=index).body:
                raise DocStoreError("document store insert failed: index does not exist")
            actions = ({"_op_type": "index", "_index": index, "_id": row["id"], "_source": row} for row in prepared)
            _, errors = helpers.bulk(self._client, actions, raise_on_error=False, stats_only=False)
            self._client.indices.refresh(index=index)
        failed = [str(next(iter(item.values())).get("_id")) for item in errors] if isinstance(errors, list) else []
        if failed:
            logger.warning("document store bulk insert had failures", extra={"failed": len(failed), "total": len(prepared)})
        return failed

    def get(self, chunk_id: str, index_name: str, dataset_ids: list[str]) -> dict | None:
        index = validate_single_index(index_name)
        scope = require_dataset_ids(dataset_ids)
        if not isinstance(chunk_id, str) or not chunk_id:
            raise InvalidFilter("a chunk id is required")
        query = {"bool": {"filter": [{"ids": {"values": [chunk_id]}}, {"terms": {"kb_id": scope}}]}}
        with _guard("get"):
            try:
                hits = self._client.search(index=index, query=query, size=1).body["hits"]["hits"]
            except NotFoundError:
                return None
        if not hits:
            return None
        return {**hits[0]["_source"], "id": hits[0]["_id"]}

    def update(self, condition: dict, new_value: dict, index_name: str, dataset_id: str) -> bool:
        index = validate_single_index(index_name)
        require_dataset_id(dataset_id)
        require_condition(condition)
        if not isinstance(new_value, dict) or not new_value:
            raise InvalidFilter("a non-empty set of new values is required")
        validate_condition_keys(new_value)
        if any(key in IMMUTABLE_FIELDS for key in new_value):
            raise InvalidFilter("id and kb_id cannot be updated")
        check_row_vectors([new_value])
        query = {"bool": {"filter": _filter_clauses(condition, [dataset_id])}}
        script = {"lang": "painless", "source": UPDATE_SCRIPT, "params": {"fields": new_value}}
        with _guard("update"):
            body = self._client.update_by_query(index=index, query=query, script=script, refresh=True, conflicts="proceed").body
        return not body.get("failures")

    def delete(self, condition: dict, index_name: str, dataset_id: str) -> int:
        index = validate_single_index(index_name)
        require_dataset_id(dataset_id)
        require_condition(condition)
        query = {"bool": {"filter": _filter_clauses(condition, [dataset_id])}}
        with _guard("delete"):
            body = self._client.delete_by_query(index=index, query=query, refresh=True, conflicts="proceed").body
        return int(body.get("deleted", 0))

    def search(
        self,
        select_fields: list[str],
        highlight_fields: list[str],
        condition: dict,
        match_expressions: list[MatchExpr],
        order_by: OrderByExpr | None,
        offset: int,
        limit: int,
        index_names: str | list[str],
        dataset_ids: list[str],
        agg_fields: list[str] | None = None,
        rank_feature: dict | None = None,
    ) -> SearchResult:
        indices = validate_index_names(index_names)
        scope = require_dataset_ids(dataset_ids)
        filters = _filter_clauses(condition or {}, scope)
        if isinstance(offset, bool) or isinstance(limit, bool) or not isinstance(offset, int) or not isinstance(limit, int) or offset < 0 or limit < 0:
            raise InvalidFilter("offset and limit must be non-negative integers")
        if offset >= MAX_RESULT_WINDOW:
            raise InvalidFilter("offset is beyond the result window")
        for name in [*(select_fields or []), *(highlight_fields or []), *(agg_fields or [])]:
            if not isinstance(name, str) or FIELD_RE.fullmatch(name) is None:
                raise InvalidFilter("invalid field name")

        fusion = next((e for e in match_expressions if isinstance(e, FusionExpr)), None)
        text_boost, dense_boost = _weights(fusion)
        must: list[dict[str, Any]] = []
        knns: list[dict[str, Any]] = []
        for expr in match_expressions:
            if isinstance(expr, MatchTextExpr):
                must.append(_text_query(expr, text_boost))
            elif isinstance(expr, MatchDenseExpr):
                knns.append(_knn(expr, dense_boost, filters))
            elif isinstance(expr, MatchSparseExpr):
                raise NotSupported("sparse match is not supported by this document store")
            elif not isinstance(expr, FusionExpr):
                raise NotSupported("unknown match expression")
        bool_query: dict[str, Any] = {"filter": filters}
        if must:
            bool_query["must"] = must
        if rank_feature:
            should = []
            for name, weight in rank_feature.items():
                if not isinstance(name, str) or RANK_FEATURE_RE.fullmatch(name) is None:
                    raise InvalidFilter("invalid rank feature name")
                should.append({"rank_feature": {"field": name, "boost": float(weight)}})
            bool_query["should"] = should

        body: dict[str, Any] = {
            "from": offset,
            "size": min(limit, MAX_RESULT_WINDOW - offset),
            "track_total_hits": True,
        }
        if knns and not must:
            body["knn"] = knns if len(knns) > 1 else knns[0]
        else:
            body["query"] = {"bool": bool_query}
            if knns:
                body["knn"] = knns if len(knns) > 1 else knns[0]
        if select_fields:
            body["_source"] = list(select_fields)
        if highlight_fields:
            body["highlight"] = {"fields": {name: {} for name in highlight_fields}, "pre_tags": ["<em>"], "post_tags": ["</em>"]}
        if order_by is not None and order_by.fields:
            body["sort"] = [{field: {"order": "desc" if direction else "asc", "unmapped_type": "long"}} for field, direction in order_by.fields]
        if agg_fields:
            body["aggs"] = {name: {"terms": {"field": name, "size": 100}} for name in agg_fields}

        with _guard("search"):
            response = self._client.search(index=indices, **body).body
        hits = []
        for raw in response["hits"]["hits"]:
            hit = {**raw.get("_source", {}), "id": raw["_id"], "_score": raw.get("_score") or 0.0}
            if raw.get("highlight"):
                hit["_highlight"] = raw["highlight"]
            hits.append(hit)
        aggregations = {name: [{"key": b["key"], "doc_count": b["doc_count"]} for b in agg["buckets"]] for name, agg in response.get("aggregations", {}).items()}
        return SearchResult(total=int(response["hits"]["total"]["value"]), hits=hits, aggregations=aggregations)


_instances: dict[str, ESConnection] = {}
_instances_lock = threading.Lock()


def get_doc_store(settings: Settings) -> ESConnection:
    """One shared connection per hosts string; the client is thread-safe."""
    key = settings.es.hosts
    with _instances_lock:
        if key not in _instances:
            _instances[key] = ESConnection(settings)
        return _instances[key]
