"""First-superuser startup hook: validation, no-op rules and log hygiene (D-03, D-02, D-29, T-02-87/88)."""
from __future__ import annotations

import dataclasses
import logging

import pytest

from api.db.services import superuser_service
from common.bootstrap import ensure_superuser
from common.settings import AuthSettings, parse_settings

pytestmark = pytest.mark.unit

FAKE_EMAIL = "Root-Admin@Example.TEST"
FAKE_SECRET = "fake-unit-seed-0001"  # obviously fake; test files are exempt from the secret scan


def _settings(email: str, secret: str):
    base = parse_settings(
        {
            "ragflow": {"host": "h", "http_port": 1},
            "mysql": {"name": "n", "user": "u", "password": "p", "host": "h", "port": 3306, "max_connections": 1, "stale_timeout": 1},
            "redis": {"host": "h", "port": 1, "password": "p"},
            "minio": {"user": "u", "password": "p", "host": "h", "port": 1},
            "es": {"hosts": "http://h:1", "username": "u", "password": "p"},
            "security": {"secret_key": "unit-test-secret-key-0123456789abcdef0123456789"},
        }
    )
    return dataclasses.replace(base, auth=AuthSettings(superuser_email=email, superuser_password=secret))


@pytest.fixture
def seed_calls(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake(email: str, password: str) -> bool:
        calls.append((email, password))
        return True

    monkeypatch.setattr(superuser_service, "ensure_superuser", fake)
    return calls


@pytest.mark.parametrize(("email", "secret"), [("", ""), (FAKE_EMAIL, ""), ("", FAKE_SECRET), ("   ", FAKE_SECRET)])
async def test_ensure_superuser_is_a_noop_unless_both_values_are_set(seed_calls, email, secret):
    assert await ensure_superuser.run(_settings(email, secret)) is False
    assert seed_calls == []


async def test_ensure_superuser_calls_the_service_with_both_values(seed_calls):
    assert await ensure_superuser.run(_settings(FAKE_EMAIL, FAKE_SECRET)) is True
    assert seed_calls == [(FAKE_EMAIL, FAKE_SECRET)]


@pytest.mark.parametrize("secret", ["short", "1234567", "x" * 129])
def test_ensure_superuser_rejects_password_length_without_echoing_it(secret):
    with pytest.raises(superuser_service.SuperuserConfigError) as err:
        superuser_service.validate_credentials(FAKE_EMAIL, secret)
    assert "SUPERUSER_PASSWORD" in str(err.value)
    assert secret not in str(err.value) and secret not in repr(err.value)


@pytest.mark.parametrize("secret", ["x" * 8, "x" * 128, "pässwörd-ünïcode-ok"])
def test_ensure_superuser_accepts_the_documented_length_range(secret):
    email, _ = superuser_service.validate_credentials(FAKE_EMAIL, secret)
    assert email == "root-admin@example.test"


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "a@@example.test", "@example.test", "a b@example.test", "x" * 250 + "@example.test"])
def test_ensure_superuser_rejects_a_malformed_email_naming_the_setting(email):
    with pytest.raises(superuser_service.SuperuserConfigError) as err:
        superuser_service.validate_credentials(email, FAKE_SECRET)
    assert "SUPERUSER_EMAIL" in str(err.value)
    assert FAKE_SECRET not in str(err.value)


def test_ensure_superuser_normalises_the_email_like_registration():
    assert superuser_service.normalise_email("  Root-Admin@Example.TEST ") == "root-admin@example.test"


async def test_ensure_superuser_bad_password_aborts_before_the_service_runs(seed_calls, caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(superuser_service.SuperuserConfigError):
        await ensure_superuser.run(_settings(FAKE_EMAIL, "tiny"))
    assert seed_calls == []
    assert "tiny" not in caplog.text


async def test_ensure_superuser_never_logs_the_password(seed_calls, caplog):
    caplog.set_level(logging.DEBUG)
    await ensure_superuser.run(_settings(FAKE_EMAIL, FAKE_SECRET))
    assert FAKE_SECRET not in caplog.text
    assert all(FAKE_SECRET not in str(getattr(r, "args", "")) for r in caplog.records)


def test_ensure_superuser_settings_repr_masks_the_password():
    assert FAKE_SECRET not in repr(_settings(FAKE_EMAIL, FAKE_SECRET).auth)


def test_ensure_superuser_hook_is_registered_by_boot(monkeypatch):
    import api.ragflow_server as server

    registry: list = []
    monkeypatch.setattr(server, "_HOOKS", registry)
    server.register_startup_hook("ensure_superuser", lambda: None)
    server.register_startup_hook("ensure_superuser", lambda: None)
    assert [name for name, _ in registry].count("ensure_superuser") == 1
    assert hasattr(server, "install_superuser_hook")
