from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from api.utils.validation import SafeIdentifier, SafeText
from test.helpers.app import make_test_app

pytestmark = pytest.mark.unit

PROBES = ["' OR 1=1 --", "; rm -rf /", "$(id)", "a" * 10_000, "", "../etc/passwd"]


@pytest.mark.parametrize("value", PROBES)
async def test_probe_strings_rejected_before_service(value):
    calls: list[str] = []
    resp = await make_test_app(service=calls.append).test_client().post("/test/named", json={"name": value})
    assert resp.status_code == 400
    assert await resp.get_json() == {"code": 101, "message": "invalid request", "data": None}
    assert calls == []


async def test_valid_name_reaches_service_once():
    calls: list[str] = []
    resp = await make_test_app(service=calls.append).test_client().post("/test/named", json={"name": "kb_01-a"})
    assert resp.status_code == 200
    assert calls == ["kb_01-a"]


async def test_missing_and_wrong_type_rejected():
    client = make_test_app().test_client()
    assert (await client.post("/test/named", json={})).status_code == 400
    assert (await client.post("/test/named", json={"name": 5})).status_code == 400


def test_safe_text_length_cap():
    class M(BaseModel):
        t: SafeText

    M(t="x" * 4096)
    with pytest.raises(ValidationError):
        M(t="x" * 4097)


def test_safe_identifier_type():
    class M(BaseModel):
        i: SafeIdentifier

    assert M(i="abc_1").i == "abc_1"
    with pytest.raises(ValidationError):
        M(i="a b")
