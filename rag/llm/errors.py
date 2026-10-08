"""Model-call error codes and the one exception type drivers raise (plan 03-05, LLM-19, Pitfall 14).

``ModelException`` carries a provider-neutral ``code`` plus a ``safe_message``: the provider's own ``error.message`` parsed
out of the response body, cut to 200 characters and passed through the shared redactor. The raw body is parsed and then
dropped, ``str()`` returns only the code, and no provider exception text is ever stored. Callers map ``code`` to an HTTP
status at the API edge; they never forward ``provider_status``.
"""
from __future__ import annotations

import json
from enum import StrEnum

from common.log_utils import redact_text

SAFE_MESSAGE_LIMIT = 200
_PARSE_LIMIT = 65536
_REDACT_WINDOW = 4096


class LLMErrorCode(StrEnum):
    ERROR_RATE_LIMIT = "ERROR_RATE_LIMIT"
    ERROR_AUTHENTICATION = "ERROR_AUTHENTICATION"
    ERROR_INVALID_REQUEST = "ERROR_INVALID_REQUEST"
    ERROR_SERVER = "ERROR_SERVER"
    ERROR_TIMEOUT = "ERROR_TIMEOUT"
    ERROR_CONNECTION = "ERROR_CONNECTION"
    ERROR_MODEL = "ERROR_MODEL"
    ERROR_MAX_ROUNDS = "ERROR_MAX_ROUNDS"
    ERROR_CONTENT_FILTER = "ERROR_CONTENT_FILTER"
    ERROR_QUOTA = "ERROR_QUOTA"
    ERROR_MAX_RETRIES = "ERROR_MAX_RETRIES"
    ERROR_GENERIC = "ERROR_GENERIC"


def _provider_message(body: str | bytes | None) -> str:
    """The ``error.message`` (OpenAI shape) or ``error`` string (Ollama shape) of a JSON body, else the empty string."""
    if body is None or len(body) > _PARSE_LIMIT:
        return ""
    try:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        parsed = json.loads(text)
    except (UnicodeDecodeError, ValueError):
        return ""
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        error = error.get("message")
    return error if isinstance(error, str) else ""


def safe_text(text: str) -> str:
    """Redact first, then truncate, so a key straddling the cut never leaves a recognisable fragment."""
    cleaned = "".join(" " if c in "\r\n\t" else c for c in text[:_REDACT_WINDOW] if c >= " " and c != "\x7f" or c in "\r\n\t")
    return redact_text(cleaned)[:SAFE_MESSAGE_LIMIT]


class ModelException(Exception):
    def __init__(
        self,
        code: LLMErrorCode,
        *,
        retryable: bool = False,
        provider_status: int | None = None,
        retry_after: float | None = None,
        body: str | bytes | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable
        self.provider_status = provider_status
        self.retry_after = retry_after
        self.safe_message = safe_text(message if message is not None else _provider_message(body))

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ModelException({self.code.value}, status={self.provider_status}, retryable={self.retryable})"
