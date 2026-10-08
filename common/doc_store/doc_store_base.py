"""The document-store port (plan 03-08, IDX-05): one abstract connection, its value objects and the hardening rules.

Every engine adapter (Elasticsearch now, Infinity later) subclasses :class:`DocStoreConnection`. The signatures are the ones
Phase 5 retrieval uses unchanged: later phases add behaviour behind these methods, never parameters.

Safety rules shared by every adapter and enforced here, before any request is sent:

* index names must be ``ragflow_`` plus 32 lowercase hex characters, so a wildcard, a comma list or ``_all`` can never address
  another tenant's index (:func:`validate_index_names`);
* ``dataset_ids`` is required and non-empty on every read and write (:func:`require_dataset_ids`);
* ``condition`` may never be empty for ``update`` and ``delete`` (:func:`require_condition`) and its keys are plain field names
  (:func:`validate_condition_keys`);
* a vector field is ``q_{dim}_vec`` with ``1 <= dim <= 4096`` (:func:`vector_field`), and a vector with the wrong length or zero
  magnitude is refused before a bulk call can half-fail (:func:`check_row_vectors`).

This module imports nothing from ``api``, ``rag`` or ``quart`` (layering test).
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from common.constants import INDEX_PREFIX

TENANT_ID_RE = re.compile(r"[0-9a-f]{32}")
INDEX_NAME_RE = re.compile(re.escape(INDEX_PREFIX) + r"[0-9a-f]{32}")
DATASET_ID_RE = TENANT_ID_RE
VECTOR_FIELD_RE = re.compile(r"q_([0-9]{1,4})_vec")
CONDITION_KEY_RE = re.compile(r"[A-Za-z0-9_]{1,64}")
MIN_VECTOR_SIZE = 1
MAX_VECTOR_SIZE = 4096


class DocStoreError(Exception):
    """A document-store operation failed or was refused. The message names the operation, never a host, credential or body."""


class NotSupported(DocStoreError):
    """The engine does not implement the requested operation or expression."""


class ZeroVectorError(DocStoreError):
    """A zero-magnitude vector was supplied; cosine similarity is undefined for it."""


class DimensionConflict(DocStoreError):
    """The vector field already exists with different dimensions or options."""


class InvalidVectorSize(DocStoreError, ValueError):
    """A vector dimension is outside 1..4096 or is not an integer."""


class InvalidFilter(DocStoreError, ValueError):
    """A dataset-id list, a condition or a row ownership claim is empty, malformed or would widen the scope."""


class InvalidIndexName(DocStoreError, ValueError):
    """An index name is not ``ragflow_`` plus a 32-hex tenant id."""


def index_name(tenant_id: str) -> str:
    """Return the shared tenant index name ``ragflow_{tenant_id}``; the id must be 32 lowercase hex characters."""
    if not isinstance(tenant_id, str) or TENANT_ID_RE.fullmatch(tenant_id) is None:
        raise InvalidIndexName("invalid tenant id for index name")
    return f"{INDEX_PREFIX}{tenant_id}"


def validate_index_names(names: str | Sequence[str]) -> list[str]:
    """Return ``names`` as a list after checking every element; a wildcard, a comma list or an empty list is refused."""
    items = [names] if isinstance(names, str) else list(names) if isinstance(names, Sequence) else None
    if not items:
        raise InvalidIndexName("invalid index name")
    for item in items:
        if not isinstance(item, str) or INDEX_NAME_RE.fullmatch(item) is None:
            raise InvalidIndexName("invalid index name")
    return items


def validate_single_index(name: str) -> str:
    """Validate exactly one index name (never a list) and return it."""
    if not isinstance(name, str):
        raise InvalidIndexName("invalid index name")
    return validate_index_names(name)[0]


def vector_field(dim: int) -> str:
    """Return ``q_{dim}_vec``; ``dim`` must be an int (not a bool) in 1..4096."""
    if isinstance(dim, bool) or not isinstance(dim, int) or not MIN_VECTOR_SIZE <= dim <= MAX_VECTOR_SIZE:
        raise InvalidVectorSize(f"vector size must be an integer between {MIN_VECTOR_SIZE} and {MAX_VECTOR_SIZE}")
    return f"q_{dim}_vec"


def require_dataset_id(dataset_id: str) -> str:
    if not isinstance(dataset_id, str) or DATASET_ID_RE.fullmatch(dataset_id) is None:
        raise InvalidFilter("invalid dataset id")
    return dataset_id


def require_dataset_ids(dataset_ids: Sequence[str]) -> list[str]:
    """Return the ids as a list; empty, non-list or non-32-hex ids are refused so a query can never lose its dataset filter."""
    if isinstance(dataset_ids, (str, bytes)) or not isinstance(dataset_ids, Sequence) or not dataset_ids:
        raise InvalidFilter("dataset ids are required")
    return [require_dataset_id(item) for item in dataset_ids]


def require_condition(condition: Mapping[str, Any]) -> dict[str, Any]:
    """Return a non-empty condition dict; an empty one would turn update or delete into match-everything."""
    if not isinstance(condition, Mapping) or not condition:
        raise InvalidFilter("a non-empty condition is required")
    return dict(condition)


def validate_condition_keys(condition: Mapping[str, Any]) -> None:
    """Condition keys are plain field names (letters, digits, underscore, 1..64); nothing else reaches a query or script."""
    if not isinstance(condition, Mapping):
        raise InvalidFilter("invalid condition")
    for key in condition:
        if not isinstance(key, str) or CONDITION_KEY_RE.fullmatch(key) is None:
            raise InvalidFilter("invalid condition field name")


def check_vector(field: str, value: Any) -> None:
    """Refuse a vector whose length differs from the dimension in its ``q_{dim}_vec`` name, or whose magnitude is zero."""
    match = VECTOR_FIELD_RE.fullmatch(field)
    if match is None:
        return
    dims = int(match.group(1))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != dims:
        raise DocStoreError("vector length does not match its field dimension")
    total = 0.0
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise DocStoreError("vector holds a non-numeric or non-finite value")
        total += float(item) * float(item)
    if total == 0.0:
        raise ZeroVectorError("zero-magnitude vector is not allowed")


def check_row_vectors(rows: Sequence[Mapping[str, Any]]) -> None:
    """Check every ``q_{dim}_vec`` value of every row; call before any request so a bulk write never half-fails."""
    for row in rows:
        for field, value in row.items():
            if isinstance(field, str):
                check_vector(field, value)


@dataclass(frozen=True)
class MatchTextExpr:
    fields: list[str]
    matching_text: str
    topn: int
    extra_options: dict | None = None  # e.g. minimum_should_match


@dataclass(frozen=True)
class MatchDenseExpr:
    vector_column_name: str
    embedding_data: Sequence[float]
    embedding_data_type: str  # "float"
    distance_type: str
    topn: int = 10
    extra_options: dict | None = None  # e.g. similarity threshold


@dataclass(frozen=True)
class MatchSparseExpr:
    """Reserved for engines with sparse vectors (Infinity). The Elasticsearch adapter raises :class:`NotSupported`."""

    extra_options: dict | None = None


@dataclass(frozen=True)
class FusionExpr:
    method: str  # "weighted_sum"
    topn: int
    fusion_params: dict | None = None  # {"weights": "0.05,0.95"}: text weight, then dense weight


MatchExpr = MatchTextExpr | MatchDenseExpr | MatchSparseExpr | FusionExpr


class OrderByExpr:
    """Ordered sort keys. ``fields`` is a list of ``(field, direction)`` with 0 ascending and 1 descending."""

    def __init__(self) -> None:
        self._fields: list[tuple[str, int]] = []

    def asc(self, field: str) -> OrderByExpr:
        self._fields.append((field, 0))
        return self

    def desc(self, field: str) -> OrderByExpr:
        self._fields.append((field, 1))
        return self

    @property
    def fields(self) -> list[tuple[str, int]]:
        return list(self._fields)


@dataclass(frozen=True)
class SearchResult:
    """Engine-neutral search answer: callers never touch an engine response. Each hit is a ``_source`` dict with ``id`` and ``_score``."""

    total: int
    hits: list[dict]
    aggregations: dict


class DocStoreConnection(ABC):
    @abstractmethod
    def db_type(self) -> str: ...

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def create_idx(self, index_name: str, dataset_id: str, vector_size: int, parser_id: str | None = None) -> bool:
        """Ensure the tenant index and the ``q_{vector_size}_vec`` field exist. Idempotent."""

    @abstractmethod
    def delete_idx(self, index_name: str, dataset_id: str) -> None:
        """Remove one dataset's rows. The shared tenant index itself is kept."""

    @abstractmethod
    def index_exist(self, index_name: str, dataset_id: str | None = None) -> bool: ...

    @abstractmethod
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
    ) -> SearchResult: ...

    @abstractmethod
    def get(self, chunk_id: str, index_name: str, dataset_ids: list[str]) -> dict | None: ...

    @abstractmethod
    def insert(self, rows: list[dict], index_name: str, dataset_id: str) -> list[str]:
        """Insert rows and return the ids that failed (empty on success)."""

    @abstractmethod
    def update(self, condition: dict, new_value: dict, index_name: str, dataset_id: str) -> bool: ...

    @abstractmethod
    def delete(self, condition: dict, index_name: str, dataset_id: str) -> int:
        """Delete the matching rows of one dataset and return how many."""

    def sql(self, *args: Any, **kwargs: Any) -> Any:
        """Text-to-SQL arrives in a later phase."""
        raise NotSupported("sql is not supported by this document store")
