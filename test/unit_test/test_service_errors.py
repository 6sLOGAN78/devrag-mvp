"""Mapping of typed service errors to HTTP answers (plan 03-12, D-19, D-20, Pitfall 7)."""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from api.apps.service_errors import not_found_response, service_error_response
from api.db.services.service_errors import Kind, ServiceError

pytestmark = pytest.mark.unit

NOT_FOUND_BODY = {"code": 404, "message": "not found", "data": None}
EXPECTED_STATUS = {
    Kind.NOT_FOUND: 404,
    Kind.FORBIDDEN: 403,
    Kind.CONFLICT: 409,
    Kind.INVALID: 400,
    Kind.RATE_LIMITED: 429,
    Kind.UNAVAILABLE: 503,
    Kind.TIMEOUT: 504,
    Kind.BAD_GATEWAY: 502,
    Kind.PAYLOAD_TOO_LARGE: 413,
}


async def _answer(exc: ServiceError) -> tuple[int, dict[str, Any], Any]:
    response = service_error_response(exc)
    return response.status_code, json.loads(await response.get_data(as_text=True)), response.headers


def test_every_kind_has_an_expected_status() -> None:
    assert set(EXPECTED_STATUS) == set(Kind), "a new Kind needs a row in this table and in service_error_response"


@pytest.mark.parametrize("kind", list(Kind), ids=lambda k: k.value)
async def test_each_kind_maps_to_its_http_status_and_never_to_401(kind: Kind) -> None:
    status, body, _headers = await _answer(ServiceError(kind, "some_reason", "a short message"))
    assert status == EXPECTED_STATUS[kind]
    assert body["code"] != 401 and status != 401
    assert set(body) == {"code", "message", "data"}


@pytest.mark.parametrize("reason", ["provider_not_configured", "dataset_not_found", "anything_at_all"])
async def test_not_found_is_one_body_whatever_the_reason(reason: str) -> None:
    exc = ServiceError(Kind.NOT_FOUND, reason, "that specific thing is missing", data={"extra": "detail"})
    status, body, _ = await _answer(exc)
    assert status == 404 and body == NOT_FOUND_BODY
    plain = not_found_response()
    assert plain.status_code == 404 and json.loads(await plain.get_data(as_text=True)) == NOT_FOUND_BODY


async def test_forbidden_is_the_standard_forbidden_envelope() -> None:
    status, body, _ = await _answer(ServiceError(Kind.FORBIDDEN, "no_role", "you may not"))
    assert (status, body["code"], body["message"]) == (403, 403, "forbidden")


@pytest.mark.parametrize("kind", [Kind.CONFLICT, Kind.INVALID, Kind.TIMEOUT, Kind.BAD_GATEWAY, Kind.UNAVAILABLE, Kind.RATE_LIMITED, Kind.PAYLOAD_TOO_LARGE])
async def test_other_kinds_carry_the_reason_and_the_service_message(kind: Kind) -> None:
    status, body, _ = await _answer(ServiceError(kind, "the_reason", "the user safe message", data={"limit": 3}))
    assert body["data"] == {"reason": "the_reason", "limit": 3}
    assert body["message"] == "the user safe message"
    assert status == EXPECTED_STATUS[kind]


async def test_invalid_is_argument_error_101() -> None:
    _, body, _ = await _answer(ServiceError(Kind.INVALID, "provider_refused", "the provider said no"))
    assert body["code"] == 101 and body["data"] == {"reason": "provider_refused"}


@pytest.mark.parametrize(("retry_after", "header"), [(2.3, "3"), (2.0, "2"), (0.0, "1"), (0.2, "1"), (120.0, "120")])
async def test_retry_after_is_integer_seconds_of_at_least_one_and_zero_is_not_falsy(retry_after: float, header: str) -> None:
    for kind in (Kind.RATE_LIMITED, Kind.UNAVAILABLE):
        status, _, headers = await _answer(ServiceError(kind, "r", "m", retry_after=retry_after))
        assert status == EXPECTED_STATUS[kind]
        assert headers["Retry-After"] == header
    assert header == str(max(1, math.ceil(retry_after)))


@pytest.mark.parametrize("kind", [Kind.RATE_LIMITED, Kind.UNAVAILABLE, Kind.CONFLICT, Kind.INVALID])
async def test_no_retry_after_header_without_a_value(kind: Kind) -> None:
    _, _, headers = await _answer(ServiceError(kind, "r", "m"))
    assert "Retry-After" not in headers


async def test_not_found_never_sets_retry_after_even_when_the_error_has_one() -> None:
    _, _, headers = await _answer(ServiceError(Kind.NOT_FOUND, "r", "m", retry_after=5.0))
    assert "Retry-After" not in headers


@pytest.mark.parametrize("kind", list(Kind), ids=lambda k: k.value)
async def test_no_body_holds_the_exception_class_name_or_the_repr(kind: Kind) -> None:
    exc = ServiceError(kind, "the_reason", "a short message")
    response = service_error_response(exc)
    text = await response.get_data(as_text=True)
    for forbidden in ("ServiceError", "Kind.", repr(exc), "Traceback"):
        assert forbidden not in text
