"""Authenticated encryption for provider API keys at rest (SEC-03, LLM-16, D-23).

Wire format (one string, safe to store in a VARCHAR/LONGTEXT column)::

    v1:<kid>:<base64url(nonce || ciphertext || tag)>

* ``v1``   - format version.
* ``kid``  - key identifier, ``[A-Za-z0-9]{1,16}``; selects the key in the keyring when opening.
* nonce is 12 random bytes, tag is 16 bytes (AES-256-GCM). The base64url alphabet has no ``:``.

The additional authenticated data (AAD) is ``tenant_id|provider|instance`` (see ``aad_for``). A sealed
value copied to another row, tenant or provider therefore fails to open. Opening never returns
plaintext on failure and every failure raises ``SecretBoxError`` with a fixed message that names
neither the plaintext, the key nor the envelope. This module does not log.

Rotation: ``seal`` always uses the active kid; ``open_`` uses the kid named in the envelope only.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

if TYPE_CHECKING:
    from common.settings import LlmSettings

VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
MIN_MASKABLE_LENGTH = 8
_KID = re.compile(r"^[A-Za-z0-9]{1,16}$")
_OPEN_FAILED = "cannot open sealed value"


class SecretBoxError(ValueError):
    """Raised for any seal/open failure. Messages never contain secret material."""


def aad_for(tenant_id: str, provider: str, instance: str) -> str:
    """Bind a sealed value to its owner row: the three parts joined by ``|``."""
    parts = (tenant_id, provider, instance)
    if any("|" in part for part in parts):
        raise SecretBoxError("invalid binding value")
    return "|".join(parts)


def _check_kid(kid: str) -> None:
    if not isinstance(kid, str) or not _KID.match(kid):
        raise SecretBoxError("invalid key id")


def seal(key: bytes, kid: str, plaintext: str, aad: str, *, _nonce: bytes | None = None) -> str:
    """Encrypt ``plaintext`` into a ``v1`` envelope.

    ``_nonce`` is a test-only seam for reproducing fixed vectors; production callers never pass it.
    """
    _check_kid(kid)
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise SecretBoxError("invalid encryption key")
    nonce = _nonce if _nonce is not None else get_random_bytes(NONCE_BYTES)
    if len(nonce) != NONCE_BYTES:
        raise SecretBoxError("invalid nonce")
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(aad.encode("utf-8"))
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    # The documented alphabet has no "=": padding is dropped here and restored by open_ (a padded blob could never be opened).
    blob = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii").rstrip("=")
    return f"{VERSION}:{kid}:{blob}"


def open_(keys: Mapping[str, bytes], envelope: str, aad: str) -> str:
    """Decrypt an envelope. Raises ``SecretBoxError`` on any malformed, tampered or mismatched input."""
    try:
        version, kid, blob = envelope.split(":", 2)
        if version != VERSION or not _KID.match(kid) or not re.fullmatch(r"[A-Za-z0-9_-]+", blob):
            raise ValueError
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
        if len(raw) < NONCE_BYTES + TAG_BYTES:
            raise ValueError
        nonce, ciphertext, tag = raw[:NONCE_BYTES], raw[NONCE_BYTES:-TAG_BYTES], raw[-TAG_BYTES:]
        cipher = AES.new(keys[kid], AES.MODE_GCM, nonce=nonce)
        cipher.update(aad.encode("utf-8"))
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except (ValueError, KeyError, TypeError, AttributeError, binascii.Error):
        raise SecretBoxError(_OPEN_FAILED) from None


def mask_last4(secret: str) -> str:
    """Last four characters for display (D-17); empty when the secret is too short to reveal any part."""
    if not isinstance(secret, str) or len(secret) < MIN_MASKABLE_LENGTH:
        return ""
    return secret[-4:]


def keyring_from_settings(llm: LlmSettings) -> tuple[str, dict[str, bytes]]:
    """Return ``(active kid, keyring)`` from settings; fail closed when no key is configured."""
    if not llm.encryption_key:
        raise SecretBoxError("provider key store is not configured")
    try:
        key = base64.urlsafe_b64decode(llm.encryption_key + "=" * (-len(llm.encryption_key) % 4))
    except (ValueError, binascii.Error):
        raise SecretBoxError("provider key store is not configured") from None
    if len(key) != KEY_BYTES:
        raise SecretBoxError("provider key store is not configured")
    _check_kid(llm.key_id)
    return llm.key_id, {llm.key_id: key}
