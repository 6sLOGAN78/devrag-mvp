"""A real headless Chrome executes the SPA behind the auth guard (UI-01, UI-02, UI-03, UI-04, UI-07).

The browser is driven over the DevTools pipe by ``test.helpers.chrome_cdp`` (standard library only).
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.chrome_cdp import ChromeSession, chrome_path
from test.testcases.conftest import BASE_URL, HTTP_PORT

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


def _wait_healthy_cards(browser: ChromeSession) -> None:
    browser.wait_for(
        "document.querySelector('[data-testid=\"status-card-go\"]') !== null"
        " && document.querySelector('[data-testid=\"status-card-python\"]') !== null"
        " && document.documentElement.outerHTML.split('Healthy').length - 1 >= 2",
        "both status cards rendered as Healthy behind the guard",
        timeout=60,
    )


def test_status_page_renders_healthy_cards_in_real_browser(stack_ready: object, account: Account, browser: ChromeSession) -> None:
    _store_token(browser, account.token)
    browser.navigate(f"{ORIGIN}/system-status")
    _wait_healthy_cards(browser)
    dom = browser.evaluate("document.documentElement.outerHTML")
    assert 'data-testid="status-card-go"' in dom, dom[:500]
    assert 'data-testid="status-card-python"' in dom
    assert dom.count("Healthy") >= 2
    assert browser.evaluate("location.pathname") == "/system-status"  # recovered the session, no redirect
    # The signed-in shell carries the account menu and the captioned nav group (plan 02-28).
    assert browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]') !== null") is True
    assert browser.evaluate("document.querySelector('[data-testid=\"nav-item-system-status\"]') !== null") is True


@pytest.fixture
def signout_account(stack_ready: object) -> Iterator[Account]:
    """Sign out ends the shared token for the whole account (D-10), so it must not use the session-wide account."""
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="signout")
    finally:
        registry.cleanup()


def test_sign_out_from_the_account_menu_lands_on_a_bare_login_in_real_browser(
    stack_ready: object, signout_account: Account, browser: ChromeSession
) -> None:
    _store_token(browser, signout_account.token)
    browser.navigate(f"{ORIGIN}/system-status")
    _wait_healthy_cards(browser)
    browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]').focus()")
    for event_type in ("keyDown", "keyUp"):
        browser.call(
            "Input.dispatchKeyEvent",
            {"type": event_type, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, **({"text": "\r"} if event_type == "keyDown" else {})},
        )
    browser.wait_for("document.querySelector('[data-testid=\"user-menu-signout\"]') !== null", "account menu opened by keyboard")
    browser.evaluate("document.querySelector('[data-testid=\"user-menu-signout\"]').click()")
    browser.wait_for("location.pathname === '/login'", "sign out lands on /login")
    assert browser.evaluate("location.search") == ""
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None
    assert browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]') === null") is True


def test_root_redirects_a_signed_in_visitor_to_home_in_real_browser(
    stack_ready: object, account: Account, browser: ChromeSession
) -> None:
    _store_token(browser, account.token)
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("document.querySelector('[data-testid=\"home-page\"]') !== null", "the home dashboard rendered behind the guard", timeout=60)
    assert browser.evaluate("location.pathname") == "/home"
    assert browser.evaluate("document.querySelector('[data-testid=\"stat-role\"]') !== null") is True


def test_root_redirects_a_signed_out_visitor_to_login_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login for a signed-out visitor at /")
    assert browser.evaluate("location.pathname") == "/login"
    assert browser.evaluate("location.search") == ""
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True


def test_signed_out_visitor_is_redirected_to_login_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    browser.navigate(f"{ORIGIN}/system-status")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login for a signed-out visitor")
    assert browser.evaluate("location.pathname") == "/login"
    assert browser.evaluate("location.search") == "?next=%2Fsystem-status"
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None


def test_rejected_token_is_purged_and_redirects_without_a_reload(stack_ready: object, browser: ChromeSession) -> None:
    _store_token(browser, "not-a-valid-token")
    browser.navigate(f"{ORIGIN}/system-status")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login after the server rejects the token")
    assert browser.evaluate("location.search") == "?next=%2Fsystem-status"
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True
