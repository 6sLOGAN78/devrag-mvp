"""Trust in reverse-proxy headers (R-114, R-115, R-116), identical to internal/common/clientip.go.

Inside the app container Nginx connects to Python over 127.0.0.1 and overwrites the X-Forwarded-* headers.
A loopback socket peer is therefore the trusted proxy; any other peer controls those headers itself.
"""
from __future__ import annotations

import ipaddress


def is_loopback_peer(remote_addr: str | None) -> bool:
    """True when the socket peer address is loopback (IPv4, IPv6 or IPv4-mapped IPv6)."""
    if not remote_addr:
        return False
    host = remote_addr.strip().strip("[]")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback
