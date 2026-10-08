"""The document-store port: value objects, validation helpers and the abstract surface (plan 03-08, IDX-05).

No engine is needed. The adapter and the engine-agnostic contract are exercised in test/integration/test_doc_store_es.py.
"""
from __future__ import annotations

import dataclasses

import pytest

from common.doc_store import doc_store_base as port

pytestmark = pytest.mark.unit

TENANT = "0123456789abcdef0123456789abcdef"
DATASET = "fedcba9876543210fedcba9876543210"


def test_index_name_is_prefix_plus_validated_tenant_id():
    assert port.index_name(TENANT) == f"ragflow_{TENANT}"


@pytest.mark.parametrize(
    "bad",
    ["*", "a,b", TENANT.upper(), TENANT[:31], f"../{TENANT}", "", "ragflow_x", f"{TENANT}\n", f"{TENANT},{TENANT}", None, 5],
)
def test_index_name_rejects_wildcards_lists_and_malformed_ids(bad):
    with pytest.raises(port.InvalidIndexName):
        port.index_name(bad)


def test_validate_index_names_accepts_a_string_or_a_list():
    full = f"ragflow_{TENANT}"
    assert port.validate_index_names(full) == [full]
    assert port.validate_index_names([full, f"ragflow_{DATASET}"]) == [full, f"ragflow_{DATASET}"]


@pytest.mark.parametrize(
    "bad",
    [
        "*",
        "ragflow_*",
        f"ragflow_{TENANT},ragflow_{DATASET}",
        f"ragflow_{TENANT.upper()}",
        f"ragflow_{TENANT}\n",
        "ragflow_x",
        "",
        [],
        [f"ragflow_{TENANT}", "*"],
        ["", f"ragflow_{TENANT}"],
        "_all",
        None,
    ],
)
def test_validate_index_names_applies_the_same_rule_to_every_element(bad):
    with pytest.raises(port.InvalidIndexName):
        port.validate_index_names(bad)


def test_invalid_index_name_is_a_value_error_and_a_doc_store_error():
    assert issubclass(port.InvalidIndexName, (ValueError, port.DocStoreError))
    assert issubclass(port.InvalidFilter, (ValueError, port.DocStoreError))
    assert issubclass(port.InvalidVectorSize, (ValueError, port.DocStoreError))
    assert issubclass(port.ZeroVectorError, port.DocStoreError)
    assert issubclass(port.DimensionConflict, port.DocStoreError)
    assert issubclass(port.NotSupported, port.DocStoreError)


def test_vector_field_names_the_dimension():
    assert port.vector_field(1024) == "q_1024_vec"
    assert port.vector_field(1) == "q_1_vec"
    assert port.vector_field(4096) == "q_4096_vec"


@pytest.mark.parametrize("bad", [0, -1, 4097, "1024", 1024.0, None, True])
def test_vector_field_rejects_out_of_range_and_non_int(bad):
    with pytest.raises(port.InvalidVectorSize):
        port.vector_field(bad)


@pytest.mark.parametrize("bad", [[], [""], ["abc"], [TENANT.upper()], [TENANT, "*"], TENANT, None, [None], [5]])
def test_require_dataset_ids_rejects_empty_and_non_hex(bad):
    with pytest.raises(port.InvalidFilter):
        port.require_dataset_ids(bad)


def test_require_dataset_ids_returns_the_validated_list():
    assert port.require_dataset_ids([TENANT, DATASET]) == [TENANT, DATASET]


@pytest.mark.parametrize("bad", [{}, None, [], "x"])
def test_require_condition_refuses_an_empty_or_non_dict_condition(bad):
    with pytest.raises(port.InvalidFilter):
        port.require_condition(bad)


def test_require_condition_returns_a_non_empty_dict():
    assert port.require_condition({"doc_id": "d1"}) == {"doc_id": "d1"}


def test_search_result_and_expressions_are_frozen_dataclasses():
    result = port.SearchResult(total=1, hits=[{"id": "x"}], aggregations={})
    assert (result.total, result.hits, result.aggregations) == (1, [{"id": "x"}], {})
    exprs = [
        port.MatchTextExpr(["content_ltks"], "q", 5),
        port.MatchDenseExpr("q_8_vec", [0.1] * 8, "float", "cosine", 5),
        port.MatchSparseExpr(),
        port.FusionExpr("weighted_sum", 5, {"weights": "0.05,0.95"}),
        result,
    ]
    for obj in exprs:
        assert dataclasses.is_dataclass(obj)
        first = dataclasses.fields(obj)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, first, None)


def test_order_by_chains_and_lists_fields():
    order = port.OrderByExpr().asc("position_int").desc("available_int")
    assert order.fields == [("position_int", 0), ("available_int", 1)]


def test_the_port_is_abstract_and_sql_is_not_supported_by_default():
    with pytest.raises(TypeError):
        port.DocStoreConnection()  # type: ignore[abstract]
    names = {"db_type", "health", "create_idx", "delete_idx", "index_exist", "search", "get", "insert", "update", "delete"}
    assert names <= port.DocStoreConnection.__abstractmethods__

    class Minimal(port.DocStoreConnection):
        def db_type(self):
            return "x"

        def health(self):
            return {}

        def create_idx(self, *a, **k):
            return True

        def delete_idx(self, *a, **k):
            return None

        def index_exist(self, *a, **k):
            return False

        def search(self, *a, **k):
            return port.SearchResult(0, [], {})

        def get(self, *a, **k):
            return None

        def insert(self, *a, **k):
            return []

        def update(self, *a, **k):
            return True

        def delete(self, *a, **k):
            return 0

    with pytest.raises(port.NotSupported):
        Minimal().sql("select 1")


def test_the_port_module_imports_nothing_from_api_rag_or_quart():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(port))
    imported = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not imported & {"api", "rag", "quart", "quart_schema", "elasticsearch"}
