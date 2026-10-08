"""Provider keys reach MySQL only as bound ciphertext (SEC-03, LLM-16, D-17; plan 03-09; T-03-09-01, T-03-09-02, T-03-09-06).

Real MySQL, real account, raw SQL reads through the root connection. Test keys are made-up and assembled at run time.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import secrets
from base64 import urlsafe_b64encode
from collections.abc import Iterator

import pytest
from api.db.services.service_errors import Kind, ServiceError
from common.model_ref import ModelRef

from api.db.services import tenant_llm_service as store
from api.db.services import tenant_model_service as models
from common.settings import LlmSettings, load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection

pytestmark = pytest.mark.integration

ENVELOPE = re.compile(r"^v1:k1:[A-Za-z0-9_-]+$")


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def llm() -> LlmSettings:
    return dataclasses.replace(load_settings().llm, encryption_key=urlsafe_b64encode(os.urandom(32)).decode(), key_id="k1")


@pytest.fixture
def account() -> Iterator[Account]:
    from test.testcases.conftest import BASE_URL

    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="llmstore")
    finally:
        registry.cleanup()


def fake_key() -> str:
    return "-".join(("sk", "fake", secrets.token_hex(12)))


def _rows(sql: str, params: tuple) -> list[tuple]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def _execute(sql: str, params: tuple) -> None:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
    finally:
        conn.close()


def dump_all(tenant_id: str) -> list[str]:
    """Every column value of the tenant's rows in the four model tables, as strings."""
    out: list[str] = []
    providers = _rows("SELECT * FROM `tenant_model_provider` WHERE `tenant_id` = %s", (tenant_id,))
    out += [str(v) for row in providers for v in row]
    out += [str(v) for row in _rows("SELECT * FROM `tenant_llm` WHERE `tenant_id` = %s", (tenant_id,)) for v in row]
    for provider_id in (row[0] for row in providers):
        for table in ("tenant_model_instance", "tenant_model"):
            out += [str(v) for row in _rows(f"SELECT * FROM `{table}` WHERE `provider_id` = %s", (provider_id,)) for v in row]  # noqa: S608
    return out


def assert_no_key_material(tenant_id: str, *keys: str) -> None:
    blob = "\n".join(dump_all(tenant_id))
    for key in keys:
        assert key not in blob
        for i in range(len(key) - 7):
            assert key[i : i + 8] not in blob


def _llm_rows(tenant_id: str) -> dict[str, tuple[str, str]]:
    return {r[0]: (r[1], r[2]) for r in _rows("SELECT `llm_name`, `api_key`, `llm_factory` FROM `tenant_llm` WHERE `tenant_id` = %s", (tenant_id,))}


def _chat(name: str = "chat-a") -> models.NewModel:
    return models.NewModel(name=name, model_type="chat", dimension=None, max_tokens=8192)


def _embed(name: str = "embed-a", dimension: int = 1024) -> models.NewModel:
    return models.NewModel(name=name, model_type="embedding", dimension=dimension, max_tokens=8192)


def _save(llm_settings: LlmSettings, account: Account, key: str | None, *, provider: str = "OpenRouter", instance: str = "default", model_list=None, **kw):
    return models.save_instance(
        llm_settings,
        account.tenant_id,
        provider,
        instance,
        api_key=key,
        api_base=kw.pop("api_base", None),
        api_version=kw.pop("api_version", None),
        models=model_list if model_list is not None else [_chat(), _embed()],
        replace_key=kw.pop("replace_key", True),
    )


def test_key_is_envelope_only_in_tenant_llm(llm, account):
    key = fake_key()
    _save(llm, account, key, api_base="https://openrouter.example/v1", api_version="2024-02-01")
    assert_no_key_material(account.tenant_id, key)

    rows = _llm_rows(account.tenant_id)
    assert set(rows) == {"chat-a", "embed-a"}
    assert all(ENVELOPE.match(envelope) for envelope, _ in rows.values())

    provider_id = _rows("SELECT `id` FROM `tenant_model_provider` WHERE `tenant_id` = %s", (account.tenant_id,))[0][0]
    ((mask, extra),) = _rows("SELECT `api_key`, `extra` FROM `tenant_model_instance` WHERE `provider_id` = %s", (provider_id,))
    assert mask.endswith(key[-4:]) and key[-5:] not in mask and key[-8:] not in mask
    parsed = json.loads(extra)
    assert parsed["last4"] == key[-4:]
    assert parsed["api_base"] == "https://openrouter.example/v1"
    assert parsed["api_version"] == "2024-02-01"
    assert not any(key[-8:] in str(v) for v in parsed.values())


def test_stored_envelope_opens_back_to_the_key(llm, account):
    key = fake_key()
    _save(llm, account, key)
    envelope = _llm_rows(account.tenant_id)["chat-a"][0]
    assert store.open_key(llm, account.tenant_id, "OpenRouter", "default", envelope) == key
    cred = store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "default", "OpenRouter"), "chat")
    assert cred is not None
    assert cred.api_key == key
    assert (cred.provider, cred.instance, cred.model, cred.model_type) == ("OpenRouter", "default", "chat-a", "chat")


def test_copied_envelope_fails(llm, account):
    key = fake_key()
    other = fake_key()
    _save(llm, account, key, provider="OpenRouter")
    _save(llm, account, other, provider="OpenAI", model_list=[_chat("gpt-x")])
    envelope = _llm_rows(account.tenant_id)["chat-a"][0]

    for provider, instance in (("OpenAI", "default"), ("OpenRouter", "prod")):
        with pytest.raises(ServiceError) as err:
            store.open_key(llm, account.tenant_id, provider, instance, envelope)
        assert err.value.kind is Kind.UNAVAILABLE
        assert err.value.reason == "key_unreadable"
        assert key not in err.value.message and key not in str(err.value) and key not in repr(err.value)
    with pytest.raises(ServiceError):
        store.open_key(llm, "0" * 32, "OpenRouter", "default", envelope)

    # Copied into another provider's stored row: that model's credential can no longer be opened.
    _execute("UPDATE `tenant_llm` SET `api_key` = %s WHERE `tenant_id` = %s AND `llm_name` = %s", (envelope, account.tenant_id, "gpt-x"))
    with pytest.raises(ServiceError) as err:
        store.get_credential(llm, account.tenant_id, ModelRef("gpt-x", "default", "OpenAI"), "chat")
    assert err.value.reason == "key_unreadable"
    assert_no_key_material(account.tenant_id, key, other)


def test_unconfigured_key_store_stores_nothing(account):
    empty = LlmSettings(encryption_key="")
    key = fake_key()
    with pytest.raises(ServiceError) as err:
        _save(empty, account, key)
    assert err.value.kind is Kind.UNAVAILABLE
    assert err.value.reason == "key_store_unavailable"
    assert key not in err.value.message
    assert dump_all(account.tenant_id) == []
    assert _llm_rows(account.tenant_id) == {}


def test_open_with_unconfigured_store_is_unavailable(llm, account):
    _save(llm, account, fake_key())
    envelope = _llm_rows(account.tenant_id)["chat-a"][0]
    with pytest.raises(ServiceError) as err:
        store.open_key(LlmSettings(encryption_key=""), account.tenant_id, "OpenRouter", "default", envelope)
    assert err.value.reason == "key_store_unavailable"


def test_credential_repr_and_str_hide_the_key():
    key = fake_key()
    cred = store.ModelCredential(provider="OpenAI", instance="default", model="m", model_type="chat", api_key=key, api_base=None, api_version=None, max_tokens=1)
    for text in (repr(cred), str(cred), f"{cred}", f"{cred!r}"):
        assert key not in text
        assert key[-6:] not in text
    assert "OpenAI" in repr(cred)


def test_get_credential_is_tenant_and_instance_scoped(llm, account):
    from test.testcases.conftest import BASE_URL

    key = fake_key()
    _save(llm, account, key, instance="prod")
    ok = ModelRef("chat-a", "prod", "OpenRouter")
    assert store.get_credential(llm, account.tenant_id, ok).api_key == key
    assert store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "default", "OpenRouter")) is None
    assert store.get_credential(llm, account.tenant_id, ModelRef("missing", "prod", "OpenRouter")) is None
    assert store.get_credential(llm, account.tenant_id, ok, "embedding") is None
    assert store.get_credential(llm, account.tenant_id, ModelRef("embed-a", "prod", "OpenRouter"), "embedding").api_key == key
    assert store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "prod", "nope")) is None
    other = AccountRegistry(BASE_URL)
    try:
        stranger = other.register(prefix="llmother")
        assert store.get_credential(llm, stranger.tenant_id, ok) is None
    finally:
        other.cleanup()


def test_keyless_provider_has_no_envelope_and_no_key(llm, account):
    _save(llm, account, None, provider="Ollama", api_base="http://ollama.example:11434", model_list=[_chat("llama3")], replace_key=False)
    assert _llm_rows(account.tenant_id)["llama3"][0] in ("", None)
    cred = store.get_credential(llm, account.tenant_id, ModelRef("llama3", "default", "Ollama"), "chat")
    assert cred is not None and cred.api_key is None
    assert cred.api_base == "http://ollama.example:11434"
    assert models.get_instance(account.tenant_id, "Ollama", "default").has_key is False


def test_internal_hosts_names_the_backing_services():
    hosts = store.internal_hosts(load_settings())
    settings = load_settings()
    assert settings.mysql.host.lower() in hosts
    assert settings.redis.host.lower() in hosts
    assert settings.minio.host.lower() in hosts
    assert isinstance(hosts, frozenset)
    assert all(h == h.lower() for h in hosts)
