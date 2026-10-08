"""Bounded executors and the shared handler plumbing (plan 03-12, D-26, TEN-13)."""
from __future__ import annotations

import threading

import pytest
from quart import Quart, g

from api.apps import handler_support
from api.apps.handler_support import acting_scope, credentials_visible, forbid_unless
from api.db.services.auth_service import Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from api.utils import blocking
from api.utils.blocking import DB_EXECUTOR, DOCSTORE_EXECUTOR, PROVIDER_EXECUTOR, STORAGE_EXECUTOR, run_blocking

pytestmark = pytest.mark.unit

OWN = "a" * 32
OTHER = "b" * 32


def _principal(auth_type: str = "jwt", role: str = "owner") -> Principal:
    return Principal(user_id="u" * 32, tenant_id=OWN, role=role, auth_type=auth_type, is_superuser=False)


# --- executors ---------------------------------------------------------------------------------------------------


def test_four_named_bounded_executors_exist() -> None:
    expected = {DB_EXECUTOR: ("db", 16), PROVIDER_EXECUTOR: ("provider", 8), DOCSTORE_EXECUTOR: ("docstore", 8), STORAGE_EXECUTOR: ("storage", 8)}
    for executor, (prefix, workers) in expected.items():
        assert executor._thread_name_prefix.startswith(prefix)  # noqa: SLF001
        assert executor._max_workers == workers  # noqa: SLF001
    assert len({id(e) for e in expected}) == 4


async def test_run_blocking_returns_the_value_and_runs_off_the_loop() -> None:
    names: list[str] = []

    def work(a: int, b: int) -> int:
        names.append(threading.current_thread().name)
        return a + b

    assert await run_blocking(PROVIDER_EXECUTOR, work, 2, 3, timeout=5) == 5
    assert names and names[0].startswith("provider") and names[0] != threading.current_thread().name


async def test_run_blocking_propagates_the_worker_exception_unchanged() -> None:
    error = ServiceError(Kind.CONFLICT, "model_exists", "already there")

    def work() -> None:
        raise error

    with pytest.raises(ServiceError) as caught:
        await run_blocking(DB_EXECUTOR, work, timeout=5)
    assert caught.value is error


@pytest.mark.parametrize(
    ("executor", "reason", "kind"),
    [(PROVIDER_EXECUTOR, "provider_timeout", Kind.TIMEOUT), (DB_EXECUTOR, "operation_timeout", Kind.TIMEOUT), (STORAGE_EXECUTOR, "operation_timeout", Kind.TIMEOUT)],
)
async def test_a_timeout_becomes_a_typed_service_error(executor, reason: str, kind: Kind) -> None:  # type: ignore[no-untyped-def]
    release = threading.Event()
    try:
        with pytest.raises(ServiceError) as caught:
            await run_blocking(executor, release.wait, 30, timeout=0.05)
    finally:
        release.set()  # a timed-out worker cannot be cancelled: let it finish
    assert (caught.value.kind, caught.value.reason) == (kind, reason)


def test_blocking_module_documents_why_the_default_executor_is_not_used() -> None:
    text = (blocking.__doc__ or "") + open(blocking.__file__, encoding="utf-8").read()
    assert "default executor" in text and "cannot be cancelled" in text


# --- credentials_visible ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "subject", "visible"),
    [
        ("owner", "owner", True),
        ("admin", "admin", True),
        ("normal", "normal", False),
        ("owner", "api_token", False),  # an API token inherits the owner's role; its subject decides (D-26)
        ("owner", "beta_token", False),
        ("invite", "invite", False),
    ],
)
def test_credentials_are_visible_only_to_the_owner_and_admin_subjects(role: str, subject: str, visible: bool) -> None:
    assert credentials_visible(ActingScope(OWN, role, subject)) is visible


# --- forbid_unless ------------------------------------------------------------------------------------------------


async def test_forbid_unless_passes_an_allowed_subject_and_refuses_the_rest_with_403() -> None:
    assert forbid_unless(ActingScope(OWN, "owner", "owner"), "tenant_settings", "update_llm_keys") is None
    assert forbid_unless(ActingScope(OWN, "admin", "admin"), "tenant_settings", "update_llm_keys") is None
    for subject in ("normal", "api_token", "beta_token", "invite"):
        denied = forbid_unless(ActingScope(OWN, "owner", subject), "tenant_settings", "update_llm_keys")
        assert denied is not None and denied.status_code == 403
    listing = forbid_unless(ActingScope(OWN, "normal", "normal"), "tenant_settings", "view_models")
    assert listing is None
    assert forbid_unless(ActingScope(OWN, "owner", "owner"), "tenant_settings", "no_such_action") is not None


# --- acting_scope: the parts that need no database ------------------------------------------------------------------


async def _scope(principal: Principal, requested: str | None) -> ActingScope | None:
    app = Quart(__name__)
    async with app.test_request_context("/"):
        g.principal = principal
        return await acting_scope(requested)


async def test_no_request_and_the_own_id_resolve_to_the_own_workspace() -> None:
    expected = ActingScope(OWN, "owner", "owner")
    assert await _scope(_principal(), None) == expected
    assert await _scope(_principal(), OWN) == expected
    assert await _scope(_principal("api"), None) == ActingScope(OWN, "owner", "api_token")


@pytest.mark.parametrize("bad", ["", "zz" * 16, OTHER.upper(), OTHER[:-1], OTHER + "0", "../" + OTHER[:29], " " + OTHER[:31], OTHER + "\n"])
async def test_a_malformed_workspace_id_is_not_found_without_a_lookup(bad: str) -> None:
    assert await _scope(_principal(), bad) is None


async def test_a_token_cannot_act_in_another_workspace() -> None:
    assert await _scope(_principal("api"), OTHER) is None
    assert await _scope(_principal("beta"), OTHER) is None


def test_handler_support_does_not_import_a_model_or_peewee() -> None:
    text = open(handler_support.__file__, encoding="utf-8").read()
    for forbidden in ("api.db.models", "api.db.database", "import peewee"):
        assert forbidden not in text
