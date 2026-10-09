"""Response leak sweep (plan 02-25, SEC-01, T-02-120).

Every implemented endpoint of conf/routes.yaml is called through Nginx with real accounts, on its success path and on at least one
error path, and each real response (body and headers) is scanned by ``_leak_sweep``: no password field, no ``pbkdf2:`` hash, no
``access_token``, no OTP or reset ticket (except the verify response's own ticket), no internal column, no login token outside the
login row, and none of the *values* the run used or read back from the database. A registry row the sweep does not exercise fails the
test, like the cross-tenant matrix.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from test.conftest import stack_env
from test.helpers.accounts import TEST_PASSWORD, Account, AccountRegistry, unique_email
from test.helpers.db import root_connection
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.mail import delete_mail_for, extract_code, wait_for_mail
from test.helpers.uploads import pdf_bytes
from test.testcases._leak_sweep import CREDENTIAL_ROWS, LOGIN, TOKEN_ROWS, VERIFY, Secret, scan_response
from test.testcases._matrix_fixtures import (
    A_CHAT_MODEL,
    A_EMBED_MODEL,
    A_PROVIDER_KEY,
    B_PROVIDER_KEY,
    COMPAT,
    DATASETS,
    MODELS,
    MODELS_DEFAULT,
    PROVIDER_SLUG,
    PROVIDERS,
    UPLOAD,
    World,
    build_world,
)
from test.testcases._routes import ROUTES_FILE
from test.testcases.conftest import BASE_URL

SENTINEL_PROVIDER_KEY = "-".join(("leak", "sweep", "provider", "key", "0003"))
ROTATED_PROVIDER_KEY = "-".join(("leak", "sweep", "provider", "key", "0004"))
NEW_PASSWORD = "leak-sweep-new-pass-0007"
CHANGED_PASSWORD = "leak-sweep-changed-pass-0008"
TOKENS = "/api/v1/system/tokens"
USERS = "/api/v1/tenants/{tenant_id}/users"


def implemented_rows(path: Path = ROUTES_FILE) -> list[str]:
    """``METHOD path`` of every implemented registry row, whatever its scope."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [f"{str(e['method']).upper()} {e['path']}" for e in data["endpoints"] if e.get("implemented") is True]


@dataclass
class Sweep:
    client: httpx.Client
    registry: AccountRegistry
    responses: list[tuple[str, str, httpx.Response]] = field(default_factory=list)
    secrets: list[Secret] = field(default_factory=list)

    def req(
        self, row: str, label: str, method: str, path: str, token: str | None = None, body: Any = None, *, files: Any = None, content: bytes | None = None, content_type: str | None = None
    ) -> httpx.Response:
        self.client.cookies.clear()  # only the bearer under test authenticates
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if content_type:
            headers["Content-Type"] = content_type
        resp = self.client.request(method, path, headers=headers, json=body if files is None and content is None else None, files=files, content=content)
        self.responses.append((row, label, resp))
        return resp

    def secret(self, label: str, value: str, allowed: frozenset[str] = frozenset(), bounded: bool = False) -> None:
        if value:
            self.secrets.append(Secret(label, value, allowed, bounded))

    def account(self, prefix: str) -> Account:
        acc = self.registry.register(prefix=prefix)
        self.secret(f"session token of {prefix}", acc.token, frozenset({LOGIN}))
        return acc

    def errors(self, row: str, method: str, path: str, wrong_method: str = "PUT") -> None:
        """No credential, a made-up bearer value, and the wrong method."""
        self.req(row, "no credential", method, path)
        self.req(row, "made-up bearer", method, path, token="not-a-real-credential-" + uuid.uuid4().hex)
        self.req(row, "wrong method", wrong_method, path)


# --- exercisers: one group of rows each ---------------------------------------------------------------------------


def sweep_public_rows(s: Sweep) -> None:
    for path in ("/health", "/api/v1/system/ping", "/api/v1/system/config", "/api/v1/language", "/api/v1/system/healthz", "/system/healthz"):
        s.req(f"GET {path}", "success", "GET", path)
        s.req(f"GET {path}", "wrong method", "POST", path)


def sweep_session_rows(s: Sweep, main: Account) -> None:
    for path in ("/api/v1/system/version", "/api/v1/system/status", "/system/status", "/v1/user/info", "/v1/user/tenant_info", "/v1/tenant/list"):
        row = f"GET {path}"
        s.req(row, "success", "GET", path, main.token)
        s.errors(row, "GET", path, "DELETE")
    api_token = s.req(f"POST {TOKENS}", "create for openapi", "POST", TOKENS, main.token).json()["data"]
    s.secret("api token of main", api_token["token"], TOKEN_ROWS)
    s.secret("beta value of main", api_token["beta"], TOKEN_ROWS)
    row = "GET /api/v1/openapi.json"
    s.req(row, "success with a session", "GET", "/api/v1/openapi.json", main.token)
    s.req(row, "success with an API token", "GET", "/api/v1/openapi.json", api_token["token"])
    s.errors(row, "GET", "/api/v1/openapi.json", "DELETE")
    row = "POST /v1/user/setting"
    s.req(row, "success", "POST", "/v1/user/setting", main.token, {"nickname": "leak-" + uuid.uuid4().hex[:8]})
    s.req(row, "invalid body", "POST", "/v1/user/setting", main.token, {"nickname": ""})
    s.req(row, "not an object", "POST", "/v1/user/setting", main.token, [1, 2])
    s.errors(row, "POST", "/v1/user/setting", "DELETE")


def sweep_account_rows(s: Sweep) -> None:
    email = unique_email("leakreg")
    row = "POST /api/v1/users"
    body = {"email": email, "password": TEST_PASSWORD, "nickname": "leak-reg"}
    resp = s.req(row, "success", "POST", "/api/v1/users", body=body)
    data = resp.json().get("data") or {}
    if data.get("id"):  # record the created rows for cleanup
        s.registry.created.append(Account(email, TEST_PASSWORD, "leak-reg", str(data["id"]), str(data.get("tenant_id") or data["id"]), ""))
    s.req(row, "duplicate email", "POST", "/api/v1/users", body=body)
    s.req(row, "invalid email", "POST", "/api/v1/users", body={**body, "email": "not-an-email"})
    s.req(row, "short password", "POST", "/api/v1/users", body={**body, "email": unique_email("leakreg"), "password": "short"})
    s.req(row, "wrong method", "GET", "/api/v1/users")

    login_acc = s.account("leakin")
    row = LOGIN
    ok = s.req(row, "success", "POST", "/api/v1/auth/login", body={"email": login_acc.email, "password": TEST_PASSWORD})
    s.secret("session token from a second login", str((ok.json().get("data") or {}).get("token", "")), frozenset({LOGIN}))
    s.req(row, "wrong password", "POST", "/api/v1/auth/login", body={"email": login_acc.email, "password": "wrong-" + TEST_PASSWORD})
    s.req(row, "unknown email", "POST", "/api/v1/auth/login", body={"email": unique_email("ghost"), "password": TEST_PASSWORD})
    s.req(row, "malformed", "POST", "/api/v1/auth/login", body={"email": 5})
    s.req(row, "wrong method", "GET", "/api/v1/auth/login")

    out = s.account("leakout")
    row = "POST /api/v1/auth/logout"
    s.req(row, "success", "POST", "/api/v1/auth/logout", out.token)
    s.req(row, "repeat with the ended session", "POST", "/api/v1/auth/logout", out.token)
    s.errors(row, "POST", "/api/v1/auth/logout", "GET")

    pw = s.account("leakpw")
    row = "POST /v1/user/setting/password"
    s.secret("changed password", CHANGED_PASSWORD)
    s.req(row, "wrong old password", "POST", "/v1/user/setting/password", pw.token, {"old_password": "wrong-" + TEST_PASSWORD, "new_password": CHANGED_PASSWORD})
    s.req(row, "weak new password", "POST", "/v1/user/setting/password", pw.token, {"old_password": TEST_PASSWORD, "new_password": "short"})
    s.req(row, "success", "POST", "/v1/user/setting/password", pw.token, {"old_password": TEST_PASSWORD, "new_password": CHANGED_PASSWORD})
    s.errors(row, "POST", "/v1/user/setting/password", "GET")


def sweep_password_reset_rows(s: Sweep) -> None:
    acc = s.account("leakrs")
    forgot, verify, reset = "/api/v1/auth/password/forgot/otp", "/api/v1/auth/password/forgot/otp/verify", "/api/v1/auth/password/reset"
    ghost = unique_email("leakghost")
    s.secret("new password of the reset flow", NEW_PASSWORD)
    try:
        s.req(f"POST {forgot}", "success", "POST", forgot, body={"email": acc.email})
        s.req(f"POST {forgot}", "unknown email", "POST", forgot, body={"email": ghost})
        s.req(f"POST {forgot}", "rate limited", "POST", forgot, body={"email": acc.email})
        s.req(f"POST {forgot}", "malformed", "POST", forgot, body={"email": 5})
        s.req(f"POST {forgot}", "wrong method", "GET", forgot)
        code = extract_code(wait_for_mail(acc.email))
        wrong = "000000" if code != "000000" else "000001"
        s.secret("the real one-time code", code, bounded=True)
        s.secret("a wrong one-time code", wrong, bounded=True)
        s.req(f"POST {verify}", "wrong code", "POST", verify, body={"email": acc.email, "otp": wrong})
        ok = s.req(f"POST {verify}", "success", "POST", verify, body={"email": acc.email, "otp": code})
        ticket = str((ok.json().get("data") or {}).get("reset_ticket", ""))
        s.secret("the reset ticket", ticket, frozenset({VERIFY}))
        s.req(f"POST {verify}", "malformed", "POST", verify, body={"email": acc.email})
        s.req(f"POST {verify}", "wrong method", "GET", verify)
        s.req(f"POST {reset}", "bad ticket", "POST", reset, body={"email": acc.email, "reset_ticket": "x" * 30, "new_password": NEW_PASSWORD})
        s.req(f"POST {reset}", "success", "POST", reset, body={"email": acc.email, "reset_ticket": ticket, "new_password": NEW_PASSWORD})
        s.req(f"POST {reset}", "replay", "POST", reset, body={"email": acc.email, "reset_ticket": ticket, "new_password": NEW_PASSWORD})
        s.req(f"POST {reset}", "wrong method", "GET", reset)
    finally:
        delete_mail_for(acc.email)


def sweep_tenant_rows(s: Sweep, w: World) -> None:
    a, b = w.a, w.b
    for tok in w.a_tokens:
        s.secret("API token of tenant A", str(tok["token"]), TOKEN_ROWS)
        s.secret("beta value of tenant A", str(tok["beta"]), TOKEN_ROWS)
    s.secret("API token of tenant B", w.b_api_token, TOKEN_ROWS)
    row = f"GET {TOKENS}"
    s.req(row, "success", "GET", TOKENS, a.token)
    s.req(row, "as an outsider", "GET", TOKENS, b.token)
    s.errors(row, "GET", TOKENS, "PUT")
    row = f"POST {TOKENS}"
    created = s.req(row, "success", "POST", TOKENS, a.token).json()["data"]
    s.secret("API token created in the sweep", str(created["token"]), TOKEN_ROWS)
    s.secret("beta value created in the sweep", str(created["beta"]), TOKEN_ROWS)
    s.req(row, "with an API token", "POST", TOKENS, w.b_api_token)
    s.errors(row, "POST", TOKENS, "PUT")
    row = f"DELETE {TOKENS}/{{token}}"
    s.req(row, "as an outsider", "DELETE", f"{TOKENS}/{w.a_tokens[1]['token']}", b.token)
    s.req(row, "nonexistent", "DELETE", f"{TOKENS}/ragflow-{uuid.uuid4().hex}", a.token)
    s.req(row, "success", "DELETE", f"{TOKENS}/{w.a_tokens[1]['token']}", a.token)
    s.errors(row, "DELETE", f"{TOKENS}/ragflow-{uuid.uuid4().hex}", "GET")

    users = USERS.format(tenant_id=a.tenant_id)
    row = f"GET {USERS}"
    s.req(row, "success as owner", "GET", users, a.token)
    s.req(row, "success as member", "GET", users, w.normal.token)
    s.req(row, "as an outsider", "GET", users, b.token)
    s.errors(row, "GET", users, "PUT")
    row = f"POST {USERS}"
    s.req(row, "success", "POST", users, a.token, {"email": w.spare.email})
    s.req(row, "already invited", "POST", users, a.token, {"email": w.spare.email})
    s.req(row, "unknown user", "POST", users, a.token, {"email": unique_email("nobody")})
    s.req(row, "invalid email", "POST", users, a.token, {"email": "nope"})
    s.req(row, "as an admin", "POST", users, w.admin.token, {"email": w.spare.email})
    s.req(row, "as an outsider", "POST", users, b.token, {"email": w.spare.email})
    s.errors(row, "POST", users, "PUT")
    row = "PATCH /api/v1/tenants/{tenant_id}"
    one = f"/api/v1/tenants/{a.tenant_id}"
    s.req(row, "invalid action", "PATCH", one, w.spare.token, {"action": "bogus"})
    s.req(row, "success (accept)", "PATCH", one, w.spare.token, {"action": "accept"})
    s.req(row, "repeat", "PATCH", one, w.spare.token, {"action": "accept"})
    s.req(row, "as an outsider", "PATCH", one, b.token, {"action": "accept"})
    s.errors(row, "PATCH", one, "PUT")
    row = "PATCH /api/v1/tenants/{tenant_id}/users/{user_id}"
    role = f"{users}/{w.normal.user_id}"
    s.req(row, "success", "PATCH", role, a.token, {"role": "admin"})
    s.req(row, "refused role", "PATCH", role, a.token, {"role": "owner"})
    s.req(row, "as an outsider", "PATCH", role, b.token, {"role": "admin"})
    s.req(row, "as an admin", "PATCH", f"{users}/{w.victim.user_id}", w.admin.token, {"role": "admin"})
    s.errors(row, "PATCH", role, "PUT")
    row = f"DELETE {USERS}"
    s.req(row, "as an admin", "DELETE", users, w.admin.token, {"user_id": w.victim.user_id})
    s.req(row, "as an outsider", "DELETE", users, b.token, {"user_id": w.victim.user_id})
    s.req(row, "success", "DELETE", users, a.token, {"user_id": w.victim.user_id})
    s.req(row, "repeat", "DELETE", users, a.token, {"user_id": w.victim.user_id})
    s.errors(row, "DELETE", users, "PUT")


def sweep_provider_rows(s: Sweep, w: World) -> None:
    """All six provider rows, each on a success and on an error path (plan 03-12). The sentinel key is sent in request bodies only."""
    assert w.fake is not None
    a, b, member = w.a, w.b, w.normal
    provider_keys = {
        "tenant A's provider key": A_PROVIDER_KEY,
        "tenant B's provider key": B_PROVIDER_KEY,
        "the sentinel provider key": SENTINEL_PROVIDER_KEY,
        "the rotated provider key": ROTATED_PROVIDER_KEY,
    }
    for label, key in provider_keys.items():
        s.secret(label, key, frozenset())  # no row may carry a key, including the PUT answer that received it
    chat = {"name": "leak-chat", "type": "chat"}
    scope = f"?tenant_id={a.tenant_id}"
    save = {"provider": COMPAT, "base_url": w.fake.stack_base_url, "models": [chat]}
    compat = f"{PROVIDERS}/{PROVIDER_SLUG}"

    row = f"GET {PROVIDERS}"
    s.req(row, "success as owner", "GET", PROVIDERS, a.token)
    s.req(row, "success as member", "GET", PROVIDERS + scope, member.token)
    s.req(row, "success with an API token", "GET", PROVIDERS, str(w.a_tokens[0]["token"]))
    s.req(row, "as an outsider", "GET", PROVIDERS + scope, b.token)
    s.errors(row, "GET", PROVIDERS, "DELETE")

    row = f"PUT {PROVIDERS}"
    s.req(row, "success (new key)", "PUT", PROVIDERS, a.token, {**save, "api_key": SENTINEL_PROVIDER_KEY})
    s.req(row, "success (rotation)", "PUT", PROVIDERS, a.token, {**save, "api_key": ROTATED_PROVIDER_KEY})
    s.req(row, "refused by the provider", "PUT", PROVIDERS, a.token, {**save, "api_key": SENTINEL_PROVIDER_KEY, "models": [{"name": "fake-401", "type": "chat"}]})
    s.req(row, "refused address", "PUT", PROVIDERS, a.token, {**save, "api_key": SENTINEL_PROVIDER_KEY, "base_url": "http://169.254.169.254/v1"})
    s.req(row, "unknown field", "PUT", PROVIDERS, a.token, {**save, "api_key": SENTINEL_PROVIDER_KEY, "created_by": a.user_id})
    s.req(row, "as a member", "PUT", PROVIDERS, member.token, {**save, "api_key": SENTINEL_PROVIDER_KEY, "tenant_id": a.tenant_id})
    s.req(row, "as an outsider", "PUT", PROVIDERS, b.token, {**save, "api_key": SENTINEL_PROVIDER_KEY, "tenant_id": a.tenant_id})
    s.req(row, "with an API token", "PUT", PROVIDERS, str(w.a_tokens[0]["token"]), {**save, "api_key": SENTINEL_PROVIDER_KEY})
    s.errors(row, "PUT", PROVIDERS, "PATCH")
    s.req(row, "second provider (Ollama)", "PUT", PROVIDERS, a.token, {"provider": "Ollama", "base_url": w.fake.stack_ollama_url, "models": [chat]})

    row = f"GET {PROVIDERS}/{{provider}}/models"
    s.req(row, "success as owner", "GET", f"{compat}/models", a.token)
    s.req(row, "success as member", "GET", f"{compat}/models{scope}", member.token)
    s.req(row, "unknown provider", "GET", f"{PROVIDERS}/{uuid.uuid4().hex}/models", a.token)
    s.req(row, "as an outsider", "GET", f"{compat}/models{scope}", b.token)
    s.errors(row, "GET", f"{compat}/models", "DELETE")

    row = f"GET {PROVIDERS}/{{provider}}/instances/{{instance}}"
    s.req(row, "success", "GET", f"{compat}/instances/default", a.token)
    s.req(row, "nonexistent instance", "GET", f"{compat}/instances/{uuid.uuid4().hex[:12]}", a.token)
    s.req(row, "as a member", "GET", f"{compat}/instances/default{scope}", member.token)
    s.req(row, "as an outsider", "GET", f"{compat}/instances/default{scope}", b.token)
    s.req(row, "with an API token", "GET", f"{compat}/instances/default", str(w.a_tokens[0]["token"]))
    s.errors(row, "GET", f"{compat}/instances/default", "DELETE")

    row = f"POST {PROVIDERS}/{{provider}}/instances"
    added = {"models": [{"name": "leak-chat-2", "type": "chat"}]}
    s.req(row, "success (models only)", "POST", f"{compat}/instances", a.token, added)
    s.req(row, "duplicate model", "POST", f"{compat}/instances", a.token, added)
    s.req(row, "unconfigured provider", "POST", f"{PROVIDERS}/openai/instances", a.token, added)
    s.req(row, "invalid body", "POST", f"{compat}/instances", a.token, {"models": []})
    s.req(row, "as a member", "POST", f"{compat}/instances", member.token, {**added, "tenant_id": a.tenant_id})
    s.req(row, "as an outsider", "POST", f"{compat}/instances", b.token, {**added, "tenant_id": a.tenant_id})
    s.req(row, "with an API token", "POST", f"{compat}/instances", str(w.a_tokens[0]["token"]), added)
    s.errors(row, "POST", f"{compat}/instances", "GET")

    row = f"DELETE {PROVIDERS}/{{provider}}"
    ollama = f"{PROVIDERS}/ollama"
    s.req(row, "as a member", "DELETE", ollama + scope, member.token)
    s.req(row, "as an outsider", "DELETE", ollama + scope, b.token)
    s.req(row, "with an API token", "DELETE", ollama, str(w.a_tokens[0]["token"]))
    s.req(row, "success", "DELETE", ollama, a.token)
    s.req(row, "repeat", "DELETE", ollama, a.token)
    s.errors(row, "DELETE", ollama, "GET")


def sweep_model_rows(s: Sweep, w: World) -> None:
    """The three model rows, each on a success and on error paths (plan 03-13). Runs after the provider rows, which leave ``leak-chat`` configured."""
    a, b, member = w.a, w.b, w.normal
    token = str(w.a_tokens[0]["token"])
    scope = f"?tenant_id={a.tenant_id}"
    chat_id = f"leak-chat@{COMPAT}"

    row = f"GET {MODELS}"
    s.req(row, "success as owner", "GET", MODELS, a.token)
    s.req(row, "filtered by type", "GET", MODELS + "?type=embedding", a.token)
    s.req(row, "success as member", "GET", MODELS + scope, member.token)
    s.req(row, "success with an API token", "GET", MODELS, token)
    s.req(row, "invalid type", "GET", MODELS + "?type=image", a.token)
    s.req(row, "as an outsider", "GET", MODELS + scope, b.token)
    s.errors(row, "GET", MODELS, "DELETE")

    row = f"GET {MODELS_DEFAULT}"
    s.req(row, "success as owner", "GET", MODELS_DEFAULT, a.token)
    s.req(row, "success as member", "GET", MODELS_DEFAULT + scope, member.token)
    s.req(row, "success with an API token", "GET", MODELS_DEFAULT, token)
    s.req(row, "as an outsider", "GET", MODELS_DEFAULT + scope, b.token)
    s.errors(row, "GET", MODELS_DEFAULT, "DELETE")

    row = f"PATCH {MODELS_DEFAULT}"
    s.req(row, "success (choose)", "PATCH", MODELS_DEFAULT, a.token, {"chat": chat_id})
    s.req(row, "success (clear)", "PATCH", MODELS_DEFAULT, a.token, {"chat": None})
    s.req(row, "unknown model", "PATCH", MODELS_DEFAULT, a.token, {"chat": f"no-such-model@{COMPAT}"})
    s.req(row, "over-long id", "PATCH", MODELS_DEFAULT, a.token, {"embedding": "x" * 129 + f"@{COMPAT}"})
    s.req(row, "empty body", "PATCH", MODELS_DEFAULT, a.token, {})
    s.req(row, "unknown field", "PATCH", MODELS_DEFAULT, a.token, {"chat": None, "created_by": a.user_id})
    s.req(row, "as a member", "PATCH", MODELS_DEFAULT, member.token, {"chat": None, "tenant_id": a.tenant_id})
    s.req(row, "as an outsider", "PATCH", MODELS_DEFAULT, b.token, {"chat": None, "tenant_id": a.tenant_id})
    s.req(row, "with an API token", "PATCH", MODELS_DEFAULT, token, {"chat": None})
    s.errors(row, "PATCH", MODELS_DEFAULT, "PUT")


def sweep_dataset_rows(s: Sweep, w: World) -> None:
    """The three dataset rows, each on a success and on error paths (plan 03-14). A's embedding default exists since the world was built."""
    a, b, member = w.a, w.b, w.normal
    token = str(w.a_tokens[0]["token"])
    scope = f"?tenant_id={a.tenant_id}"
    name = "leak-dataset-" + uuid.uuid4().hex[:8]

    row = f"POST {DATASETS}"
    made = s.req(row, "success (team)", "POST", DATASETS, a.token, {"name": name, "permission": "team", "description": "leak sweep"})
    s.req(row, "success (explicit model)", "POST", DATASETS, a.token, {"name": name + "-b", "embd_id": f"{A_EMBED_MODEL}@{COMPAT}"})
    s.req(row, "duplicate name", "POST", DATASETS, a.token, {"name": name.upper()})
    s.req(row, "unknown embedding model", "POST", DATASETS, a.token, {"name": name + "-c", "embd_id": f"no-such-model@{COMPAT}"})
    s.req(row, "over-long model id", "POST", DATASETS, a.token, {"name": name + "-d", "embd_id": "x" * 129 + f"@{COMPAT}"})
    s.req(row, "invalid name", "POST", DATASETS, a.token, {"name": ""})
    s.req(row, "invalid parser", "POST", DATASETS, a.token, {"name": name + "-e", "parser_id": "bogus"})
    s.req(row, "unknown field", "POST", DATASETS, a.token, {"name": name + "-f", "created_by": a.user_id})
    s.req(row, "no default embedding", "POST", DATASETS, b.token, {"name": name + "-g"})
    s.req(row, "as an outsider", "POST", DATASETS, b.token, {"name": name + "-h", "tenant_id": a.tenant_id})
    s.req(row, "with an API token", "POST", DATASETS, token, {"name": name + "-i"})
    s.errors(row, "POST", DATASETS, "PATCH")
    dataset_id = str((made.json().get("data") or {}).get("id", ""))

    row = f"GET {DATASETS}"
    s.req(row, "success as owner", "GET", DATASETS, a.token)
    s.req(row, "success with keywords and paging", "GET", DATASETS + "?keywords=leak&page=1&page_size=2", a.token)
    s.req(row, "success as member", "GET", DATASETS + scope, member.token)
    s.req(row, "success with an API token", "GET", DATASETS, token)
    s.req(row, "invalid page size", "GET", DATASETS + "?page_size=101", a.token)
    s.req(row, "as an outsider", "GET", DATASETS + scope, b.token)
    s.errors(row, "GET", DATASETS, "PATCH")

    row = f"GET {DATASETS}/{{dataset_id}}"
    detail = f"{DATASETS}/{dataset_id}"
    s.req(row, "success as owner", "GET", detail, a.token)
    s.req(row, "success as member (team)", "GET", detail, member.token)
    s.req(row, "success with an API token", "GET", detail, token)
    s.req(row, "private dataset as a member", "GET", f"{DATASETS}/{w.a_private_dataset['id']}", member.token)
    s.req(row, "absent id", "GET", f"{DATASETS}/{uuid.uuid4().hex}", a.token)
    s.req(row, "malformed id", "GET", f"{DATASETS}/not-an-id", a.token)
    s.req(row, "as an outsider", "GET", detail, b.token)
    s.errors(row, "GET", detail, "PATCH")


def sweep_upload_rows(s: Sweep, w: World) -> None:
    """``POST /api/v1/documents/upload`` on success and error paths (plan 03-16). Uploads land in A's team dataset; the registry removes them with A's workspace."""
    a, b, member = w.a, w.b, w.normal
    token = str(w.a_tokens[0]["token"])
    row = f"POST {UPLOAD}"
    team = f"{UPLOAD}?dataset_id={w.a_team_dataset['id']}"
    private = f"{UPLOAD}?dataset_id={w.a_private_dataset['id']}"

    def pdf(name: str) -> list[tuple[str, tuple[str, bytes, str]]]:
        return [("file", (name, pdf_bytes("leak"), "application/pdf"))]

    s.req(row, "success as owner", "POST", team, a.token, files=pdf("leak-one.pdf"))
    s.req(row, "success as member (team)", "POST", team, member.token, files=pdf("leak-two.pdf"))
    s.req(row, "success with an API token", "POST", team, token, files=pdf("leak-three.pdf"))
    s.req(row, "success with a parser override", "POST", team + "&parser_id=book", a.token, files=pdf("leak-four.pdf"))
    s.req(row, "bad extension", "POST", team, a.token, files=[("file", ("leak.exe", b"MZ\x90\x00", "application/octet-stream"))])
    s.req(row, "wrong magic bytes", "POST", team, a.token, files=[("file", ("leak.pdf", b"not a pdf", "application/pdf"))])
    s.req(row, "traversal name", "POST", team, a.token, files=pdf("../../etc/passwd.pdf"))
    s.req(row, "invalid parser", "POST", team + "&parser_id=bogus", a.token, files=pdf("leak-five.pdf"))
    s.req(row, "no files", "POST", team, a.token, content=b"{}", content_type="application/json")
    s.req(row, "private dataset as a member", "POST", private, member.token, files=pdf("leak-six.pdf"))
    s.req(row, "absent dataset", "POST", f"{UPLOAD}?dataset_id={uuid.uuid4().hex}", a.token, files=pdf("leak-seven.pdf"))
    s.req(row, "malformed dataset id", "POST", f"{UPLOAD}?dataset_id=not-an-id", a.token, files=pdf("leak-eight.pdf"))
    s.req(row, "no dataset id", "POST", UPLOAD, a.token, files=pdf("leak-nine.pdf"))
    s.req(row, "as an outsider", "POST", team, b.token, files=pdf("leak-ten.pdf"))
    s.errors(row, "POST", team, "PATCH")


def sweep_document_rows(s: Sweep, w: World) -> None:
    """``GET`` and ``DELETE`` on ``/api/v1/datasets/{dataset_id}/documents``, each on success and error paths (plan 03-17).

    Documents to delete are uploaded through the real route first (their responses are scanned under the upload row). The registry removes whatever is left
    with A's workspace.
    """
    a, b, member = w.a, w.b, w.normal
    token = str(w.a_tokens[0]["token"])
    team = f"{DATASETS}/{w.a_team_dataset['id']}/documents"
    private = f"{DATASETS}/{w.a_private_dataset['id']}/documents"
    upload_row = f"POST {UPLOAD}"

    def uploaded(who_token: str, name: str) -> str:
        files = [("file", (name, pdf_bytes("leak-doc"), "application/pdf"))]
        resp = s.req(upload_row, "document for the delete sweep", "POST", f"{UPLOAD}?dataset_id={w.a_team_dataset['id']}", who_token, files=files)
        return str(resp.json()["data"][0]["id"])

    row = f"GET {DATASETS}/{{dataset_id}}/documents"
    s.req(row, "success as owner", "GET", team, a.token)
    s.req(row, "success with keywords and paging", "GET", team + "?keywords=matrix&page=1&page_size=1", a.token)
    s.req(row, "success as member (team)", "GET", team, member.token)
    s.req(row, "success with an API token", "GET", team, token)
    s.req(row, "own private dataset", "GET", private, a.token)
    s.req(row, "invalid page size", "GET", team + "?page_size=101", a.token)
    s.req(row, "invalid page", "GET", team + "?page=0", a.token)
    s.req(row, "private dataset as a member", "GET", private, member.token)
    s.req(row, "absent dataset", "GET", f"{DATASETS}/{uuid.uuid4().hex}/documents", a.token)
    s.req(row, "malformed dataset id", "GET", f"{DATASETS}/not-an-id/documents", a.token)
    s.req(row, "as an outsider", "GET", team, b.token)
    s.errors(row, "GET", team, "PATCH")

    row = f"DELETE {DATASETS}/{{dataset_id}}/documents"
    first, second = uploaded(a.token, "leak-del-one.pdf"), uploaded(a.token, "leak-del-two.pdf")
    s.req(row, "success as owner", "DELETE", team, a.token, {"ids": [first]})
    s.req(row, "repeated delete", "DELETE", team, a.token, {"ids": [first]})
    s.req(row, "success as the uploading member", "DELETE", team, member.token, {"ids": [uploaded(member.token, "leak-del-member.pdf")]})
    s.req(row, "another member's document", "DELETE", team, member.token, {"ids": [second]})
    s.req(row, "success with an API token", "DELETE", team, token, {"ids": [uploaded(token, "leak-del-token.pdf")]})
    s.req(row, "ids that are not ids", "DELETE", team, a.token, {"ids": ["not-hex"]})
    s.req(row, "empty ids", "DELETE", team, a.token, {"ids": []})
    s.req(row, "unknown field", "DELETE", team, a.token, {"ids": [second], "tenant_id": a.tenant_id})
    s.req(row, "unknown document", "DELETE", team, a.token, {"ids": [uuid.uuid4().hex]})
    s.req(row, "private dataset as a member", "DELETE", private, member.token, {"ids": [str(w.a_private_documents[0]["id"])]})
    s.req(row, "absent dataset", "DELETE", f"{DATASETS}/{uuid.uuid4().hex}/documents", a.token, {"ids": [second]})
    s.req(row, "malformed dataset id", "DELETE", f"{DATASETS}/not-an-id/documents", a.token, {"ids": [second]})
    s.req(row, "as an outsider", "DELETE", team, b.token, {"ids": [second]})
    s.errors(row, "DELETE", team, "PATCH")


def sweep_dataset_write_rows(s: Sweep, w: World) -> None:
    """``PUT /api/v1/datasets/{dataset_id}`` and ``DELETE /api/v1/datasets`` on success and error paths (plan 03-18).

    The datasets they change are made here through the real create route (scanned under the create row), so the world's own datasets stay for the checks that
    run after the sweep. Deleting runs last for the same reason.
    """
    a, b, member = w.a, w.b, w.normal
    token = str(w.a_tokens[0]["token"])
    create_row = f"POST {DATASETS}"
    suffix = uuid.uuid4().hex[:8]

    def make(label: str, **extra: Any) -> str:
        resp = s.req(create_row, f"dataset for the {label} sweep", "POST", DATASETS, a.token, {"name": f"leak-w-{label}-{suffix}", "permission": "team", **extra})
        return str(resp.json()["data"]["id"])

    first, second, third, fourth, fifth = make("first"), make("second"), make("third"), make("fourth"), make("fifth")

    row = f"PUT {DATASETS}/{{dataset_id}}"
    path = f"{DATASETS}/{first}"
    s.req(row, "success (description and permission)", "PUT", path, a.token, {"description": "leak sweep", "permission": "team"})
    s.req(row, "success (rename)", "PUT", path, a.token, {"name": f"leak-w-renamed-{suffix}"})
    s.req(row, "success (same embedding model)", "PUT", path, a.token, {"embd_id": f"{A_EMBED_MODEL}@{COMPAT}"})
    s.req(row, "success (parser configuration)", "PUT", path, a.token, {"parser_config": {"chunk_token_num": 256}})
    s.req(row, "success with an API token", "PUT", path, token, {"description": "by token"})
    s.req(row, "duplicate name", "PUT", path, a.token, {"name": f"leak-w-second-{suffix}".upper()})
    s.req(row, "unknown embedding model", "PUT", path, a.token, {"embd_id": f"no-such-model@{COMPAT}"})
    s.req(row, "chat model as embedding model", "PUT", path, a.token, {"embd_id": f"{A_CHAT_MODEL}@{COMPAT}"})
    s.req(row, "invalid parser", "PUT", path, a.token, {"parser_id": "bogus"})
    s.req(row, "null name", "PUT", path, a.token, {"name": None})
    s.req(row, "no changes", "PUT", path, a.token, {})
    s.req(row, "unknown field", "PUT", path, a.token, {"description": "x", "created_by": a.user_id})
    s.req(row, "plain member of a team dataset", "PUT", path, member.token, {"description": "member"})
    s.req(row, "private dataset as a member", "PUT", f"{DATASETS}/{w.a_private_dataset['id']}", member.token, {"description": "member"})
    s.req(row, "absent id", "PUT", f"{DATASETS}/{uuid.uuid4().hex}", a.token, {"description": "x"})
    s.req(row, "malformed id", "PUT", f"{DATASETS}/not-an-id", a.token, {"description": "x"})
    s.req(row, "as an outsider", "PUT", path, b.token, {"description": "outsider"})
    s.errors(row, "PUT", path, "PATCH")

    row = f"DELETE {DATASETS}"
    s.req(row, "success as owner", "DELETE", DATASETS, a.token, {"ids": [third]})
    s.req(row, "repeated delete", "DELETE", DATASETS, a.token, {"ids": [third]})
    s.req(row, "success with an API token", "DELETE", DATASETS, token, {"ids": [fourth], "tenant_id": a.tenant_id})
    s.req(row, "plain member of a team dataset", "DELETE", DATASETS, member.token, {"ids": [first], "tenant_id": a.tenant_id})
    s.req(row, "private dataset as a member", "DELETE", DATASETS, member.token, {"ids": [str(w.a_private_dataset["id"])], "tenant_id": a.tenant_id})
    s.req(row, "ids that are not ids", "DELETE", DATASETS, a.token, {"ids": ["not-hex"]})
    s.req(row, "empty ids", "DELETE", DATASETS, a.token, {"ids": []})
    s.req(row, "unknown field", "DELETE", DATASETS, a.token, {"ids": [first], "created_by": a.user_id})
    s.req(row, "unknown dataset", "DELETE", DATASETS, a.token, {"ids": [uuid.uuid4().hex]})
    s.req(row, "one unknown id with a real one", "DELETE", DATASETS, a.token, {"ids": [first, uuid.uuid4().hex]})
    s.req(row, "as an outsider", "DELETE", DATASETS, b.token, {"ids": [first]})
    s.req(row, "as an outsider naming the workspace", "DELETE", DATASETS, b.token, {"ids": [first], "tenant_id": a.tenant_id})
    s.errors(row, "DELETE", DATASETS, "PATCH")
    s.req(row, "success with several ids", "DELETE", DATASETS, a.token, {"ids": [first, second, fifth], "tenant_id": a.tenant_id})


def collect_database_secrets(s: Sweep) -> None:
    """Hashes and stored access tokens of every account the sweep touched, read back from MySQL."""
    ids = [acc.user_id for acc in s.registry.created]
    if not ids:
        return
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            for acc in s.registry.created:  # sealed provider keys: the envelope must never be shown either
                cur.execute("SELECT DISTINCT `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s AND `api_key` LIKE 'v1:%%'", (acc.tenant_id,))
                for (envelope,) in cur.fetchall():
                    s.secret("a sealed provider key envelope", str(envelope), frozenset())
            for user_id in ids:
                cur.execute("SELECT `password`, `access_token` FROM `user` WHERE `id` = %s", (user_id,))
                for password_hash, access_token in cur.fetchall():
                    s.secret("a stored password hash", str(password_hash or ""))
                    s.secret("a stored access token", str(access_token or ""), frozenset({LOGIN}))
    finally:
        conn.close()


def infrastructure_secrets() -> list[Secret]:
    out: list[Secret] = []
    for key, value in stack_env().items():
        if any(word in key.upper() for word in ("PASSWORD", "SECRET", "_KEY")) and len(value) >= 6:
            out.append(Secret(f"stack setting {key}", value))
    return out


@pytest.fixture(scope="module")
def sweep(ingress: httpx.Client) -> Iterator[Sweep]:
    registry = AccountRegistry(BASE_URL)
    with running_stack_fake_provider() as fake, httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=False) as client:
        s = Sweep(client, registry)
        try:
            s.secret("the shared test password", TEST_PASSWORD)
            sweep_public_rows(s)
            main = s.account("leakmain")
            sweep_session_rows(s, main)
            sweep_account_rows(s)
            sweep_password_reset_rows(s)
            world = build_world(client, registry, fake)
            for acc in (world.a, world.b, world.pending, world.admin, world.normal, world.victim, world.spare):
                s.secret("a session token of the tenant world", acc.token, frozenset({LOGIN}))
            sweep_tenant_rows(s, world)
            sweep_provider_rows(s, world)
            sweep_model_rows(s, world)
            sweep_dataset_rows(s, world)
            sweep_upload_rows(s, world)
            sweep_document_rows(s, world)
            sweep_dataset_write_rows(s, world)
            collect_database_secrets(s)
            s.secrets.extend(infrastructure_secrets())
            yield s
        finally:
            registry.cleanup()


# --- the sweep ----------------------------------------------------------------------------------------------------


@pytest.mark.e2e
def test_every_implemented_row_is_exercised_on_a_success_and_an_error_path(sweep: Sweep) -> None:
    rows = implemented_rows()
    seen: dict[str, list[int]] = {}
    for row, _label, resp in sweep.responses:
        seen.setdefault(row, []).append(resp.status_code)
    missing = [r for r in rows if r not in seen]
    assert not missing, f"registry rows the leak sweep never called: {missing}; add them to the exercisers in test/testcases/test_response_leaks.py"
    unknown = [r for r in seen if r not in rows]
    assert not unknown, f"sweep rows that are not implemented registry rows: {unknown}"
    no_success = [r for r in rows if not any(200 <= c < 300 for c in seen[r])]
    no_error = [r for r in rows if not any(c >= 400 for c in seen[r])]
    assert not no_success, f"rows without a success response: {no_success}"
    assert not no_error, f"rows without an error response: {no_error}"
    assert len(sweep.responses) >= 2 * len(rows)


@pytest.mark.e2e
def test_no_response_leaks_a_credential_a_hash_or_an_internal_column(sweep: Sweep) -> None:
    findings: list[str] = []
    for row, label, resp in sweep.responses:
        findings += scan_response(row, label, dict(resp.headers), resp.text, sweep.secrets)
    assert not findings, "\n".join(findings)
    assert len(sweep.secrets) >= 20, "the sweep should have collected the run's secrets, hashes and stored tokens"


@pytest.mark.e2e
def test_the_login_token_is_returned_only_by_login(sweep: Sweep) -> None:
    holders = {row for row, _l, resp in sweep.responses if resp.status_code < 300 and '"token"' in resp.text.replace(" ", "")}
    assert holders <= CREDENTIAL_ROWS, f"a token field appears in {holders - CREDENTIAL_ROWS}"
    assert LOGIN in holders


# --- the scanner itself has teeth ---------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "body", "needle"),
    [
        ("GET /v1/user/info", {"data": {"password": "x"}}, "forbidden field"),
        ("GET /v1/user/info", {"data": {"nested": [{"Access_Token": "x"}]}}, "forbidden field"),
        ("GET /v1/user/info", {"data": {"note": "pbkdf2:sha256:600000$salt$hash"}}, "password hash"),
        ("GET /v1/user/info", {"data": {"token": "x"}}, "credential field"),
        ("POST /api/v1/auth/password/forgot/otp", {"data": {"reset_ticket": "x"}}, "forbidden field"),
        ("GET /v1/tenant/list", {"data": [{"status": "1"}]}, "forbidden field"),
    ],
)
def test_scanner_flags_planted_leaks(row: str, body: dict[str, Any], needle: str) -> None:
    findings = scan_response(row, "planted", {}, json.dumps(body), [])
    assert findings and needle in findings[0]


@pytest.mark.unit
def test_scanner_flags_secret_values_by_value_and_never_prints_them() -> None:
    secret = Secret("a planted password", "planted-secret-value-123")
    findings = scan_response("GET /v1/user/info", "planted", {"X-Echo": "planted-secret-value-123"}, json.dumps({"data": {"harmless": "planted-secret-value-123"}}), [secret])
    assert len(findings) == 1 and "a planted password" in findings[0]
    assert "planted-secret-value-123" not in findings[0]
    allowed = Secret("a token", "planted-secret-value-123", frozenset({LOGIN}))
    assert scan_response(LOGIN, "login", {}, json.dumps({"data": {"token": "planted-secret-value-123"}}), [allowed]) == []
    bounded = Secret("an otp", "123456", bounded=True)
    assert scan_response("GET /health", "x", {}, json.dumps({"id": "a123456b", "n": 1234567}), [bounded]) == []
    assert len(scan_response("GET /health", "x", {}, json.dumps({"n": "code 123456."}), [bounded])) == 1


@pytest.mark.unit
def test_scanner_accepts_the_documented_fields() -> None:
    assert scan_response(VERIFY, "ok", {}, json.dumps({"data": {"reset_ticket": "t"}}), []) == []
    assert scan_response(LOGIN, "ok", {"set-cookie": "ragflow_auth=abc"}, json.dumps({"data": {"token": "t", "user": {"id": "1"}}}), [Secret("s", "abc", frozenset())]) == []
    assert scan_response("GET /api/v1/system/tokens", "ok", {}, json.dumps({"data": [{"token": "t", "beta": "b", "create_time": 1}]}), []) == []
