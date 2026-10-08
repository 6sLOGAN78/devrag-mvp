"""Token usage and the stream sanitizer (plan 03-05, LLM-20).

Provider streams are untrusted and uneven: OpenRouter ends with a chunk whose ``choices`` is empty and which alone carries
``usage``; some gateways send annotation chunks with no delta; a connection can break mid-line and leave a partial JSON
fragment. ``StreamSanitizer.feed`` turns one raw item (a decoded chunk object, a dict, or an SSE line) into the text to show,
or ``None`` when there is nothing to show, and remembers ``usage`` from whichever item carries it. Pure: no SDK imports.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated: bool = False


def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_from(raw: Any) -> Usage | None:
    """Read a provider ``usage`` object or dict. ``None`` when it carries no token counts."""
    prompt, completion, total = (_count(_get(raw, n)) for n in ("prompt_tokens", "completion_tokens", "total_tokens"))
    if prompt is None and completion is None and total is None:
        return None
    prompt, completion = prompt or 0, completion or 0
    return Usage(prompt, completion, total if total is not None else prompt + completion, False)


def strip_control(text: str) -> str:
    """Drop ASCII control characters except newline and tab (and DEL)."""
    return "".join(c for c in text if c in "\n\t" or (c >= " " and c != "\x7f"))


class StreamSanitizer:
    def __init__(self) -> None:
        self.usage: Usage | None = None

    @staticmethod
    def _decode(item: Any) -> Any:
        if isinstance(item, bytes):
            item = item.decode("utf-8", errors="ignore")
        if not isinstance(item, str):
            return item
        line = item.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            return None
        try:
            return json.loads(line)
        except ValueError:
            return None  # a trailing partial fragment: ignore it, the complete line never arrived

    def feed(self, item: Any) -> str | None:
        chunk = self._decode(item)
        if chunk is None:
            return None
        found = usage_from(_get(chunk, "usage"))
        if found is not None:
            self.usage = found
        choices = _get(chunk, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            return None
        content = _get(_get(choices[0], "delta"), "content")
        if not isinstance(content, str):
            return None
        return strip_control(content) or None
