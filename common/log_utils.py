"""Structured JSON logging with secret redaction (D-28, SEC-04)."""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

REDACTED = "***"
SENSITIVE_KEYS = ("password", "passwd", "pwd", "secret", "api_key", "apikey", "token", "authorization", "cookie")
_SENSITIVE_WORDS = re.compile(r"password|passwd|pwd|secret|api[_-]?key|token|authorization|cookie", re.IGNORECASE)
# Redaction is a linear two-stage scan (CR-02, D-31): every quantifier is bounded, every value
# match is anchored at a position found by KEYSEP, and a consumed span is never rescanned.
_MAX_INPUT = 64 * 1024
_MAX_RUN = 4096  # value runs are capped at {0,4096}; quantifiers below use this bound
_TRUNCATED = "[truncated]"
MAX_LOG_FIELD = 512
# Stage 1: a word run followed by a key/value separator. The lookbehind makes each word run
# start exactly once, so a long run without a separator costs one pass, not one per offset.
KEYSEP = re.compile(r"""(?<![\w-])(?P<key>["']?[\w-]+["']?)(?P<sep>[ \t]*[=:][ \t]*)""")
_SCHEME = re.compile(r"(?P<scheme>Bearer|Basic|Digest|Token|ApiKey|Api-Key|Negotiate|AWS4-HMAC-SHA256)[ \t]+", re.IGNORECASE)
_QUOTED = {q: re.compile(rf"{q}(?:\\.|[^{q}\\]){{0,{_MAX_RUN}}}+{q}") for q in ('"', "'")}
_BARE = re.compile(rf"[^\s,;&}}]{{1,{_MAX_RUN}}}")
# Stage 0: scheme:// locator and authority terminator for URL userinfo.
_URL_SCHEME = re.compile(r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_AUTH_END = re.compile(r"[/?#\s]")
_STANDARD = set(vars(logging.LogRecord("x", 0, "x", 0, "", None, None))) | {"message", "asctime", "taskName"}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(s in lowered for s in SENSITIVE_KEYS)


def _redact_userinfo(text: str) -> str:
    """scheme://user:password@host -> keep scheme, user and host (linear, last ``@`` of the authority)."""
    out: list[str] = []
    pos = 0
    while (m := _URL_SCHEME.search(text, pos)) is not None:
        start = m.end()
        end_m = _AUTH_END.search(text, start, start + _MAX_RUN)
        end = end_m.start() if end_m else min(len(text), start + _MAX_RUN)
        at = text.rfind("@", start, end)
        if at == -1:
            out.append(text[pos:start])
            pos = start
            continue
        userinfo = text[start:at]
        user, colon, _ = userinfo.partition(":")
        out.append(text[pos:start])
        out.append(f"{user}:{REDACTED}@" if colon else userinfo + "@")
        pos = at + 1
    out.append(text[pos:])
    return "".join(out)


def _value_end(text: str, pos: int, key: str) -> tuple[int, str]:
    """Return (end, quote) of the secret value starting at ``pos``; end == pos means no value."""
    for q, pattern in _QUOTED.items():
        if text.startswith(q, pos):
            m = pattern.match(text, pos)
            if m:
                return m.end(), q
    eol = text.find("\n", pos)
    eol = len(text) if eol == -1 else eol
    if "cookie" in key.lower():
        return eol, ""
    sm = _SCHEME.match(text, pos)
    if sm is not None:
        if sm.group("scheme").upper() == "AWS4-HMAC-SHA256":
            return eol, ""
        for q, pattern in _QUOTED.items():
            if text.startswith(q, sm.end()):
                m = pattern.match(text, sm.end())
                if m:
                    return m.end(), q
        bm = _BARE.match(text, sm.end())
        if bm:
            return bm.end(), ""
    bm = _BARE.match(text, pos)
    return (bm.end() if bm else pos), ""


def _redact_keys(text: str) -> str:
    out: list[str] = []
    pos = 0
    cursor = 0
    while (m := KEYSEP.search(text, cursor)) is not None:
        cursor = m.end()
        key = m.group("key")
        if _SENSITIVE_WORDS.search(key) is None:
            continue
        end, quote = _value_end(text, m.end(), key)
        if end == m.end():
            continue
        out.append(text[pos : m.end()])
        out.append(f"{quote}{REDACTED}{quote}")
        pos = cursor = end
    out.append(text[pos:])
    return "".join(out)


def redact_text(text: str) -> str:
    if len(text) > _MAX_INPUT:
        return redact_text(text[:_MAX_INPUT]) + _TRUNCATED
    return _redact_keys(_redact_userinfo(text))


def truncate_field(value: str, limit: int = MAX_LOG_FIELD) -> str:
    """Bound an untrusted, client-controlled field at the log site (D-31)."""
    return value if len(value) <= limit else value[:limit] + _TRUNCATED


def redact_value(key: str, value: Any) -> Any:
    if _is_sensitive(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value("", v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value("", v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    """Masks sensitive extras and key=value pairs in the formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = None
        for key in list(vars(record)):
            if key not in _STANDARD:
                setattr(record, key, redact_value(key, getattr(record, key)))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


class _UtcFormatter(JsonFormatter):
    converter = staticmethod(time.gmtime)


def init_root_logger(name: str, log_dir: str | None = None, level: str = "INFO") -> logging.Logger:
    """Configure the root logger: JSON lines to stdout and optionally ``<log_dir>/<name>.log``."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level.upper())
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(Path(log_dir) / f"{name}.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(_UtcFormatter())
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    return logging.getLogger(name)
