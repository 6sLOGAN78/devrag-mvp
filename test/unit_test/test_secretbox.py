"""AES-256-GCM secret box for provider keys (SEC-03, LLM-16, D-23)."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from common.security import secretbox
from common.security.secretbox import SecretBoxError, aad_for, mask_last4, open_, seal

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VECTOR = json.loads((FIXTURES / "secretbox_vectors.json").read_text(encoding="utf-8"))

# Obviously fake key material, built from parts so the secrets gate stays quiet.
KEY = (("fake-key-for-tests-only-0123456789" * 2).encode())[:32]
OTHER_KEY = (("another-fake-key-for-tests-9876543210" * 2).encode())[:32]
AAD = "tenant-0001|OpenAI|primary"
PLAIN = "sk-or-v1-" + "FAKE" * 4 + "abcd"
ENVELOPE_RE = re.compile(r"^v1:[A-Za-z0-9_-]{1,16}:[A-Za-z0-9_-]+$")


def test_vector_key_matches_the_test_key():
    assert VECTOR["key_text"].encode()[:32] == KEY
    assert len(KEY) == 32


def test_round_trip():
    env = seal(KEY, "k1", PLAIN, AAD)
    assert open_({"k1": KEY}, env, AAD) == PLAIN


def test_envelope_shape():
    env = seal(KEY, "k1", PLAIN, AAD)
    assert ENVELOPE_RE.match(env)
    raw = base64.urlsafe_b64decode(env.split(":", 2)[2] + "=" * (-len(env.split(":", 2)[2]) % 4))
    assert len(raw) == 12 + len(PLAIN.encode()) + 16


def test_two_seals_differ():
    assert seal(KEY, "k1", PLAIN, AAD) != seal(KEY, "k1", PLAIN, AAD)


def test_fixed_vector_opens():
    key = VECTOR["key_text"].encode()[:32]
    assert open_({VECTOR["kid"]: key}, VECTOR["envelope"], VECTOR["aad"]) == VECTOR["plaintext"]


def test_fixed_vector_is_reproduced_with_the_injected_nonce():
    """``_nonce`` is a test-only seam of ``seal``: production code never passes it."""
    key = VECTOR["key_text"].encode()[:32]
    env = seal(key, VECTOR["kid"], VECTOR["plaintext"], VECTOR["aad"], _nonce=bytes.fromhex(VECTOR["nonce_hex"]))
    assert env == VECTOR["envelope"]


def _assert_clean(err: SecretBoxError) -> None:
    text = str(err)
    assert PLAIN not in text and "FAKE" not in text
    assert KEY.decode() not in text and OTHER_KEY.decode() not in text


def test_wrong_aad_fails():
    env = seal(KEY, "k1", PLAIN, AAD)
    with pytest.raises(SecretBoxError) as err:
        open_({"k1": KEY}, env, aad_for("tenant-0002", "OpenAI", "primary"))
    _assert_clean(err.value)


def test_wrong_key_fails():
    env = seal(KEY, "k1", PLAIN, AAD)
    with pytest.raises(SecretBoxError) as err:
        open_({"k1": OTHER_KEY}, env, AAD)
    _assert_clean(err.value)


def test_tampered_envelope_fails():
    env = seal(KEY, "k1", PLAIN, AAD)
    last = env[-1]
    flipped = env[:-1] + ("A" if last != "A" else "B")
    with pytest.raises(SecretBoxError) as err:
        open_({"k1": KEY}, flipped, AAD)
    _assert_clean(err.value)


def test_unknown_kid_fails():
    env = seal(KEY, "k1", PLAIN, AAD)
    with pytest.raises(SecretBoxError) as err:
        open_({"k2": KEY}, env, AAD)
    _assert_clean(err.value)


@pytest.mark.parametrize("bad", ["", "v1:k1", "v2:k1:AAAA", "v1:k1:", "v1:k1:AAAA", "v1:k 1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "not-an-envelope", "v1::AAAA"])
def test_malformed_envelope_fails(bad):
    with pytest.raises(SecretBoxError) as err:
        open_({"k1": KEY}, bad, AAD)
    assert str(err.value) == "cannot open sealed value"


def test_rotation_opens_old_kid_and_seals_with_the_active_one():
    old = seal(OTHER_KEY, "k0", PLAIN, AAD)
    ring = {"k0": OTHER_KEY, "k1": KEY}
    assert open_(ring, old, AAD) == PLAIN
    assert seal(KEY, "k1", PLAIN, AAD).startswith("v1:k1:")


@pytest.mark.parametrize("kid", ["", "k" * 17, "k-1", "k 1", "k:1"])
def test_seal_rejects_bad_kid(kid):
    with pytest.raises(SecretBoxError):
        seal(KEY, kid, PLAIN, AAD)


def test_seal_rejects_wrong_key_length():
    with pytest.raises(SecretBoxError):
        seal(b"short", "k1", PLAIN, AAD)


def test_aad_for_joins_with_pipe_and_rejects_pipe():
    assert aad_for("t1", "OpenAI", "primary") == "t1|OpenAI|primary"
    for parts in (("t|1", "p", "i"), ("t", "p|x", "i"), ("t", "p", "i|")):
        with pytest.raises(SecretBoxError):
            aad_for(*parts)


def test_mask_last4():
    assert mask_last4("sk-or-v1-FAKEFAKEFAKEFAKEabcd") == "abcd"
    assert mask_last4("12345678") == "5678"


@pytest.mark.parametrize("short", ["", "a", "1234567"])
def test_mask_last4_short_secret_is_empty(short):
    assert mask_last4(short) == ""


def test_keyring_from_settings():
    from common.settings import LlmSettings

    encoded = base64.urlsafe_b64encode(KEY).decode()
    kid, ring = secretbox.keyring_from_settings(LlmSettings(encryption_key=encoded, key_id="k7"))
    assert kid == "k7" and ring == {"k7": KEY}


def test_keyring_from_settings_unconfigured_fails_closed():
    from common.settings import LlmSettings

    with pytest.raises(SecretBoxError, match="provider key store is not configured"):
        secretbox.keyring_from_settings(LlmSettings(encryption_key=""))
