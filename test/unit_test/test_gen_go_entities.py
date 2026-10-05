"""Go entity generator: determinism, type mapping, drift detection, formatting and compilation (DATA-06, D-11)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import gen_go_entities as gen
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

GEN = REPO_ROOT / "scripts" / "gen_go_entities.py"
CHECK = REPO_ROOT / "scripts" / "ci" / "check_generated.py"


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=120, check=False, cwd=REPO_ROOT)  # noqa: S603


def test_generation_is_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    assert run(GEN, "--out-root", a).returncode == 0
    assert run(GEN, "--out-root", b).returncode == 0
    names = sorted(p.name for p in (a / "internal/entity").glob("*.go"))
    assert names == sorted(p.name for p in (b / "internal/entity").glob("*.go"))
    for n in names:
        assert (a / "internal/entity" / n).read_bytes() == (b / "internal/entity" / n).read_bytes()


def test_one_file_per_table_plus_registry() -> None:
    tables = json.loads((REPO_ROOT / "conf/schema.json").read_text())["tables"]
    files = sorted(p.name for p in (REPO_ROOT / "internal/entity").glob("*.go"))
    assert len(tables) == 38
    assert files == sorted([f"{t['name']}.go" for t in tables] + ["registry.go"])
    for p in (REPO_ROOT / "internal/entity").glob("*.go"):
        assert "DO NOT EDIT" in p.read_text()


@pytest.mark.parametrize(("mysql", "nullable", "go"), [
    ("varchar(32)", False, "string"), ("varchar(32)", True, "*string"), ("longtext", True, "*string"),
    ("tinyint(1)", False, "bool"), ("int", False, "int32"), ("smallint", False, "int32"), ("bigint", False, "int64"),
    ("bigint", True, "*int64"), ("float", False, "float64"), ("double", True, "*float64"),
    ("datetime", False, "time.Time"), ("datetime", True, "*time.Time"), ("timestamp", False, "time.Time"),
])
def test_type_mapping(mysql: str, nullable: bool, go: str) -> None:
    assert gen.go_type(mysql, nullable) == go


def test_struct_names() -> None:
    assert gen.struct_name("user_tenant") == "UserTenant"
    assert gen.struct_name("api_4_conversation") == "API4Conversation"
    assert gen.struct_name("tenant_llm") == "TenantLLM"


def test_unmapped_type_fails(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "conf").mkdir(parents=True)
    data = json.loads((REPO_ROOT / "conf/schema.json").read_text())
    data["tables"][0]["columns"][0]["type"] = "geometry"
    (root / "conf/schema.json").write_text(json.dumps(data))
    proc = run(GEN, "--root", root, "--out-root", tmp_path / "out")
    assert proc.returncode != 0
    assert "unmapped MySQL type" in proc.stderr
    with pytest.raises(gen.GenError):
        gen.go_type("json", False)


def test_check_passes_on_committed_files_and_detects_drift(tmp_path: Path) -> None:
    assert run(GEN, "--check").returncode == 0
    root = tmp_path / "r"
    shutil.copytree(REPO_ROOT / "conf", root / "conf")
    shutil.copytree(REPO_ROOT / "internal/entity", root / "internal/entity")
    p = root / "internal/entity/document.go"
    p.write_text(p.read_text().replace("string", "int32", 1))
    proc = run(GEN, "--check", "--root", root)
    assert proc.returncode == 1
    assert "document.go" in proc.stdout


def test_generated_files_are_gofmt_clean_and_build() -> None:
    fmt = subprocess.run(["gofmt", "-l", "internal/entity"], capture_output=True, text=True, cwd=REPO_ROOT, check=False)  # noqa: S603,S607
    assert fmt.returncode == 0
    assert fmt.stdout == ""
    build = subprocess.run(["go", "build", "./internal/entity"], capture_output=True, text=True, cwd=REPO_ROOT, check=False)  # noqa: S603,S607
    assert build.returncode == 0, build.stderr


def test_check_generated_fails_when_schema_json_column_edited(tmp_path: Path) -> None:
    root = tmp_path / "r"
    shutil.copytree(REPO_ROOT / "conf", root / "conf")
    shutil.copytree(REPO_ROOT / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO_ROOT / "internal/entity", root / "internal/entity")
    for rel in ("docker/nginx/ragflow.conf", "docker/nginx/ragflow.https.conf", "web/src/constants/api-routes.generated.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, root / rel)
    for pkg in ("api", "common"):  # export_schema.py imports the Peewee models relative to its own repo root
        (root / pkg).symlink_to(REPO_ROOT / pkg, target_is_directory=True)
    baseline = run(CHECK, "--root", root)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    data = json.loads((root / "conf/schema.json").read_text())
    data["tables"][0]["columns"][0]["type"] = "bigint"
    (root / "conf/schema.json").write_text(json.dumps(data, indent=2) + "\n")
    proc = run(CHECK, "--root", root)
    assert proc.returncode == 1
    assert "drift or error in" in proc.stdout
    assert "schema" in proc.stdout
