"""Provider save with test-before-save against the real MySQL, the real Valkey and the loopback provider (plan 03-10).

The recording fake provider is a stand-in for a third party over real HTTP, never a stub of our code. Keys are made-up and
built from parts. Rows and Valkey keys are removed by recorded id.
"""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
import socket
from base64 import urlsafe_b64encode
from collections.abc import Iterator

import pytest
import valkey

from api.db.services import provider_service as svc
from api.db.services import tenant_llm_service as store
from api.db.services import tenant_model_service as structure
from api.db.services.provider_service import ModelRequest, SaveRequest
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.model_ref import ModelRef
from common.ratelimit import FixedWindowLimiter
from common.security.secretbox import mask_last4
from common.settings import RateLimitSettings, RedisSettings, Settings, load_settings
from rag.llm import PROVIDER_SPECS, resolve_provider
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection
from test.helpers.fake_provider import SECRET_ECHO_KEY, FakeProvider, running_fake_provider

pytestmark = pytest.mark.integration

COMPAT = "OpenAI-API-Compatible"
CHAT = ModelRequest("chat-x", "chat")
EMBED = ModelRequest("embed-x", "embedding")


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture
def account() -> Iterator[Account]:
    from test.testcases.conftest import BASE_URL

    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="provsvc")
    finally:
        registry.cleanup()


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        yield provider


def make_settings(*, allow_private: bool = True, encryption: bool = True, timeout: int = 5, per_tenant: int = 50) -> Settings:
    base = load_settings()
    llm = dataclasses.replace(
        base.llm,
        encryption_key=urlsafe_b64encode(os.urandom(32)).decode() if encryption else "",
        key_id="k1",
        allow_private_base_urls=allow_private,
        key_test_timeout_seconds=timeout,
        max_retries=0,
    )
    # The stack runs on loopback in tests, so name the services as a deployment would; otherwise the fake provider's own
    # 127.0.0.1 would be on the deny list.
    return dataclasses.replace(
        base,
        llm=llm,
        mysql=dataclasses.replace(base.mysql, host="mysql"),
        redis=dataclasses.replace(base.redis, host="redis"),
        minio=dataclasses.replace(base.minio, host="minio"),
        es=dataclasses.replace(base.es, hosts="http://es01:9200"),
        ratelimit=RateLimitSettings(provider_test_per_tenant=per_tenant, provider_test_window_seconds=60),
    )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def limiter(account: Account) -> Iterator[FixedWindowLimiter]:
    rd = load_settings().redis
    yield FixedWindowLimiter(rd)
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=2, socket_connect_timeout=2)
    try:
        client.delete(f"provider-test:{account.tenant_id}")
    finally:
        client.close()


def fake_key(prefix: str = "sk") -> str:
    return "-".join((prefix, "fake", secrets.token_hex(12)))


def request(account: Account, fake: FakeProvider, *, key: str | None, models: tuple[ModelRequest, ...] = (CHAT, EMBED), provider: str = COMPAT, instance: str = "default", **extra) -> SaveRequest:
    fields = {"base_url": fake.base_url} | extra
    return SaveRequest(tenant_id=account.tenant_id, provider=provider, instance=instance, api_key=key, models=models, **fields)


def windows(text: str, size: int = 8) -> set[str]:
    return {text[i : i + size] for i in range(len(text) - size + 1)}


def assert_no_key(key: str, *objects: object) -> None:
    for obj in objects:
        text = repr(obj) + json.dumps(obj, default=repr) if isinstance(obj, (dict, list)) else repr(obj)
        assert key not in text
        assert not (windows(key) & windows(text)), "an 8-character window of the key appears"


def rows(sql: str, params: tuple = ()) -> list[tuple]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def counts(tenant_id: str) -> dict[str, int]:
    provider_ids = [r[0] for r in rows("SELECT `id` FROM `tenant_model_provider` WHERE `tenant_id` = %s", (tenant_id,))]
    out = {"provider": len(provider_ids), "instance": 0, "model": 0}
    for pid in provider_ids:
        out["instance"] += rows("SELECT COUNT(*) FROM `tenant_model_instance` WHERE `provider_id` = %s", (pid,))[0][0]
        out["model"] += rows("SELECT COUNT(*) FROM `tenant_model` WHERE `provider_id` = %s", (pid,))[0][0]
    out["llm"] = rows("SELECT COUNT(*) FROM `tenant_llm` WHERE `tenant_id` = %s", (tenant_id,))[0][0]
    return out


def model_ids(tenant_id: str) -> dict[str, str]:
    sql = "SELECT m.`model_name`, m.`id` FROM `tenant_model` m JOIN `tenant_model_provider` p ON p.`id` = m.`provider_id` WHERE p.`tenant_id` = %s"
    return {r[0]: r[1] for r in rows(sql, (tenant_id,))}


def opened(settings: Settings, account: Account, model: str, provider: str = COMPAT, instance: str = "default"):
    return store.get_credential(settings.llm, account.tenant_id, ModelRef(model, instance, resolve_provider(provider).name))


def authorization(record) -> str | None:
    return record.headers.get("authorization")


def chat_hits(fake: FakeProvider):
    return fake.hits("/v1/chat/completions")


def embed_hits(fake: FakeProvider):
    return fake.hits("/v1/embeddings")


def closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ----------------------------------------------------------------------------- save


def test_save_tests_each_model_once_stores_both_and_records_the_dimension(settings, account, limiter, fake):
    key = fake_key()
    fake.embedding_dim = 8
    info = svc.save_provider(settings, request(account, fake, key=key), limiter=limiter)

    assert len(chat_hits(fake)) == 1 and len(embed_hits(fake)) == 1
    assert authorization(chat_hits(fake)[0]) == f"Bearer {key}"
    assert authorization(embed_hits(fake)[0]) == f"Bearer {key}"
    body = chat_hits(fake)[0].body
    assert body["max_completion_tokens"] == 16
    assert key not in json.dumps(body)
    assert len(embed_hits(fake)[0].body["input"]) == 1

    by_name = {m.model: m for m in info.models}
    assert by_name["chat-x"].model_type == "chat" and by_name["embed-x"].model_type == "embedding"
    assert by_name["embed-x"].dimension == 8 and by_name["chat-x"].dimension is None
    stored = json.loads(rows("SELECT m.`extra` FROM `tenant_model` m WHERE m.`id` = %s", (by_name["embed-x"].id,))[0][0])
    assert stored["dimension"] == 8
    assert counts(account.tenant_id) == {"provider": 1, "instance": 1, "model": 2, "llm": 2}
    assert_no_key(key, info)


def test_views_carry_no_key_and_only_elevated_callers_see_the_address(settings, account, limiter, fake):
    key = fake_key()
    info = svc.save_provider(settings, request(account, fake, key=key), limiter=limiter)
    spec = resolve_provider(COMPAT)

    public = svc.provider_dto(spec, info, include_credentials=False)
    elevated = svc.provider_dto(spec, info, include_credentials=True)
    assert public["configured"] is True and public["name"] == COMPAT and public["slug"] == spec.slug
    for inst in public["instances"]:
        assert {"last4", "base_url", "api_version"}.isdisjoint(inst)
    assert elevated["instances"][0]["last4"] == mask_last4(key)
    assert elevated["instances"][0]["base_url"] == fake.base_url
    assert "api_version" in elevated["instances"][0]
    model = next(m for m in public["models"] if m["name"] == "embed-x")
    assert model["id"] == "embed-x@OpenAI-API-Compatible" and model["type"] == "embedding" and model["dimension"] == 8
    assert {"instance", "max_tokens", "used_tokens"} <= set(model)

    forbidden = {"status", "source", "token", "secret", "api_key", "key", "envelope"}

    def keys_of(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys_of(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys_of(v)}
        return set()

    assert forbidden.isdisjoint(keys_of(public) | keys_of(elevated))
    assert_no_key(key, public, elevated, info, structure.get_instance(account.tenant_id, COMPAT, "default"))


def test_list_provider_dtos_has_one_entry_per_provider_in_registry_order(settings, account, limiter, fake):
    svc.save_provider(settings, request(account, fake, key=fake_key()), limiter=limiter)
    listed = svc.list_provider_dtos(account.tenant_id, include_credentials=False)
    assert [d["name"] for d in listed] == [s.name for s in PROVIDER_SPECS]
    configured = {d["name"]: d["configured"] for d in listed}
    assert configured[COMPAT] is True
    assert [n for n, c in configured.items() if c] == [COMPAT]


@pytest.mark.parametrize(
    ("model", "kind", "reason"),
    [
        ("fake-401", Kind.INVALID, reasons.PROVIDER_REFUSED),
        ("fake-402", Kind.INVALID, reasons.PROVIDER_REFUSED),
        ("fake-filter", Kind.INVALID, reasons.PROVIDER_REFUSED),
        ("fake-429", Kind.UNAVAILABLE, reasons.PROVIDER_RATE_LIMITED),
        ("fake-500", Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE),
    ],
)
def test_a_refused_test_stores_nothing_and_maps_to_a_typed_reason(settings, account, limiter, fake, model, kind, reason):
    key = fake_key()
    before = counts(account.tenant_id)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=key, models=(ModelRequest(model, "chat"),)), limiter=limiter)
    assert caught.value.kind == kind and caught.value.reason == reason
    assert len(chat_hits(fake)) == 1, "a refused test is not retried"
    assert counts(account.tenant_id) == before
    assert_no_key(key, caught.value.message, caught.value)
    if reason == reasons.PROVIDER_RATE_LIMITED:
        assert caught.value.retry_after is not None


def test_a_provider_401_is_a_refusal_and_never_an_authentication_failure(settings, account, limiter, fake):
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key(), models=(ModelRequest("fake-401", "chat"),)), limiter=limiter)
    assert caught.value.kind == Kind.INVALID
    assert "auth" not in caught.value.reason


def test_an_echoed_secret_never_reaches_the_message(settings, account, limiter, fake):
    key = fake_key()
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=key, models=(ModelRequest("fake-secret-echo", "chat"),)), limiter=limiter)
    assert caught.value.reason == reasons.PROVIDER_REFUSED
    assert key not in caught.value.message and SECRET_ECHO_KEY not in caught.value.message
    assert key not in repr(caught.value) and SECRET_ECHO_KEY not in str(caught.value)


def test_a_slow_provider_times_out(account, limiter, fake):
    settings = make_settings(timeout=1)
    before = counts(account.tenant_id)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, SaveRequest(tenant_id=account.tenant_id, provider=COMPAT, api_key=fake_key(), base_url=fake.slow_url, models=(CHAT,)), limiter=limiter)
    assert caught.value.kind == Kind.TIMEOUT and caught.value.reason == reasons.PROVIDER_TIMEOUT
    assert counts(account.tenant_id) == before


def test_an_absurd_vector_size_is_refused_before_storing(settings, account, limiter, fake):
    fake.embedding_dim = 4097
    before = counts(account.tenant_id)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key(), models=(EMBED,)), limiter=limiter)
    assert caught.value.kind == Kind.INVALID and caught.value.reason == reasons.DIMENSION_UNSUPPORTED
    assert counts(account.tenant_id) == before


def test_the_largest_accepted_vector_size_is_4096(settings, account, limiter, fake):
    fake.embedding_dim = 4096
    info = svc.save_provider(settings, request(account, fake, key=fake_key(), models=(EMBED,)), limiter=limiter)
    assert info.models[0].dimension == 4096


@pytest.mark.parametrize("url", ["http://169.254.169.254/v1", "http://es01:9200", "http://user:pw@127.0.0.1/"])
def test_dangerous_addresses_are_refused_without_a_request(settings, account, limiter, fake, url):
    before = counts(account.tenant_id)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key(), base_url=url), limiter=limiter)
    assert caught.value.kind == Kind.INVALID and caught.value.reason == reasons.BASE_URL_REFUSED
    assert "pw" not in caught.value.message and "169" not in caught.value.message and "es01" not in caught.value.message
    assert fake.requests == []
    assert counts(account.tenant_id) == before


def test_private_addresses_are_refused_unless_the_setting_allows_them(account, limiter, fake):
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(make_settings(allow_private=False), request(account, fake, key=fake_key()), limiter=limiter)
    assert caught.value.reason == reasons.BASE_URL_REFUSED
    assert fake.requests == []


def test_an_unconfigured_key_store_fails_closed_without_a_request(account, limiter, fake):
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(make_settings(encryption=False), request(account, fake, key=fake_key()), limiter=limiter)
    assert caught.value.kind == Kind.UNAVAILABLE and caught.value.reason == reasons.KEY_STORE_UNAVAILABLE
    assert fake.requests == []


def test_an_exhausted_window_is_refused_without_a_request(account, limiter, fake):
    settings = make_settings(per_tenant=1)
    svc.save_provider(settings, request(account, fake, key=fake_key(), models=(CHAT,)), limiter=limiter)
    sent = len(fake.requests)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key(), models=(CHAT,), instance="second"), limiter=limiter)
    assert caught.value.kind == Kind.RATE_LIMITED and caught.value.reason == reasons.PROVIDER_TEST_RATE_LIMITED
    assert caught.value.retry_after is not None and caught.value.retry_after >= 1
    assert len(fake.requests) == sent


def test_an_unreachable_valkey_is_refused_without_a_request(settings, account, fake):
    broken = FixedWindowLimiter(RedisSettings(host="127.0.0.1", port=closed_port(), password="", db=0))
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key()), limiter=broken)
    assert caught.value.kind == Kind.UNAVAILABLE and caught.value.reason == reasons.RATE_LIMIT_UNAVAILABLE
    assert fake.requests == []


def test_an_unknown_provider_is_refused(settings, account, limiter, fake):
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=fake_key(), provider="Nope"), limiter=limiter)
    assert caught.value.reason == reasons.PROVIDER_UNKNOWN
    assert fake.requests == []


# ----------------------------------------------------------------------------- rotation and address change


def test_saving_over_an_instance_with_a_new_key_rotates_every_row(settings, account, limiter, fake):
    k1, k2 = fake_key(), fake_key()
    svc.save_provider(settings, request(account, fake, key=k1), limiter=limiter)
    ids_before = model_ids(account.tenant_id)
    fake.reset()

    info = svc.save_provider(settings, request(account, fake, key=k2, models=(CHAT,)), limiter=limiter)

    assert len(chat_hits(fake)) == 1 and embed_hits(fake) == []
    assert authorization(chat_hits(fake)[0]) == f"Bearer {k2}"
    assert opened(settings, account, "chat-x").api_key == k2
    assert opened(settings, account, "embed-x").api_key == k2
    assert model_ids(account.tenant_id) == ids_before
    assert {m.model for m in info.models} == {"chat-x", "embed-x"}
    dto = svc.provider_dto(resolve_provider(COMPAT), info, include_credentials=True)
    assert dto["instances"][0]["last4"] == mask_last4(k2)
    assert_no_key(k1, info, dto)
    assert_no_key(k2, info, dto)


def test_a_refused_rotation_leaves_the_old_key_everywhere(settings, account, limiter, fake):
    k1, k2 = fake_key(), fake_key()
    svc.save_provider(settings, request(account, fake, key=k1), limiter=limiter)
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=k2, models=(ModelRequest("fake-401", "chat"),)), limiter=limiter)
    assert caught.value.reason == reasons.PROVIDER_REFUSED
    assert opened(settings, account, "chat-x").api_key == k1
    assert opened(settings, account, "embed-x").api_key == k1
    assert counts(account.tenant_id) == {"provider": 1, "instance": 1, "model": 2, "llm": 2}


def test_saving_again_without_a_key_and_with_an_unchanged_address_is_idempotent(settings, account, limiter, fake):
    k1 = fake_key()
    svc.save_provider(settings, request(account, fake, key=k1), limiter=limiter)
    ids_before = model_ids(account.tenant_id)
    fake.reset()

    svc.save_provider(settings, request(account, fake, key=None), limiter=limiter)

    assert authorization(chat_hits(fake)[0]) == f"Bearer {k1}"
    assert authorization(embed_hits(fake)[0]) == f"Bearer {k1}"
    assert model_ids(account.tenant_id) == ids_before
    assert opened(settings, account, "chat-x").api_key == k1


def test_a_keyless_instance_may_move_to_a_new_address(settings, account, limiter, fake):
    model = (ModelRequest("chat-o", "chat"),)
    with running_fake_provider() as second:
        svc.save_provider(settings, SaveRequest(tenant_id=account.tenant_id, provider="Ollama", api_key=None, base_url=fake.ollama_url, models=model), limiter=limiter)
        first_requests = len(fake.requests)
        ids_before = model_ids(account.tenant_id)

        info = svc.save_provider(settings, SaveRequest(tenant_id=account.tenant_id, provider="Ollama", api_key=None, base_url=second.ollama_url, models=model), limiter=limiter)

        assert len(fake.requests) == first_requests
        assert len(second.hits("/api/chat")) == 1
        assert "authorization" not in second.hits("/api/chat")[0].headers
        assert model_ids(account.tenant_id) == ids_before
        dto = svc.provider_dto(resolve_provider("Ollama"), info, include_credentials=True)
        assert dto["instances"][0]["base_url"] == second.ollama_url
        assert opened(settings, account, "chat-o", provider="Ollama").api_base == second.ollama_url


def test_a_changed_dimension_is_a_mismatch_and_changes_nothing(settings, account, limiter, fake):
    k1, k2 = fake_key(), fake_key()
    fake.embedding_dim = 8
    svc.save_provider(settings, request(account, fake, key=k1, models=(EMBED,)), limiter=limiter)
    fake.embedding_dim = 16
    with pytest.raises(ServiceError) as caught:
        svc.save_provider(settings, request(account, fake, key=k2, models=(EMBED,)), limiter=limiter)
    assert caught.value.kind == Kind.INVALID and caught.value.reason == reasons.DIMENSION_MISMATCH
    assert opened(settings, account, "embed-x").api_key == k1
    assert structure.find_model(account.tenant_id, ModelRef("embed-x", "default", COMPAT)).dimension == 8


def test_a_short_key_still_blocks_an_address_change_without_a_new_key(settings, account, limiter, fake):
    short = "".join(("EM", "PTY"))
    with running_fake_provider() as second:
        svc.save_provider(settings, request(account, fake, key=short, models=(CHAT,)), limiter=limiter)
        assert structure.get_instance(account.tenant_id, COMPAT, "default").last4 == ""
        with pytest.raises(ServiceError) as caught:
            svc.save_provider(settings, request(account, second, key=None, models=(CHAT,)), limiter=limiter)
        assert caught.value.kind == Kind.INVALID and caught.value.reason == reasons.KEY_REQUIRED_FOR_NEW_ADDRESS
        assert second.requests == []
    credential = opened(settings, account, "chat-x")
    assert credential.api_key == short and credential.api_base == fake.base_url
    assert structure.get_instance(account.tenant_id, COMPAT, "default").api_base == fake.base_url


# ----------------------------------------------------------------------------- add model and delete


def test_adding_a_model_tests_it_with_the_stored_key(settings, account, limiter, fake):
    k1 = fake_key()
    svc.save_provider(settings, request(account, fake, key=k1, models=(CHAT,)), limiter=limiter)
    fake.reset()

    info = svc.add_models(settings, account.tenant_id, COMPAT, "default", (ModelRequest("chat-y", "chat"),), limiter=limiter)

    assert len(chat_hits(fake)) == 1 and authorization(chat_hits(fake)[0]) == f"Bearer {k1}"
    assert chat_hits(fake)[0].body["model"] == "chat-y"
    assert {m.model for m in info.models} == {"chat-x", "chat-y"}
    assert opened(settings, account, "chat-y").api_key == k1

    with pytest.raises(ServiceError) as caught:
        svc.add_models(settings, account.tenant_id, COMPAT, "default", (ModelRequest("chat-y", "chat"),), limiter=limiter)
    assert caught.value.kind == Kind.CONFLICT and caught.value.reason == reasons.MODEL_EXISTS


def test_adding_a_model_to_an_unconfigured_instance_is_not_found(settings, account, limiter, fake):
    with pytest.raises(ServiceError) as caught:
        svc.add_models(settings, account.tenant_id, COMPAT, "default", (CHAT,), limiter=limiter)
    assert caught.value.kind == Kind.NOT_FOUND and caught.value.reason == reasons.PROVIDER_NOT_CONFIGURED
    assert fake.requests == []


def test_a_model_whose_composite_id_is_too_long_is_refused_without_a_request(settings, account, limiter, fake):
    svc.save_provider(settings, request(account, fake, key=fake_key(), models=(CHAT,)), limiter=limiter)
    fake.reset()
    name = "m" * 128
    with pytest.raises(ServiceError) as caught:
        svc.add_models(settings, account.tenant_id, COMPAT, "default", (ModelRequest(name, "chat"),), limiter=limiter)
    assert caught.value.reason == reasons.MODELS_INVALID
    assert fake.requests == []


def test_delete_provider_removes_everything_once(settings, account, limiter, fake):
    svc.save_provider(settings, request(account, fake, key=fake_key()), limiter=limiter)
    assert svc.delete_provider(account.tenant_id, COMPAT) is True
    assert counts(account.tenant_id) == {"provider": 0, "instance": 0, "model": 0, "llm": 0}
    assert svc.delete_provider(account.tenant_id, COMPAT) is False
