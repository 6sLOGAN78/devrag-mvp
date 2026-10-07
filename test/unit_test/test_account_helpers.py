"""Pure parts of test/helpers/accounts.py (the endpoint-backed parts need plan 02-09)."""
import pytest

from test.helpers.accounts import AccountFixtureError, register_account, unique_email, unique_name

pytestmark = pytest.mark.unit


def test_unique_email_is_lowercase_and_unique():
    emails = {unique_email("Alice") for _ in range(1000)}
    assert len(emails) == 1000
    assert all(e == e.lower() and e.endswith("@example.test") and e.startswith("alice-") for e in emails)


def test_unique_name_is_unique():
    assert len({unique_name("kb") for _ in range(1000)}) == 1000


def test_register_account_surfaces_endpoint_failure_without_credentials():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AccountFixtureError) as err:
        register_account("http://x.invalid", client=client)
    assert "HTTP 404" in str(err.value)
    assert "test-only-pass" not in str(err.value)
