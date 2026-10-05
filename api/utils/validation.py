"""Reusable constrained request types (API-07, SEC-10).

Request models use these so that injection-shaped input is rejected at the boundary,
before any service runs. They are an input contract only; SQL still uses parameters.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
DEFAULT_TEXT_MAX_LENGTH = 4096

SafeIdentifier = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN)]
SafeText = Annotated[str, StringConstraints(max_length=DEFAULT_TEXT_MAX_LENGTH)]

