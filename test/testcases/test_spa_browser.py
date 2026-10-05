"""A real headless Chrome executes the SPA and renders both engine cards as Healthy (UI-01, UI-03)."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from test.testcases.conftest import HTTP_PORT

pytestmark = pytest.mark.e2e


def test_status_page_renders_healthy_cards_in_real_browser(stack_ready: object) -> None:
    chrome = shutil.which("google-chrome")
    assert chrome, "google-chrome is not installed; see BLOCKERS (browser check not run)"
    result = subprocess.run(  # noqa: S603
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=15000", "--dump-dom", f"http://127.0.0.1:{HTTP_PORT}/"],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    dom = result.stdout
    assert 'data-testid="status-card-go"' in dom, dom[:500]
    assert 'data-testid="status-card-python"' in dom
    assert dom.count("Healthy") >= 2
