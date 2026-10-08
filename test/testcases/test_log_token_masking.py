"""No credential reaches the Go, Python or Nginx logs, and a token carried in a URL path is logged as its route template
(plan 02-25, SEC-01, T-02-94, T-02-119).

The logs are the real container output (``docker compose -p devrag-stack logs app``): Nginx access lines, the Go JSON lines and the
Python JSON lines share that stream. The secrets are the values this test itself creates and uses (session tokens, an API token and
its beta value, passwords, a one-time code, a reset ticket); they are searched for as values, and only counts are ever printed.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

from test.helpers.accounts import TEST_PASSWORD, Account, AccountRegistry
from test.helpers.mail import delete_mail_for, extract_code, wait_for_mail
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL, compose

pytestmark = pytest.mark.e2e

FAMILY = "/api/v1/system/tokens/"
GO_TEMPLATE = FAMILY + ":token"
NGINX_MASK = FAMILY + "***"
NEW_PASSWORD = "log-sweep-new-pass-0009"
# fixed fake credentials used by other tests of this suite; they must not appear anywhere in the logs of the whole run
FIXED_FAKES = (TEST_PASSWORD, "reset-new-pass-0003", "yet-another-pass-9", "leak-sweep-new-pass-0007", "leak-sweep-changed-pass-0008")
_NGINX_LINE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3} - ")
_API_TOKEN = re.compile(r"ragflow-[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class Streams:
    nginx: list[str]
    go: list[str]
    python: list[str]
    whole: str


def read_logs() -> Streams:
    """The app container's real log output, split into the three engines' lines."""
    proc = compose("logs", "--no-color", "--no-log-prefix", "app", timeout=170)
    assert proc.returncode == 0, "docker compose logs failed"
    lines = (proc.stdout + proc.stderr).splitlines()
    return Streams(
        nginx=[line for line in lines if _NGINX_LINE.match(line)],
        go=[line for line in lines if line.startswith('{"level"')],
        python=[line for line in lines if line.startswith('{"ts"') and '"ragflow' in line],
        whole="\n".join(lines),
    )


def occurrences(text: str, value: str, bounded: bool = False) -> int:
    if bounded:
        return len(re.findall(rf"(?<![0-9A-Za-z]){re.escape(value)}(?![0-9A-Za-z])", text))
    return text.count(value)


@pytest.fixture(scope="module")
def account() -> Iterator[Account]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="logmask")
    finally:
        registry.cleanup()


def test_token_in_path_is_logged_as_the_route_template_by_every_engine(ingress: httpx.Client, account: Account) -> None:
    agent = f"devrag-masking-{uuid.uuid4().hex}"
    headers = {"Authorization": f"Bearer {account.token}", "User-Agent": agent}
    created = ingress.post("/api/v1/system/tokens", headers=headers)
    assert created.status_code == 200
    api_token, beta = created.json()["data"]["token"], created.json()["data"]["beta"]
    invalid = "ragflow-" + uuid.uuid4().hex + uuid.uuid4().hex[:11]
    before = read_logs()
    go_before = sum(GO_TEMPLATE in line for line in before.go)

    # a Python-owned route sees the API token as a bearer credential, a Go-owned route sees the token in the path
    probe = f"/api/v1/logmask-probe-{uuid.uuid4().hex}"
    assert ingress.get(probe, headers={"Authorization": f"Bearer {api_token}", "User-Agent": agent}).status_code == 404
    assert ingress.delete(f"{FAMILY}{api_token}", headers=headers).status_code == 200
    assert ingress.delete(f"{FAMILY}{invalid}", headers=headers).status_code == 404
    # other spellings of the same path (percent-encoded letter, merged slashes) are normalised by Nginx before it routes and logs
    spelled = ["ragflow-" + uuid.uuid4().hex + uuid.uuid4().hex[:11] for _ in range(2)]
    ingress.delete(f"/api/v1/system/%74okens/{spelled[0]}", headers=headers)
    ingress.delete(f"/api/v1/system//tokens/{spelled[1]}", headers=headers)
    # a mistyped endpoint with a real credential in it: Go-unmatched and Python-unmatched requests mask the credential-shaped segment
    typo = "ragflow-" + uuid.uuid4().hex + uuid.uuid4().hex[:11]
    ingress.delete(f"/api/v1/system/token/{typo}", headers=headers)
    ingress.get(f"/v1/user/token/{typo}", headers=headers)
    assert ingress.get(probe, headers={"Authorization": f"Bearer {api_token}", "User-Agent": agent}).status_code == 401

    def logged() -> Streams | None:
        now = read_logs()
        mine = [line for line in now.nginx if agent in line]
        deletes = [line for line in mine if "DELETE" in line]
        go_now = sum(GO_TEMPLATE in line for line in now.go)
        return now if len(deletes) >= 5 and go_now - go_before >= 2 and sum(probe in line for line in now.python) >= 2 else None

    now = wait_until(logged, timeout=60, interval=1.0, describe=lambda: "the request lines did not appear in the container logs")
    mine = [line for line in now.nginx if agent in line]
    deletes = [line for line in mine if "DELETE" in line]
    family = [line for line in deletes if FAMILY in line]
    assert len(family) >= 4 and all(NGINX_MASK in line for line in family), "the Nginx access log must record the masked path for a token-bearing URL"
    assert any("/system/token/ragflow-***" in line for line in deletes), "a credential-shaped segment in a mistyped path is masked by Nginx"
    checked = (
        ("the API token", api_token),
        ("its beta value", beta),
        ("the invalid token", invalid),
        ("an invalid token, encoded spelling", spelled[0]),
        ("an invalid token, doubled slash", spelled[1]),
        ("a token in a mistyped endpoint", typo),
    )
    for label, secret in checked:
        for engine, lines in (("nginx", now.nginx), ("go", now.go), ("python", now.python)):
            hits = occurrences("\n".join(lines), secret)
            assert hits == 0, f"{label} appears {hits} time(s) in the {engine} log"
    assert any(GO_TEMPLATE in line for line in now.go), "Go logs the route template"
    assert occurrences("\n".join(now.go), FAMILY + api_token[:12]) == 0
    assert not [line for line in mine if _API_TOKEN.search(line)], "no API-token-shaped value in this test's Nginx lines"


def test_credentials_used_in_a_whole_flow_never_reach_any_log(ingress: httpx.Client) -> None:
    registry = AccountRegistry(BASE_URL)
    email = ""
    try:
        acc = registry.register(prefix="logflow")
        email = acc.email
        forgot, verify, reset = "/api/v1/auth/password/forgot/otp", "/api/v1/auth/password/forgot/otp/verify", "/api/v1/auth/password/reset"
        assert ingress.post(forgot, json={"email": acc.email}).status_code == 200
        code = extract_code(wait_for_mail(acc.email))
        wrong = "000000" if code != "000000" else "000001"
        assert ingress.post(verify, json={"email": acc.email, "otp": wrong}).status_code == 400
        ticket = ingress.post(verify, json={"email": acc.email, "otp": code}).json()["data"]["reset_ticket"]
        assert ingress.post(reset, json={"email": acc.email, "reset_ticket": ticket, "new_password": NEW_PASSWORD}).status_code == 200
        login = ingress.post("/api/v1/auth/login", json={"email": acc.email, "password": NEW_PASSWORD})
        assert login.status_code == 200
        session = login.json()["data"]["token"]
        assert ingress.get("/v1/user/info", headers={"Authorization": f"Bearer {session}", "Cookie": f"ragflow_auth={session}"}).status_code == 200
        marker = f"/api/v1/logmask-flow-{uuid.uuid4().hex}"
        assert ingress.get(marker, headers={"Authorization": f"Bearer {session}"}).status_code == 404

        def marker_logged() -> Streams | None:
            current = read_logs()
            return current if any(marker in line for line in current.python) else None

        now = wait_until(marker_logged, timeout=60, interval=1.0, describe=lambda: "the marker request did not appear in the Python log")
        secrets = [
            ("the old password", TEST_PASSWORD, False),
            ("the new password", NEW_PASSWORD, False),
            ("the first session token", acc.token, False),
            ("the new session token", session, False),
            ("the reset ticket", ticket, False),
            ("the real one-time code", code, True),
            ("a wrong one-time code", wrong, True),
        ]
        for label, value, bounded in secrets:
            for engine, text in (("nginx", "\n".join(now.nginx)), ("go", "\n".join(now.go)), ("python", "\n".join(now.python)), ("the whole container output", now.whole)):
                hits = occurrences(text, value, bounded)
                assert hits == 0, f"{label} appears {hits} time(s) in {engine}"
    finally:
        if email:
            delete_mail_for(email)
        registry.cleanup()


def test_no_fixed_fake_password_or_bearer_value_appears_in_the_whole_container_log() -> None:
    now = read_logs()
    for value in FIXED_FAKES:
        hits = occurrences(now.whole, value)
        assert hits == 0, f"a fixed test password appears {hits} time(s) in the container log"
    bearer_values = re.findall(r"Bearer\s+\S{8,}", now.whole)
    assert not bearer_values, f"{len(bearer_values)} Authorization bearer value(s) appear in the container log"
