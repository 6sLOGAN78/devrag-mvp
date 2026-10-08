import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# docs/apikey llm.md was ignored until the user reviewed it on 2026-10-07 (B-01, R-49); it is now tracked.
IGNORED = [".env", ".env.local", "docker/.env"]
TRACKABLE = ["docker/.env.example"]


def check_ignore(cwd: Path, path: str) -> int:
    return subprocess.run(["git", "check-ignore", "-q", "--", path], cwd=cwd, check=False).returncode


def git_lines(cwd: Path, *args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln]


def assert_hygiene(cwd: Path) -> None:
    for p in IGNORED:
        assert check_ignore(cwd, p) == 0, f"{p} must be git-ignored"
    for p in TRACKABLE:
        assert check_ignore(cwd, p) == 1, f"{p} must stay trackable"


@pytest.mark.parametrize("path", IGNORED)
def test_secret_paths_ignored(repo_root, path):
    assert check_ignore(repo_root, path) == 0


def test_env_example_not_ignored(repo_root):
    assert check_ignore(repo_root, "docker/.env.example") == 1


def test_authoritative_docs_are_tracked(repo_root):
    # Until 2026-10-07 this test asserted the opposite: docs/ stayed out of git while the user reviewed it
    # for credentials (B-01). The user released it, so the specification the decision register cites must now
    # be in the repository.
    tracked = set(git_lines(repo_root, "ls-files", "docs"))
    assert "docs/spec.md" in tracked
    assert "docs/04-api/endpoint-catalog.md" in tracked


def test_hygiene_passes_in_temp_repo_with_real_gitignore(repo_root, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text((repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    assert_hygiene(tmp_path)


def test_hygiene_fails_when_env_example_exception_removed(repo_root, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    lines = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    # `!.env.example` already un-ignores docker/.env.example at any depth, so both exceptions must go.
    kept = [ln for ln in lines if ln.strip() not in {"!docker/.env.example", "!.env.example"}]
    assert len(kept) == len(lines) - 2
    (tmp_path / ".gitignore").write_text("\n".join(kept) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"docker/\.env\.example"):
        assert_hygiene(tmp_path)


def test_no_test_module_needs_docker_env_at_import_time() -> None:
    """A machine without docker/.env (CI) must still collect every module: stack_env() is {} there, so a
    module-level stack_env()["KEY"] raises KeyError during collection and breaks even the unit selection."""
    import ast

    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in sorted((root / "test").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for stmt in tree.body:  # module level only; code inside functions runs after collection
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "stack_env"
                ):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, offenders
