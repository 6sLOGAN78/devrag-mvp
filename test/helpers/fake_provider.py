"""Loopback stand-in for a third-party model provider (plan 03-05, D-03, D-15).

A real Quart app served by Hypercorn on an ephemeral 127.0.0.1 port, in its own thread and event loop. It is not a stub of any
devRag code: it is the *other end* of the wire, so driver tests exercise the real HTTP client. It records every request
(method, path, query, headers, parsed JSON body) and serves OpenAI, Azure and Ollama shaped chat and embedding endpoints plus
scripted failures chosen by the requested model name.

Use the ``fake_provider`` fixture (one fresh server per test) or the ``running_fake_provider`` context manager (module scope).
No fixed sleeps: readiness is polled with ``wait_until``; ``/slow`` waits on an ``asyncio.Event`` that teardown releases.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from hypercorn.asyncio import serve
from hypercorn.config import Config
from quart import Quart, Response, jsonify, request

from test.helpers.wait import wait_until

FAKE_KEY_PART = ("fake", "provider", "key", "0001")
FAKE_KEY = "-".join(FAKE_KEY_PART)
SECRET_ECHO_KEY = "-".join(("sk", "fakeechoedsecretvalue", "0123456789abcdef"))
CHAT_PIECES = ("Hel", "lo ", "from ", "the fake")
CHAT_TEXT = "".join(CHAT_PIECES)
PROMPT_TOKENS = 11
COMPLETION_TOKENS = 5


@dataclass
class Recorded:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: Any


@dataclass
class FakeProvider:
    port: int
    requests: list[Recorded] = field(default_factory=list)
    embedding_dim: int = 8
    shuffle_embeddings: bool = False
    _counters: dict[str, int] = field(default_factory=dict)
    _loop: asyncio.AbstractEventLoop | None = None
    _release: asyncio.Event | None = None

    @property
    def root(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def base_url(self) -> str:
        return f"{self.root}/v1"

    @property
    def azure_url(self) -> str:
        return self.root

    @property
    def ollama_url(self) -> str:
        return self.root

    @property
    def slow_url(self) -> str:
        return f"{self.root}/slow/v1"

    def reset(self) -> None:
        self.requests.clear()
        self._counters.clear()

    def hits(self, path: str) -> list[Recorded]:
        return [r for r in self.requests if r.path == path]

    def release_slow(self) -> None:
        if self._loop is not None and self._release is not None:
            self._loop.call_soon_threadsafe(self._release.set)

    def _bump(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]


def _error_body(message: str, code: str | None = None, kind: str = "invalid_request_error") -> dict[str, Any]:
    return {"error": {"message": message, "type": kind, "code": code, "param": None}}


def _scripted_failure(state: FakeProvider, model: str) -> Response | None:
    """The scripted failures, chosen by requested model name. ``None`` means serve a normal answer."""
    headers = {"Retry-After": "0"}
    if model == "fake-401":
        return _json(_error_body("Incorrect API key provided.", "invalid_api_key", "authentication_error"), 401)
    if model == "fake-402":
        return _json(_error_body("Insufficient credits.", "insufficient_quota", "billing_error"), 402)
    if model == "fake-404":
        return _json(_error_body("The model does not exist.", "model_not_found"), 404)
    if model == "fake-429":
        return _json(_error_body("Rate limit reached.", "rate_limit_exceeded", "rate_limit_error"), 429, headers)
    if model == "fake-429-once" and state._bump("429-once") == 1:
        return _json(_error_body("Rate limit reached.", "rate_limit_exceeded", "rate_limit_error"), 429, headers)
    if model == "fake-500":
        return _json(_error_body("The server had an error.", None, "server_error"), 500)
    if model == "fake-filter":
        return _json(_error_body("The response was filtered due to the prompt triggering content management policy.", "content_filter"), 400)
    if model == "fake-secret-echo":
        return _json(_error_body(f"Incorrect API key provided: {SECRET_ECHO_KEY}. You can find your key elsewhere.", "invalid_api_key"), 400)
    return None


def _json(body: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None) -> Response:
    response = jsonify(body)
    response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def _chat_completion(model: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": CHAT_TEXT}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS, "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS},
    }
    if model == "fake-no-usage":
        del body["usage"]
    return body


def _sse(model: str, wants_usage: bool) -> AsyncIterator[bytes]:
    def frame(payload: dict[str, Any]) -> bytes:
        return b"data: " + json.dumps(payload).encode() + b"\n\n"

    base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": 1, "model": model}

    async def generate() -> AsyncIterator[bytes]:
        yield frame({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
        for piece in CHAT_PIECES:
            yield frame({**base, "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
        yield frame({**base, "choices": []})  # annotation chunk with no choices
        yield frame({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        if wants_usage and model != "fake-no-usage":
            usage = {"prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS, "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS}
            yield frame({**base, "choices": [], "usage": usage})
        yield b"data: [DONE]\n\n"

    return generate()


def _embedding_response(state: FakeProvider, model: str, texts: list[str]) -> dict[str, Any]:
    rows = [{"object": "embedding", "index": i, "embedding": [round((i + 1) / 10 + j / 100, 4) for j in range(state.embedding_dim)]} for i, _ in enumerate(texts)]
    if state.shuffle_embeddings:
        rows.reverse()
    tokens = sum(len(t.split()) or 1 for t in texts)
    body: dict[str, Any] = {"object": "list", "data": rows, "model": model, "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}
    if model == "fake-no-usage":
        del body["usage"]
    return body


def _redirect() -> Response:
    response = Response(status=302)
    response.headers["Location"] = "/v1/redirect-target"
    return response


def _inputs(body: Any) -> list[str]:
    value = (body or {}).get("input", [])
    return [value] if isinstance(value, str) else list(value)


def build_app(state: FakeProvider) -> Quart:
    app = Quart("fake-provider")

    @app.before_request
    async def record() -> None:
        body = await request.get_json(force=True, silent=True)
        state.requests.append(Recorded(request.method, request.path, dict(request.args), {k.lower(): v for k, v in request.headers}, body))

    @app.get("/health")
    async def health() -> Response:
        return _json({"ok": True})

    async def openai_chat(model_hint: str | None = None) -> Response:
        body = await request.get_json(force=True, silent=True) or {}
        model = model_hint or str(body.get("model", ""))
        failure = _scripted_failure(state, model)
        if failure is not None:
            return failure
        if model == "fake-redirect":
            response = Response(status=302)
            response.headers["Location"] = "/v1/redirect-target"
            return response
        if body.get("stream"):
            usage = bool((body.get("stream_options") or {}).get("include_usage"))
            return Response(_sse(model, usage), mimetype="text/event-stream")
        return _json(_chat_completion(model))

    @app.post("/v1/chat/completions")
    async def chat() -> Response:
        return await openai_chat()

    @app.post("/slow/v1/chat/completions")
    async def slow_chat() -> Response:
        assert state._release is not None
        await state._release.wait()
        return await openai_chat()

    @app.get("/slow")
    async def slow() -> Response:
        assert state._release is not None
        await state._release.wait()
        return _json({"ok": True})

    @app.route("/v1/redirect-target", methods=["GET", "POST"])
    async def redirect_target() -> Response:
        return _json({"reached": True})

    @app.get("/redirect")
    async def redirect() -> Response:
        response = Response(status=302)
        response.headers["Location"] = "/v1/redirect-target"
        return response

    @app.post("/v1/embeddings")
    async def embeddings() -> Response:
        body = await request.get_json(force=True, silent=True) or {}
        model = str(body.get("model", ""))
        failure = _scripted_failure(state, model)
        if model == "fake-redirect":
            return _redirect()
        return failure if failure is not None else _json(_embedding_response(state, model, _inputs(body)))

    def azure_guard() -> Response | None:
        if "api-key" not in request.headers or "api-version" not in request.args:
            return _json(_error_body("Missing api-key header or api-version query.", "missing"), 401)
        return None

    @app.post("/openai/deployments/<deployment>/chat/completions")
    async def azure_chat(deployment: str) -> Response:
        return azure_guard() or await openai_chat(deployment)

    @app.post("/openai/deployments/<deployment>/embeddings")
    async def azure_embeddings(deployment: str) -> Response:
        denied = azure_guard()
        if denied is not None:
            return denied
        body = await request.get_json(force=True, silent=True) or {}
        failure = _scripted_failure(state, deployment)
        return failure if failure is not None else _json(_embedding_response(state, deployment, _inputs(body)))

    @app.post("/api/chat")
    async def ollama_chat() -> Response:
        body = await request.get_json(force=True, silent=True) or {}
        model = str(body.get("model", ""))
        failure = _scripted_failure(state, model)
        if failure is not None:
            return failure
        if model == "fake-redirect":
            response = Response(status=302)
            response.headers["Location"] = "/v1/redirect-target"
            return response
        counts = {"prompt_eval_count": PROMPT_TOKENS, "eval_count": COMPLETION_TOKENS}
        if body.get("stream", True):

            async def lines() -> AsyncIterator[bytes]:
                for piece in CHAT_PIECES:
                    yield json.dumps({"model": model, "message": {"role": "assistant", "content": piece}, "done": False}).encode() + b"\n"
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", **counts}).encode() + b"\n"

            return Response(lines(), mimetype="application/x-ndjson")
        return _json({"model": model, "created_at": "2026-01-01T00:00:00Z", "message": {"role": "assistant", "content": CHAT_TEXT}, "done": True, "done_reason": "stop", **counts})

    @app.post("/api/embed")
    async def ollama_embed() -> Response:
        body = await request.get_json(force=True, silent=True) or {}
        model = str(body.get("model", ""))
        failure = _scripted_failure(state, model)
        if failure is not None:
            return failure
        if model == "fake-redirect":
            return _redirect()
        texts = _inputs(body)
        vectors = [[round((i + 1) / 10 + j / 100, 4) for j in range(state.embedding_dim)] for i, _ in enumerate(texts)]
        counts = {} if model == "fake-no-usage" else {"prompt_eval_count": sum(len(t.split()) or 1 for t in texts)}
        return _json({"model": model, "embeddings": vectors, **counts})

    return app


def _serve_in_thread(state: FakeProvider, sock: socket.socket, ready: threading.Event, stop_box: list[Any]) -> None:
    async def main() -> None:
        loop = asyncio.get_running_loop()
        state._loop = loop
        state._release = asyncio.Event()
        stop = asyncio.Event()
        stop_box.extend([loop, stop])
        config = Config()
        config.bind = [f"fd://{sock.fileno()}"]
        config.accesslog = None
        config.errorlog = None
        config.graceful_timeout = 2.0
        ready.set()
        await serve(build_app(state), config, shutdown_trigger=stop.wait)

    asyncio.run(main())


@contextlib.contextmanager
def running_fake_provider() -> Iterator[FakeProvider]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    state = FakeProvider(port=sock.getsockname()[1])
    ready = threading.Event()
    stop_box: list[Any] = []
    thread = threading.Thread(target=_serve_in_thread, args=(state, sock, ready, stop_box), daemon=True, name="fake-provider")
    thread.start()
    try:
        assert ready.wait(10), "fake provider thread did not start"

        def up() -> bool:
            try:
                return httpx.get(f"{state.root}/health", timeout=2.0).status_code == 200
            except httpx.HTTPError:
                return False

        wait_until(up, timeout=15, interval=0.05)
        state.reset()
        yield state
    finally:
        state.release_slow()
        if stop_box:
            loop, stop = stop_box
            loop.call_soon_threadsafe(stop.set)
        thread.join(10)
        with contextlib.suppress(OSError):  # Hypercorn closes the inherited descriptor itself on shutdown
            sock.close()


@pytest.fixture
def fake_provider() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        yield provider
