from __future__ import annotations

import json
import logging
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
