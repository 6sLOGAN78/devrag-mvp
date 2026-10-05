import pytest

from test.helpers.wait import wait_until

pytestmark = pytest.mark.unit


def test_returns_first_truthy_value_after_n_polls():
    calls = {"n": 0}

    def predicate():
        calls["n"] += 1
        return "ready" if calls["n"] >= 3 else None

    assert wait_until(predicate, timeout=5.0, interval=0.001) == "ready"
    assert calls["n"] == 3


def test_timeout_message_contains_timeout_and_last_value():
    with pytest.raises(TimeoutError) as exc:
        wait_until(lambda: 0, timeout=0.01, interval=0.001, describe=lambda: "svc down")
    msg = str(exc.value)
    assert "0.01" in msg
    assert "last=0" in msg
    assert "svc down" in msg
