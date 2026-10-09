"""Per-request limits of the upload route, in-process (plan 03-16; D-11, Pitfall 5, Pitfall 8, T-03-16-04, T-03-16-08).

The real application factory and the real ``read_upload_files`` run behind a probe route that stands in for the handler's body half
(authorising the dataset needs MySQL and is covered by the integration and e2e tiers). No database is contacted.
"""
from __future__ import annotations

import dataclasses

import pytest
from quart import Blueprint, Quart, current_app, request

from api.apps import create_app
from api.apps.restful_apis.document_api import apply_upload_limits, close_upload_streams, read_upload_files
from api.apps.service_errors import service_error_response
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from common.settings import UploadSettings
from test.helpers.app import StubPrincipalResolver, make_client, memory_settings

pytestmark = pytest.mark.unit

BOUNDARY = "devragtestboundary"
MULTIPART = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}
MIB = 1024 * 1024
FILE_CAP = 4096
BODY_TIMEOUT = 7
PDF = b"%PDF-1.4\n" + b"x" * 64


def part(name: str, filename: str | None, content: bytes, content_type: str | None = "application/pdf") -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"' + (f'; filename="{filename}"' if filename is not None else "")
    head = disposition + (f"\r\nContent-Type: {content_type}" if filename is not None and content_type else "")
    return f"--{BOUNDARY}\r\n{head}\r\n\r\n".encode() + content + b"\r\n"


def closing() -> bytes:
    return f"--{BOUNDARY}--\r\n".encode()


def build_app(**upload: int) -> Quart:
    limits = dataclasses.replace(UploadSettings(), max_file_bytes=FILE_CAP, body_timeout_seconds=BODY_TIMEOUT)
    limits = dataclasses.replace(limits, **upload)
    probe = Blueprint("upload_probe", __name__)

    @probe.post("/test/upload-probe")
    async def upload_probe():
        try:
            items = await read_upload_files(current_app.extensions["ragflow_settings"].upload)
        except ServiceError as exc:
            return service_error_response(exc)
        first = items[0].stream.read() if items else b""
        close_upload_streams()
        return json_result(
            {
                "names": [i.name for i in items],
                "mimes": [i.mime for i in items],
                "first": first.decode("latin1"),
                "max_content_length": request.max_content_length,
                "body_timeout": request.body_timeout,
            }
        )

    @probe.post("/test/other-probe")
    async def other_probe():
        return json_result({"max_content_length": request.max_content_length, "body_timeout": request.body_timeout})

    resolver = StubPrincipalResolver()
    app = create_app(memory_settings(upload=limits), extra_blueprints=(probe,), principal_resolver=resolver)
    app.extensions["stub_resolver"] = resolver
    return app


@pytest.fixture
def client():
    return make_client(build_app())


async def post(client, raw: bytes, headers: dict[str, str] | None = None, path: str = "/test/upload-probe"):
    return await client.post(path, data=raw, headers=headers or MULTIPART)


def test_apply_upload_limits_sets_the_request_cap_and_the_body_timeout():
    class FakeRequest:
        max_content_length = None
        body_timeout = 60

    req = FakeRequest()
    apply_upload_limits(req, UploadSettings(max_file_bytes=10 * MIB, body_timeout_seconds=123))
    assert req.max_content_length == 10 * MIB + MIB
    assert req.body_timeout == 123


async def test_the_upload_route_gets_its_own_limits_and_other_routes_keep_the_default(client):
    answer = await post(client, part("file", "a.pdf", PDF) + closing())
    data = (await answer.get_json())["data"]
    assert answer.status_code == 200, data
    assert data["max_content_length"] == FILE_CAP + MIB and data["body_timeout"] == BODY_TIMEOUT
    assert data["names"] == ["a.pdf"] and data["mimes"] == ["application/pdf"] and data["first"].startswith("%PDF-1.4")

    other = await post(client, b"", {"Content-Type": "application/json"}, path="/test/other-probe")
    seen = (await other.get_json())["data"]
    assert seen["body_timeout"] == 60, "Quart's default stays everywhere else (Pitfall 8)"
    assert seen["max_content_length"] == 1024 * MIB, "the application-wide ceiling is untouched"


async def test_only_the_file_field_counts_and_every_file_of_it_is_returned(client):
    raw = part("note", None, b"hello") + part("file", "one.pdf", PDF) + part("other", "ignored.pdf", PDF) + part("file", "two.pdf", PDF) + closing()
    data = (await (await post(client, raw)).get_json())["data"]
    assert data["names"] == ["one.pdf", "two.pdf"]


async def test_a_missing_file_name_arrives_as_an_empty_name_for_the_service_to_refuse(client):
    raw = part("file", "", PDF) + closing()
    data = (await (await post(client, raw)).get_json())["data"]
    assert data["names"] == [""]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(closing(), id="no-parts"),
        pytest.param(part("note", None, b"just a field") + closing(), id="fields-only"),
        pytest.param(part("file", "a.pdf", PDF)[:40], id="truncated-inside-the-headers"),
        pytest.param(part("file", "a.pdf", PDF)[:-30], id="truncated-inside-the-body"),
        pytest.param(b"not multipart at all", id="garbage"),
    ],
)
async def test_a_malformed_multipart_is_400_no_files_never_a_silent_success(client, raw):
    answer = await post(client, raw)
    body = await answer.get_json()
    assert answer.status_code == 400, body
    assert body["data"]["reason"] == "no_files"


async def test_a_multipart_without_a_boundary_and_a_json_body_are_400_no_files(client):
    for headers in ({"Content-Type": "multipart/form-data"}, {"Content-Type": "application/json"}):
        answer = await post(client, part("file", "a.pdf", PDF) + closing(), headers)
        assert answer.status_code == 400, headers
        assert (await answer.get_json())["data"]["reason"] == "no_files"


async def test_a_body_over_the_cap_is_413_file_too_large_even_without_a_content_length(client):
    big = b"%PDF-1.4\n" + b"y" * (FILE_CAP + MIB)
    answer = await post(client, part("file", "big.pdf", big) + closing())
    body = await answer.get_json()
    assert answer.status_code == 413, body
    assert body["data"]["reason"] == "file_too_large"


async def test_a_declared_length_over_the_cap_is_refused_before_the_body_is_read(client):
    headers = {**MULTIPART, "Content-Length": str(FILE_CAP + MIB + 1)}
    answer = await post(client, part("file", "a.pdf", PDF) + closing(), headers)
    body = await answer.get_json()
    assert answer.status_code == 413, body
    assert body["data"]["reason"] == "file_too_large"


async def test_a_body_exactly_at_the_cap_is_still_read(client):
    pad = FILE_CAP + MIB - len(part("file", "a.pdf", b"") + closing()) - len(b"%PDF-1.4\n")
    raw = part("file", "a.pdf", b"%PDF-1.4\n" + b"z" * pad) + closing()
    assert len(raw) == FILE_CAP + MIB
    answer = await post(client, raw)
    assert answer.status_code == 200, await answer.get_json()


async def test_the_cap_follows_the_configured_file_size():
    small = make_client(build_app(max_file_bytes=1))
    over = b"%PDF-1.4\n" + b"q" * MIB
    answer = await post(small, part("file", "a.pdf", over) + closing())
    assert answer.status_code == 413
    assert (await answer.get_json())["data"]["reason"] == "file_too_large"
