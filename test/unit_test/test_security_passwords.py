from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from common.security import passwords

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "test" / "fixtures" / "password_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vec", DATA["positive"], ids=[v["id"] for v in DATA["positive"]])
def test_positive_vectors(vec):
    assert passwords.verify_password(vec["password"], vec["hash"]) is True


@pytest.mark.parametrize("vec", DATA["negative"], ids=[v["id"] for v in DATA["negative"]])
def test_negative_vectors(vec):
    assert passwords.verify_password(vec["password"], vec["hash"]) is False


def test_hash_prefix_and_shape():
    h = passwords.hash_password("pw12345678")
    assert h.startswith("pbkdf2:sha256:600000$")
    scheme, salt, digest = h.split("$")
    assert scheme == "pbkdf2:sha256:600000"
    assert len(salt) == 16 and salt.isalnum() and salt.isascii()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert passwords.verify_password("pw12345678", h) is True
    assert passwords.verify_password("pw12345679", h) is False


def test_hash_is_salted():
    assert passwords.hash_password("pw12345678") != passwords.hash_password("pw12345678")


def test_no_code_path_emits_non_pbkdf2_hash():
    assert passwords.PASSWORD_METHOD == "pbkdf2:sha256:600000"
    for src in (ROOT / "common" / "security").glob("*.py"):
        text = src.read_text(encoding="utf-8")
        for call in re.findall(r"generate_password_hash\(([^)]*)\)", text):
            assert "method=PASSWORD_METHOD" in call or 'method="pbkdf2:sha256:600000"' in call
        assert "scrypt" not in text.replace("scrypt and other", "") or "reject" in text


def test_non_string_inputs_fail_closed():
    assert passwords.verify_password(None, "x") is False  # type: ignore[arg-type]
    assert passwords.verify_password("pw12345678", None) is False  # type: ignore[arg-type]


def test_python_hash_parses_for_go():
    h = passwords.hash_password("pw12345678")
    method, salt, digest = h.split("$")
    kind, algo, iters = method.split(":")
    assert (kind, algo, int(iters)) == ("pbkdf2", "sha256", 600000)
    assert len(salt) == 16 and len(digest) == 64
