"""E2E-03: create a knowledge base through the API and prove the row and the real index (plan 03-14; KB-03, IDX-04, IDX-05, E2E-03).

docs/21-end-to-end-flows/create-knowledge-base.md: the dataset is a MySQL row plus a vector field in the tenant's Elasticsearch index.
The index name is the tenant's (``ragflow_{tenant_id}``, decision recorded by plan 03-28); the dense vector field is ``q_{dim}_vec``.
Here the embedding model is the fake provider's, configured with 1024 dimensions through a real provider save, and the assertions read
MySQL and Elasticsearch directly, not the API's own account of what it did.
"""
from __future__ import annotations

import httpx
import pytest
from elasticsearch import Elasticsearch

from common.settings import load_settings
from test.conftest import stack_env
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.testcases.test_dataset_flow import DATASETS, DEFAULTS, EMBED_ID, PROVIDERS
from test.testcases.test_provider_flow import api, ok, registry, save_body, sql  # noqa: F401  (registry is a fixture)

pytestmark = pytest.mark.e2e

DIMENSION = 1024


@pytest.fixture(scope="module")
def raw_es():
    es = load_settings().es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    yield client
    client.close()


def vector_mapping(client: Elasticsearch, index: str, field: str) -> dict | None:
    body = client.indices.get_field_mapping(index=index, fields=field).body
    found = body.get(index, {}).get("mappings", {})
    return found[field]["mapping"][field] if field in found else None


def test_creating_a_dataset_writes_the_row_and_the_vector_field(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, raw_es: Elasticsearch) -> None:  # noqa: F811
    fake = fake_provider_stack
    fake.embedding_dim = DIMENSION
    owner = registry.register(prefix="e2ekb")
    saved = ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    assert {m["name"]: m["dimension"] for m in saved["models"]}["fake-embed"] == DIMENSION, "the dimension is recorded at provider save"
    ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"embedding": EMBED_ID}))
    index = f"ragflow_{owner.tenant_id}"
    assert raw_es.indices.exists(index=index).body is False, "nothing exists before the dataset does"

    data = ok(api(ingress, "POST", DATASETS, owner.token, body={"name": "E2E knowledge base"}))
    assert data["embedding_dimension"] == DIMENSION

    # MySQL, read by an independent connection.
    rows = sql(
        "SELECT `tenant_id`, `created_by`, `embd_id`, `parser_id`, `permission`, `name`, `doc_num` FROM `knowledgebase` WHERE `id` = %s",
        (data["id"],),
    )
    assert rows == [(owner.tenant_id, owner.user_id, EMBED_ID, "naive", "me", "E2E knowledge base", 0)]

    # Elasticsearch, read through the raw client.
    assert raw_es.indices.exists(index=index).body is True
    mapping = vector_mapping(raw_es, index, "q_1024_vec")
    assert mapping is not None, "the vector field of this dimension exists"
    assert mapping["type"] == "dense_vector" and mapping["dims"] == DIMENSION
    assert mapping["similarity"] == "cosine"
    options = mapping["index_options"]
    assert options["type"] == "hnsw" and options["m"] == 16 and options["ef_construction"] == 200
    assert vector_mapping(raw_es, index, "q_8_vec") is None, "only the dimension in use is mapped"


def test_cleanup_removes_the_tenants_rows_index_and_objects_and_nothing_else(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, raw_es: Elasticsearch) -> None:  # noqa: F811
    from minio import Minio

    fake = fake_provider_stack
    mine, bystander = registry.register(prefix="e2ecl"), registry.register(prefix="e2ecl2")
    for who in (mine, bystander):
        ok(api(ingress, "PUT", PROVIDERS, who.token, body=save_body(fake)))
        ok(api(ingress, "PATCH", DEFAULTS, who.token, body={"embedding": EMBED_ID}))
        ok(api(ingress, "POST", DATASETS, who.token, body={"name": "cleanup probe"}))

    env = stack_env()
    storage = Minio(f"127.0.0.1:{env.get('MINIO_PORT', '9000')}", access_key=env.get("MINIO_USER", "rag_flow"), secret_key=env["MINIO_PASSWORD"], secure=False)
    import io

    keys = {who.tenant_id: f"{who.tenant_id}/cleanup-probe.txt" for who in (mine, bystander)}
    for key in keys.values():
        storage.put_object("ragflow", key, io.BytesIO(b"probe"), 5)

    def left(who) -> tuple[int, bool, bool]:
        count = int(sql("SELECT COUNT(*) FROM `knowledgebase` WHERE `tenant_id` = %s", (who.tenant_id,))[0][0])
        index = raw_es.indices.exists(index=f"ragflow_{who.tenant_id}").body
        object_exists = any(True for _ in storage.list_objects("ragflow", prefix=f"{who.tenant_id}/", recursive=True))
        return count, bool(index), object_exists

    assert left(mine) == (1, True, True) and left(bystander) == (1, True, True)
    from test.helpers.accounts import delete_accounts

    try:
        delete_accounts([mine])
        registry.created.remove(mine)
        assert left(mine) == (0, False, False), "the recorded tenant's row, index and objects are gone"
        assert left(bystander) == (1, True, True), "another tenant's are untouched"
    finally:
        registry.cleanup()
    assert left(bystander) == (0, False, False)
