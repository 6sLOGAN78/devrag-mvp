"""The live_model tier: the platform proven against the user's real OpenRouter account (plan 03-27).

LLM-03, LLM-16, LLM-19, LLM-21, LLM-24, KB-02, KB-03, SEC-02, SEC-03, E2E-03; D-01 to D-06, D-23, D-25, D-29.

Everything here is real: the provider is saved through the product API (the app container makes the test calls to OpenRouter), a dataset
is created with the recorded dimension and its Elasticsearch field is read back, and chat, streamed chat and an embedding batch run
through ``LLMBundle`` with the key opened from the sealed row. The tier is tiny on purpose (D-05): at most 6 chat-class calls and 3
embedding calls for the whole file, on the cheapest suitable models, named in non-secret variables of ``docker/.env``.

The key is read only inside this process by ``stack_env()`` and travels only in the PUT body. No assertion message, f-string or print
below contains it: results are reduced to booleans and counts before they are asserted. Without the key the tier fails outright (D-04).
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from elasticsearch import Elasticsearch

from api.db.services.llm_service import LLMBundle
from common.settings import Settings, load_settings
from test.conftest import stack_env
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection
from test.testcases.conftest import BASE_URL, compose
from test.testcases.test_create_kb_e2e import raw_es, vector_mapping  # noqa: F401  (raw_es is a fixture)

pytestmark = pytest.mark.live_model

PROVIDERS = "/api/v1/providers"
DEFAULTS = "/api/v1/models/default"
DATASETS = "/api/v1/datasets"
USER_INFO = "/v1/user/info"
PROVIDER = "OpenRouter"
MISSING_KEY_MESSAGE = "OPENROUTER_API_KEY is missing from docker/.env; the Phase 3 gate fails without it (D-04)"
BAD_KEY = "-".join(("live", "tier", "bad", "key", "never", "valid", "0001"))
WINDOW = 12
CHAT_BUDGET, EMBEDDING_BUDGET = 6, 3
HISTORY = [{"role": "user", "content": "Reply with the single word: ready"}]
GEN_CONF = {"max_completion_tokens": 16, "temperature": 0}


@dataclass
class Budget:
    """Provider calls made by this file, counted where they are made; the last test asserts the ceiling (D-05)."""

    chat: int = 0
    embedding: int = 0


BUDGET = Budget()
EVIDENCE: list[str] = []  # non-secret facts (model names, sizes, counts) printed once at the end of the file


@dataclass(frozen=True)
class LiveEnv:
    key: str = field(repr=False)
    chat_model: str
    embed_model: str
    dimension: int
    llm_key: str = field(repr=False)
    key_id: str

    @property
    def chat_id(self) -> str:
        return f"{self.chat_model}@{PROVIDER}"

    @property
    def embed_id(self) -> str:
        return f"{self.embed_model}@{PROVIDER}"


class Recorder:
    """Keeps the text and headers of every response of this module's client, for the leak scan at the end."""

    def __init__(self) -> None:
        self.captured: list[str] = []

    def hook(self, response: httpx.Response) -> None:
        response.read()
        self.captured.append(response.text + "\n" + "\n".join(f"{name}: {value}" for name, value in response.headers.items()))


@pytest.fixture(scope="module")
def live_env() -> LiveEnv:
    env = stack_env()
    if not env.get("OPENROUTER_API_KEY", "").strip():
        pytest.fail(MISSING_KEY_MESSAGE)
    return LiveEnv(
        key=env["OPENROUTER_API_KEY"].strip(),
        chat_model=env.get("LIVE_CHAT_MODEL") or "meta-llama/llama-3.1-8b-instruct",
        embed_model=env.get("LIVE_EMBED_MODEL") or "baai/bge-m3",
        dimension=int(env.get("LIVE_EXPECTED_DIM") or 1024),
        llm_key=env.get("LLM_KEY_ENCRYPTION_KEY", ""),
        key_id=env.get("LLM_KEY_ID", "k1"),
    )


@pytest.fixture(scope="module")
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture(scope="module")
def started_at() -> str:
    return (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def client(ingress: httpx.Client, recorder: Recorder) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=90.0, follow_redirects=False, event_hooks={"response": [recorder.hook]}) as http:
        yield http


@pytest.fixture(scope="module")
def owner(ingress: httpx.Client, live_env: LiveEnv, started_at: str) -> Iterator[Account]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="livemodel")
    finally:
        registry.cleanup()


@pytest.fixture(scope="module", autouse=True)
def bound_database(live_env: LiveEnv) -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


def call(client: httpx.Client, method: str, path: str, token: str, body: Any = None) -> httpx.Response:
    client.cookies.clear()
    response = client.request(method, path, headers={"Authorization": f"Bearer {token}"}, json=body)
    assert response.headers.get("x-api-source") == "python", (method, path, response.status_code)
    return response


def data_of(response: httpx.Response) -> Any:
    assert response.status_code == 200, response.status_code
    body = response.json()
    assert body["code"] == 0, body.get("message")
    return body["data"]


def sql(query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(query, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def used_tokens(tenant_id: str, model: str) -> int:
    rows = sql("SELECT `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (tenant_id, model))
    assert len(rows) == 1
    return int(rows[0][0])


def leaks(text: str, key: str) -> int:
    """How many times the key, or any 12-character window of it, occurs in the text. A count, so a failure prints no secret."""
    windows = {key[i : i + WINDOW] for i in range(len(key) - WINDOW + 1)}
    return int(key in text) + sum(1 for window in windows if window in text)


def bundle_settings(live: LiveEnv) -> Settings:
    base = load_settings()
    llm = dataclasses.replace(base.llm, encryption_key=live.llm_key, key_id=live.key_id, chat_timeout_seconds=60, embedding_timeout_seconds=60, max_retries=1)
    return dataclasses.replace(base, llm=llm)


@pytest.fixture(scope="module")
def saved(client: httpx.Client, owner: Account, live_env: LiveEnv) -> dict[str, Any]:
    """The provider saved through the product API: the app container tests one chat and one embedding model for real first."""
    models = [{"name": live_env.chat_model, "type": "chat"}, {"name": live_env.embed_model, "type": "embedding"}]
    BUDGET.chat += 1
    BUDGET.embedding += 1
    body = {"provider": PROVIDER, "api_key": live_env.key, "models": models}
    return data_of(call(client, "PUT", PROVIDERS, owner.token, body))


# --- the product API against the real provider ------------------------------------------------------------------------


def test_provider_saves_after_real_test_calls(saved: dict[str, Any], live_env: LiveEnv) -> None:
    assert saved["name"] == PROVIDER and saved["configured"] is True
    (instance,) = saved["instances"]
    last4_matches = instance["last4"] == live_env.key[-4:]
    assert last4_matches, "the masked tail does not match the saved key"
    dimensions = {m["name"]: m["dimension"] for m in saved["models"]}
    assert dimensions[live_env.embed_model] == live_env.dimension, "the recorded dimension is the one the live response had"
    assert dimensions[live_env.chat_model] is None
    assert {m["name"]: m["type"] for m in saved["models"]} == {live_env.chat_model: "chat", live_env.embed_model: "embedding"}
    assert leaks(str(saved), live_env.key) == 0


def test_defaults_and_dataset_index_use_the_live_dimension(client: httpx.Client, owner: Account, live_env: LiveEnv, saved: dict[str, Any], raw_es: Elasticsearch) -> None:  # noqa: F811
    defaults = data_of(call(client, "PATCH", DEFAULTS, owner.token, {"chat": live_env.chat_id, "embedding": live_env.embed_id}))
    assert defaults["embedding"] == live_env.embed_id and defaults["chat"] == live_env.chat_id

    dataset = data_of(call(client, "POST", DATASETS, owner.token, {"name": "Live model knowledge base"}))
    assert dataset["embd_id"] == live_env.embed_id
    assert dataset["embedding_dimension"] == live_env.dimension
    detail = data_of(call(client, "GET", f"{DATASETS}/{dataset['id']}", owner.token))
    assert detail["embedding_dimension"] == live_env.dimension

    index = f"ragflow_{owner.tenant_id}"
    mapping = vector_mapping(raw_es, index, f"q_{live_env.dimension}_vec")
    assert mapping is not None, "the vector field of the live dimension exists in the tenant's index"
    assert mapping["type"] == "dense_vector" and mapping["dims"] == live_env.dimension
    assert mapping["similarity"] == "cosine"
    options = mapping["index_options"]
    assert options["type"] == "hnsw" and options["m"] == 16 and options["ef_construction"] == 200


# --- LLMBundle with the key opened from the sealed row ------------------------------------------------------------------


def test_real_chat_and_stream_record_usage(owner: Account, live_env: LiveEnv, saved: dict[str, Any], gc_at_loop_teardown: None) -> None:
    settings = bundle_settings(live_env)
    llm = LLMBundle(owner.tenant_id, live_env.chat_id, "chat", settings=settings)
    assert used_tokens(owner.tenant_id, live_env.chat_model) == 0, "the test calls made at save are not counted as usage"

    BUDGET.chat += 1
    answer = llm.chat("You answer in one word.", HISTORY, GEN_CONF)
    after_chat = used_tokens(owner.tenant_id, live_env.chat_model)
    assert isinstance(answer, str) and answer.strip() != ""
    assert after_chat > 0, "the counter rises after a non-streamed call"
    EVIDENCE.append(f"chat model={live_env.chat_model} used_tokens_after_chat={after_chat}")
    assert llm.last_usage is not None and llm.last_usage.total_tokens == after_chat

    BUDGET.chat += 1
    pieces = list(llm.chat_streamly("You answer in one word.", HISTORY, GEN_CONF))
    after_stream = used_tokens(owner.tenant_id, live_env.chat_model)
    assert pieces and "" not in pieces, "deltas arrive in order, with no empty fragment"
    assert "".join(pieces).strip() != ""
    assert after_stream > after_chat, "the counter rises again after the stream ends"
    assert llm.last_usage is not None and llm.last_usage.total_tokens == after_stream - after_chat
    EVIDENCE.append(f"stream pieces={len(pieces)} used_tokens_after_stream={after_stream} estimated={llm.last_usage.estimated}")


def test_real_embedding_batch_matches_the_recorded_dimension(client: httpx.Client, owner: Account, live_env: LiveEnv, saved: dict[str, Any], gc_at_loop_teardown: None) -> None:
    settings = bundle_settings(live_env)
    page = data_of(call(client, "GET", DATASETS, owner.token))
    assert page["total"] == 1, "the dataset made by the previous test is the only one"
    recorded = int(page["items"][0]["embedding_dimension"])
    llm = LLMBundle(owner.tenant_id, live_env.embed_id, "embedding", settings=settings, expected_dimension=recorded)
    before = used_tokens(owner.tenant_id, live_env.embed_model)

    BUDGET.embedding += 1
    vectors, tokens = llm.encode(["alpha", "beta"])

    assert len(vectors) == 2
    assert {len(v) for v in vectors} == {live_env.dimension}, "the live response has the expected dimension"
    assert recorded == live_env.dimension, "and it equals the dataset's recorded dimension"
    assert tokens > 0
    after = used_tokens(owner.tenant_id, live_env.embed_model)
    assert after > before
    EVIDENCE.append(f"embedding model={live_env.embed_model} dimension_observed={len(vectors[0])} dimension_recorded={recorded} used_tokens={after}")


def test_bad_key_is_refused_without_ending_the_session(client: httpx.Client, owner: Account, live_env: LiveEnv, saved: dict[str, Any]) -> None:
    def counts() -> tuple[int, int]:
        providers = sql("SELECT COUNT(*) FROM `tenant_model_provider` WHERE `tenant_id` = %s", (owner.tenant_id,))[0][0]
        models = sql("SELECT COUNT(*) FROM `tenant_llm` WHERE `tenant_id` = %s", (owner.tenant_id,))[0][0]
        return int(providers), int(models)

    before = counts()
    BUDGET.chat += 1
    body = {"provider": PROVIDER, "instance_name": "badkey", "api_key": BAD_KEY, "models": [{"name": live_env.chat_model, "type": "chat"}]}
    response = call(client, "PUT", PROVIDERS, owner.token, body)

    assert response.status_code == 400, "a provider 401 reaches the SPA as 400, never 401"
    payload = response.json()
    assert payload["data"]["reason"] == "provider_refused"
    EVIDENCE.append(f"bad key: http={response.status_code} reason={payload['data']['reason']} message={payload['message']!r}")
    assert BAD_KEY not in response.text
    assert counts() == before, "nothing was stored"
    session = client.get(USER_INFO, headers={"Authorization": f"Bearer {owner.token}"})
    assert session.status_code == 200, "the session is still valid"


# --- the budget and the leak scan ---------------------------------------------------------------------------------------


def test_no_response_or_log_contains_the_live_key(live_env: LiveEnv, recorder: Recorder, started_at: str, saved: dict[str, Any]) -> None:
    assert BUDGET.chat <= CHAT_BUDGET, "chat-class call budget (D-05)"
    assert BUDGET.embedding <= EMBEDDING_BUDGET, "embedding call budget (D-05)"
    assert recorder.captured, "responses were recorded"
    response_hits = sum(leaks(text, live_env.key) for text in recorder.captured)
    assert response_hits == 0, "the key or a window of it appears in a response"

    logs = compose("logs", "--no-color", "--since", started_at, "app")
    assert logs.returncode == 0
    assert logs.stdout.strip() != "", "the scan read the app logs"
    log_hits = leaks(logs.stdout + logs.stderr, live_env.key)
    assert log_hits == 0, "the key or a window of it appears in the app container logs"
    EVIDENCE.append(f"calls: chat_class={BUDGET.chat}/{CHAT_BUDGET} embedding={BUDGET.embedding}/{EMBEDDING_BUDGET}; response_hits={response_hits} log_hits={log_hits}")
    for line in EVIDENCE:
        print("LIVE-EVIDENCE", line)
