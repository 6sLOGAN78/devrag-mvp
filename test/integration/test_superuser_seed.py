"""First-superuser seed against real MySQL on a scratch database (D-03, D-24, T-02-87..91, AUTH-02)."""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.db.database import DB, init_database
from api.db.migrations.runner import run_migrations
from api.db.models import Tenant, User, UserTenant
from api.db.services import superuser_service
from api.db.services.superuser_service import SuperuserConfigError, SuperuserSeedError, ensure_superuser
from api.ragflow_server import boot
from common.security.passwords import hash_password, verify_password
from common.settings import AuthSettings, load_settings
from test.helpers.db import app_connection_settings, scratch_database

pytestmark = pytest.mark.integration

EMAIL = "seed-admin@example.test"
FAKE_SECRET = "fake-seed-pass-0001"  # obviously fake test value


@pytest.fixture
def scratch() -> Iterator[str]:
    with scratch_database() as name:
        database = init_database(app_connection_settings(name))
        try:
            run_migrations()
            yield name
        finally:
            database.close_all()
            DB.initialize(None)


def _seed(email: str = EMAIL, password: str = FAKE_SECRET) -> bool:
    return ensure_superuser(email, password)


def _counts() -> tuple[int, int, int]:
    with DB.connection_context():
        return User.select().count(), Tenant.select().count(), UserTenant.select().count()


def test_superuser_seed_creates_user_tenant_and_owner_row(scratch):
    assert _seed("  Seed-Admin@Example.TEST ") is True
    with DB.connection_context():
        user = User.get(User.email == EMAIL)
        tenant = Tenant.get_by_id(user.id)
        rows = list(UserTenant.select().where(UserTenant.user_id == user.id))
    assert user.is_superuser is True and user.status == "1"
    assert user.password.startswith("pbkdf2:sha256:600000$")
    assert verify_password(FAKE_SECRET, user.password)
    assert tenant.id == user.id and tenant.llm_id == "" and tenant.embd_id == "" and tenant.rerank_id == ""
    assert len(rows) == 1 and rows[0].tenant_id == user.id and rows[0].role == "owner" and rows[0].invited_by == user.id
    assert _counts() == (1, 1, 1)


def test_superuser_seed_is_idempotent_and_keeps_the_stored_hash(scratch):
    assert _seed() is True
    with DB.connection_context():
        before = User.get(User.email == EMAIL).password
    assert _seed(password="another-fake-pass-0002") is False
    with DB.connection_context():
        after = User.get(User.email == EMAIL).password
    assert before == after
    assert _counts() == (1, 1, 1)


def test_superuser_seed_refuses_to_promote_an_existing_normal_account(scratch):
    stored = hash_password("some-normal-pass-0003")
    with DB.connection_context():
        User.create(id="a" * 32, email=EMAIL, nickname="normal", password=stored, is_superuser=False)
    with pytest.raises(SuperuserSeedError) as err:
        _seed()
    assert FAKE_SECRET not in str(err.value)
    with DB.connection_context():
        row = User.get(User.email == EMAIL)
    assert row.is_superuser is False and row.password == stored
    assert _counts() == (1, 0, 0)


def test_superuser_seed_is_all_or_nothing(scratch, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("simulated failure on the third insert")

    monkeypatch.setattr(UserTenant, "create", boom)
    with pytest.raises(RuntimeError):
        _seed()
    assert _counts() == (0, 0, 0)


def test_superuser_seed_two_concurrent_starts_create_one_superuser(scratch):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _i: _seed(), range(4)))
    assert results.count(True) == 1 and results.count(False) == 3
    assert _counts() == (1, 1, 1)


def test_superuser_seed_rejects_bad_input_before_touching_the_database(scratch):
    with pytest.raises(SuperuserConfigError):
        _seed(password="short")
    with pytest.raises(SuperuserConfigError):
        _seed(email="not-an-email")
    assert _counts() == (0, 0, 0)


def test_superuser_seed_never_logs_the_password(scratch, caplog):
    caplog.set_level(logging.DEBUG)
    _seed()
    _seed()
    with pytest.raises(SuperuserConfigError):
        _seed(password=FAKE_SECRET[:5])
    assert FAKE_SECRET not in caplog.text
    assert superuser_service.logger.name in {r.name for r in caplog.records}


async def test_superuser_seed_runs_as_a_boot_hook_only_when_both_values_are_set(scratch):
    base = dataclasses.replace(load_settings(), mysql=app_connection_settings(scratch))

    unset = boot(base, init_logging=False)
    async with unset.test_app():
        pass
    assert _counts() == (0, 0, 0)

    configured = dataclasses.replace(base, auth=AuthSettings(superuser_email=EMAIL, superuser_password=FAKE_SECRET))
    app = boot(configured, init_logging=False)
    async with app.test_app():
        pass
    async with boot(configured, init_logging=False).test_app():
        pass
    assert _counts() == (1, 1, 1)


async def test_superuser_boot_fails_for_a_bad_password_without_leaking_it(scratch, caplog):
    caplog.set_level(logging.DEBUG)
    bad = "tiny-pw"
    settings = dataclasses.replace(
        load_settings(), mysql=app_connection_settings(scratch), auth=AuthSettings(superuser_email=EMAIL, superuser_password=bad)
    )
    app = boot(settings, init_logging=False)
    with pytest.raises(Exception) as err:  # noqa: PT011 - quart wraps the hook error in a lifespan error
        async with app.test_app():
            pass
    assert "SUPERUSER_PASSWORD" in str(err.value) or "SUPERUSER_PASSWORD" in repr(err.value.__cause__)
    assert bad not in str(err.value) and bad not in caplog.text
    assert _counts() == (0, 0, 0)
