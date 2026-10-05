from __future__ import annotations

import subprocess
import sys

import pytest

from scripts.render_conf import MissingVariable, render
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit


def test_default_used_when_unset():
    assert render("a: ${A:-x}", {}) == "a: x"


def test_env_overrides_default():
    assert render("a: ${A:-x}", {"A": "y"}) == "a: y"


def test_empty_env_uses_default():
    assert render("a: ${A:-x}", {"A": ""}) == "a: x"


def test_required_missing_names_variable_and_message():
    with pytest.raises(MissingVariable) as err:
        render("p: ${B:?need B}", {})
    assert err.value.name == "B"
    assert "need B" in str(err.value)


def test_required_present():
    assert render("p: ${B:?need B}", {"B": "s"}) == "p: s"


def test_double_dollar_untouched():
    assert render("cost: $$5 and $${NOT}", {}) == "cost: $$5 and $${NOT}"


def test_no_leftover_placeholders():
    out = render("${A:-1} ${B:-2} ${C:?m}", {"C": "c"})
    assert "${" not in out


def test_cli_missing_secret_exits_1_and_names_it(tmp_path):
    env = {"PATH": "/usr/bin:/bin"}
    res = subprocess.run(
        [sys.executable, "scripts/render_conf.py", "--template", "conf/service_conf.yaml.template", "--out", str(tmp_path / "x.yaml")],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT, check=False,
    )
    assert res.returncode == 1
    assert "MYSQL_PASSWORD" in res.stderr
    assert not (tmp_path / "x.yaml").exists()


def test_cli_renders_full_template(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "MYSQL_PASSWORD": "m", "REDIS_PASSWORD": "r", "MINIO_PASSWORD": "n", "ELASTIC_PASSWORD": "e"}
    out = tmp_path / "x.yaml"
    res = subprocess.run(
        [sys.executable, "scripts/render_conf.py", "--template", "conf/service_conf.yaml.template", "--out", str(out)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT, check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "${" not in out.read_text()
    assert (out.stat().st_mode & 0o777) == 0o600
