"""The one email identity rule, shared with the Go engine (R-129).

Trim surrounding white space, apply Unicode NFKC, then lower-case ASCII letters only. The Go twin is
``internal/common/email.go``; both run against ``test/fixtures/email_canonical_vectors.json``.
Lower-casing is ASCII-only on purpose: Go and Python disagree on special cases of non-ASCII letters
(dotted capital I, final sigma), and the database collation already merges case and accent variants.
"""

from __future__ import annotations

import unicodedata

_ASCII_UPPER = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}


def canonical_email(email: str) -> str:
    """Return the canonical spelling every code path starts from."""
    return unicodedata.normalize("NFKC", email.strip()).translate(_ASCII_UPPER)


def new_account_email_chars(canonical: str) -> bool:
    """True when a canonical address is printable ASCII without white space (required of NEW accounts)."""
    return all(" " < ch <= "~" for ch in canonical)
