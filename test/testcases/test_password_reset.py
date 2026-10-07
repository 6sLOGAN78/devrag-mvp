"""AUTH-16..18: the forgot-password flow through Nginx against the real Go engine, Valkey, MySQL and Mailpit (plan 02-17).

The code is read from the real captured message; nothing is read from Redis or the logs. Every test uses its own
email so the per-email rate limits (production values) never couple tests.
"""
from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from test.helpers.accounts import TEST_PASSWORD, Account, delete_accounts, register_account, unique_email
from test.helpers.mail import assert_no_mail_for, delete_mail_for, extract_code, wait_for_mail
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.e2e

FORGOT = "/api/v1/auth/password/forgot/otp"
VERIFY = "/api/v1/auth/password/forgot/otp/verify"
RESET = "/api/v1/auth/password/reset"
NEW_PASSWORD = "reset-new-pass-0003"


@pytest.fixture
def reset_account(ingress: httpx.Client) -> Iterator[Account]:
    acc = register_account(BASE_URL, prefix="reset")
    try:
        yield acc
    finally:
        delete_mail_for(acc.email)
        delete_accounts([acc])


def _wrong(code: str) -> str:
    return "000001" if code == "000000" else "000000"


def test_password_reset_full_flow_signs_every_device_out(ingress: httpx.Client, reset_account: Account) -> None:
    acc = reset_account
    resp = ingress.post(FORGOT, json={"email": acc.email})
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-api-source"] == "go"
    assert "set-cookie" not in resp.headers
    message = wait_for_mail(acc.email)
    code = extract_code(message)
    assert message["Subject"] == "Your devRag password reset code"
    assert [a["Address"] for a in message["To"]] == [acc.email]
    assert not message.get("Cc") and not message.get("Bcc")
    assert acc.email not in message["Text"] and TEST_PASSWORD not in message["Text"]

    verified = ingress.post(VERIFY, json={"email": acc.email, "otp": code})
    assert verified.status_code == 200, verified.text
    ticket = verified.json()["data"]["reset_ticket"]
    assert len(ticket) >= 22
    reset = ingress.post(RESET, json={"email": acc.email, "reset_ticket": ticket, "new_password": NEW_PASSWORD})
    assert reset.status_code == 200, reset.text
    assert "set-cookie" not in reset.headers
    assert NEW_PASSWORD not in reset.text and ticket not in reset.text

    old = {"Authorization": f"Bearer {acc.token}"}
    assert ingress.get("/v1/user/info", headers=old).status_code == 401  # Go
    assert ingress.get("/api/v1/system/status", headers=old).status_code == 401  # Python
    assert ingress.post("/api/v1/auth/login", json={"email": acc.email, "password": TEST_PASSWORD}).status_code == 401
    login = ingress.post("/api/v1/auth/login", json={"email": acc.email, "password": NEW_PASSWORD})
    assert login.status_code == 200
    fresh = {"Authorization": f"Bearer {login.json()['data']['token']}"}
    assert ingress.get("/v1/user/info", headers=fresh).status_code == 200
    assert ingress.get("/api/v1/system/status", headers=fresh).status_code == 200
    replay = ingress.post(RESET, json={"email": acc.email, "reset_ticket": ticket, "new_password": "yet-another-pass-9"})
    assert replay.status_code == 400


def test_password_reset_unknown_email_is_byte_identical_and_sends_nothing(ingress: httpx.Client, reset_account: Account) -> None:
    ghost = unique_email("ghost")
    try:
        real = ingress.post(FORGOT, json={"email": reset_account.email})
        unknown = ingress.post(FORGOT, json={"email": ghost})
        assert real.status_code == unknown.status_code == 200
        assert real.content == unknown.content
        wait_for_mail(reset_account.email)
        assert_no_mail_for(ghost)
    finally:
        delete_mail_for(ghost)


def test_password_reset_five_wrong_codes_invalidate_the_real_code(ingress: httpx.Client, reset_account: Account) -> None:
    acc = reset_account
    assert ingress.post(FORGOT, json={"email": acc.email}).status_code == 200
    code = extract_code(wait_for_mail(acc.email))
    statuses = [ingress.post(VERIFY, json={"email": acc.email, "otp": _wrong(code)}).status_code for _ in range(5)]
    assert statuses == [400] * 5
    assert ingress.post(VERIFY, json={"email": acc.email, "otp": code}).status_code == 400
    assert ingress.post(RESET, json={"email": acc.email, "otp": code, "new_password": NEW_PASSWORD}).status_code == 400
    assert ingress.post("/api/v1/auth/login", json={"email": acc.email, "password": TEST_PASSWORD}).status_code == 200


def test_password_reset_request_is_rate_limited_per_email(ingress: httpx.Client) -> None:
    ghost = unique_email("rl-ghost")
    assert ingress.post(FORGOT, json={"email": ghost}).status_code == 200
    limited = ingress.post(FORGOT, json={"email": ghost})
    assert limited.status_code == 429
    assert 0 < int(limited.headers["retry-after"]) <= 60


def test_password_reset_rejects_short_and_overlong_passwords_without_burning_the_ticket(ingress: httpx.Client, reset_account: Account) -> None:
    acc = reset_account
    assert ingress.post(FORGOT, json={"email": acc.email}).status_code == 200
    code = extract_code(wait_for_mail(acc.email))
    ticket = ingress.post(VERIFY, json={"email": acc.email, "otp": code}).json()["data"]["reset_ticket"]
    for bad in ("1234567", "x" * 129):
        resp = ingress.post(RESET, json={"email": acc.email, "reset_ticket": ticket, "new_password": bad})
        assert resp.status_code in (400, 413), resp.status_code
    ok = ingress.post(RESET, json={"email": acc.email, "reset_ticket": ticket, "new_password": "x" * 128})
    assert ok.status_code == 200, ok.text
