"""Single-site constants for documented identifiers and API return codes (D-22).

Renaming a documented identifier is a one-line change here; no other module may
spell these strings.
"""
from __future__ import annotations

from enum import IntEnum

SERVICE_NAME = "ragflow_server"
INDEX_PREFIX = "ragflow_"
BUCKET_NAME = "ragflow"
NETWORK_NAME = "ragflow"
API_SOURCE_PYTHON = "python"


class RetCode(IntEnum):
    """Return codes. Legacy block 0-109 and HTTP-like block follow the reference verbatim,
    plus METHOD_NOT_ALLOWED (405) and SERVICE_UNAVAILABLE (503) required by the docs."""

    SUCCESS = 0
    NOT_EFFECTIVE = 10
    EXCEPTION_ERROR = 100
    ARGUMENT_ERROR = 101
    DATA_ERROR = 102
    OPERATING_ERROR = 103
    CONNECTION_ERROR = 105
    RUNNING = 106
    PERMISSION_ERROR = 108
    AUTHENTICATION_ERROR = 109
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503
