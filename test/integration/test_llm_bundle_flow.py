"""LLMBundle against the real MySQL and the recording loopback provider (plan 03-11; LLM-14, LLM-15, LLM-21, LLM-03, LLM-16).

Rows are written through ``tenant_model_service.save_instance`` with a made-up key and the fake provider's address, so the key
is sealed exactly as in production. The fake is a stand-in for a third party over real HTTP, never a stub of our code. Retry
sleeps are injected (recorded, never waited). Rows are removed by account cleanup.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import secrets
from base64 import urlsafe_b64encode
from collections.abc import Iterator

import pytest

from api.db.services import llm_service
from api.db.services import tenant_model_service as structure
from api.db.services.llm_service import LLMBundle
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import NewModel
from api.utils import reasons
from common.settings import Settings, load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection
from test.helpers.fake_provider import CHAT_PIECES, CHAT_TEXT, COMPLETION_TOKENS, PROMPT_TOKENS, FakeProvider, running_fake_provider

pytestmark = pytest.mark.integration

COMPAT = "OpenAI-API-Compatible"
CHAT_ID = f"fake-chat@{COMPAT}"
EMBED_ID = f"fake-embed@{COMPAT}"
CHAT_TOTAL = PROMPT_TOKENS + COMPLETION_TOKENS
HISTORY = [{"role": "user", "content": "hello"}]
DIMENSION = 8

DEFAULT_MODELS = (
    NewModel("fake-chat", "chat", None, 8192),
    NewModel("fake-embed", "embedding", DIMENSION, 8192),
    NewModel("fake-401", "chat", None, 8192),
    NewModel("fake-500", "chat", None, 8192),
    NewModel("fake-no-usage", "chat", None, 8192),
    NewModel("fake-429-once", "chat", None, 8192),
)


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    from test.testcases.conftest import BASE_URL

    reg = AccountRegistry(BASE_URL)
    try:
        yield reg
    finally:
        reg.cleanup()


@pytest.fixture
def account(registry: AccountRegistry) -> Account:
    return registry.register(prefix="bundle")


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        provider.embedding_dim = DIMENSION
        yield provider


def make_settings(*, encryption: bool = True, key: bytes | None = None) -> Settings:
    base = load_settings()
    llm = dataclasses.replace(
        base.llm,
        encryption_key=(urlsafe_b64encode(key or os.urandom(32)).decode() if encryption else ""),
        key_id="k1",
        allow_private_base_urls=True,
        chat_timeout_seconds=10,
        embedding_timeout_seconds=10,
        max_retries=2,
    )
    # Name the services as a deployment would; otherwise the loopback fake would sit on the URL guard's deny list.
    return dataclasses.replace(
        base,
        llm=llm,
        mysql=dataclasses.replace(base.mysql, host="mysql"),
        redis=dataclasses.replace(base.redis, host="redis"),
        minio=dataclasses.replace(base.minio, host="minio"),
        es=dataclasses.replace(base.es, hosts="http://es01:9200"),
    )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


def fake_key() -> str:
    return "-".join(("sk", "fake", secrets.token_hex(12)))


def seed(settings: Settings, account: Account, fake: FakeProvider, key: str, models=DEFAULT_MODELS, instance: str = "default") -> None:
    structure.save_instance(
        settings.llm, account.tenant_id, COMPAT, instance, api_key=key, api_base=fake.base_url, api_version=None, models=list(models), replace_key=True
    )


class Sleeps:
    """The injected retry sleep: records the delays and returns at once."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def bundle(settings, account, model_id=CHAT_ID, model_type="chat", sleeps: Sleeps | None = None, **extra) -> LLMBundle:
    return LLMBundle(account.tenant_id, model_id, model_type, settings=settings, sleep=sleeps or Sleeps(), **extra)


def rows(sql: str, params: tuple = ()) -> list[tuple]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def used(account: Account, model: str = "fake-chat") -> int:
    return rows("SELECT `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (account.tenant_id, model))[0][0]


def envelope_of(account: Account, model: str = "fake-chat") -> str:
    return rows("SELECT `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (account.tenant_id, model))[0][0]


def chat_hits(fake: FakeProvider):
    return fake.hits("/v1/chat/completions")


def embed_hits(fake: FakeProvider):
    return fake.hits("/v1/embeddings")


# ----------------------------------------------------------------------------- chat


def test_chat_returns_the_providers_text_with_the_tenants_own_key_and_counts_tokens(settings, account, fake):
    key = fake_key()
    seed(settings, account, fake, key)
    assert used(account) == 0

    answer = bundle(settings, account).chat("be brief", HISTORY)

    assert answer == CHAT_TEXT
    assert [r.headers.get("authorization") for r in chat_hits(fake)] == [f"Bearer {key}"]
    assert used(account) == CHAT_TOTAL


def test_a_second_call_adds_to_the_counter_once_more(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account)
    llm.chat("s", HISTORY)
    llm.chat("s", HISTORY)
    assert used(account) == 2 * CHAT_TOTAL


def test_streaming_yields_the_deltas_in_order_and_counts_after_the_stream_ends(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account)

    stream = llm.chat_streamly("s", HISTORY)
    first = next(stream)
    assert first == CHAT_PIECES[0]
    assert used(account) == 0, "nothing is counted while the stream is still open"
    rest = list(stream)

    assert [first, *rest] == list(CHAT_PIECES)
    assert "" not in rest, "the empty-choices annotation chunk is never yielded"
    assert used(account) == CHAT_TOTAL
    assert chat_hits(fake)[0].body["stream_options"]["include_usage"] is True
    assert llm.last_usage is not None and llm.last_usage.total_tokens == CHAT_TOTAL


def test_a_consumer_that_stops_early_adds_no_tokens(settings, account, fake):
    seed(settings, account, fake, fake_key())
    stream = bundle(settings, account).chat_streamly("s", HISTORY)
    assert next(stream) == CHAT_PIECES[0]
    stream.close()
    assert used(account) == 0


def test_a_provider_that_reports_no_usage_is_counted_by_estimate(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account, "fake-no-usage@" + COMPAT)
    llm.chat("s", HISTORY)
    assert llm.last_usage is not None and llm.last_usage.estimated is True
    assert llm.last_usage.total_tokens > 0
    assert used(account, "fake-no-usage") == llm.last_usage.total_tokens


def test_last_usage_is_reset_at_the_start_of_each_call(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account)
    llm.chat("s", HISTORY)
    assert llm.last_usage is not None
    seen = []
    stream = llm.chat_streamly("s", HISTORY)
    next(stream)
    seen.append(llm.last_usage)
    list(stream)
    assert seen == [None]
    assert llm.last_usage is not None


# ----------------------------------------------------------------------------- embeddings


def test_encode_returns_vectors_of_the_providers_size_and_counts_tokens(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account, EMBED_ID, "embedding")

    vectors, tokens = llm.encode(["a", "b"])

    assert len(vectors) == 2 and all(len(v) == DIMENSION for v in vectors)
    assert tokens == 2
    assert used(account, "fake-embed") == 2
    assert len(embed_hits(fake)) == 1


def test_encode_queries_returns_one_vector(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account, EMBED_ID, "embedding", expected_dimension=DIMENSION)
    vector, tokens = llm.encode_queries("a question")
    assert len(vector) == DIMENSION and tokens == 2
    assert used(account, "fake-embed") == 2


def test_a_different_vector_size_raises_dimension_mismatch_and_adds_no_tokens(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account, EMBED_ID, "embedding", expected_dimension=DIMENSION + 4)
    with pytest.raises(ServiceError) as caught:
        llm.encode(["a", "b"])
    assert (caught.value.kind, caught.value.reason) == (Kind.INVALID, reasons.DIMENSION_MISMATCH)
    assert used(account, "fake-embed") == 0
    with pytest.raises(ServiceError) as again:
        llm.encode_queries("a")
    assert again.value.reason == reasons.DIMENSION_MISMATCH
    assert used(account, "fake-embed") == 0


def test_the_expected_dimension_passes_when_it_matches(settings, account, fake):
    seed(settings, account, fake, fake_key())
    vectors, _ = bundle(settings, account, EMBED_ID, "embedding", expected_dimension=DIMENSION).encode(["a"])
    assert len(vectors[0]) == DIMENSION


def test_encoding_nothing_makes_no_request_and_counts_nothing(settings, account, fake):
    seed(settings, account, fake, fake_key())
    assert bundle(settings, account, EMBED_ID, "embedding", expected_dimension=DIMENSION).encode([]) == ([], 0)
    assert embed_hits(fake) == [] and used(account, "fake-embed") == 0


# ----------------------------------------------------------------------------- resolution


def test_the_three_part_id_resolves_to_the_same_row(settings, account, fake):
    seed(settings, account, fake, fake_key())
    answer = bundle(settings, account, f"fake-chat@default@{COMPAT}").chat("s", HISTORY)
    assert answer == CHAT_TEXT
    assert used(account) == CHAT_TOTAL


def test_a_named_instance_uses_its_own_key(settings, account, fake):
    default_key, other_key = fake_key(), fake_key()
    seed(settings, account, fake, default_key, models=(NewModel("fake-chat", "chat", None, 8192),))
    seed(settings, account, fake, other_key, models=(NewModel("other-chat", "chat", None, 8192),), instance="team")
    bundle(settings, account, f"other-chat@team@{COMPAT}").chat("s", HISTORY)
    assert chat_hits(fake)[0].headers["authorization"] == f"Bearer {other_key}"
    with pytest.raises(ServiceError) as caught:
        bundle(settings, account, f"other-chat@default@{COMPAT}")
    assert caught.value.reason == reasons.MODEL_UNAVAILABLE, "a model is only reachable on its own instance"


def test_another_tenants_model_is_model_unavailable_and_makes_no_request(settings, registry, fake):
    owner, stranger = registry.two_accounts()
    seed(settings, owner, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        bundle(settings, stranger)
    assert (caught.value.kind, caught.value.reason) == (Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE)
    assert fake.requests == []


@pytest.mark.parametrize(
    ("model_id", "model_type"),
    [
        (EMBED_ID, "chat"),
        (CHAT_ID, "embedding"),
        ("fake-chat@NoSuchProvider", "chat"),
        (f"missing-model@{COMPAT}", "chat"),
        (f"fake-chat@nosuchinstance@{COMPAT}", "chat"),
    ],
)
def test_a_wrong_type_unknown_provider_model_or_instance_is_model_unavailable(settings, account, fake, model_id, model_type):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        bundle(settings, account, model_id, model_type)
    assert (caught.value.kind, caught.value.reason) == (Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE)
    assert fake.requests == []


def test_an_empty_encryption_key_is_key_store_unavailable_with_no_request(settings, account, fake):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        bundle(make_settings(encryption=False), account)
    assert (caught.value.kind, caught.value.reason) == (Kind.UNAVAILABLE, reasons.KEY_STORE_UNAVAILABLE)
    assert fake.requests == []


def test_a_different_encryption_key_is_key_unreadable_with_no_request(settings, account, fake):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        bundle(make_settings(), account)
    assert (caught.value.kind, caught.value.reason) == (Kind.UNAVAILABLE, reasons.KEY_UNREADABLE)
    assert fake.requests == []


def test_a_tampered_envelope_is_key_unreadable_and_the_message_holds_no_plaintext(settings, account, fake):
    key = fake_key()
    seed(settings, account, fake, key)
    stored = envelope_of(account)
    last = stored[-1]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    flipped = alphabet[(alphabet.index(last) + 32) % 64]  # differs in the high bits, so the decoded bytes change
    tampered = stored[:-1] + flipped
    assert tampered != stored
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute("UPDATE `tenant_llm` SET `api_key` = %s WHERE `tenant_id` = %s AND `llm_name` = %s", (tampered, account.tenant_id, "fake-chat"))
    finally:
        conn.close()

    with pytest.raises(ServiceError) as caught:
        bundle(settings, account)

    assert (caught.value.kind, caught.value.reason) == (Kind.UNAVAILABLE, reasons.KEY_UNREADABLE)
    text = f"{caught.value.message} {caught.value!r} {caught.value}"
    assert key not in text and stored not in text and tampered not in text
    assert fake.requests == []


# ----------------------------------------------------------------------------- failures and retries


def test_a_refused_key_is_provider_refused_after_one_request_and_adds_no_tokens(settings, account, fake):
    key = fake_key()
    seed(settings, account, fake, key)
    sleeps = Sleeps()
    with pytest.raises(ServiceError) as caught:
        bundle(settings, account, f"fake-401@{COMPAT}", sleeps=sleeps).chat("s", HISTORY)
    assert (caught.value.kind, caught.value.reason) == (Kind.INVALID, reasons.PROVIDER_REFUSED)
    assert len(chat_hits(fake)) == 1 and sleeps.delays == []
    assert used(account, "fake-401") == 0
    assert key not in f"{caught.value.message} {caught.value!r}"
    assert caught.value.__cause__ is None


def test_a_server_error_is_provider_unreachable_and_adds_no_tokens(settings, account, fake):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        bundle(settings, account, f"fake-500@{COMPAT}").chat("s", HISTORY)
    assert (caught.value.kind, caught.value.reason) == (Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE)
    assert used(account, "fake-500") == 0


def test_a_rate_limit_that_clears_succeeds_after_one_retry_and_counts_once(settings, account, fake):
    seed(settings, account, fake, fake_key())
    sleeps = Sleeps()
    answer = bundle(settings, account, f"fake-429-once@{COMPAT}", sleeps=sleeps).chat("s", HISTORY)
    assert answer == CHAT_TEXT
    assert len(chat_hits(fake)) == 2 and len(sleeps.delays) == 1
    assert used(account, "fake-429-once") == CHAT_TOTAL


def test_an_embedding_rate_limit_that_clears_succeeds_after_one_retry_and_counts_once(settings, account, fake):
    seed(settings, account, fake, fake_key(), models=(NewModel("fake-429-once", "embedding", DIMENSION, 8192),))
    llm = bundle(settings, account, f"fake-429-once@{COMPAT}", "embedding", expected_dimension=DIMENSION)
    vectors, tokens = llm.encode(["a", "b"])
    assert len(vectors) == 2 and tokens == 2
    assert len(embed_hits(fake)) == 2
    assert used(account, "fake-429-once") == 2


def test_a_failed_embedding_call_adds_no_tokens(settings, account, fake):
    seed(settings, account, fake, fake_key(), models=(NewModel("fake-401", "embedding", DIMENSION, 8192),))
    with pytest.raises(ServiceError) as caught:
        bundle(settings, account, f"fake-401@{COMPAT}", "embedding").encode(["a"])
    assert caught.value.reason == reasons.PROVIDER_REFUSED
    assert len(embed_hits(fake)) == 1
    assert used(account, "fake-401") == 0


# ----------------------------------------------------------------------------- secrets


def test_repr_and_logs_never_hold_the_key_or_the_envelope(settings, account, fake, caplog):
    key = fake_key()
    seed(settings, account, fake, key)
    stored = envelope_of(account)
    caplog.set_level(logging.DEBUG)
    llm = bundle(settings, account)
    llm.chat("s", HISTORY)
    list(llm.chat_streamly("s", HISTORY))
    with pytest.raises(ServiceError):
        bundle(settings, account, f"fake-401@{COMPAT}").chat("s", HISTORY)

    assert key not in repr(llm) and stored not in repr(llm) and key not in str(llm)
    assert "fake-chat" in repr(llm) and COMPAT in repr(llm)
    assert not any(attr.startswith("_") and key in repr(getattr(llm, attr)) for attr in vars(llm)), "the plaintext is not an attribute of the bundle"
    blob = caplog.text + " ".join(repr(vars(r)) for r in caplog.records)
    assert key not in blob and stored not in blob
    usage_lines = [r for r in caplog.records if r.name == llm_service.__name__ and r.getMessage() == "llm usage"]
    assert len(usage_lines) == 2
    line = usage_lines[0]
    assert (line.tenant, line.provider, line.model) == (account.tenant_id, COMPAT, "fake-chat")
    assert (line.usage_in, line.usage_out, line.usage_total) == (PROMPT_TOKENS, COMPLETION_TOKENS, CHAT_TOTAL)
    assert line.estimated is False


# ----------------------------------------------------------------------------- async variants


async def test_async_chat_matches_the_sync_result_and_counts_once(settings, account, fake):
    seed(settings, account, fake, fake_key())
    answer = await bundle(settings, account).async_chat("s", HISTORY)
    assert answer == CHAT_TEXT
    assert used(account) == CHAT_TOTAL


async def test_async_streaming_matches_the_sync_deltas_and_counts_after_the_end(settings, account, fake):
    seed(settings, account, fake, fake_key())
    llm = bundle(settings, account)
    pieces = []
    async for piece in llm.async_chat_streamly("s", HISTORY):
        pieces.append(piece)
        if len(pieces) == 1:
            assert used(account) == 0
    assert pieces == list(CHAT_PIECES)
    assert used(account) == CHAT_TOTAL


async def test_async_failure_is_a_service_error(settings, account, fake):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        await bundle(settings, account, f"fake-401@{COMPAT}").async_chat("s", HISTORY)
    assert caught.value.reason == reasons.PROVIDER_REFUSED
    assert used(account, "fake-401") == 0


async def test_async_stream_failure_to_open_is_a_service_error(settings, account, fake):
    seed(settings, account, fake, fake_key())
    with pytest.raises(ServiceError) as caught:
        async for _ in bundle(settings, account, f"fake-401@{COMPAT}").async_chat_streamly("s", HISTORY):
            pass
    assert caught.value.reason == reasons.PROVIDER_REFUSED
    assert used(account, "fake-401") == 0
