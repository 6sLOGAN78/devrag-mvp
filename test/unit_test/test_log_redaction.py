from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from common.log_utils import JsonFormatter, RedactingFilter, init_root_logger

pytestmark = pytest.mark.unit


def emit(msg: str, **extra) -> dict:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    for k, v in extra.items():
        setattr(record, k, v)
    RedactingFilter().filter(record)
    return json.loads(JsonFormatter().format(record))


def test_extra_secret_keys_masked():
    out = emit("hello", password="p1", api_key="k1", authorization="Bearer zzz", token="t1", secret="s1")
    for key in ("password", "api_key", "authorization", "token", "secret"):
        assert out[key] == "***"
    assert "p1" not in json.dumps(out) and "zzz" not in json.dumps(out)


def test_message_key_value_masked():
    out = emit("login failed password=abc user=bob")
    assert "abc" not in out["msg"]
    assert "password=***" in out["msg"]
    assert "user=bob" in out["msg"]


def test_json_style_and_header_masked():
    out = emit('payload {"api_key": "sk-123"} Authorization: Bearer abc.def')
    assert "sk-123" not in out["msg"] and "abc.def" not in out["msg"]


def test_nested_dict_extra_masked():
    out = emit("x", headers={"Authorization": "Bearer q", "ok": "fine"})
    assert out["headers"]["Authorization"] == "***" and out["headers"]["ok"] == "fine"


def test_structured_fields_present():
    out = emit("req", method="GET", path="/health", status=200, duration_ms=3)
    assert {"ts", "level", "logger", "msg"} <= out.keys()
    assert (out["method"], out["path"], out["status"], out["duration_ms"]) == ("GET", "/health", 200, 3)


def test_init_root_logger_writes_one_json_line_per_record(tmp_path, capsys):
    log = init_root_logger("svc", log_dir=str(tmp_path), level="INFO")
    log.info("started token=abc123", extra={"path": "/x"})
    for h in logging.getLogger().handlers:
        h.flush()
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["msg"] == "started token=***" and data["path"] == "/x"
    assert "abc123" not in (tmp_path / "svc.log").read_text()
    for h in list(logging.getLogger().handlers):
        h.close()
        logging.getLogger().removeHandler(h)


_VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "log_redaction_vectors.json").read_text())


@pytest.mark.parametrize("vec", _VECTORS, ids=[v["id"] for v in _VECTORS])
def test_shared_redaction_vectors(vec):
    from common.log_utils import redact_text

    out = redact_text(vec["input"])
    for secret in vec["secrets"]:
        assert secret not in out
    for kept in vec["keep"]:
        assert kept in out
    assert emit(vec["input"])["msg"] == out


def test_nested_list_and_tuple_secrets_masked():
    out = emit("x", items=[{"password": "hunter2-fake"}, ("token", "t-fake"), "password=in-list-fake"])
    dumped = json.dumps(out)
    for secret in ("hunter2-fake", "in-list-fake"):
        assert secret not in dumped


def test_x_api_key_header_extra_masked():
    out = emit("x", headers={"x-api-key": "k-fake", "ok": "fine"})
    assert out["headers"]["x-api-key"] == "***" and out["headers"]["ok"] == "fine"


_HOSTILE = {
    "a_run": "a" * 100000,
    "token_repeat": "token" * 20000,
    "password_equals_repeat": "password=" * 12000,
    "password_open_quote": 'password="' * 10000,
    "dash_run": "a-" * 50000,
    "cookie_colon_repeat": "cookie:" * 14000,
    "scheme_repeat": "a://" * 25000,
}
TIMING_BOUND_S = 0.25


@pytest.mark.parametrize("name", list(_HOSTILE), ids=list(_HOSTILE))
def test_hostile_100kb_line_redacts_in_bounded_time(name):
    from common.log_utils import redact_text

    started = time.perf_counter()
    redact_text(_HOSTILE[name])
    elapsed = time.perf_counter() - started
    assert elapsed < TIMING_BOUND_S, f"{name}: {elapsed:.3f}s"


def test_oversized_input_is_capped_with_marker():
    from common.log_utils import redact_text

    out = redact_text("x" * 200000)
    assert len(out) < 70000 and out.endswith("[truncated]")


def test_otp_and_reset_ticket_fields_masked():
    out = emit("reset otp=424242 reset_ticket=abcDEF123_-xyz", otp="424242", reset_ticket="abcDEF123_-xyz")
    assert out["otp"] == "***" and out["reset_ticket"] == "***"
    rendered = json.dumps(out)
    assert "424242" not in rendered and "abcDEF123" not in rendered
