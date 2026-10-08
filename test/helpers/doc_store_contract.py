"""Engine-agnostic contract for a ``DocStoreConnection`` adapter (plan 03-08, TEST-08, D-22: no mocked engine).

A concrete test class subclasses :class:`DocStoreContract` and supplies five fixtures: ``store`` (the adapter under test),
``tenant_index`` (a valid, not yet created tenant index name that is removed at teardown), ``dataset_ids`` (two distinct
32-hex ids), and ``engine`` (an object with ``field_mapping(index, field) -> dict | None`` and
``seed_vector_field(index, field, dims)`` that talk to the engine directly, bypassing the adapter).

The class name has no ``Test`` prefix, so pytest collects it only through a subclass. Tests never wait on a timer: visibility is the
adapter's responsibility (every write refreshes before it returns).
"""
from __future__ import annotations

import pytest
from common.doc_store.doc_store_base import (
    DimensionConflict,
    DocStoreError,
    FusionExpr,
    InvalidFilter,
    InvalidIndexName,
    InvalidVectorSize,
    MatchDenseExpr,
    MatchTextExpr,
    OrderByExpr,
    SearchResult,
    ZeroVectorError,
)

DIM = 8


def unit_vector(axis: int, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


def row(chunk_id: str, doc_id: str, text: str, axis: int, position: int = 0) -> dict:
    return {
        "id": chunk_id,
        "doc_id": doc_id,
        "content_ltks": text,
        "title_tks": "title",
        "position_int": position,
        "available_int": 1,
        f"q_{DIM}_vec": unit_vector(axis),
    }


def search(store, index, dataset_ids, *, condition=None, matches=None, order_by=None, offset=0, limit=20, select=None):
    return store.search(
        select_fields=select or [],
        highlight_fields=[],
        condition=condition or {},
        match_expressions=matches or [],
        order_by=order_by,
        offset=offset,
        limit=limit,
        index_names=index,
        dataset_ids=dataset_ids,
    )


class DocStoreContract:
    """Behaviour every adapter must show. Fixtures are supplied by the subclass."""

    # --- fixtures to override -------------------------------------------------------------------------------------
    @pytest.fixture
    def store(self):
        raise NotImplementedError

    @pytest.fixture
    def tenant_index(self):
        raise NotImplementedError

    @pytest.fixture
    def dataset_ids(self):
        raise NotImplementedError

    @pytest.fixture
    def engine(self):
        raise NotImplementedError

    # --- index lifecycle ------------------------------------------------------------------------------------------
    def test_create_idx_is_idempotent_and_index_exist_follows_it(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        assert store.index_exist(tenant_index) is False
        assert store.index_exist(tenant_index, ds) is False
        assert store.create_idx(tenant_index, ds, DIM) is True
        assert store.create_idx(tenant_index, ds, DIM) is True
        assert store.index_exist(tenant_index) is True
        assert store.index_exist(tenant_index, ds) is True
        # datasets share the tenant index, so a second dataset sees the same index
        assert store.index_exist(tenant_index, dataset_ids[1]) is True

    def test_vector_field_mapping_has_cosine_hnsw_16_200_and_dimensions_coexist(self, store, engine, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, 1024)
        store.create_idx(tenant_index, ds, 1536)
        for dims in (1024, 1536):
            mapping = engine.field_mapping(tenant_index, f"q_{dims}_vec")
            assert mapping is not None
            assert mapping["type"] == "dense_vector"
            assert mapping["dims"] == dims
            assert mapping["similarity"] == "cosine"
            assert mapping["index_options"]["type"] == "hnsw"
            assert mapping["index_options"]["m"] == 16
            assert mapping["index_options"]["ef_construction"] == 200

    def test_dimension_outside_range_is_refused_before_any_request(self, store, tenant_index, dataset_ids):
        for bad in (0, 4097, -1):
            with pytest.raises(InvalidVectorSize):
                store.create_idx(tenant_index, dataset_ids[0], bad)
        assert store.index_exist(tenant_index) is False

    def test_conflicting_dimension_on_an_existing_field_raises_dimension_conflict(self, store, engine, tenant_index, dataset_ids):
        engine.seed_vector_field(tenant_index, f"q_{DIM}_vec", DIM - 1)
        with pytest.raises(DimensionConflict):
            store.create_idx(tenant_index, dataset_ids[0], DIM)

    def test_dynamic_templates_map_the_idx_06_fields(self, store, engine, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        full = row("c1", "d1", "alpha", 0)
        full.update(
            {
                "important_kwd": ["k1", "k2"],
                "question_tks": "what is alpha",
                "title_sm_tks": "title sm",
                "important_tks": "imp",
                "content_sm_ltks": "alpha sm",
            }
        )
        assert store.insert([full], tenant_index, ds) == []
        for field in ("content_ltks", "title_tks", "question_tks", "title_sm_tks", "important_tks", "content_sm_ltks"):
            mapping = engine.field_mapping(tenant_index, field)
            assert mapping is not None, field
            assert mapping["type"] == "text", field
            assert mapping["analyzer"] == "whitespace", field
        for field in ("id", "doc_id", "kb_id", "important_kwd"):
            mapping = engine.field_mapping(tenant_index, field)
            assert mapping is not None and mapping["type"] == "keyword", field
        for field in ("position_int", "available_int"):
            mapping = engine.field_mapping(tenant_index, field)
            assert mapping is not None and mapping["type"] == "integer", field

    # --- insert / get / update / delete ---------------------------------------------------------------------------
    def test_insert_get_update_delete_round_trip(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        rows = [row("c1", "d1", "alpha", 0), row("c2", "d1", "beta", 1), row("c3", "d2", "gamma", 2)]
        assert store.insert(rows, tenant_index, ds) == []

        got = store.get("c1", tenant_index, [ds])
        assert got is not None and got["doc_id"] == "d1" and got["content_ltks"] == "alpha" and got["kb_id"] == ds
        assert store.get("missing", tenant_index, [ds]) is None

        assert store.update({"id": "c1"}, {"available_int": 0, "content_ltks": "alpha changed"}, tenant_index, ds) is True
        changed = store.get("c1", tenant_index, [ds])
        assert changed["available_int"] == 0 and changed["content_ltks"] == "alpha changed"

        assert store.delete({"doc_id": ["d1"]}, tenant_index, ds) == 2
        assert store.get("c1", tenant_index, [ds]) is None
        assert store.get("c3", tenant_index, [ds]) is not None

    def test_insert_refuses_a_zero_vector_and_inserts_nothing(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        bad = row("c2", "d1", "beta", 1)
        bad[f"q_{DIM}_vec"] = [0.0] * DIM
        with pytest.raises(ZeroVectorError):
            store.insert([row("c1", "d1", "alpha", 0), bad], tenant_index, ds)
        assert search(store, tenant_index, [ds]).total == 0

    def test_insert_refuses_a_vector_of_the_wrong_length(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        bad = row("c1", "d1", "alpha", 0)
        bad[f"q_{DIM}_vec"] = [0.5] * (DIM - 1)
        with pytest.raises(DocStoreError) as err:
            store.insert([bad], tenant_index, ds)
        assert not isinstance(err.value, ZeroVectorError)
        assert search(store, tenant_index, [ds]).total == 0

    def test_insert_refuses_a_row_owned_by_another_dataset(self, store, tenant_index, dataset_ids):
        ds, other = dataset_ids
        store.create_idx(tenant_index, ds, DIM)
        stolen = row("c1", "d1", "alpha", 0)
        stolen["kb_id"] = other
        with pytest.raises(InvalidFilter):
            store.insert([stolen], tenant_index, ds)

    # --- search ---------------------------------------------------------------------------------------------------
    def test_text_search_is_scoped_to_the_requested_datasets(self, store, tenant_index, dataset_ids):
        a, b = dataset_ids
        store.create_idx(tenant_index, a, DIM)
        store.insert([row("a1", "da", "shared words here", 0)], tenant_index, a)
        store.insert([row("b1", "db", "shared words here", 1)], tenant_index, b)

        text = MatchTextExpr(["content_ltks"], "shared", 10)
        only_a = search(store, tenant_index, [a], matches=[text])
        assert [h["id"] for h in only_a.hits] == ["a1"] and only_a.total == 1
        only_b = search(store, tenant_index, [b], matches=[text])
        assert [h["id"] for h in only_b.hits] == ["b1"]
        both = search(store, tenant_index, [a, b], matches=[text])
        assert {h["id"] for h in both.hits} == {"a1", "b1"} and both.total == 2
        assert store.get("b1", tenant_index, [a]) is None

    def test_dense_search_returns_the_nearest_row_first(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        store.insert([row("c1", "d1", "alpha", 0), row("c2", "d1", "beta", 1), row("c3", "d1", "gamma", 2)], tenant_index, ds)
        near = MatchDenseExpr(f"q_{DIM}_vec", unit_vector(1), "float", "cosine", 3)
        result = search(store, tenant_index, [ds], matches=[near], limit=3)
        assert isinstance(result, SearchResult)
        assert result.hits[0]["id"] == "c2"
        assert len(result.hits) == 3

    def test_hybrid_search_with_weighted_fusion_returns_both_kinds_ordered_by_combined_score(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        store.insert([row("t1", "d1", "apple", 0), row("v1", "d1", "cherry", 1), row("n1", "d1", "plum", 2)], tenant_index, ds)
        text = MatchTextExpr(["content_ltks"], "apple", 10)
        dense = MatchDenseExpr(f"q_{DIM}_vec", unit_vector(1), "float", "cosine", 1)
        fusion = FusionExpr("weighted_sum", 10, {"weights": "0.05,0.95"})
        result = search(store, tenant_index, [ds], matches=[text, dense, fusion], limit=10)
        ids = [h["id"] for h in result.hits]
        assert "t1" in ids and "v1" in ids and "n1" not in ids
        assert ids[0] == "v1"  # the dense side carries 0.95 of the weight
        scores = [h["_score"] for h in result.hits]
        assert scores == sorted(scores, reverse=True)

    def test_offset_and_limit_page_the_results_and_select_fields_limits_the_row(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        store.insert([row(f"c{i}", "d1", f"text{i}", i, position=i) for i in range(5)], tenant_index, ds)
        order = OrderByExpr().asc("position_int")
        page = search(store, tenant_index, [ds], order_by=order, offset=2, limit=2)
        assert [h["id"] for h in page.hits] == ["c2", "c3"] and page.total == 5
        slim = search(store, tenant_index, [ds], order_by=order, limit=1, select=["doc_id"])
        assert set(slim.hits[0]) <= {"id", "doc_id", "_score"}
        assert slim.hits[0]["doc_id"] == "d1"

    def test_condition_filters_the_search(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        store.insert([row("c1", "d1", "x", 0), row("c2", "d2", "x", 1), row("c3", "d3", "x", 2)], tenant_index, ds)
        got = search(store, tenant_index, [ds], condition={"doc_id": ["d1", "d3"]})
        assert {h["id"] for h in got.hits} == {"c1", "c3"}

    # --- refusals, all before any request -------------------------------------------------------------------------
    def test_search_with_empty_dataset_ids_is_refused(self, store, tenant_index):
        with pytest.raises(InvalidFilter):
            search(store, tenant_index, [])

    @pytest.mark.parametrize("bad", ["*", "ragflow_*", "_all", "a,b"])
    def test_wildcard_and_list_index_names_are_refused(self, store, dataset_ids, bad):
        with pytest.raises(InvalidIndexName):
            search(store, bad, [dataset_ids[0]])
        with pytest.raises(InvalidIndexName):
            store.index_exist(bad)
        with pytest.raises(InvalidIndexName):
            store.insert([row("c1", "d1", "x", 0)], bad, dataset_ids[0])

    def test_empty_condition_is_refused_for_update_and_delete(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        store.insert([row("c1", "d1", "alpha", 0)], tenant_index, ds)
        with pytest.raises(InvalidFilter):
            store.delete({}, tenant_index, ds)
        with pytest.raises(InvalidFilter):
            store.update({}, {"available_int": 0}, tenant_index, ds)
        assert store.get("c1", tenant_index, [ds]) is not None

    def test_hostile_condition_keys_are_refused(self, store, tenant_index, dataset_ids):
        ds = dataset_ids[0]
        store.create_idx(tenant_index, ds, DIM)
        for key in ("doc_id; DROP", "a.b", "", "x" * 65, "kb_id\n"):
            with pytest.raises(InvalidFilter):
                store.delete({key: "v"}, tenant_index, ds)
            with pytest.raises(InvalidFilter):
                search(store, tenant_index, [ds], condition={key: "v"})

    def test_a_condition_cannot_widen_the_scope_beyond_the_dataset(self, store, tenant_index, dataset_ids):
        a, b = dataset_ids
        store.create_idx(tenant_index, a, DIM)
        store.insert([row("a1", "d1", "x", 0)], tenant_index, a)
        store.insert([row("b1", "d1", "x", 1)], tenant_index, b)
        assert store.delete({"doc_id": "d1"}, tenant_index, a) == 1
        assert store.get("b1", tenant_index, [b]) is not None
        assert search(store, tenant_index, [b], condition={"kb_id": a}).total == 0

    # --- dataset removal and health -------------------------------------------------------------------------------
    def test_delete_idx_removes_one_datasets_rows_and_keeps_the_index(self, store, tenant_index, dataset_ids):
        a, b = dataset_ids
        store.create_idx(tenant_index, a, DIM)
        store.insert([row("a1", "d1", "x", 0), row("a2", "d1", "y", 1)], tenant_index, a)
        store.insert([row("b1", "d2", "x", 2)], tenant_index, b)
        store.delete_idx(tenant_index, a)
        assert store.index_exist(tenant_index) is True
        assert search(store, tenant_index, [a]).total == 0
        assert [h["id"] for h in search(store, tenant_index, [b]).hits] == ["b1"]
        store.delete_idx(tenant_index, a)  # idempotent

    def test_health_reports_status_and_type_and_no_host_text(self, store):
        report = store.health()
        assert {"status", "type"} <= set(report)
        assert report["status"] == "ok"
        assert store.db_type() == report["type"]
        text = repr(report)
        assert "127.0.0.1" not in text and "9200" not in text and "http" not in text

    def test_insert_into_an_index_that_was_never_created_is_refused_and_creates_nothing(self, store, tenant_index, dataset_ids):
        with pytest.raises(DocStoreError) as err:
            store.insert([row("c1", "d1", "x", 0)], tenant_index, dataset_ids[0])
        assert "127.0.0.1" not in str(err.value) and "http" not in str(err.value).lower()
        assert store.index_exist(tenant_index) is False

