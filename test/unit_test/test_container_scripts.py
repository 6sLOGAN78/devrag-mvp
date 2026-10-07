"""Container shell scripts (prepare_runtime.sh, healthcheck.sh, wait_stack.sh) tested with fake binaries on PATH."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / "docker" / "prepare_runtime.sh"
HEALTH = ROOT / "docker" / "healthcheck.sh"
WAIT = ROOT / "scripts" / "wait_stack.sh"

HTTP_CONF = "# plain http conf\n"
HTTPS_CONF = "# https conf\n"


def _fake(bindir: Path, name: str, body: str) -> None:
    bindir.mkdir(exist_ok=True)
    path = bindir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _prepare_env(tmp_path: Path, tls: str | None, certs: set[str] | None, template: bool = True) -> tuple[dict[str, str], Path, Path]:
    conf_dir = tmp_path / "conf.d"
    conf_dir.mkdir()
    (conf_dir / "ragflow.conf").write_text(HTTP_CONF)
    cert_dir = tmp_path / "certs"
    if certs is not None:
        cert_dir.mkdir()
        for name in certs:
            (cert_dir / name).write_text("x")
    tpl = tmp_path / "ragflow.https.conf"
    if template:
        tpl.write_text(HTTPS_CONF)
    calls = tmp_path / "chown.log"
    _fake(tmp_path / "bin", "chown", f'echo "$@" >> "{calls}"\n')
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "NGINX_CONF_DIR": str(conf_dir),
        "NGINX_CERT_DIR": str(cert_dir),
        "NGINX_HTTPS_CONF": str(tpl),
        "LOG_DIR": str(tmp_path / "logs"),
    }
    env.pop("NGINX_TLS", None)
    if tls is not None:
        env["NGINX_TLS"] = tls
    return env, conf_dir / "ragflow.conf", calls


def _run_prepare(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(PREPARE)], capture_output=True, text=True, env=env, check=False)


@pytest.mark.parametrize("tls", [None, "0"])
def test_plain_mode_creates_and_chowns_log_dir(tmp_path: Path, tls: str | None) -> None:
    env, conf, calls = _prepare_env(tmp_path, tls, None)
    env.update(APP_UID="1234", APP_GID="5678")
    result = _run_prepare(env)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "logs").is_dir()
    assert conf.read_text() == HTTP_CONF
    assert f"1234:5678 {tmp_path / 'logs'}" in calls.read_text()


def test_default_uid_gid_is_1000(tmp_path: Path) -> None:
    env, _, calls = _prepare_env(tmp_path, None, None)
    env.pop("APP_UID", None)
    env.pop("APP_GID", None)
    assert _run_prepare(env).returncode == 0
    assert f"1000:1000 {tmp_path / 'logs'}" in calls.read_text()


def test_tls_with_cert_and_key_swaps_in_https_conf(tmp_path: Path) -> None:
    env, conf, _ = _prepare_env(tmp_path, "1", {"server.crt", "server.key"})
    result = _run_prepare(env)
    assert result.returncode == 0, result.stderr
    assert conf.read_text() == HTTPS_CONF


@pytest.mark.parametrize("certs", [set(), {"server.crt"}, {"server.key"}, None], ids=["empty", "crt-only", "key-only", "no-dir"])
def test_tls_without_full_pair_fails_closed(tmp_path: Path, certs: set[str] | None) -> None:
    env, conf, _ = _prepare_env(tmp_path, "1", certs)
    result = _run_prepare(env)
    assert result.returncode == 1
    assert "NGINX_TLS=1" in result.stderr
    assert "missing" in result.stderr
    assert conf.read_bytes() == HTTP_CONF.encode()


def test_tls_with_unreadable_template_fails(tmp_path: Path) -> None:
    env, conf, _ = _prepare_env(tmp_path, "1", {"server.crt", "server.key"}, template=False)
    result = _run_prepare(env)
    assert result.returncode != 0
    assert conf.read_text() == HTTP_CONF


def test_entrypoint_delegates_to_prepare_runtime() -> None:
    entry = (ROOT / "docker" / "entrypoint.sh").read_text()
    assert "prepare_runtime.sh" in entry
    assert "NGINX_TLS" not in entry
    assert "prepare_runtime.sh" in (ROOT / "Dockerfile").read_text()
    assert os.access(PREPARE, os.X_OK)


def _run_health(tmp_path: Path, codes: dict[str, str], tls: str | None) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    log = tmp_path / "curl.log"
    cases = "\n".join(f'  *"{url}"*) printf "%s" "{code}" ;;' for url, code in codes.items())
    _fake(
        tmp_path / "bin",
        "curl",
        f'for a in "$@"; do last="$a"; done\necho "$last" >> "{log}"\ncase "$last" in\n{cases}\n  *) printf "000" ;;\nesac\n',
    )
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    for k in ("NGINX_TLS", "GO_API_PORT", "SVR_HTTP_PORT"):
        env.pop(k, None)
    if tls is not None:
        env["NGINX_TLS"] = tls
    result = subprocess.run(["bash", str(HEALTH)], capture_output=True, text=True, env=env, check=False)
    return result, (log.read_text().split() if log.exists() else [])


GO_URL = "http://127.0.0.1:9384/health"
PY_URL = "http://127.0.0.1:9380/api/v1/system/healthz"
NGX_URL = "http://127.0.0.1:80/"


@pytest.mark.parametrize(
    ("codes", "tls", "ok"),
    [
        ({GO_URL: "200", PY_URL: "200", NGX_URL: "200"}, None, True),
        ({GO_URL: "200", PY_URL: "200", NGX_URL: "301"}, "1", True),
        ({GO_URL: "200", PY_URL: "200", NGX_URL: "301"}, None, False),
        ({GO_URL: "503", PY_URL: "503", NGX_URL: "301"}, "1", False),
        ({GO_URL: "200", PY_URL: "000", NGX_URL: "200"}, None, False),
        ({GO_URL: "000", PY_URL: "200", NGX_URL: "200"}, None, False),
        ({GO_URL: "200", PY_URL: "200", NGX_URL: "502"}, None, False),
    ],
)
def test_healthcheck_matrix(tmp_path: Path, codes: dict[str, str], tls: str | None, ok: bool) -> None:
    result, urls = _run_health(tmp_path, codes, tls)
    assert (result.returncode == 0) is ok, result.stderr
    if not ok:
        assert result.stderr.strip()
    assert GO_URL in urls or not ok


def test_healthcheck_probes_backends_directly() -> None:
    text = HEALTH.read_text()
    assert "127.0.0.1:80/health" not in text
    assert "GO_API_PORT" in text
    assert "SVR_HTTP_PORT" in text


def _probe(tmp_path: Path, tls: str | None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "COMPOSE_PROJECT_NAME": "devrag-stack"}
    env.pop("NGINX_TLS", None)
    if tls is not None:
        env["NGINX_TLS"] = tls
    return subprocess.run(["bash", str(WAIT), "--print-probe-urls"], capture_output=True, text=True, env=env, check=False, cwd=tmp_path)


def test_wait_stack_plain_probe_urls(tmp_path: Path) -> None:
    result = _probe(tmp_path, None)
    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:" in result.stdout
    assert "https://" not in result.stdout
    assert "-k" not in result.stdout.split()


def test_wait_stack_tls_probe_urls(tmp_path: Path) -> None:
    result = _probe(tmp_path, "1")
    assert result.returncode == 0, result.stderr
    assert "https://127.0.0.1:" in result.stdout
    assert "-k" in result.stdout.split()


# --- scripts/init_env.sh --append-missing (SEC-09, R-96, T-02-15) ---
INIT_ENV = ROOT / "scripts" / "init_env.sh"
FAKE_EXAMPLE = "A=1\n# secret\nSECRET_KEY=\n# secret\nSMTP_PASSWORD=\nB=two\n"


def _init_env(tmp_path: Path, existing: str | None, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    example = tmp_path / "env.example"
    example.write_text(FAKE_EXAMPLE)
    target = tmp_path / "env"
    if existing is not None:
        target.write_text(existing)
    env = {**os.environ, "ENV_EXAMPLE": str(example), "ENV_TARGET": str(target)}
    result = subprocess.run(["bash", str(INIT_ENV), *args], capture_output=True, text=True, env=env, check=False)
    return result, target


def test_append_missing_adds_only_absent_keys_and_keeps_existing_lines(tmp_path: Path) -> None:
    existing = "A=custom\nUNRELATED=keep\n"
    result, target = _init_env(tmp_path, existing, "--append-missing")
    assert result.returncode == 0, result.stderr
    text = target.read_text()
    assert text.startswith(existing)
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))
    assert values["A"] == "custom"
    assert values["B"] == "two"
    assert len(values["SECRET_KEY"]) == 64 and int(values["SECRET_KEY"], 16) >= 0
    assert values["SMTP_PASSWORD"] == ""
    assert values["SECRET_KEY"] not in result.stdout + result.stderr


def test_append_missing_is_idempotent_and_never_regenerates(tmp_path: Path) -> None:
    _, target = _init_env(tmp_path, "A=1\n", "--append-missing")
    first = target.read_bytes()
    result, _ = _init_env(tmp_path, None, "--append-missing")
    assert result.returncode == 0
    assert target.read_bytes() == first


def test_append_missing_keeps_existing_secret_key(tmp_path: Path) -> None:
    existing = "SECRET_KEY=" + "ab" * 32 + "\n"
    _, target = _init_env(tmp_path, existing, "--append-missing")
    assert target.read_text().count("SECRET_KEY=") == 1
    assert target.read_text().startswith(existing)


def test_append_missing_creates_missing_file_with_operator_keys_empty(tmp_path: Path) -> None:
    result, target = _init_env(tmp_path, None, "--append-missing")
    assert result.returncode == 0
    assert "SMTP_PASSWORD=\n" in target.read_text()


def test_plain_mode_still_refuses_existing_env_and_leaves_operator_secret_empty(tmp_path: Path) -> None:
    result, target = _init_env(tmp_path, "A=1\n")
    assert result.returncode == 0
    assert target.read_text() == "A=1\n"
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _, target = _init_env(fresh, None)
    text = target.read_text()
    assert "SMTP_PASSWORD=\n" in text
    assert len(dict(line.split("=", 1) for line in text.splitlines() if "=" in line)["SECRET_KEY"]) == 64
