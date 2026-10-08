"""Model structure rows, defaults and usage counting against the real MySQL (plan 03-09; LLM-29, TEN-12, LLM-21).

Every test registers its own account and the registry removes exactly those rows afterwards.
"""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
from base64 import urlsafe_b64encode
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from api.db.services.service_errors import Kind, ServiceError
from common.model_ref import ModelRef, parse_model_ref

from api.db.services import tenant_llm_service as store
from api.db.services import tenant_model_service as svc
from common.settings import load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection

pytestmark = pytest.mark.integration

INT_CAP = 2147483647


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def llm():
    return dataclasses.replace(load_settings().llm, encryption_key=urlsafe_b64encode(os.urandom(32)).decode(), key_id="k1")


@pytest.fixture
def account() -> Iterator[Account]:
    from test.testcases.conftest import BASE_URL

    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="llmsvc")
    finally:
        registry.cleanup()


def fake_key() -> str:
    return "-".join(("sk", "fake", secrets.token_hex(12)))


def _rows(sql: str, params: tuple = ()) -> list[tuple]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def _execute(sql: str, params: tuple = ()) -> None:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
    finally:
        conn.close()


def counts(tenant_id: str) -> dict[str, int]:
    provider_ids = [r[0] for r in _rows("SELECT `id` FROM `tenant_model_provider` WHERE `tenant_id` = %s", (tenant_id,))]
    out = {"provider": len(provider_ids), "instance": 0, "model": 0}
    for pid in provider_ids:
        out["instance"] += _rows("SELECT COUNT(*) FROM `tenant_model_instance` WHERE `provider_id` = %s", (pid,))[0][0]
        out["model"] += _rows("SELECT COUNT(*) FROM `tenant_model` WHERE `provider_id` = %s", (pid,))[0][0]
    out["llm"] = _rows("SELECT COUNT(*) FROM `tenant_llm` WHERE `tenant_id` = %s", (tenant_id,))[0][0]
    return out


def envelopes(tenant_id: str) -> dict[str, str]:
    return {r[0]: r[1] for r in _rows("SELECT `llm_name`, `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s", (tenant_id,))}


def model_ids(tenant_id: str) -> dict[str, str]:
    sql = "SELECT m.`model_name`, m.`id` FROM `tenant_model` m JOIN `tenant_model_provider` p ON p.`id` = m.`provider_id` WHERE p.`tenant_id` = %s"
    return {r[0]: r[1] for r in _rows(sql, (tenant_id,))}


def chat(name: str = "chat-a", max_tokens: int = 8192) -> svc.NewModel:
    return svc.NewModel(name=name, model_type="chat", dimension=None, max_tokens=max_tokens)


def embed(name: str = "embed-a", dimension: int = 1024) -> svc.NewModel:
    return svc.NewModel(name=name, model_type="embedding", dimension=dimension, max_tokens=8192)


def save(llm, account, key, *, provider="OpenRouter", instance="default", model_list=None, api_base=None, api_version=None, replace_key=True):
    return svc.save_instance(
        llm,
        account.tenant_id,
        provider,
        instance,
        api_key=key,
        api_base=api_base,
        api_version=api_version,
        models=[chat(), embed()] if model_list is None else model_list,
        replace_key=replace_key,
    )


def tenant_defaults(tenant_id: str) -> tuple:
    return _rows("SELECT `llm_id`, `tenant_llm_id`, `embd_id`, `tenant_embd_id` FROM `tenant` WHERE `id` = %s", (tenant_id,))[0]


# ----------------------------------------------------------------------------- structure


def test_save_creates_the_four_row_kinds(llm, account):
    info = save(llm, account, fake_key())
    assert counts(account.tenant_id) == {"provider": 1, "instance": 1, "model": 2, "llm": 2}
    assert info.provider == "OpenRouter"
    assert [i.instance for i in info.instances] == ["default"]
    by_name = {m.model: m for m in info.models}
    assert by_name["chat-a"].model_type == "chat" and by_name["chat-a"].dimension is None
    assert by_name["embed-a"].model_type == "embedding" and by_name["embed-a"].dimension == 1024
    assert by_name["chat-a"].composite == "chat-a@OpenRouter"
    assert by_name["embed-a"].max_tokens == 8192 and by_name["embed-a"].used_tokens == 0
    types = dict(_rows("SELECT m.`model_name`, m.`model_type` FROM `tenant_model` m JOIN `tenant_model_provider` p ON p.`id` = m.`provider_id` WHERE p.`tenant_id` = %s", (account.tenant_id,)))
    assert types == {"chat-a": 1, "embed-a": 2}
    llm_types = dict(_rows("SELECT `llm_name`, `model_type` FROM `tenant_llm` WHERE `tenant_id` = %s", (account.tenant_id,)))
    assert llm_types == {"chat-a": "chat", "embed-a": "embedding"}


def test_non_default_instance_uses_the_three_part_composite(llm, account):
    info = save(llm, account, fake_key(), instance="prod")
    assert {m.composite for m in info.models} == {"chat-a@prod@OpenRouter", "embed-a@prod@OpenRouter"}


def test_provider_name_is_canonical(llm, account):
    info = save(llm, account, fake_key(), provider="openrouter")
    assert info.provider == "OpenRouter"
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), provider="NoSuchProvider")
    assert err.value.kind is Kind.INVALID and err.value.reason == "provider_unknown"


def test_resave_without_key_keeps_the_envelope_byte_for_byte(llm, account):
    save(llm, account, fake_key(), api_base="https://one.example/v1")
    before = envelopes(account.tenant_id)
    ((mask_before,),) = _rows("SELECT i.`api_key` FROM `tenant_model_instance` i JOIN `tenant_model_provider` p ON p.`id` = i.`provider_id` WHERE p.`tenant_id` = %s", (account.tenant_id,))
    info = save(llm, account, None, api_base="https://two.example/v1", replace_key=False)
    assert envelopes(account.tenant_id) == before
    ((mask_after,),) = _rows("SELECT i.`api_key` FROM `tenant_model_instance` i JOIN `tenant_model_provider` p ON p.`id` = i.`provider_id` WHERE p.`tenant_id` = %s", (account.tenant_id,))
    assert mask_after == mask_before
    assert info.instances[0].api_base == "https://two.example/v1"


def test_second_save_is_an_upsert_that_keeps_ids_and_usage(llm, account):
    save(llm, account, fake_key())
    ids_before = model_ids(account.tenant_id)
    store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", 41)
    info = save(llm, account, fake_key(), model_list=[chat(), chat("chat-b")], replace_key=True)
    ids_after = model_ids(account.tenant_id)
    assert ids_after["chat-a"] == ids_before["chat-a"] and ids_after["embed-a"] == ids_before["embed-a"]
    assert set(ids_after) == {"chat-a", "embed-a", "chat-b"}
    assert {m.model: m.used_tokens for m in info.models}["chat-a"] == 41
    assert counts(account.tenant_id) == {"provider": 1, "instance": 1, "model": 3, "llm": 3}


def test_model_owned_by_another_instance_conflicts_and_rolls_back(llm, account):
    save(llm, account, fake_key(), instance="a", model_list=[chat("shared")])
    before = counts(account.tenant_id)
    env_before = envelopes(account.tenant_id)
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), instance="b", model_list=[chat("fresh"), chat("shared")])
    assert err.value.kind is Kind.CONFLICT and err.value.reason == "model_exists"
    assert counts(account.tenant_id) == before
    assert envelopes(account.tenant_id) == env_before


def test_embedding_dimension_change_is_refused_and_changes_nothing(llm, account):
    save(llm, account, fake_key())
    before, env_before = counts(account.tenant_id), envelopes(account.tenant_id)
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), model_list=[chat("chat-new"), embed(dimension=768)])
    assert err.value.kind is Kind.INVALID and err.value.reason == "dimension_mismatch"
    assert counts(account.tenant_id) == before
    assert envelopes(account.tenant_id) == env_before
    assert svc.find_model(account.tenant_id, ModelRef("embed-a", "default", "OpenRouter")).dimension == 1024


def test_overlong_composite_is_refused_before_any_write(llm, account):
    # Azure-OpenAI is 12 characters: 120 + 1 + 12 = 133 > 128.
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), provider="Azure-OpenAI", api_base="https://x.example", api_version="v", model_list=[chat("m" * 120)])
    assert err.value.kind is Kind.INVALID and err.value.reason == "models_invalid"
    assert counts(account.tenant_id) == {"provider": 0, "instance": 0, "model": 0, "llm": 0}

    save(llm, account, fake_key(), model_list=[chat("ok")])
    before = counts(account.tenant_id)
    with pytest.raises(ServiceError) as err:
        svc.add_models(llm, account.tenant_id, "OpenRouter", "default", [chat("m" * 120)])
    assert err.value.reason == "models_invalid"
    assert counts(account.tenant_id) == before

    # "OpenRouter" is 10 characters: 117 + 1 + 10 = 128 exactly, so it is saved.
    info = save(llm, account, fake_key(), model_list=[chat("ok"), chat("n" * 117)])
    assert {len(m.composite) for m in info.models} == {len("ok@OpenRouter"), 128}
    # A non-default instance name adds its own length.
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), instance="prod", model_list=[chat("n" * 117)])
    assert err.value.reason == "models_invalid"


def test_invalid_model_requests_are_refused(llm, account):
    bad = [
        [svc.NewModel("m", "tts", None, 1)],
        [svc.NewModel("a@b", "chat", None, 1)],
        [svc.NewModel("", "chat", None, 1)],
        [svc.NewModel("e", "embedding", None, 1)],
        [svc.NewModel("e", "embedding", 0, 1)],
        [chat("dup"), chat("dup")],
        [svc.NewModel("m", "chat", None, 0)],
    ]
    for models in bad:
        with pytest.raises(ServiceError) as err:
            save(llm, account, fake_key(), model_list=models)
        assert err.value.reason == "models_invalid", models
    with pytest.raises(ServiceError) as err:
        save(llm, account, fake_key(), instance="pr|od")
    assert err.value.kind is Kind.INVALID
    assert counts(account.tenant_id)["provider"] == 0


def test_has_key_is_true_for_a_short_key_and_false_without_one(llm, account):
    short = "EM" + "PTY"
    save(llm, account, short, provider="OpenAI", model_list=[chat("gpt-x")])
    inst = svc.get_instance(account.tenant_id, "OpenAI", "default")
    assert inst.has_key is True and inst.last4 == ""

    save(llm, account, fake_key(), provider="OpenRouter")
    long_inst = svc.get_instance(account.tenant_id, "OpenRouter", "default")
    assert long_inst.has_key is True and len(long_inst.last4) == 4

    save(llm, account, None, provider="Ollama", api_base="http://ollama.example:11434", model_list=[chat("llama3")], replace_key=False)
    keyless = svc.get_instance(account.tenant_id, "Ollama", "default")
    assert keyless.has_key is False and keyless.last4 == ""
    assert svc.get_instance(account.tenant_id, "OpenAI", "nope") is None


def test_add_models_reuses_the_stored_envelope(llm, account):
    key = fake_key()
    save(llm, account, key, model_list=[chat()])
    stored = envelopes(account.tenant_id)["chat-a"]
    info = svc.add_models(llm, account.tenant_id, "OpenRouter", "default", [chat("chat-b"), embed("embed-b", 512)])
    after = envelopes(account.tenant_id)
    assert after["chat-b"] == after["embed-b"] == stored
    assert {m.model for m in info.models} == {"chat-a", "chat-b", "embed-b"}
    cred = store.get_credential(llm, account.tenant_id, ModelRef("embed-b", "default", "OpenRouter"), "embedding")
    assert cred.api_key == key
    with pytest.raises(ServiceError) as err:
        svc.add_models(llm, account.tenant_id, "OpenRouter", "default", [chat("chat-a")])
    assert err.value.kind is Kind.CONFLICT and err.value.reason == "model_exists"
    with pytest.raises(ServiceError) as err:
        svc.add_models(llm, account.tenant_id, "OpenRouter", "missing", [chat("zzz")])
    assert err.value.kind is Kind.NOT_FOUND


def test_reads_never_expose_a_key_and_find_model_is_tenant_scoped(llm, account):
    from test.testcases.conftest import BASE_URL

    key = fake_key()
    save(llm, account, key)
    providers = svc.list_providers(account.tenant_id)
    text = json.dumps([dataclasses.asdict(p) for p in providers])
    assert key not in text and "v1:" not in text
    names: set[str] = set()
    for p in providers:
        for obj in (p, *p.instances, *p.models):
            names |= {f.name for f in dataclasses.fields(obj)}
    assert not names & {"api_key", "envelope", "secret", "key"}

    ref = parse_model_ref("chat-a@OpenRouter")
    found = svc.find_model(account.tenant_id, ref)
    assert found is not None and found.model == "chat-a" and found.provider == "OpenRouter"
    assert svc.find_model(account.tenant_id, parse_model_ref("chat-a@OpenAI")) is None
    assert svc.find_model(account.tenant_id, parse_model_ref("chat-a@nope@OpenRouter")) is None
    assert svc.get_provider(account.tenant_id, "nope") is None
    assert svc.get_provider(account.tenant_id, "OpenRouter").provider == "OpenRouter"

    registry = AccountRegistry(BASE_URL)
    try:
        stranger = registry.register(prefix="llmother")
        assert svc.find_model(stranger.tenant_id, ref) is None
        assert svc.list_providers(stranger.tenant_id) == []
    finally:
        registry.cleanup()

    assert [m.model for m in svc.list_models(account.tenant_id, "embedding")] == ["embed-a"]
    assert [m.model for m in svc.list_models(account.tenant_id, "chat")] == ["chat-a"]
    assert {m.model for m in svc.list_models(account.tenant_id)} == {"chat-a", "embed-a"}


# ----------------------------------------------------------------------------- rotation and address


def test_rotation_reseals_every_row_of_the_instance(llm, account):
    old, new = fake_key(), fake_key()
    save(llm, account, old)
    store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", 7)
    ids_before = _rows("SELECT `id`, `llm_name`, `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s ORDER BY `llm_name`", (account.tenant_id,))
    counts_before = counts(account.tenant_id)

    # The Change key dialog lists only one model.
    svc.save_instance(llm, account.tenant_id, "OpenRouter", "default", api_key=new, api_base=None, api_version=None, models=[chat()], replace_key=True)

    rows = _rows("SELECT `llm_name`, `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s", (account.tenant_id,))
    assert {r[0] for r in rows} == {"chat-a", "embed-a"}
    for _name, envelope in rows:
        assert store.open_key(llm, account.tenant_id, "OpenRouter", "default", envelope) == new
    assert store.get_credential(llm, account.tenant_id, ModelRef("embed-a", "default", "OpenRouter"), "embedding").api_key == new
    assert store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "default", "OpenRouter"), "chat").api_key == new
    assert svc.get_instance(account.tenant_id, "OpenRouter", "default").last4 == new[-4:]
    ((mask, extra),) = _rows(
        "SELECT i.`api_key`, i.`extra` FROM `tenant_model_instance` i JOIN `tenant_model_provider` p ON p.`id` = i.`provider_id` WHERE p.`tenant_id` = %s", (account.tenant_id,)
    )
    assert mask.endswith(new[-4:]) and json.loads(extra)["last4"] == new[-4:]
    assert _rows("SELECT `id`, `llm_name`, `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s ORDER BY `llm_name`", (account.tenant_id,)) == ids_before
    assert counts(account.tenant_id) == counts_before

    blob = "\n".join(str(v) for t in ("tenant_llm",) for row in _rows(f"SELECT * FROM `{t}` WHERE `tenant_id` = %s", (account.tenant_id,)) for v in row)  # noqa: S608
    for secret in (old, new):
        assert all(secret[i : i + 8] not in blob for i in range(len(secret) - 7))


def test_failed_rotation_leaves_every_envelope_untouched(llm, account):
    old, new = fake_key(), fake_key()
    save(llm, account, old)
    before = envelopes(account.tenant_id)
    with pytest.raises(ServiceError) as err:
        save(llm, account, new, model_list=[chat(), embed(dimension=999)], replace_key=True)
    assert err.value.reason == "dimension_mismatch"
    assert envelopes(account.tenant_id) == before
    assert store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "default", "OpenRouter")).api_key == old
    assert svc.get_instance(account.tenant_id, "OpenRouter", "default").last4 == old[-4:]


def test_address_change_on_a_keyless_instance_writes_everywhere_and_no_envelope(llm, account):
    save(llm, account, None, provider="Ollama", api_base="http://one.example:11434", model_list=[chat("llama3"), embed("nomic", 768)], replace_key=False)
    info = save(llm, account, None, provider="Ollama", api_base="http://two.example:11434", model_list=[chat("llama3")], replace_key=False)
    assert info.instances[0].api_base == "http://two.example:11434"
    assert {m.model for m in info.models} == {"llama3", "nomic"}
    for base, key in _rows("SELECT `api_base`, `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s", (account.tenant_id,)):
        assert base == "http://two.example:11434" and not key
    ((extra,),) = _rows("SELECT i.`extra` FROM `tenant_model_instance` i JOIN `tenant_model_provider` p ON p.`id` = i.`provider_id` WHERE p.`tenant_id` = %s", (account.tenant_id,))
    assert json.loads(extra)["api_base"] == "http://two.example:11434"


def test_address_change_on_a_keyed_instance_keeps_the_envelopes(llm, account):
    key = fake_key()
    save(llm, account, key, api_base="https://one.example/v1")
    before = envelopes(account.tenant_id)
    save(llm, account, None, api_base="https://two.example/v1", replace_key=False)
    assert envelopes(account.tenant_id) == before
    assert {r[0] for r in _rows("SELECT `api_base` FROM `tenant_llm` WHERE `tenant_id` = %s", (account.tenant_id,))} == {"https://two.example/v1"}
    assert store.get_credential(llm, account.tenant_id, ModelRef("chat-a", "default", "OpenRouter")).api_key == key


# ----------------------------------------------------------------------------- defaults


def test_defaults_store_composite_ids_and_model_row_ids(llm, account):
    save(llm, account, fake_key(), instance="prod")
    svc.set_defaults(account.tenant_id, chat=None, embedding=None)
    assert svc.get_defaults(account.tenant_id) == svc.Defaults(chat="", embedding="")

    chat_ref, emb_ref = ModelRef("chat-a", "prod", "OpenRouter"), ModelRef("embed-a", "prod", "OpenRouter")
    result = svc.set_defaults(account.tenant_id, chat=chat_ref, embedding=emb_ref)
    assert result == svc.Defaults(chat="chat-a@prod@OpenRouter", embedding="embed-a@prod@OpenRouter")
    llm_id, tenant_llm_id, embd_id, tenant_embd_id = tenant_defaults(account.tenant_id)
    assert llm_id == "chat-a@prod@OpenRouter" and embd_id == "embed-a@prod@OpenRouter"
    assert tenant_llm_id == svc.find_model(account.tenant_id, chat_ref).id
    assert tenant_embd_id == svc.find_model(account.tenant_id, emb_ref).id
    assert svc.get_defaults(account.tenant_id) == result


def test_set_defaults_leaves_unset_values_alone_and_none_clears(llm, account):
    save(llm, account, fake_key())
    chat_ref, emb_ref = ModelRef("chat-a", "default", "OpenRouter"), ModelRef("embed-a", "default", "OpenRouter")
    svc.set_defaults(account.tenant_id, chat=chat_ref, embedding=emb_ref)
    assert svc.set_defaults(account.tenant_id, chat=None).embedding == "embed-a@OpenRouter"
    assert svc.get_defaults(account.tenant_id) == svc.Defaults(chat="", embedding="embed-a@OpenRouter")
    llm_id, tenant_llm_id, _, _ = tenant_defaults(account.tenant_id)
    assert llm_id == "" and not tenant_llm_id
    svc.set_defaults(account.tenant_id)
    assert svc.get_defaults(account.tenant_id).embedding == "embed-a@OpenRouter"


def test_set_defaults_refuses_missing_wrong_type_and_foreign_models(llm, account):
    from test.testcases.conftest import BASE_URL

    save(llm, account, fake_key())
    svc.set_defaults(account.tenant_id, chat=None, embedding=None)
    for kwargs in (
        {"chat": ModelRef("missing", "default", "OpenRouter")},
        {"chat": ModelRef("embed-a", "default", "OpenRouter")},
        {"embedding": ModelRef("chat-a", "default", "OpenRouter")},
        {"embedding": ModelRef("embed-a", "default", "OpenAI")},
    ):
        with pytest.raises(ServiceError) as err:
            svc.set_defaults(account.tenant_id, **kwargs)
        assert err.value.kind is Kind.INVALID and err.value.reason == "model_unavailable"
    assert svc.get_defaults(account.tenant_id) == svc.Defaults(chat="", embedding="")

    registry = AccountRegistry(BASE_URL)
    try:
        stranger = registry.register(prefix="llmother")
        with pytest.raises(ServiceError) as err:
            svc.set_defaults(stranger.tenant_id, chat=ModelRef("chat-a", "default", "OpenRouter"))
        assert err.value.reason == "model_unavailable"
    finally:
        registry.cleanup()


def test_delete_provider_removes_everything_and_clears_matching_defaults(llm, account):
    save(llm, account, fake_key(), provider="OpenRouter")
    save(llm, account, fake_key(), provider="OpenAI", model_list=[chat("gpt-x"), embed("emb-x", 256)])
    svc.set_defaults(account.tenant_id, chat=ModelRef("chat-a", "default", "OpenRouter"), embedding=ModelRef("emb-x", "default", "OpenAI"))

    assert svc.delete_provider(account.tenant_id, "OpenRouter") is True
    assert counts(account.tenant_id) == {"provider": 1, "instance": 1, "model": 2, "llm": 2}
    assert svc.get_defaults(account.tenant_id) == svc.Defaults(chat="", embedding="emb-x@OpenAI")
    llm_id, tenant_llm_id, _, tenant_embd_id = tenant_defaults(account.tenant_id)
    assert llm_id == "" and not tenant_llm_id and tenant_embd_id

    assert svc.delete_provider(account.tenant_id, "OpenRouter") is False
    assert svc.delete_provider(account.tenant_id, "Ollama") is False
    assert svc.delete_provider(account.tenant_id, "OpenAI") is True
    assert counts(account.tenant_id) == {"provider": 0, "instance": 0, "model": 0, "llm": 0}
    assert svc.get_defaults(account.tenant_id) == svc.Defaults(chat="", embedding="")


# ----------------------------------------------------------------------------- usage


def _used(tenant_id: str, name: str) -> int:
    return _rows("SELECT `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (tenant_id, name))[0][0]


def test_used_tokens_never_loses_a_concurrent_increment(llm, account):
    save(llm, account, fake_key())
    assert _used(account.tenant_id, "chat-a") == 0

    def work(_: int) -> None:
        for _i in range(25):
            store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", 3)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(8)))
    assert _used(account.tenant_id, "chat-a") == 600
    assert _used(account.tenant_id, "embed-a") == 0


def test_used_tokens_stops_at_the_32_bit_cap(llm, account):
    save(llm, account, fake_key())
    _execute("UPDATE `tenant_llm` SET `used_tokens` = %s WHERE `tenant_id` = %s AND `llm_name` = %s", (INT_CAP - 5, account.tenant_id, "chat-a"))
    store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", 100)
    assert _used(account.tenant_id, "chat-a") == INT_CAP
    store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", INT_CAP)
    assert _used(account.tenant_id, "chat-a") == INT_CAP


def test_non_positive_token_counts_are_ignored(llm, account):
    save(llm, account, fake_key())
    for n in (0, -5):
        store.add_used_tokens(account.tenant_id, "OpenRouter", "chat-a", n)
    assert _used(account.tenant_id, "chat-a") == 0
