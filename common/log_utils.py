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
SENSITIVE_KEYS = ("password", "secret", "api_key", "apikey", "token", "authorization", "cookie")
_KEY_ALT = "|".join(SENSITIVE_KEYS)
# key=value, key: value and "key": "value" forms inside free text
_SCHEME = r"(?:(?:Bearer|Basic|Digest|Token)\s+)?"
_PATTERN = re.compile(
    rf"""(?P<key>["']?(?:[\w-]*(?:{_KEY_ALT})[\w-]*)["']?)(?P<sep>\s*[=:]\s*)"""
    rf"""(?P<val>{_SCHEME}"[^"]*"|{_SCHEME}'[^']*'|{_SCHEME}[^\s,;&}}]+)""",
    re.IGNORECASE,
)
_STANDARD = set(vars(logging.LogRecord("x", 0, "x", 0, "", None, None))) | {"message", "asctime", "taskName"}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(s in lowered for s in SENSITIVE_KEYS)


def redact_text(text: str) -> str:
    def sub(m: re.Match[str]) -> str:
        val = m.group("val")
        quote = val[-1] if val and val[-1] in "\"'" else ""
        return f"{m.group('key')}{m.group('sep')}{quote}{REDACTED}{quote}"

    return _PATTERN.sub(sub, text)


def redact_value(key: str, value: Any) -> Any:
    if _is_sensitive(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
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
