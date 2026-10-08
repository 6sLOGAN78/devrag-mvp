"""Elasticsearch adapter run through the engine-agnostic contract on the live compose stack (plan 03-08, TEST-08).

Every index created here lives under a random 32-hex tenant id and is deleted by its recorded name at teardown.
"""
from __future__ import annotations

import dataclasses
import uuid

import pytest
from common.doc_store.doc_store_base import DocStoreError, index_name
from elasticsearch import Elasticsearch
from rag.utils.es_conn import ESConnection, get_doc_store

from common.settings import EsSettings, load_settings
from test.helpers.doc_store_contract import DocStoreContract

pytestmark = pytest.mark.integration


class _EsEngine:
    """Direct engine access for read-back and for pre-seeding a conflicting field (bypasses the adapter on purpose)."""

    def __init__(self, client: Elasticsearch) -> None:
        self.client = client

    def field_mapping(self, index: str, field: str) -> dict | None:
        body = self.client.indices.get_field_mapping(index=index, fields=field).body
        found = body.get(index, {}).get("mappings", {})
        if field not in found:
            return None
        return found[field]["mapping"][field.rsplit(".", 1)[-1]]

    def seed_vector_field(self, index: str, field: str, dims: int) -> None:
        self.client.indices.create(index=index)
        self.client.indices.put_mapping(
            index=index,
            properties={field: {"type": "dense_vector", "dims": dims, "index": True, "similarity": "cosine"}},
        )


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def raw_client(settings):
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    yield client
    client.close()


class TestEsDocStore(DocStoreContract):
    @pytest.fixture
    def store(self, settings):
        return ESConnection(settings)

    @pytest.fixture
    def engine(self, raw_client):
        return _EsEngine(raw_client)

    @pytest.fixture
    def dataset_ids(self):
        return [uuid.uuid4().hex, uuid.uuid4().hex]

    @pytest.fixture
    def tenant_index(self, raw_client):
        name = index_name(uuid.uuid4().hex)
        yield name
        raw_client.indices.delete(index=name, ignore_unavailable=True)
        assert raw_client.indices.exists(index=name).body is False

    # --- adapter specifics that the engine-agnostic contract does not cover ----------------------------------------
    def test_settings_are_one_shard_no_replica_with_the_scripted_similarity(self, store, raw_client, tenant_index, dataset_ids):
        store.create_idx(tenant_index, dataset_ids[0], 8)
        cfg = raw_client.indices.get_settings(index=tenant_index).body[tenant_index]["settings"]["index"]
        assert cfg["number_of_shards"] == "1" and cfg["number_of_replicas"] == "0"
        assert "scripted_sim" in cfg["similarity"]

    def test_concurrent_create_idx_calls_both_succeed(self, store, tenant_index, dataset_ids):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: store.create_idx(tenant_index, dataset_ids[0], 8), range(4)))
        assert results == [True] * 4

    def test_unsupported_match_and_fusion_are_named(self, store, tenant_index, dataset_ids):
        from common.doc_store.doc_store_base import FusionExpr, MatchSparseExpr, NotSupported

        from test.helpers.doc_store_contract import search

        store.create_idx(tenant_index, dataset_ids[0], 8)
        with pytest.raises(NotSupported):
            search(store, tenant_index, [dataset_ids[0]], matches=[MatchSparseExpr()])
        with pytest.raises(NotSupported, match="rrf"):
            search(store, tenant_index, [dataset_ids[0]], matches=[FusionExpr("rrf", 10)])

    def test_an_unreachable_engine_fails_with_a_message_free_of_host_and_credentials(self, settings):
        dead = dataclasses.replace(settings, es=EsSettings(hosts="http://127.0.0.1:1", username="elastic", password="not-a-real-password"))
        store = ESConnection(dead)
        with pytest.raises(DocStoreError) as err:
            store.index_exist(index_name(uuid.uuid4().hex))
        text = str(err.value)
        assert "127.0.0.1" not in text and "not-a-real-password" not in text
        report = store.health()
        assert report["status"] == "error" and report["type"] == "elasticsearch"
        assert "127.0.0.1" not in repr(report)

    def test_get_doc_store_caches_one_instance_per_hosts_string(self, settings):
        assert get_doc_store(settings) is get_doc_store(settings)
