from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.security import tokens

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DATA = json.loads((FIXTURES / "access_token_vectors.json").read_text(encoding="utf-8"))
VECTORS = DATA["vectors"]


def test_fixture_has_enough_vectors():
    assert len(VECTORS) >= 18
    assert len({v["id"] for v in VECTORS}) == len(VECTORS)


@pytest.mark.parametrize("vec", VECTORS, ids=[v["id"] for v in VECTORS])
def test_shared_vector(vec):
    got = tokens.verify(vec["token"], DATA["secret"], DATA["max_age"], now=vec["now"])
    if vec["expect"] == "ok":
        assert got == vec["inner"]
        assert tokens.valid_inner(got) is vec["inner_valid"]
    else:
        assert got is None


def test_boundary_vectors_present():
    ids = {v["id"] for v in VECTORS}
    assert {"valid_at_max_age", "expired_by_one_second", "future_timestamp"} <= ids


def test_dump_roundtrip_with_injected_clock():
    token = tokens.dump(DATA["inner"], DATA["secret"], now=DATA["signed_at"])
    assert tokens.verify(token, DATA["secret"], now=DATA["signed_at"] + 5) == DATA["inner"]
    assert tokens.verify(token, "another-fake-secret-0123456789abcdef0123", now=DATA["signed_at"] + 5) is None


def test_overlong_rejected_before_hmac(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("serializer must not be reached")

    monkeypatch.setattr(tokens, "_serializer", boom)
    assert tokens.verify("a" * 1025, DATA["secret"]) is None


@pytest.mark.parametrize("value,ok", [("0" * 32, True), ("f" * 40, True), ("0" * 31, False), ("   ", False), ("", False), ("INVALID_" + "a" * 30, False), (None, False), (123, False)])
def test_valid_inner(value, ok):
    assert tokens.valid_inner(value) is ok


def test_go_issued_token_verifies_in_python():
    go = json.loads((FIXTURES / "go_issued_token.json").read_text(encoding="utf-8"))
    for field in ("token", "secret", "inner", "issued_at", "max_age"):
        assert field in go
    assert go["max_age"] == 2592000
    assert tokens.verify(go["token"], go["secret"], go["max_age"], now=go["issued_at"] + 10) == go["inner"]
    assert tokens.verify(go["token"], go["secret"], go["max_age"], now=go["issued_at"] + go["max_age"]) == go["inner"]


def test_go_issued_token_rejected_with_other_secret_or_late():
    go = json.loads((FIXTURES / "go_issued_token.json").read_text(encoding="utf-8"))
    assert tokens.verify(go["token"], go["secret"] + "x", go["max_age"], now=go["issued_at"] + 1) is None
    assert tokens.verify(go["token"], go["secret"], go["max_age"], now=go["issued_at"] + 2592001) is None
