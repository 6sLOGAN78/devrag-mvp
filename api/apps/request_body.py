"""A request body that can refuse to grow past a per-request cap (plan 03-16; D-11, T-03-16-04).

Quart checks a declared ``Content-Length`` against the application-wide ``MAX_CONTENT_LENGTH`` (1 GiB here, because Nginx sets the real
per-route limits) and checks the streamed size only when a handler awaits the whole body. The upload route reads its body through the multipart
parser, which never awaits it as a whole, so a per-request ``request.max_content_length`` would only reach the parser's memory guard. This body
counts the bytes the server hands over and, once the route's cap (see ``cap``) is crossed, records ``RequestEntityTooLarge`` for the reader to raise
and keeps nothing more, so a client that ignores a 413 cannot fill memory.

Only ``put`` is overridden; the rest is Quart's own ``Body``. Routes that never call ``cap`` behave exactly as before.

``CappedRequest`` also remembers every temporary file the multipart parser opens (a file over 500 KB spools to disk), including the one of a part
that never completed because the body was cut short, so ``close_streams`` can close them all deterministically instead of leaving it to the garbage collector.
"""
from __future__ import annotations

from typing import IO

from quart.formparser import FormDataParser
from quart.wrappers.request import Body, Request
from werkzeug.exceptions import RequestEntityTooLarge


class CappedBody(Body):
    def __init__(self, expected_content_length: int | None, max_content_length: int | None) -> None:
        super().__init__(expected_content_length, max_content_length)
        self._cap: int | None = None
        self._received = 0

    def cap(self, limit: int | None) -> None:
        """Refuse bodies over ``limit`` bytes from now on, counting what already arrived."""
        self._cap = limit
        if limit is not None and self._received > limit and self._must_raise is None:
            self._must_raise = RequestEntityTooLarge()

    async def put(self, data: bytes) -> None:
        self._received += len(data)
        if self._cap is not None and self._received > self._cap:
            if self._must_raise is not None:
                return  # the reader already knows: keep nothing more
            # The chunk that crossed the cap is still queued so a reader blocked on the queue wakes up and finds the error.
            self._must_raise = RequestEntityTooLarge()
        await super().put(data)


class CappedRequest(Request):
    body_class = CappedBody

    def make_form_data_parser(self) -> FormDataParser:
        parser = super().make_form_data_parser()
        make_stream = parser.stream_factory
        opened: list[IO[bytes]] = self.__dict__.setdefault("_opened_streams", [])

        def tracked(*args: int | str | None) -> IO[bytes]:
            stream = make_stream(*args)  # type: ignore[arg-type]
            opened.append(stream)
            return stream

        parser.stream_factory = tracked  # type: ignore[assignment]
        return parser

    def close_streams(self) -> None:
        """Close every temporary file the parser opened for this request. Safe to call twice."""
        for stream in self.__dict__.get("_opened_streams", []):
            stream.close()
