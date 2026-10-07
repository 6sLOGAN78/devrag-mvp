"""Password hashing contract shared with Go (internal/common/password.go).

Format is the werkzeug string ``pbkdf2:sha256:<iterations>$<salt>$<hex>``. The method is
always passed explicitly: werkzeug's default is scrypt, which the Go engine rejects.
Hashes with any other scheme fail verification (fail closed).
"""

from __future__ import annotations

import hashlib
import hmac
import re

from werkzeug.security import generate_password_hash

HASH_METHOD = "pbkdf2:sha256:600000"
MIN_ITERATIONS = 100_000
MAX_ITERATIONS = 10_000_000
_HASH_RE = re.compile(r"pbkdf2:sha256:(\d{1,9})\$([A-Za-z0-9]{1,64})\$([0-9a-f]{64})")


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=HASH_METHOD)


def verify_password(password: str, stored: str) -> bool:
    if not isinstance(password, str) or not isinstance(stored, str) or not password:
        return False
    m = _HASH_RE.fullmatch(stored)
    if m is None:
        return False
    iterations = int(m.group(1))
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), m.group(2).encode("ascii"), iterations).hex()
    return hmac.compare_digest(digest, m.group(3))
