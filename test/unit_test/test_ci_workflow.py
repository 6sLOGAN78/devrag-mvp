"""Static structure checks for .github/workflows/ci.yml.

GitHub Actions cannot be run here (B-06): these tests pin the shape only and prove nothing about a real run.
"""
from __future__ import annotations

import re

import pytest
import yaml

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(workflow) -> list[dict]:
    jobs = workflow["jobs"]
    assert len(jobs) == 1
    return next(iter(jobs.values()))["steps"]


def _index(steps, pred) -> int:
    for i, step in enumerate(steps):
        if pred(step):
            return i
    raise AssertionError("step not found")


def _uses(name):
    return lambda s: str(s.get("uses", "")).startswith(name + "@")


def _run(cmd):
    return lambda s: str(s.get("run", "")).strip() == cmd


def test_workflow_triggers_present(workflow):
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 loads `on` as True
    assert "push" in triggers and "pull_request" in triggers


def test_permissions_read_only(workflow):
    assert workflow["permissions"] == {"contents": "read"}


def test_setup_go_uses_go_mod(steps):
    step = steps[_index(steps, _uses("actions/setup-go"))]
    assert step["with"]["go-version-file"] == "go.mod"


def test_setup_node_22_with_npm_cache(steps):
    step = steps[_index(steps, _uses("actions/setup-node"))]
    assert str(step["with"]["node-version"]) == "22"
    assert step["with"]["cache"] == "npm"
    assert step["with"]["cache-dependency-path"] == "web/package-lock.json"


def test_npm_ci_runs_in_web(steps):
    step = steps[_index(steps, lambda s: str(s.get("run", "")).startswith("npm ci"))]
    assert step["working-directory"] == "web"


def test_action_versions_pinned_by_major_tag(steps):
    for step in steps:
        if "uses" in step:
            assert re.fullmatch(r"(actions|astral-sh)/[\w-]+@v\d+", step["uses"]), step["uses"]


def test_step_order(steps):
    order = [
        _index(steps, _uses("actions/checkout")),
        _index(steps, _uses("astral-sh/setup-uv")),
        _index(steps, _uses("actions/setup-go")),
        _index(steps, _uses("actions/setup-node")),
        _index(steps, lambda s: str(s.get("run", "")).startswith("npm ci")),
        _index(steps, _run("uv sync --frozen")),
        _index(steps, _run("make ci")),
        _index(steps, _run("make test-unit")),
    ]
    assert order == sorted(order)
    assert len(set(order)) == len(order)


def test_no_secrets_referenced():
    assert "secrets." not in WORKFLOW.read_text(encoding="utf-8")


def test_run_commands_exist_as_make_targets(steps):
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for step in steps:
        match = re.fullmatch(r"make (\S+)", str(step.get("run", "")).strip())
        if match:
            assert re.search(rf"^{re.escape(match.group(1))}:", makefile, re.M), match.group(1)
