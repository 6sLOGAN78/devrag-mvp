"""Scanner for the response leak sweep (plan 02-25, SEC-01, T-02-120).

A response may carry a credential only where the registry documents one. Everything else is a leak:

* key names that are internal columns or credential material (``password``, ``access_token``, ``ticket``, ...), anywhere in the JSON;
* hash-looking values (``pbkdf2:`` and friends) anywhere, whatever the key is called;
* the *values* of every secret the run created or used (passwords, session tokens, API tokens, OTP codes, reset tickets, the hashes and
  stored access tokens read back from the database, the stack's own infrastructure secrets), found as substrings of the body or headers.

Findings never contain a secret value: they name the row, the response label and the secret's label.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

BANNED_KEY = re.compile(
    r"password|passwd|pbkdf2|access_token|secret|salt|ticket|(?:^|[_-])otp(?:$|[_-])|is_authenticated|is_active|is_anonymous|login_channel|invited_by|dialog_id|delete_time",
    re.IGNORECASE,
)
# Internal columns of the user, tenant, user_tenant and api_token tables whose names are also ordinary words. A health or status probe
# legitimately has a ``status`` field, so these two are banned everywhere except in the system rows.
INTERNAL_COLUMN = re.compile(r"^(status|source)$", re.IGNORECASE)
SYSTEM_ROWS = re.compile(r"^\w+ (/health|/api/v1/system/(?!tokens)|/system/|/api/v1/openapi\.json|/api/v1/language)")
HASH_VALUE = re.compile(r"pbkdf2:|\$2[aby]\$\d{2}\$|\bscrypt:|\$argon2", re.IGNORECASE)
CREDENTIAL_KEYS = frozenset({"token", "beta"})  # the documented credential fields; see CREDENTIAL_ROWS

LOGIN = "POST /api/v1/auth/login"
VERIFY = "POST /api/v1/auth/password/forgot/otp/verify"
TOKEN_ROWS = frozenset({"GET /api/v1/system/tokens", "POST /api/v1/system/tokens"})
CREDENTIAL_ROWS = TOKEN_ROWS | {LOGIN}
# A key that is documented for exactly one row (the reset ticket is the verify response's whole purpose).
DOCUMENTED_KEYS: Mapping[str, frozenset[str]] = {VERIFY: frozenset({"reset_ticket"})}


@dataclass(frozen=True)
class Secret:
    """A value that must not appear in any response, except in the rows listed in ``allowed_rows``."""

    label: str
    value: str
    allowed_rows: frozenset[str] = frozenset()
    bounded: bool = False  # short numeric values (an OTP) must match as a whole token, not inside a longer run


def _walk(node: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _count(haystack: str, secret: Secret) -> int:
    if not secret.value:
        return 0
    if secret.bounded:
        return len(re.findall(rf"(?<![0-9A-Za-z]){re.escape(secret.value)}(?![0-9A-Za-z])", haystack))
    return haystack.count(secret.value)


def scan_response(row: str, label: str, headers: Mapping[str, str], text: str, secrets: list[Secret]) -> list[str]:
    """Findings for one response; empty when it is clean. No finding contains a secret value."""
    findings: list[str] = []
    where = f"{row} [{label}]"
    try:
        body = json.loads(text)
    except ValueError:
        body = None
    for key, value in _walk(body):
        lowered = key.lower()
        if lowered in CREDENTIAL_KEYS:
            if row not in CREDENTIAL_ROWS:
                findings.append(f"{where}: credential field {key!r} outside the documented rows")
        elif key in DOCUMENTED_KEYS.get(row, frozenset()):
            continue
        elif BANNED_KEY.search(lowered) or (INTERNAL_COLUMN.match(lowered) and not SYSTEM_ROWS.match(row)):
            findings.append(f"{where}: forbidden field {key!r}")
        if isinstance(value, str) and HASH_VALUE.search(value):
            findings.append(f"{where}: a value under {key!r} looks like a password hash")
    if body is None and HASH_VALUE.search(text):
        findings.append(f"{where}: the body looks like it contains a password hash")
    head = "\n".join(f"{k}: {v}" for k, v in headers.items() if not (k.lower() == "set-cookie" and row == LOGIN))
    for secret in secrets:
        if row in secret.allowed_rows:
            continue
        hits = _count(text, secret) + _count(head, secret)
        if hits:
            findings.append(f"{where}: contains the value of {secret.label} ({hits} occurrence(s))")
    return findings
