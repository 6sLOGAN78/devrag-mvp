"""Fixture self-tests for check_secrets.py using throwaway git repos."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_secrets.py"
pytestmark = pytest.mark.unit
DEFAULT_PW = "infini_" + "rag_flow"


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=60)
    return tmp_path


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60, check=False)


@pytest.mark.parametrize(
    "body",
    [
        f"MYSQL_PASSWORD={DEFAULT_PW}\n",
        "password: rag_" + "flow\n",
        "DB_PASSWORD = 'rag_" + "flow'\n",
        'password = "hunter2"\n',
        "api_key: 'sk-abc123'\n",
        'SECRET_KEY = "changeme"\n',
    ],
)
def test_secret_literals_fail(tmp_path: Path, body: str) -> None:
    root = repo(tmp_path)
    put(root, "conf/service.py", body)
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "conf/service.py:1" in r.stdout


@pytest.mark.parametrize("body", ['password = ""\n', "password: ${MYSQL_PASSWORD}\n", 'api_key = os.environ["K"]\n', "x = 1\n"])
def test_empty_and_reference_values_pass(tmp_path: Path, body: str) -> None:
    root = repo(tmp_path)
    put(root, "conf/service.py", body)
    assert run(root).returncode == 0


def test_example_files_and_test_paths_are_exempt_from_assignment_rule(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "docker/.env.example", 'password = "hunter2"\n')
    put(root, "test/test_a.py", 'password = "hunter2"\n')
    assert run(root).returncode == 0


def test_default_literal_fails_even_in_test_paths(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "test/test_a.py", f"x = '{DEFAULT_PW}'\n")
    assert run(root).returncode == 1


def test_docs_tree_is_never_scanned(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "docs/x.md", f"password = '{DEFAULT_PW}'\n")
    put(root, "docs/apikey llm.md", 'api_key = "sk-should-never-be-read"\n')
    r = run(root)
    assert r.returncode == 0, r.stdout


def test_ignored_files_are_never_read(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, ".gitignore", ".env\n")
    put(root, ".env", f"MYSQL_PASSWORD={DEFAULT_PW}\n")
    assert run(root).returncode == 0


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("deploy/app.env", "SECRET_KEY=abcdefabcdefabcdefabcdefabcdef12\n"),
        ("conf/service.yaml", "smtp_password: hunter22222\n"),
        ("scripts/run.sh", "export API_KEY=abcdefabcdefabcdef1234\n"),
        ("internal/auth/keys.go", 'secretKey := "abcdefabcdefabcdefabcdef"\n'),
        ("internal/auth/keys.go", 'const AccessToken = "abcdefabcdefabcdefabcdef"\n'),
        ("api/conf.py", 'refresh_token = "abcdefabcdefabcdefabcdef"\n'),
        ("conf/service.yaml", "access_token: abcdefabcdefabcdefabcdef\n"),
    ],
)
def test_wr23_blind_spots_are_flagged(tmp_path: Path, rel: str, body: str) -> None:
    root = repo(tmp_path)
    put(root, rel, body)
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert f"{rel}:1" in r.stdout


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("docker/.env.example", "SECRET_KEY=\n"),
        ("docker/.env.example", "SECRET_KEY=abcdefabcdefabcdefabcdefabcdef12\n"),
        ("conf/service.yaml", "smtp_password: ${SMTP_PASSWORD}\n"),
        ("conf/service.yaml", "smtp_password:\n"),
        ("conf/service.yaml", "token: true\n"),
        ("deploy/app.env", "SECRET_KEY=\n"),
        ("deploy/app.env", "SECRET_KEY=${SECRET_KEY}\n"),
        ("internal/auth/keys.go", 'tokenType := "Bearer"\n'),
        ("internal/auth/keys.go", "secretKey := os.Getenv(\"SECRET_KEY\")\n"),
        ("api/conf.py", "token = request.headers['Authorization']\n"),
        ("test/fixtures/conf.env", "SECRET_KEY=abcdefabcdefabcdefabcdefabcdef12\n"),
        ("internal/auth/keys_test.go", 'secretKey := "abcdefabcdefabcdefabcdef"\n'),
        ("test/unit_test/test_x.py", 'refresh_token = "abcdefabcdefabcdefabcdef"\n'),
    ],
)
def test_wr23_allowed_shapes_pass(tmp_path: Path, rel: str, body: str) -> None:
    root = repo(tmp_path)
    put(root, rel, body)
    r = run(root)
    assert r.returncode == 0, r.stdout


def test_locale_catalog_copy_is_not_mistaken_for_a_credential(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "web/src/locales/en.json", '{"auth": {"field": {"password": "Password"}, "password": {"show": "Show password"}}}\n')
    result = run(root)
    assert result.returncode == 0, result.stdout


def test_locale_catalog_is_still_scanned_for_the_default_literal(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "web/src/locales/en.json", '{"hint": "' + DEFAULT_PW + '"}\n')
    assert run(root).returncode == 1


def test_the_catalog_exemption_does_not_cover_source_files(tmp_path: Path) -> None:
    root = repo(tmp_path)
    put(root, "web/src/pages/login.ts", 'const password = "hunter2hunter2";\n')
    assert run(root).returncode == 1
