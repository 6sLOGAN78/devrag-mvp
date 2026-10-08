"""Permission table (conf/permissions.yaml) and its generated Go and Python modules (D-13, D-26, TEN-04, TEN-05).

The shared oracle test/fixtures/permission_cases.json is hand-written from docs/16-auth/permissions.md and is
also walked by internal/common/permissions_test.go, so the two generated tables are proven identical.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

GEN = REPO_ROOT / "scripts" / "gen_routes.py"
ORACLE = json.loads((REPO_ROOT / "test/fixtures/permission_cases.json").read_text(encoding="utf-8"))
TABLE = REPO_ROOT / "conf" / "permissions.yaml"
GENERATED = ("internal/common/permissions_gen.go", "api/apps/permissions_gen.py")
DOC_AREAS = {"datasets", "agent_canvas", "search_bots", "mcp_server", "tenant_settings", "team_admin", "enterprise_admin"}


def module() -> Any:
    return importlib.import_module("api.apps.permissions_gen")


def _root(tmp_path: Path) -> Path:
    (tmp_path / "conf").mkdir()
    shutil.copy(REPO_ROOT / "conf/routes.yaml", tmp_path / "conf/routes.yaml")
    shutil.copy(TABLE, tmp_path / "conf/permissions.yaml")
    return tmp_path


def _gen(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GEN), "--root", str(root), *args], capture_output=True, text=True, check=False, timeout=60)


def _mutate(root: Path, fn: Any) -> subprocess.CompletedProcess[str]:
    data = yaml.safe_load((root / "conf/permissions.yaml").read_text(encoding="utf-8"))
    fn(data)
    (root / "conf/permissions.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return _gen(root)


def test_every_row_of_the_docs_matrix_matches_the_oracle() -> None:
    mod = module()
    for row in ORACLE["rows"]:
        for subject in ORACLE["subjects"]:
            assert mod.allowed(subject, row["area"], row["action"]) is (subject in row["allowed"]), (subject, row["area"], row["action"])


def test_team_admin_is_owner_only() -> None:
    mod = module()
    assert mod.allowed("owner", "team_admin", "manage_members") is True
    for subject in ("admin", "normal", "beta_token", "api_token"):
        assert mod.allowed(subject, "team_admin", "manage_members") is False, subject


def test_invite_and_unknown_subjects_are_denied_for_every_area() -> None:
    mod = module()
    for subject in ORACLE["never_allowed_subjects"]:
        for row in ORACLE["rows"]:
            assert mod.allowed(subject, row["area"], row["action"]) is False, (subject, row)


def test_unknown_area_or_action_defaults_to_deny() -> None:
    mod = module()
    for area, action in ORACLE["unknown_pairs"]:
        for subject in ORACLE["subjects"]:
            assert mod.allowed(subject, area, action) is False, (subject, area, action)


def test_table_covers_every_documented_area_and_nothing_extra_is_allowed() -> None:
    data = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
    areas = {r["area"] for r in data["permissions"]}
    assert DOC_AREAS <= areas
    assert len(data["permissions"]) == len(ORACLE["rows"]) == 12
    got = {(r["area"], r["action"]): sorted(r["allow"]) for r in data["permissions"]}
    want = {(r["area"], r["action"]): sorted(r["allowed"]) for r in ORACLE["rows"]}
    assert got == want
    assert "invite" not in {s for r in data["permissions"] for s in r["allow"]}


def test_rows_say_which_phase_enforces_them() -> None:
    data = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
    for row in data["permissions"]:
        assert row["enforced_in"], row
    team = next(r for r in data["permissions"] if r["area"] == "team_admin")
    assert team["enforced_in"] == "02-22"


def test_committed_outputs_have_no_drift() -> None:
    res = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True, check=False, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


def test_generated_modules_carry_a_do_not_edit_header_and_are_byte_stable(tmp_path: Path) -> None:
    for rel in GENERATED:
        assert "do not edit" in (REPO_ROOT / rel).read_text(encoding="utf-8")[:300].lower(), rel
    root = _root(tmp_path)
    assert _gen(root).returncode == 0
    first = {rel: (root / rel).read_bytes() for rel in GENERATED}
    assert _gen(root).returncode == 0
    assert first == {rel: (root / rel).read_bytes() for rel in GENERATED}
    assert first == {rel: (REPO_ROOT / rel).read_bytes() for rel in GENERATED}, "committed output differs from a fresh generation"


def test_check_fails_when_permissions_change_without_regeneration(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _gen(root).returncode == 0
    assert _gen(root, "--check").returncode == 0
    data = yaml.safe_load((root / "conf/permissions.yaml").read_text(encoding="utf-8"))
    team = next(r for r in data["permissions"] if r["area"] == "team_admin")
    team["allow"] = ["owner", "admin"]
    (root / "conf/permissions.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    res = _gen(root, "--check")
    assert res.returncode == 1, res.stdout + res.stderr
    for rel in GENERATED:
        target = root / rel
        original = target.read_text(encoding="utf-8")
        assert _gen(root).returncode == 0
        target.write_text(original + "\n# stale\n", encoding="utf-8")
        assert _gen(root, "--check").returncode == 1, rel
        assert _gen(root).returncode == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["permissions"][0].update(allow=["owner", "invite"]),
        lambda d: d["permissions"][0].update(allow=["owner", "superuser"]),
        lambda d: d["permissions"][0].update(allow="owner"),
        lambda d: d["permissions"][0].pop("enforced_in"),
        lambda d: d["permissions"][0].update(surprise=1),
        lambda d: d["permissions"][0].update(area="Bad Area"),
        lambda d: d["permissions"].append(dict(d["permissions"][0])),
        lambda d: d["permissions"].pop(),
        lambda d: d.update(permissions=[]),
    ],
    ids=["invite-allowed", "unknown-subject", "allow-not-list", "no-enforced-in", "extra-field", "bad-area-name", "duplicate-row", "missing-doc-area", "empty"],
)
def test_invalid_table_is_rejected(tmp_path: Path, mutation: Any) -> None:
    root = _root(tmp_path)
    res = _mutate(root, mutation)
    assert res.returncode == 2, res.stdout + res.stderr


def test_missing_permissions_file_is_an_error_not_an_empty_table(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "conf/permissions.yaml").unlink()
    assert _gen(root).returncode == 2
    assert _gen(root, "--check").returncode == 2


def test_python_table_rows_equal_the_oracle() -> None:
    got = {key: sorted(value) for key, value in module().rows().items()}
    want = {(r["area"], r["action"]): sorted(r["allowed"]) for r in ORACLE["rows"]}
    assert got == want
