"""Read captured mail back from the dev Mailpit service through its HTTP API (D-05, D-20)."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any

import httpx

from test.helpers.wait import wait_until

CODE_RE = re.compile(r"\b\d{6}\b")


def base_url() -> str:
    return os.environ.get("MAILPIT_URL", "http://127.0.0.1:8025").rstrip("/")


def _request(method: str, path: str) -> Any:
    resp = httpx.request(method, f"{base_url()}{path}", timeout=5.0)
    resp.raise_for_status()
    body = resp.content
    return json.loads(body) if body.startswith((b"{", b"[")) else body.decode("utf-8", "replace")


def _first_message(recipient: str) -> dict[str, Any] | None:
    query = urllib.parse.quote(f"to:{recipient}")
    try:
        found = _request("GET", f"/api/v1/search?query={query}&limit=1")
    except httpx.HTTPError:
        return None
    messages = found.get("messages") or []
    return messages[0] if messages else None


def wait_for_mail(recipient: str, timeout: float = 30.0) -> dict[str, Any]:
    """Wait for the newest message addressed to ``recipient`` and return its full body (Text, HTML, Subject, ...)."""
    summary = wait_until(lambda: _first_message(recipient), timeout=timeout, interval=0.3, describe=lambda: f"no mail for {recipient}")
    return _request("GET", f"/api/v1/message/{summary['ID']}")


def clear_mailbox() -> None:
    _request("DELETE", "/api/v1/messages")


def extract_code(message: dict[str, Any]) -> str:
    match = CODE_RE.search(message.get("Text") or "")
    assert match, f"no 6-digit code in message: {message.get('Subject')!r}"
    return match.group(0)


def assert_no_mail_for(recipient: str, timeout: float = 3.0) -> None:
    """Negative check: no message for ``recipient`` appears within a bounded window."""
    try:
        wait_until(lambda: _first_message(recipient), timeout=timeout, interval=0.3)
    except TimeoutError:
        return
    raise AssertionError(f"unexpected mail for {recipient}")


def delete_mail_for(recipient: str) -> None:
    """Remove the captured messages addressed to ``recipient`` (and nothing else)."""
    query = urllib.parse.quote(f"to:{recipient}")
    _request("DELETE", f"/api/v1/search?query={query}")
