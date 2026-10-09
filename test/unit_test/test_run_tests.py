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


def _stub_codes(monkeypatch, codes):
    import run_tests

    seen = []
    queue = list(codes)

    def fake_run(cmd, check=False):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, queue.pop(0))

    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)
    return run_tests, seen


def test_single_command_exit_5_is_a_failure(monkeypatch):
    run_tests, _ = _stub_codes(monkeypatch, [5])
    assert run_tests.main(["-m", "e2e"]) == 5


def test_parallel_first_pass_exit_5_is_a_failure(monkeypatch):
    run_tests, _ = _stub_codes(monkeypatch, [5, 0])
    assert run_tests.main(["-p", "-m", "e2e"]) == 5


def test_parallel_serial_pass_exit_5_alone_is_tolerated(monkeypatch):
    run_tests, _ = _stub_codes(monkeypatch, [0, 5])
    assert run_tests.main(["-p", "-m", "e2e"]) == 0


def test_allow_empty_tolerates_exit_5_and_is_not_forwarded(monkeypatch):
    run_tests, seen = _stub_codes(monkeypatch, [5])
    assert run_tests.main(["--allow-empty", "-m", "e2e"]) == 0
    assert "--allow-empty" not in seen[0]


def test_real_failures_are_returned_and_first_nonzero_wins(monkeypatch):
    run_tests, _ = _stub_codes(monkeypatch, [1, 2])
    assert run_tests.main(["-p"]) == 1
    run_tests, _ = _stub_codes(monkeypatch, [4])
    assert run_tests.main([]) == 4


def test_allow_empty_still_returns_real_failures(monkeypatch):
    run_tests, _ = _stub_codes(monkeypatch, [5, 1])
    assert run_tests.main(["-p", "--allow-empty"]) == 1


# --- Plan 03-27: the live_model marker is invisible to every default selection (D-04) -----------------------------

GATE_SELECTIONS = ["unit", "integration", "e2e and not serial", "e2e and serial"]


def _synthetic_collect(tmp_path, expression):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --strict-markers -p no:anyio\nmarkers =\n    unit\n    integration\n    e2e\n    serial\n    live_model\n")
    (tmp_path / "test_synthetic.py").write_text("import pytest\n\npytestmark = pytest.mark.live_model\n\n\ndef test_only_live():\n    assert True\n")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", expression, "-c", str(tmp_path / "pytest.ini"), "--rootdir", str(tmp_path), str(tmp_path / "test_synthetic.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


def test_live_model_marker_is_passed_through_unchanged(repo_root):
    out = dry_run(repo_root, "-m", "live_model")
    assert out.returncode == 0
    assert out.stdout.strip() == "-m pytest -m live_model"


@pytest.mark.parametrize("expression", GATE_SELECTIONS)
def test_gate_selections_do_not_pick_up_a_live_model_only_test(tmp_path, expression):
    result = _synthetic_collect(tmp_path, expression)
    assert result.returncode == 5, result.stdout + result.stderr
    assert "test_only_live" not in result.stdout


def test_live_model_selection_does_pick_it_up(tmp_path):
    result = _synthetic_collect(tmp_path, "live_model")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_only_live" in result.stdout


def test_live_model_marker_is_registered_in_pyproject(repo_root):
    text = (repo_root / "pyproject.toml").read_text()
    assert '"live_model:' in text
