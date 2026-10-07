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
    env = {"PATH": "/usr/bin:/bin", "MYSQL_PASSWORD": "m", "REDIS_PASSWORD": "r", "MINIO_PASSWORD": "n", "ELASTIC_PASSWORD": "e", "SECRET_KEY": "fake-test-secret-key-0123456789abcdef-ZZ"}
    out = tmp_path / "x.yaml"
    res = subprocess.run(
        [sys.executable, "scripts/render_conf.py", "--template", "conf/service_conf.yaml.template", "--out", str(out)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT, check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "${" not in out.read_text()
    assert (out.stat().st_mode & 0o777) == 0o600


# --- WR-19 / IN-16: escaping, control characters, post-render validation (fake values only) ---
import os  # noqa: E402

import yaml  # noqa: E402

from scripts.render_conf import InvalidValue, main  # noqa: E402

FAKE_HOSTILE = "fake'pw\\x#y: ${Z} \"q\""


def test_single_quote_round_trips():
    assert yaml.safe_load(render("pw: '${P}'", {"P": "a'b"})) == {"pw": "a'b"}


def test_doubled_single_quote_round_trips():
    assert yaml.safe_load(render("pw: '${P}'", {"P": "a''b"})) == {"pw": "a''b"}


def test_hostile_characters_round_trip_in_quoted_context():
    assert yaml.safe_load(render("pw: '${P}'", {"P": FAKE_HOSTILE})) == {"pw": FAKE_HOSTILE}


def test_quoted_context_detected_mid_line_template():
    out = render("h: 'http://${H}:${P}'", {"H": "o'k", "P": "1"})
    assert yaml.safe_load(out) == {"h": "http://o'k:1"}


@pytest.mark.parametrize("bad", ["a\nb: injected", "a\rb", "a\x00b", "a\x1bb", "a\x85b: injected", "a\u2028b: injected", "a\u2029b: injected"])
def test_control_characters_rejected_without_echo(bad):
    with pytest.raises(InvalidValue) as err:
        render("pw: '${SECRET_X}'", {"SECRET_X": bad})
    assert "SECRET_X" in str(err.value)
    assert bad not in str(err.value)
    assert "injected" not in str(err.value)


def test_tab_allowed():
    assert yaml.safe_load(render("pw: '${P}'", {"P": "a\tb"})) == {"pw": "a\tb"}


def test_unquoted_numeric_unchanged():
    assert render("http_port: ${P:-9380}", {"P": "1234"}) == "http_port: 1234"
    assert render("http_port: ${P:-9380}", {}) == "http_port: 9380"


def test_unquoted_context_rejects_quote_without_echo():
    with pytest.raises(InvalidValue) as err:
        render("port: ${P:-1}", {"P": "1'2"})
    assert "P" in str(err.value)
    assert "1'2" not in str(err.value)


def _run_main(tmp_path, monkeypatch, secrets):
    tpl = tmp_path / "t.template"
    tpl.write_text("pw: '${PW:?need}'\nport: ${PORT:-1}\n", encoding="utf-8")
    out = tmp_path / "out" / "c.yaml"
    for key in ("PW", "PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)
    return main(["--template", str(tpl), "--out", str(out)]), out


def test_main_writes_hostile_secret_that_round_trips(tmp_path, monkeypatch):
    code, out = _run_main(tmp_path, monkeypatch, {"PW": FAKE_HOSTILE})
    assert code == 0
    assert yaml.safe_load(out.read_text()) == {"pw": FAKE_HOSTILE, "port": 1}


def test_main_rejects_control_char_exit_1_no_file_no_value(tmp_path, monkeypatch, capsys):
    code, out = _run_main(tmp_path, monkeypatch, {"PW": "fake\nevil: 1"})
    assert code == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert "PW" in err
    assert "evil" not in err


def test_main_invalid_yaml_output_exit_1_no_partial_file(tmp_path, monkeypatch, capsys):
    # unquoted ': ' in a numeric slot yields a mapping-in-scalar error only after render
    code, out = _run_main(tmp_path, monkeypatch, {"PW": "ok", "PORT": "1: 2: 3"})
    assert code == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert "1: 2: 3" not in err


def test_main_output_created_0600_from_start(tmp_path, monkeypatch):
    old = os.umask(0)
    try:
        code, out = _run_main(tmp_path, monkeypatch, {"PW": "fake"})
    finally:
        os.umask(old)
    assert code == 0
    assert (out.stat().st_mode & 0o777) == 0o600


def test_render_conf_source_has_no_chmod_after_write():
    src = (REPO_ROOT / "scripts" / "render_conf.py").read_text()
    assert "chmod" not in src
    assert "0o600" in src


# --- Phase 2 sections: security, auth, mail, models, ratelimit (02-04, R-94, R-96); fake values only ---
BASE_ENV = {"MYSQL_PASSWORD": "fake-m", "REDIS_PASSWORD": "fake-r", "MINIO_PASSWORD": "fake-n", "ELASTIC_PASSWORD": "fake-e"}
FAKE_KEY = "fake-test-secret-key-0123456789abcdef-ZZ"


def _render_cli(tmp_path, extra):
    out = tmp_path / "x.yaml"
    res = subprocess.run(
        [sys.executable, "scripts/render_conf.py", "--template", "conf/service_conf.yaml.template", "--out", str(out)],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", **BASE_ENV, **extra}, cwd=REPO_ROOT, check=False,
    )
    return res, out


def test_cli_renders_phase2_sections(tmp_path):
    res, out = _render_cli(tmp_path, {"SECRET_KEY": FAKE_KEY, "SUPERUSER_EMAIL": "root@example.test", "SMTP_PASSWORD": "fake-smtp"})
    assert res.returncode == 0, res.stderr
    conf = yaml.safe_load(out.read_text())
    assert conf["security"]["secret_key"] == FAKE_KEY
    assert str(conf["auth"]["register_enabled"]) == "1"
    assert conf["auth"]["superuser_email"] == "root@example.test"
    assert conf["auth"]["superuser_password"] in ("", None)
    assert int(conf["auth"]["otp_ttl_seconds"]) == 600
    assert conf["mail"]["host"] == "mailpit" and int(conf["mail"]["port"]) == 1025
    assert conf["mail"]["security"] == "none" and conf["mail"]["password"] == "fake-smtp"
    assert conf["mail"]["from"] == "no-reply@devrag.local"
    assert {"default_chat_model", "default_embedding_model", "default_rerank_model", "default_factory", "default_base_url"} <= set(conf["models"])
    assert conf["ratelimit"] == {
        "register_per_ip": 10, "register_window_seconds": 3600, "login_failures_per_email": 5, "login_per_ip": 30,
        "login_window_seconds": 900, "otp_email_interval_seconds": 60, "otp_per_email_per_hour": 5,
        "otp_per_ip_per_hour": 20, "otp_window_seconds": 3600,
    }


def test_cli_missing_secret_key_exits_1_naming_only_the_key(tmp_path):
    res, out = _render_cli(tmp_path, {})
    assert res.returncode == 1
    assert "SECRET_KEY" in res.stderr
    assert not out.exists()


def test_cli_short_secret_key_exits_1_without_echoing_value(tmp_path):
    short = "fake-short-key-31-chars-abcdefg"
    assert len(short) < 32
    res, out = _render_cli(tmp_path, {"SECRET_KEY": short})
    assert res.returncode == 1
    assert "SECRET_KEY" in res.stderr
    assert short not in res.stderr + res.stdout
    assert not out.exists()
