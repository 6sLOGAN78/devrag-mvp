"""Production rate-limit defaults equal the R-94 numbers; only the dev overlay raises per-IP values (D-29, T-02-16A)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker" / "docker-compose.yml"
DEV = ROOT / "docker" / "docker-compose.dev.yml"
EXAMPLE = ROOT / "docker" / ".env.example"

R94 = {
    "RATE_LIMIT_REGISTER_PER_IP": "10",
    "RATE_LIMIT_REGISTER_WINDOW_SECONDS": "3600",
    "RATE_LIMIT_LOGIN_FAILURES_PER_EMAIL": "5",
    "RATE_LIMIT_LOGIN_PER_IP": "30",
    "RATE_LIMIT_LOGIN_WINDOW_SECONDS": "900",
    "RATE_LIMIT_OTP_EMAIL_INTERVAL_SECONDS": "60",
    "RATE_LIMIT_OTP_PER_EMAIL_PER_HOUR": "5",
    "RATE_LIMIT_OTP_PER_IP_PER_HOUR": "20",
    "RATE_LIMIT_OTP_WINDOW_SECONDS": "3600",
}
# Phase 3 (03-01): provider key test limits sit beside the R-94 numbers in the example file.
PROVIDER_TEST = {"RATE_LIMIT_PROVIDER_TEST_PER_TENANT": "10", "RATE_LIMIT_PROVIDER_TEST_WINDOW_SECONDS": "300"}
PER_IP = {"RATE_LIMIT_REGISTER_PER_IP", "RATE_LIMIT_LOGIN_PER_IP", "RATE_LIMIT_OTP_PER_IP_PER_HOUR"}


def _app_env() -> dict[str, str]:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return {k: str(v) for k, v in doc["x-app-env"].items()}


def test_production_compose_defaults_equal_r94() -> None:
    env = _app_env()
    for key, number in R94.items():
        assert key in env, key
        match = re.fullmatch(r"\$\{" + key + r":-(\d+)\}", env[key])
        assert match, f"{key} must be '${{{key}:-<number>}}', got {env[key]!r}"
        assert match.group(1) == number, key


def test_env_example_defaults_equal_r94() -> None:
    values = dict(line.split("=", 1) for line in EXAMPLE.read_text(encoding="utf-8").splitlines() if re.match(r"^RATE_LIMIT_\w+=", line))
    assert values == {**R94, **PROVIDER_TEST}


def test_dev_overlay_raises_only_the_three_per_ip_keys() -> None:
    doc = yaml.safe_load(DEV.read_text(encoding="utf-8"))
    env = doc["services"]["app"]["environment"]
    rate_keys = {k for k in env if k.startswith("RATE_LIMIT_")}
    assert rate_keys == PER_IP
    for key in PER_IP:
        assert env[key] == "${DEV_RATE_LIMIT_PER_IP_MAX:-100000}"


def test_dev_overlay_values_do_not_appear_in_production_compose() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "DEV_RATE_LIMIT_PER_IP_MAX" not in text
    assert "100000" not in text
