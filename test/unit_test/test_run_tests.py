import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def dry_run(repo_root, *args):
    return subprocess.run(
        [sys.executable, str(repo_root / "run_tests.py"), "--dry-run", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_markers_mapped_to_dash_m(repo_root):
    out = dry_run(repo_root, "-m", "unit")
    assert out.returncode == 0
    assert "-m pytest -m unit" in out.stdout


def test_test_name_mapped_to_dash_k(repo_root):
    assert "-k foo" in dry_run(repo_root, "-t", "foo").stdout


def test_ignore_is_repeatable(repo_root):
    out = dry_run(repo_root, "-i", "a", "-i", "b").stdout
    assert "--ignore a" in out
    assert "--ignore b" in out


def test_parallel_and_coverage(repo_root):
    out = dry_run(repo_root, "-p", "--coverage").stdout
    assert "-n auto" in out
    assert "--cov" in out


def test_unknown_flag_exits_nonzero_with_usage(repo_root):
    out = dry_run(repo_root, "--bogus")
    assert out.returncode != 0
    assert "usage" in out.stderr.lower()


def test_parallel_runs_serial_tests_in_a_separate_non_parallel_pass(repo_root):
    lines = dry_run(repo_root, "-p", "-m", "e2e").stdout.strip().splitlines()
    assert len(lines) == 2
    assert "-m (e2e) and not serial" in lines[0] and "-n auto" in lines[0]
    assert "-m (e2e) and serial" in lines[1] and "-n auto" not in lines[1]
