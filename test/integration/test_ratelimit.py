"""Fixed-window limiter against the real Valkey of the stack (plan 03-10; research security domain V13, T-03-10-05, T-03-10-06).

Keys carry a random suffix and are deleted by exact name afterwards.
"""

from __future__ import annotations

import secrets
import socket
from collections.abc import Iterator

import pytest
import valkey

from common.ratelimit import FixedWindowLimiter, RateLimited, RateLimitUnavailable
from common.settings import RedisSettings, load_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def keys() -> Iterator[list[str]]:
    names: list[str] = []
    yield names
    rd = load_settings().redis
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=2, socket_connect_timeout=2)
    try:
        for name in names:
            client.delete(name)
    finally:
        client.close()


def new_key(keys: list[str]) -> str:
    name = f"test-ratelimit:{secrets.token_hex(8)}"
    keys.append(name)
    return name


def test_the_hit_over_the_limit_raises_with_a_retry_time(keys: list[str]) -> None:
    limiter = FixedWindowLimiter(load_settings().redis)
    key = new_key(keys)
    limiter.hit(key, 2, 60)
    limiter.hit(key, 2, 60)
    with pytest.raises(RateLimited) as caught:
        limiter.hit(key, 2, 60)
    assert 1 <= caught.value.retry_after <= 60


def test_another_key_is_not_affected(keys: list[str]) -> None:
    limiter = FixedWindowLimiter(load_settings().redis)
    first, second = new_key(keys), new_key(keys)
    limiter.hit(first, 1, 60)
    with pytest.raises(RateLimited):
        limiter.hit(first, 1, 60)
    limiter.hit(second, 1, 60)


def test_the_window_is_set_once_and_not_extended_by_later_hits(keys: list[str]) -> None:
    rd = load_settings().redis
    limiter = FixedWindowLimiter(rd)
    key = new_key(keys)
    limiter.hit(key, 5, 60)
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=2, socket_connect_timeout=2)
    try:
        first = client.ttl(key)
        limiter.hit(key, 5, 600)
        second = client.ttl(key)
    finally:
        client.close()
    assert 0 < second <= first <= 60


def closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_an_unreachable_valkey_fails_closed() -> None:
    limiter = FixedWindowLimiter(RedisSettings(host="127.0.0.1", port=closed_port(), password="", db=0))
    with pytest.raises(RateLimitUnavailable):
        limiter.hit(f"test-ratelimit:{secrets.token_hex(8)}", 5, 60)


def test_a_wrong_password_fails_closed(keys: list[str]) -> None:
    rd = load_settings().redis
    wrong = RedisSettings(host=rd.host, port=rd.port, password="-".join(("not", "the", "password")), db=rd.db)
    if not rd.password:
        pytest.skip("the stack's Valkey has no password, so a wrong one is accepted")
    with pytest.raises(RateLimitUnavailable):
        FixedWindowLimiter(wrong).hit(new_key(keys), 5, 60)
