"""The env catalog covers the documented variables and secrets are fail-fast (DEPLOY-11, SEC-04)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docker" / ".env.example"
BASE = ROOT / "docker" / "docker-compose-base.yml"
DOC = ROOT / "docs" / "18-deployment" / "environment-variables.md"


def parse_env(path: Path) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    secrets: set[str] = set()
    marker = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "# secret":
            marker = True
            continue
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
            if marker:
                secrets.add(key)
        if line:
            marker = False
    return values, secrets


def test_every_documented_variable_is_in_the_example() -> None:
    if not DOC.is_file():
        pytest.skip("docs/ is untracked and absent in this checkout")
    documented = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", DOC.read_text(encoding="utf-8"), flags=re.M))
    assert len(documented) > 20
    values, _ = parse_env(EXAMPLE)
    missing = sorted(documented - set(values))
    assert not missing, f"documented variables missing from docker/.env.example: {missing}"


def test_secrets_are_empty_in_the_example() -> None:
    values, secrets = parse_env(EXAMPLE)
    required = {"MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "REDIS_PASSWORD", "MINIO_PASSWORD", "ELASTIC_PASSWORD"}
    assert required <= secrets
    for key in secrets:
        assert values[key] == "", f"{key} must be empty in the example"


def compose_config(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(BASE), "--profile", "elasticsearch", "config", "-q"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def test_compose_fails_fast_when_a_secret_is_unset() -> None:
    result = compose_config(EXAMPLE)
    assert result.returncode != 0
    assert re.search(r"(MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|REDIS_PASSWORD|MINIO_PASSWORD|ELASTIC_PASSWORD) is unset", result.stderr)


def test_compose_accepts_supplied_secrets(tmp_path: Path) -> None:
    lines = []
    values, secrets = parse_env(EXAMPLE)
    for key, value in values.items():
        lines.append(f"{key}={'dummy-value' if key in secrets else value}")
    env_file = tmp_path / "test.env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = compose_config(env_file)
    assert result.returncode == 0, result.stderr
