"""WR-03 live: an upstream failure on the token family leaves no request line in the Nginx error log.

A second, throwaway Nginx runs inside the app container on a spare loopback port. Its locations are the
GENERATED ones from docker/nginx/ragflow.conf with the upstream pointed at a closed port, so every request
fails the way a restarting Go process would. A control location without the error_log override proves the
leak exists, so the assertion on the credential family cannot pass vacuously.
"""
from __future__ import annotations

import re
import subprocess

import pytest

from test.conftest import REPO_ROOT
from test.testcases.conftest import DOCKER, PROJECT, exec_app

pytestmark = pytest.mark.e2e

WORK = "/tmp/wr03"
PORT = 18099
FAKE_TOKEN = "ragflow-fake0token0for0wr03testsABCDEFG"  # obviously not a credential


def _put(path: str, text: str) -> None:
    proc = subprocess.run(
        [DOCKER, "compose", "-p", PROJECT, "exec", "-T", "app", "sh", "-c", f"cat > {path}"],
        input=text, capture_output=True, text=True, check=False, timeout=60, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr


def _token_block() -> str:
    conf = (REPO_ROOT / "docker/nginx/ragflow.conf").read_text(encoding="utf-8")
    m = re.search(r"    location \^~ /api/v1/system/tokens/ \{.*?\n    \}\n", conf, re.S)
    assert m
    return m.group(0).replace("127.0.0.1:9384", "127.0.0.1:1")


def test_upstream_failure_does_not_log_the_token_bearing_request_line() -> None:
    block = _token_block()
    assert "error_log /dev/stderr emerg;" in block
    protected = block.replace("/dev/stderr", f"{WORK}/family.log")
    control = block.replace("/api/v1/system/tokens/", "/control/").replace("        error_log /dev/stderr emerg;\n", "")
    config = (
        f"worker_processes 1;\nerror_log {WORK}/global.log warn;\npid {WORK}/nginx.pid;\nevents {{}}\n"
        f"http {{\n    access_log off;\n    server {{\n        listen 127.0.0.1:{PORT};\n{protected}{control}    }}\n}}\n"
    )
    proxy = (REPO_ROOT / "docker/nginx/proxy.conf").read_text(encoding="utf-8")
    assert exec_app("sh", "-c", f"rm -rf {WORK} && mkdir -p {WORK}").returncode == 0
    try:
        _put(f"{WORK}/proxy.conf", proxy)
        _put(f"{WORK}/nginx.conf", config)
        start = exec_app("nginx", "-c", f"{WORK}/nginx.conf", "-p", f"{WORK}/")
        assert start.returncode == 0, start.stderr[-400:]
        for prefix in ("/api/v1/system/tokens/", "/control/"):
            hit = exec_app("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "DELETE", f"http://127.0.0.1:{PORT}{prefix}{FAKE_TOKEN}")
            assert hit.stdout.strip() == "502", hit.stdout + hit.stderr
        global_log = exec_app("cat", f"{WORK}/global.log").stdout
        family_log = exec_app("cat", f"{WORK}/family.log").stdout
        assert f"/control/{FAKE_TOKEN}" in global_log, "control: the error log really does record the request line"
        assert "/api/v1/system/tokens/" not in global_log
        assert FAKE_TOKEN not in family_log
        assert "request:" not in family_log
    finally:
        exec_app("sh", "-c", f"[ -f {WORK}/nginx.pid ] && kill $(cat {WORK}/nginx.pid); rm -rf {WORK}")
