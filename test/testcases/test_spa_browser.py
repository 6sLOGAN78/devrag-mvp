"""A real headless Chrome executes the SPA behind the auth guard (UI-01, UI-02, UI-03, UI-04, UI-07).

The browser is driven over the DevTools pipe by ``test.helpers.chrome_cdp`` (standard library only).
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from test.helpers.accounts import Account
from test.helpers.chrome_cdp import ChromeSession, chrome_path
from test.testcases.conftest import HTTP_PORT

pytestmark = pytest.mark.e2e

ORIGIN = f"http://127.0.0.1:{HTTP_PORT}"
TOKEN_KEY = "Authorization"  # web/src/utils/authorization.ts


@pytest.fixture
def browser() -> Iterator[ChromeSession]:
    assert chrome_path(), "google-chrome is not installed; see BLOCKERS (browser check not run)"
    with ChromeSession() as session:
        yield session


def _store_token(browser: ChromeSession, token: str) -> None:
    """Set the stored token on the app origin (the same origin the SPA reads), then leave a neutral page."""
    browser.navigate(f"{ORIGIN}/health")
    browser.evaluate(f"localStorage.setItem({json.dumps(TOKEN_KEY)}, {json.dumps(token)})")


def test_status_page_renders_healthy_cards_in_real_browser(stack_ready: object, account: Account, browser: ChromeSession) -> None:
    _store_token(browser, account.token)
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for(
        "document.querySelector('[data-testid=\"status-card-go\"]') !== null"
        " && document.querySelector('[data-testid=\"status-card-python\"]') !== null"
        " && document.documentElement.outerHTML.split('Healthy').length - 1 >= 2",
        "both status cards rendered as Healthy behind the guard",
        timeout=60,
    )
    dom = browser.evaluate("document.documentElement.outerHTML")
    assert 'data-testid="status-card-go"' in dom, dom[:500]
    assert 'data-testid="status-card-python"' in dom
    assert dom.count("Healthy") >= 2
    assert browser.evaluate("location.pathname") == "/"  # recovered the session, no redirect


def test_signed_out_visitor_is_redirected_to_login_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login for a signed-out visitor")
    assert browser.evaluate("location.pathname") == "/login"
    assert browser.evaluate("location.search") == "?next=%2F"
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None


def test_rejected_token_is_purged_and_redirects_without_a_reload(stack_ready: object, browser: ChromeSession) -> None:
    _store_token(browser, "not-a-valid-token")
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login after the server rejects the token")
    assert browser.evaluate("location.search") == "?next=%2F"
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True
