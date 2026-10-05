"""System health service: aggregates dependency probes into one status."""
from __future__ import annotations

from typing import Any

from common.constants import API_SOURCE_PYTHON
from common.health.probes import run_probes
from common.settings import Settings


async def get_health(settings: Settings) -> tuple[int, dict[str, Any]]:
    """Return ``(http_status, data)``: 200 only when every probe is ok, otherwise 503."""
    checks = await run_probes(settings)
    healthy = all(c["status"] == "ok" for c in checks.values())
    return (200 if healthy else 503), {"status": "ok" if healthy else "down", "engine": API_SOURCE_PYTHON, "checks": checks}


def get_language() -> dict[str, str]:
    return {"engine": API_SOURCE_PYTHON}
