"""Ownership resolution and drift behaviour of the generated Nginx ingress (R-53, R-54)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

GEN = REPO_ROOT / "scripts" / "gen_routes.py"
LOC = re.compile(r"location (=|\^~)? ?(\S+) \{\s*proxy_pass http://127\.0\.0\.1:(\d+);", re.S)


def parse(conf: str) -> tuple[dict[str, str], dict[str, str]]:
    port_owner = {"9384": "go", "9380": "python"}
    exact: dict[str, str] = {}
    prefix: dict[str, str] = {}
    for op, path, port in LOC.findall(conf):
        (exact if op == "=" else prefix)[path] = port_owner[port]
    return exact, prefix


def resolve(path: str, conf: str) -> str:
    """Nginx precedence: exact match, then longest ^~ prefix, then the SPA."""
    exact, prefix = parse(conf)
    if path in exact:
        return exact[path]
    best = max((p for p in prefix if path.startswith(p)), key=len, default=None)
    return prefix[best] if best else "spa"


@pytest.fixture(scope="module")
def conf() -> str:
    return (REPO_ROOT / "docker/nginx/ragflow.conf").read_text(encoding="utf-8")


CASES = [
    ("/health", "go"),
    ("/api/v1/system/ping", "go"),
    ("/api/v1/system/config", "go"),
    ("/api/v1/system/version", "go"),
    ("/api/v1/system/tokens", "go"),
    ("/api/v1/system/tokens/abc", "go"),
    ("/api/v1/tenants/t1/users", "go"),
    ("/api/v1/auth/logout", "go"),
    ("/api/v1/openapi.json", "python"),
    ("/api/v1/system/stats", "python"),
    ("/api/v1/system/status", "python"),
    ("/api/v1/system/healthz", "python"),
    ("/system/healthz", "python"),
    ("/system/status", "python"),
    ("/api/v1/mcp", "go"),
    ("/api/v1/mcp/servers", "python"),
    ("/api/v1/users", "go"),
    ("/api/v1/auth/login", "go"),
    ("/v1/user/info", "go"),
    ("/v1/tenant/list", "go"),
    ("/api/v1/searchbots/ask", "go"),
    ("/api/v1/language", "go"),
    ("/api/v1/datasets", "python"),
    ("/v1/anything", "python"),
    ("/", "spa"),
    ("/datasets", "spa"),
]


@pytest.mark.parametrize(("path", "owner"), CASES)
def test_resolution(conf: str, path: str, owner: str) -> None:
    assert resolve(path, conf) == owner


def test_no_regex_or_bare_prefix(conf: str) -> None:
    assert "location ~" not in conf
    bare = re.findall(r"location (?!=|\^~)(\S+) \{", conf)
    assert set(bare) <= {"/", "/assets/"}
    assert "location ^~ /api/v1/system/ {" not in conf


def run_gen(*args: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(GEN), *args] + (["--root", str(root)] if root else [])
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "conf").mkdir()
    shutil.copy(REPO_ROOT / "conf/routes.yaml", tmp_path / "conf/routes.yaml")
    assert run_gen(root=tmp_path).returncode == 0
    return tmp_path


def test_check_passes_then_detects_drift(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    assert run_gen("--check", root=root).returncode == 0
    target = root / "docker/nginx/ragflow.conf"
    target.write_text(target.read_text() + "# edit\n")
    assert run_gen("--check", root=root).returncode == 1


def test_committed_outputs_have_no_drift() -> None:
    assert run_gen("--check").returncode == 0


def test_duplicate_path_rejected(tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf/routes.yaml").write_text("ports: {python_api: 1, go_api: 2}\nroutes:\n  - {owner: go, match: exact, path: /a}\n  - {owner: python, match: exact, path: /a}\n")
    assert run_gen(root=tmp_path).returncode != 0


def test_unknown_owner_rejected(tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf/routes.yaml").write_text("ports: {python_api: 1, go_api: 2}\nroutes:\n  - {owner: rust, match: exact, path: /a}\n")
    assert run_gen(root=tmp_path).returncode != 0


def _registry_rows() -> list[dict]:
    import yaml

    return yaml.safe_load((REPO_ROOT / "conf/routes.yaml").read_text(encoding="utf-8"))["endpoints"]


@pytest.mark.parametrize("conf_name", ["ragflow.conf", "ragflow.https.conf"])
def test_registry_owner_agrees_with_nginx_location(conf_name: str) -> None:
    import re as _re

    text = (REPO_ROOT / "docker/nginx" / conf_name).read_text(encoding="utf-8")
    rows = _registry_rows()
    assert rows
    for row in rows:
        concrete = _re.sub(r"\{[^/{}]+\}", "x1", row["path"])
        assert resolve(concrete, text) == row["owner"], f"{row['method']} {row['path']}"


def test_phase2_ownership_locations_present(conf: str) -> None:
    exact, prefix = parse(conf)
    assert exact["/api/v1/system/tokens"] == "go"
    assert exact["/api/v1/auth/logout"] == "go"
    assert prefix["/api/v1/system/tokens/"] == "go"
    assert prefix["/api/v1/tenants/"] == "go"
    assert prefix["/api/"] == "python"
    assert conf.rindex("location ^~ /api/ ") > conf.rindex("location ^~ /api/v1/tenants/")
