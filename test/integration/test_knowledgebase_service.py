"""Dataset service against the real MySQL and Elasticsearch (plan 03-14; KB-01..05, KB-08, KB-09, IDX-04, IDX-05, TEN-16, D-08, D-18, D-27).

Every test registers its own accounts through the running stack; the registry removes exactly those rows afterwards, together with each
tenant's Elasticsearch index (by exact name). Models are saved through ``tenant_model_service`` with a recorded dimension, the same rows
a provider save writes, so the dimension the index is built with is the dimension the model has.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import uuid
from base64 import urlsafe_b64encode
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from elasticsearch import Elasticsearch

from api.db.database import DatabaseLock
from api.db.services import knowledgebase_service as kb
from api.db.services import tenant_model_service as models
from api.db.services.auth_service import AUTH_JWT, Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from common.doc_store.doc_store_base import index_name
from common.model_ref import ModelRef
from common.settings import EsSettings, load_settings
from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.db import root_connection
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

PROVIDER = "OpenRouter"
EMBED_A = f"embed-a@{PROVIDER}"  # dimension 8
EMBED_B = f"embed-b@{PROVIDER}"  # dimension 16
CHAT_A = f"chat-a@{PROVIDER}"


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def llm(settings):
    return dataclasses.replace(settings.llm, encryption_key=urlsafe_b64encode(os.urandom(32)).decode(), key_id="k1")


@pytest.fixture(scope="module")
def raw_es(settings) -> Iterator[Elasticsearch]:
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    yield client
    client.close()


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


def _rows(sql: str, params: tuple = ()) -> list[tuple]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def kb_rows(tenant_id: str) -> int:
    return int(_rows("SELECT COUNT(*) FROM `knowledgebase` WHERE `tenant_id` = %s", (tenant_id,))[0][0])


def fake_key() -> str:
    return "-".join(("sk", "fake", uuid.uuid4().hex[:24]))


def configure(llm, account: Account, *, default_embedding: bool = True) -> None:
    """Models of this workspace: a chat model, embeddings of 8 and 16 dimensions and one too large for the index."""
    listed = [
        models.NewModel(name="chat-a", model_type="chat", dimension=None, max_tokens=8192),
        models.NewModel(name="embed-a", model_type="embedding", dimension=8, max_tokens=8192),
        models.NewModel(name="embed-b", model_type="embedding", dimension=16, max_tokens=8192),
        models.NewModel(name="embed-huge", model_type="embedding", dimension=5000, max_tokens=8192),
    ]
    models.save_instance(llm, account.tenant_id, PROVIDER, "default", api_key=fake_key(), api_base=None, api_version=None, models=listed, replace_key=True)
    if default_embedding:
        models.set_defaults(account.tenant_id, embedding=ModelRef("embed-a", "default", PROVIDER))


def scope_of(account: Account, role: str = "owner") -> ActingScope:
    return ActingScope(tenant_id=account.tenant_id, role=role, subject=role)


def request(name: str | None = None, **kw) -> kb.CreateRequest:
    return kb.CreateRequest(name=unique_name("kb") if name is None else name, **kw)


def make(settings, account: Account, name: str | None = None, **kw) -> kb.DatasetRecord:
    return kb.create_dataset(settings, scope_of(account), account.user_id, request(name, **kw))


def refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def field_mapping(client: Elasticsearch, index: str, field: str) -> dict | None:
    body = client.indices.get_field_mapping(index=index, fields=field).body
    found = body.get(index, {}).get("mappings", {})
    return found[field]["mapping"][field] if field in found else None


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def join(owner: Account, member: Account, role: str | None = None) -> None:
    """Invite, accept and (for admin) promote through the real team API."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        users = f"/api/v1/tenants/{owner.tenant_id}/users"
        assert http.post(users, headers=_bearer(owner.token), json={"email": member.email}).status_code == 200
        accepted = http.patch(f"/api/v1/tenants/{owner.tenant_id}", headers=_bearer(member.token), json={"action": "accept"})
        assert accepted.status_code == 200, accepted.text
        if role:
            promoted = http.patch(f"{users}/{member.user_id}", headers=_bearer(owner.token), json={"role": role})
            assert promoted.status_code == 200, promoted.text


def principal_of(account: Account) -> Principal:
    return Principal(account.user_id, account.tenant_id, "owner", AUTH_JWT, False)


# ----------------------------------------------------------------------------- create


def test_create_returns_the_record_and_provisions_the_real_index(settings, llm, registry, raw_es):
    owner = registry.register(prefix="kbsvc")
    configure(llm, owner)
    record = make(settings, owner, "Docs", description="first", parser_config={"chunk_token_num": 256})

    assert record.tenant_id == owner.tenant_id and record.created_by == owner.user_id
    assert record.permission == "me" and record.doc_num == 0 and record.chunk_num == 0 and record.token_num == 0
    assert record.parser_id == "naive" and record.language == "English" and record.name == "Docs"
    assert record.embd_id == EMBED_A
    assert record.tenant_embd_id == next(m.id for m in models.list_models(owner.tenant_id, "embedding") if m.model == "embed-a")
    assert record.parser_config["chunk_token_num"] == 256, "a stored value wins over the default"
    assert "pages" in record.parser_config and record.parser_config["layout_recognize"] is True, "documented defaults fill the rest"

    index = index_name(owner.tenant_id)
    assert raw_es.indices.exists(index=index).body is True
    mapping = field_mapping(raw_es, index, "q_8_vec")
    assert mapping is not None and mapping["type"] == "dense_vector" and mapping["dims"] == 8
    assert mapping["similarity"] == "cosine"
    assert mapping["index_options"]["type"] == "hnsw" and mapping["index_options"]["m"] == 16 and mapping["index_options"]["ef_construction"] == 200

    row = _rows("SELECT `tenant_id`, `created_by`, `embd_id`, `tenant_embd_id`, `parser_id`, `permission`, `doc_num` FROM `knowledgebase` WHERE `id` = %s", (record.id,))
    assert row == [(owner.tenant_id, owner.user_id, EMBED_A, record.tenant_embd_id, "naive", "me", 0)]
    stored = _rows("SELECT `parser_config` FROM `knowledgebase` WHERE `id` = %s", (record.id,))[0][0]
    assert json.loads(stored)["chunk_token_num"] == 256


def test_a_second_dimension_adds_a_second_field_to_the_same_index(settings, llm, registry, raw_es):
    owner = registry.register(prefix="kbdim")
    configure(llm, owner)
    first = make(settings, owner, embd_id=EMBED_A)
    second = make(settings, owner, embd_id=EMBED_B)
    assert first.embd_id == EMBED_A and second.embd_id == EMBED_B
    index = index_name(owner.tenant_id)
    assert field_mapping(raw_es, index, "q_8_vec")["dims"] == 8
    assert field_mapping(raw_es, index, "q_16_vec")["dims"] == 16
    assert len(raw_es.cat.indices(index=index, format="json").body) == 1, "one index per tenant"


def test_the_creator_may_share_with_the_team_and_the_default_is_private(settings, llm, registry):
    owner = registry.register(prefix="kbperm")
    configure(llm, owner)
    assert make(settings, owner).permission == "me"
    assert make(settings, owner, permission="team").permission == "team"


def test_names_are_unique_per_workspace_case_insensitively(settings, llm, registry):
    owner, other = registry.register(prefix="kbdup"), registry.register(prefix="kbdup2")
    configure(llm, owner)
    configure(llm, other)
    make(settings, owner, "Docs")
    for variant in ("Docs", "docs", " DOCS ", "dOcS"):
        err = refused(lambda variant=variant: make(settings, owner, variant))
        assert err.kind is Kind.CONFLICT and err.reason == "duplicate_name"
    assert kb_rows(owner.tenant_id) == 1
    assert make(settings, other, "Docs").name == "Docs", "another workspace may reuse the name"
    assert make(settings, owner, "Docs 2").name == "Docs 2"


def test_concurrent_creates_of_one_name_yield_exactly_one_dataset(settings, llm, registry):
    owner = registry.register(prefix="kbrace")
    configure(llm, owner)
    name = unique_name("race")
    barrier = threading.Barrier(5)

    def attempt(_: int):
        barrier.wait()
        try:
            return make(settings, owner, name)
        except ServiceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(attempt, range(5)))
    created = [r for r in results if isinstance(r, kb.DatasetRecord)]
    errors = [r for r in results if isinstance(r, ServiceError)]
    assert len(created) == 1 and len(errors) == 4
    assert all(e.kind is Kind.CONFLICT and e.reason == "duplicate_name" for e in errors)
    assert kb_rows(owner.tenant_id) == 1


def test_the_create_lock_name_is_per_workspace_and_within_the_limit():
    name = kb.create_lock_name("a" * 32)
    assert name == "kb-create:" + "a" * 32 and len(name) == 42


def test_a_held_create_lock_is_busy_not_a_hang(settings, llm, registry, monkeypatch):
    owner = registry.register(prefix="kblock")
    configure(llm, owner)
    monkeypatch.setattr(kb, "LOCK_TIMEOUT_SECONDS", 1)
    with DatabaseLock(kb.create_lock_name(owner.tenant_id), 5):
        err = refused(lambda: make(settings, owner))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "busy"
    assert kb_rows(owner.tenant_id) == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "    "},
        {"name": "n" * 129},
        {"parser_id": "bogus"},
        {"permission": "all"},
        {"permission": "ME"},
        {"parser_config": {"k": "v" * 4100}},
        {"description": "d" * 2001},
        {"language": "L" * 33},
        {"avatar": "a" * 200001},
    ],
    ids=["empty-name", "blank-name", "name-129", "parser", "permission-all", "permission-case", "config-over-4096", "description", "language", "avatar"],
)
def test_invalid_input_is_refused_before_anything_is_written(settings, llm, registry, raw_es, kwargs):
    owner = registry.register(prefix="kbinv")
    configure(llm, owner)
    err = refused(lambda: make(settings, owner, **kwargs))
    assert err.kind is Kind.INVALID and err.reason == "dataset_invalid"
    assert kb_rows(owner.tenant_id) == 0
    assert raw_es.indices.exists(index=index_name(owner.tenant_id)).body is False, "no index was provisioned for a refused request"


def test_a_128_character_name_is_accepted(settings, llm, registry):
    owner = registry.register(prefix="kbmax")
    configure(llm, owner)
    assert len(make(settings, owner, "n" * 128).name) == 128


def test_every_documented_parser_id_is_accepted(settings, llm, registry):
    owner = registry.register(prefix="kbpar")
    configure(llm, owner)
    assert kb.PARSER_IDS[0] == "naive" and len(kb.PARSER_IDS) == 14
    assert make(settings, owner, parser_id="qa").parser_id == "qa"


def test_the_embedding_model_must_be_a_configured_embedding_model_of_this_workspace(settings, llm, registry, raw_es):
    owner, stranger = registry.register(prefix="kbmod"), registry.register(prefix="kbmod2")
    configure(llm, owner)
    configure(llm, stranger)
    other_only = models.NewModel(name="stranger-embed", model_type="embedding", dimension=8, max_tokens=8192)
    models.save_instance(llm, stranger.tenant_id, "Ollama", "default", api_key=None, api_base="http://ollama.example:11434", api_version=None, models=[other_only], replace_key=False)
    too_long = "x" * (129 - len(f"@{PROVIDER}")) + f"@{PROVIDER}"
    assert len(too_long) == 129
    for bad in (f"nope@{PROVIDER}", CHAT_A, "embed-a@NoSuchProvider", "not-a-composite-id", "a@b@c@d", too_long, "stranger-embed@Ollama", ""):
        err = refused(lambda bad=bad: make(settings, owner, embd_id=bad))
        assert err.kind is Kind.INVALID and err.reason == "model_unavailable", bad
    assert kb_rows(owner.tenant_id) == 0
    assert raw_es.indices.exists(index=index_name(owner.tenant_id)).body is False, "an over-long or unknown id changes no index"


def test_a_model_whose_dimension_the_index_cannot_hold_is_refused(settings, llm, registry):
    owner = registry.register(prefix="kbbig")
    configure(llm, owner)
    err = refused(lambda: make(settings, owner, embd_id=f"embed-huge@{PROVIDER}"))
    assert err.kind is Kind.INVALID and err.reason == "dimension_unsupported"
    assert kb_rows(owner.tenant_id) == 0


def test_without_an_embd_id_the_workspace_default_is_used_and_nothing_is_auto_picked(settings, llm, registry):
    nothing, chosen = registry.register(prefix="kbnone"), registry.register(prefix="kbdef")
    configure(llm, nothing, default_embedding=False)
    err = refused(lambda: make(settings, nothing))
    assert err.kind is Kind.INVALID and err.reason == "no_default_embedding"
    assert kb_rows(nothing.tenant_id) == 0, "embedding models exist, but none is chosen for the workspace"

    configure(llm, chosen)
    assert make(settings, chosen).embd_id == EMBED_A
    assert make(settings, chosen, embd_id=EMBED_B).embd_id == EMBED_B, "an explicit id wins over the default"


def test_an_unreachable_index_engine_is_unavailable_and_leaves_no_row(settings, llm, registry):
    owner = registry.register(prefix="kbdead")
    configure(llm, owner)
    dead = dataclasses.replace(settings, es=EsSettings(hosts="http://127.0.0.1:1", username="elastic", password="not-a-real-password"))
    err = refused(lambda: kb.create_dataset(dead, scope_of(owner), owner.user_id, request()))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    text = f"{err!r} {err} {err.message}"
    assert "127.0.0.1" not in text and "not-a-real-password" not in text
    assert kb_rows(owner.tenant_id) == 0
    assert make(settings, owner).tenant_id == owner.tenant_id, "the engine coming back is enough: nothing is half-created"


# ----------------------------------------------------------------------------- list


def test_list_shows_own_private_and_all_team_datasets_and_never_anothers_private_one(settings, llm, registry):
    owner, admin, member = registry.register(prefix="kbl-own"), registry.register(prefix="kbl-adm"), registry.register(prefix="kbl-mem")
    join(owner, admin, "admin")
    join(owner, member)
    configure(llm, owner)
    scope = scope_of(owner)
    mine = kb.create_dataset(settings, scope, owner.user_id, request("owner-private"))
    shared = kb.create_dataset(settings, scope, owner.user_id, request("owner-team", permission="team"))
    kb.create_dataset(settings, scope_of(owner, "normal"), member.user_id, request("member-private"))
    theirs_team = kb.create_dataset(settings, scope_of(owner, "normal"), member.user_id, request("member-team", permission="team"))

    def names(user: Account, role: str) -> set[str]:
        items, total = kb.list_datasets(scope_of(owner, role), user.user_id, page=1, page_size=100, keywords=None)
        assert total == len(items)
        return {d.name for d in items}

    assert names(owner, "owner") == {"owner-private", "owner-team", "member-team"}, "no owner override for another member's private dataset"
    assert names(admin, "admin") == {"owner-team", "member-team"}
    assert names(member, "normal") == {"owner-team", "member-private", "member-team"}
    assert kb.list_datasets(scope_of(owner), admin.user_id, page=1, page_size=100, keywords="private")[0] == [], "private datasets stay private under a search too"
    assert {d.id for d in kb.list_datasets(scope_of(owner), owner.user_id, page=1, page_size=100, keywords=None)[0]} == {mine.id, shared.id, theirs_team.id}


def test_list_is_scoped_to_the_acting_workspace(settings, llm, registry):
    one, two = registry.register(prefix="kbw1"), registry.register(prefix="kbw2")
    configure(llm, one)
    configure(llm, two)
    make(settings, one, "in-one", permission="team")
    make(settings, two, "in-two", permission="team")
    items, total = kb.list_datasets(scope_of(one), one.user_id, page=1, page_size=100, keywords=None)
    assert [d.name for d in items] == ["in-one"] and total == 1


def test_list_pages_orders_newest_first_and_caps_the_page_size(settings, llm, registry):
    owner = registry.register(prefix="kbpage")
    configure(llm, owner)
    created = [make(settings, owner, f"page-{i}") for i in range(5)]
    everything, total = kb.list_datasets(scope_of(owner), owner.user_id, page=1, page_size=100, keywords=None)
    assert total == 5 and len(everything) == 5
    stamps = [d.update_time for d in everything]
    assert stamps == sorted(stamps, reverse=True)
    first, total_first = kb.list_datasets(scope_of(owner), owner.user_id, page=1, page_size=2, keywords=None)
    last, total_last = kb.list_datasets(scope_of(owner), owner.user_id, page=3, page_size=2, keywords=None)
    beyond, total_beyond = kb.list_datasets(scope_of(owner), owner.user_id, page=9, page_size=2, keywords=None)
    assert (len(first), len(last), len(beyond)) == (2, 1, 0) and total_first == total_last == total_beyond == 5
    assert {d.id for d in first} | {d.id for d in last} <= {d.id for d in created}
    capped, _ = kb.list_datasets(scope_of(owner), owner.user_id, page=1, page_size=10_000, keywords=None)
    assert len(capped) == 5


def test_keywords_match_case_insensitively_and_percent_and_underscore_are_literal(settings, llm, registry):
    owner = registry.register(prefix="kbkw")
    configure(llm, owner)
    for name in ("Alpha_1", "AlphaX1", "Rate 100% done", "Rate 1000 done", "Back\\slash"):
        make(settings, owner, name)

    def found(keywords: str) -> set[str]:
        return {d.name for d in kb.list_datasets(scope_of(owner), owner.user_id, page=1, page_size=100, keywords=keywords)[0]}

    assert found("ALPHA") == {"Alpha_1", "AlphaX1"}
    assert found("a_1") == {"Alpha_1"}, "the underscore is not a wildcard"
    assert found("%") == {"Rate 100% done"}, "the percent sign is not a wildcard"
    assert found("100%") == {"Rate 100% done"}
    assert found("\\") == {"Back\\slash"}
    assert found("nothing-matches") == set()
    assert len(found("")) == 5, "an empty keyword filters nothing"


# ----------------------------------------------------------------------------- load_visible_dataset


def test_load_visible_dataset_answers_one_not_found_for_every_miss(settings, llm, registry):
    owner, admin, member, stranger = (registry.register(prefix=p) for p in ("kbv-own", "kbv-adm", "kbv-mem", "kbv-str"))
    join(owner, admin, "admin")
    join(owner, member)
    configure(llm, owner)
    private_of_member = kb.create_dataset(settings, scope_of(owner, "normal"), member.user_id, request("v-member-private"))
    team = make(settings, owner, "v-team", permission="team")
    own_private = make(settings, owner, "v-own-private")

    seen = kb.load_visible_dataset(principal_of(owner), own_private.id)
    assert seen.dataset.id == own_private.id and seen.scope.tenant_id == owner.tenant_id and seen.scope.role == "owner"
    assert kb.load_visible_dataset(Principal(member.user_id, member.tenant_id, "owner", AUTH_JWT, False), team.id).scope.role == "normal"
    assert kb.load_visible_dataset(Principal(admin.user_id, admin.tenant_id, "owner", AUTH_JWT, False), team.id).scope.role == "admin"
    assert kb.load_visible_dataset(Principal(member.user_id, member.tenant_id, "owner", AUTH_JWT, False), private_of_member.id).dataset.id == private_of_member.id

    misses = [
        (principal_of(owner), private_of_member.id),  # D-27: no owner override
        (Principal(admin.user_id, admin.tenant_id, "owner", AUTH_JWT, False), private_of_member.id),  # nor for an admin
        (Principal(member.user_id, member.tenant_id, "owner", AUTH_JWT, False), own_private.id),  # nor another member's
        (principal_of(stranger), team.id),  # a foreign workspace
        (principal_of(stranger), own_private.id),
        (principal_of(owner), uuid.uuid4().hex),  # absent
        (principal_of(owner), "not-an-id"),
        (principal_of(owner), ""),
        (principal_of(owner), "x" * 500),
        (principal_of(owner), "%"),
    ]
    answers = set()
    for principal, dataset_id in misses:
        err = refused(lambda principal=principal, dataset_id=dataset_id: kb.load_visible_dataset(principal, dataset_id))
        answers.add((err.kind, err.reason, err.message, str(err)))
    assert answers == {(Kind.NOT_FOUND, "dataset_not_found", "not found", "dataset_not_found")}


def test_the_dto_has_exactly_the_documented_keys(settings, llm, registry):
    owner = registry.register(prefix="kbdto")
    configure(llm, owner)
    record = make(settings, owner)
    plain = kb.dataset_dto(record, embedding_dimension=8, include_limits=None)
    assert set(plain) == {
        "id", "name", "description", "avatar", "language", "permission", "embd_id", "embedding_dimension", "parser_id", "parser_config",
        "doc_num", "chunk_num", "token_num", "tenant_id", "created_by", "create_time", "update_time",
    }  # fmt: skip
    detailed = kb.dataset_dto(record, embedding_dimension=8, include_limits=load_settings().upload)
    assert set(detailed["upload_limits"]) == {"max_file_bytes", "max_files_per_request", "max_documents", "allowed_extensions"}
    assert detailed["embedding_dimension"] == 8
    assert not {"status", "source", "location"} & set(detailed) and not {"status", "source", "location"} & set(detailed["upload_limits"])
