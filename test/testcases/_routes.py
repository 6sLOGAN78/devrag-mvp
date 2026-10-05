"""Helpers that expand conf/routes.yaml into probe requests (no owner table is hard-coded in tests)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from test.conftest import REPO_ROOT

ROUTES_FILE = REPO_ROOT / "conf" / "routes.yaml"


@dataclass(frozen=True)
class Probe:
    owner: str
    match: str
    path: str

    @property
    def id(self) -> str:
        return f"{self.owner}:{self.match}:{self.path}"

    def request_path(self, token: str | None = None) -> str:
        if self.match == "exact":
            return self.path
        return f"{self.path}probe-{token or uuid.uuid4().hex}"


def load_probes(path: Path = ROUTES_FILE) -> list[Probe]:
    """Expand every entry (and its ``also`` aliases) into its own probe."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    probes: list[Probe] = []
    for entry in data["routes"]:
        paths = [entry["path"], *entry.get("also", [])]
        probes.extend(Probe(entry["owner"], entry["match"], p) for p in paths)
    return probes


def ownership_mismatches(client: httpx.Client, probes: list[Probe]) -> list[str]:
    """Return one message per probe whose answering engine differs from the declared owner."""
    bad: list[str] = []
    for probe in probes:
        resp = client.get(probe.request_path())
        got = resp.headers.get("x-api-source")
        if got != probe.owner:
            bad.append(f"{probe.id}: declared {probe.owner}, answered by {got!r} (HTTP {resp.status_code})")
    return bad
