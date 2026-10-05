import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

IGNORED = ["docs/apikey llm.md", ".env", ".env.local", "docker/.env"]
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


def test_nothing_under_docs_is_tracked_or_staged(repo_root):
    assert not [p for p in git_lines(repo_root, "ls-files") if p.startswith("docs/")]
    assert not [p for p in git_lines(repo_root, "diff", "--cached", "--name-only") if p.startswith("docs/")]


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
