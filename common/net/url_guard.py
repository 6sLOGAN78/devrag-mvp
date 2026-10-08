"""Outbound base-URL guard for model providers (plan 03-02, SSRF, Pitfall 13, D-15, D-16).

A workspace admin supplies the base URL a provider client will call. ``validate_base_url`` decides, before the URL is
saved and again before it is used, whether the server may open a connection to it:

* only ``http`` and ``https``, no user name or password, no fragment, a real host and a sane port;
* link-local (169.254.0.0/16, fe80::/10) and cloud metadata addresses are never allowed;
* the project's own service names (mysql, redis, es01, minio, mailpit, app) and any caller-supplied host are never allowed;
* loopback, RFC 1918, unique-local, carrier-grade NAT and every other non-global range only when ``allow_private`` is true.

Every spelling is judged by the address it resolves to, not by the text: decimal (``2852039166``), hex (``0xa9fea9fe``),
octal, short (``127.1``) and IPv4-mapped (``::ffff:169.254.169.254``) forms are parsed to an address first, and IPv6
forms that embed an IPv4 address (IPv4-compatible, NAT64, 6to4) are judged by the embedded address too. A host name with
several records is denied if any record is denied.

The module never makes an HTTP request. Name resolution goes through the injected ``resolve`` function (the default wraps
``socket.getaddrinfo``, which has no timeout of its own: callers run it inside their bounded executor).

Residual risk (T-03-02-02): the provider SDK clients open their own connections, so the address checked here cannot be
pinned to the connection. ``assert_unchanged`` re-validates at call time to shrink the DNS-rebinding window between save and
use, but a rebind between that check and the connect is accepted and recorded.

Error messages carry only a fixed reason and never the URL, so a credential in a mistyped URL cannot reach a log.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Collection
from dataclasses import dataclass
from urllib.parse import urlsplit

INTERNAL_SERVICE_HOSTS = frozenset({"mysql", "redis", "es01", "minio", "mailpit", "app"})
REASONS = ("scheme", "userinfo", "fragment", "host", "link_local", "internal_service", "private", "unresolvable")
_MAX_URL = 2048
_DEFAULT_PORTS = {"http": 80, "https": 443}
# Metadata endpoints that are not inside a link-local range: AWS IPv6, Alibaba, Oracle.
_METADATA = frozenset(ipaddress.ip_address(a) for a in ("169.254.169.254", "fd00:ec2::254", "100.100.100.200", "192.0.0.192"))
_NUMERIC_LAST_LABEL = re.compile(r"\d+|0[xX][0-9a-fA-F]*")
_NAT64 = bytes.fromhex("0064ff9b") + bytes(8)
_PRIORITY = ("link_local", "host", "private")

Resolver = Callable[[str, int], list[str]]


class UnsafeBaseUrl(ValueError):
    """The base URL may not be used. ``reason`` is one of ``REASONS``; the message never contains the URL."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"base URL rejected: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _default_resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise OSError("lookup failed") from exc
    return [str(info[4][0]) for info in infos]


def _parse_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(text.split("%", 1)[0])


def _numeric_host(host: str) -> ipaddress.IPv4Address | None:
    """Parse the legacy IPv4 spellings (decimal, hex, octal, short) the way the C library does, locally."""
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def _candidates(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """The address itself plus any IPv4 address it embeds, so a wrapped metadata address is still seen."""
    found: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [addr]
    if isinstance(addr, ipaddress.IPv6Address):
        raw = addr.packed
        if addr.ipv4_mapped is not None:
            found.append(addr.ipv4_mapped)
        elif raw[:12] == bytes(12):
            found.append(ipaddress.IPv4Address(raw[12:]))
        elif raw[:12] == _NAT64:
            found.append(ipaddress.IPv4Address(raw[12:]))
        elif raw[:2] == bytes.fromhex("2002"):
            found.append(ipaddress.IPv4Address(raw[2:6]))
    return found


def _reason_for(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if addr in _METADATA or addr.is_link_local:
        return "link_local"
    if addr.is_loopback:
        return "private"
    if addr.is_unspecified or addr.is_multicast or addr.is_reserved:
        return "host"
    if addr.is_private or not addr.is_global:
        return "private"
    return None


def _judge(addresses: list[str], *, allow_private: bool) -> None:
    reasons: set[str] = set()
    for text in addresses:
        for candidate in _candidates(_parse_address(text)):
            reason = _reason_for(candidate)
            if reason is not None and not (reason == "private" and allow_private):
                reasons.add(reason)
    for reason in _PRIORITY:
        if reason in reasons:
            raise UnsafeBaseUrl(reason)


def _addresses_of(host: str, port: int, resolve: Resolver | None) -> list[str]:
    if ":" in host:
        try:
            return [str(_parse_address(host))]
        except ValueError:
            raise UnsafeBaseUrl("host") from None
    try:
        return [str(ipaddress.IPv4Address(host))]
    except ValueError:
        pass
    if _NUMERIC_LAST_LABEL.fullmatch(host.rsplit(".", 1)[-1]):
        numeric = _numeric_host(host)
        if numeric is None:
            raise UnsafeBaseUrl("host")
        return [str(numeric)]
    if host == "localhost" or host.endswith(".localhost"):
        return ["127.0.0.1", "::1"]
    try:
        found = (resolve or _default_resolve)(host, port)
    except (OSError, UnicodeError):
        raise UnsafeBaseUrl("unresolvable") from None
    if not found:
        raise UnsafeBaseUrl("unresolvable")
    try:
        return [str(_parse_address(a)) for a in found]
    except ValueError:
        raise UnsafeBaseUrl("unresolvable") from None


def validate_base_url(
    url: str,
    *,
    allow_private: bool,
    deny_hosts: Collection[str] = (),
    resolve: Resolver | None = None,
) -> ValidatedUrl:
    """Return the validated URL or raise ``UnsafeBaseUrl``. Resolution is injectable so tests need no network."""
    text = url.strip()
    if not text or len(text) > _MAX_URL or any(ord(c) <= 0x20 or ord(c) == 0x7F or c == "\\" for c in text):
        raise UnsafeBaseUrl("host")
    try:
        parts = urlsplit(text)
        port = parts.port
        hostname = parts.hostname
    except ValueError:
        raise UnsafeBaseUrl("host") from None
    if parts.scheme not in _DEFAULT_PORTS:
        raise UnsafeBaseUrl("scheme")
    if "@" in parts.netloc:
        raise UnsafeBaseUrl("userinfo")
    if "#" in text:
        raise UnsafeBaseUrl("fragment")
    host = (hostname or "").split("%", 1)[0].rstrip(".")
    if not host or not host.isascii() or (port is not None and port < 1):
        raise UnsafeBaseUrl("host")
    port = port if port is not None else _DEFAULT_PORTS[parts.scheme]
    denied = {h.strip().lower().rstrip(".") for h in deny_hosts} | INTERNAL_SERVICE_HOSTS
    if host in denied:
        raise UnsafeBaseUrl("internal_service")
    addresses = _addresses_of(host, port, resolve)
    if denied.intersection(addresses):
        raise UnsafeBaseUrl("internal_service")
    _judge(addresses, allow_private=allow_private)
    return ValidatedUrl(url=text.rstrip("/"), host=host, port=port, addresses=tuple(sorted(set(addresses))))


def assert_unchanged(
    validated: ValidatedUrl,
    url: str,
    *,
    allow_private: bool,
    deny_hosts: Collection[str] = (),
    resolve: Resolver | None = None,
) -> ValidatedUrl:
    """Re-validate at call time (DNS-rebinding check); raise ``UnsafeBaseUrl`` if the target is no longer allowed."""
    current = validate_base_url(url, allow_private=allow_private, deny_hosts=deny_hosts, resolve=resolve)
    if current.host != validated.host or current.port != validated.port:
        raise UnsafeBaseUrl("host")
    return current
