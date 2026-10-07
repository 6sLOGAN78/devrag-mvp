"""Default-deny authentication gate, the Python twin of internal/handler/auth.go (D-11, D-21, D-30, R-114).

``before_request`` runs before routing, so an unknown path under a catch-all answers 401, not 404, and the
response never reveals which paths exist. The policy comes from the generated registry (``policy_for``): only
an explicit ``none`` row is public; anything unmatched is ``jwt``. Failure semantics:

* any credential failure is the one 401 envelope (no cause is distinguishable);
* a cookie-authenticated unsafe request whose Origin/Referer does not name this host is 403 (CSRF, D-21);
* an infrastructure error in credential resolution fails closed with the 503 envelope (R-114).

Tokens, cookies and Authorization headers are never logged: the only text logged is a coarse category.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from urllib.parse import urlsplit

from quart import Quart, Response, g, request

from api.apps.errors import forbidden_response, service_unavailable_response, unauthorized_response
from api.apps.route_policy_gen import policy_for
from api.db.services import auth_service
from api.db.services.auth_service import AuthInfrastructureError, Principal
from common.security.proxy import is_loopback_peer
from common.settings import Settings

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = "ragflow_auth"
LOOKUP_TIMEOUT_SECONDS = 5.0
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Credential types a route's auth value accepts. `jwt` is the access token only; `api` adds API tokens;
# `beta` adds the beta token (and, as in the reference, access and API tokens).
ACCEPTED_TYPES: dict[str, tuple[str, ...]] = {
    "jwt": (auth_service.AUTH_JWT,),
    "api": (auth_service.AUTH_JWT, auth_service.AUTH_API),
    "beta": (auth_service.AUTH_BETA, auth_service.AUTH_JWT, auth_service.AUTH_API),
}
_BEARER = "bearer "

Resolver = Callable[[str, tuple[str, ...]], Principal | None]


def _credential(allow_cookie: bool) -> tuple[str | None, bool]:
    """Authorization header (Bearer or raw) first; the cookie only on jwt routes and when no header is present (D-21)."""
    header = (request.headers.get("Authorization") or "").strip()
    if header:
        if len(header) >= len(_BEARER) and header[: len(_BEARER)].lower() == _BEARER:
            header = header[len(_BEARER):].strip()
        return header, False
    cookie = request.cookies.get(AUTH_COOKIE_NAME) if allow_cookie else None
    return (cookie, True) if cookie is not None else (None, False)


def _same_origin(allowed: tuple[str, ...]) -> bool:
    """Origin, else Referer, must name this request's host or an allowed origin; a missing or opaque one is refused."""
    raw = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not raw or raw == "null":
        return False
    parts = urlsplit(raw)
    if not parts.netloc or parts.scheme not in {"http", "https"}:
        return False
    if f"{parts.scheme}://{parts.netloc}".lower() in allowed:
        return True
    host = request.headers.get("Host", "")
    forwarded = request.headers.get("X-Forwarded-Host")
    if forwarded and is_loopback_peer(request.remote_addr):
        host = forwarded  # the same-container Nginx supplies the public host, port included (R-115)
    host = host.split(",")[0].strip()
    return parts.netloc.lower() == host.lower()


async def _resolve(resolver: Resolver, credential: str, types: tuple[str, ...]) -> tuple[Principal | None, str | None]:
    """Run the blocking resolver off the event loop. Returns ``(principal, failure_category)``."""
    try:
        principal = await asyncio.wait_for(asyncio.to_thread(resolver, credential, types), LOOKUP_TIMEOUT_SECONDS)
    except TimeoutError:
        return None, "timeout"
    except AuthInfrastructureError:
        return None, "dependency"
    except Exception:
        return None, "unexpected"  # fail closed: an unknown failure is never a credential verdict
    return principal, None


def register_auth_gate(app: Quart, settings: Settings, resolver: Resolver) -> None:
    allowed_origins = tuple(origin.lower().rstrip("/") for origin in settings.cors.allowed_origins)
    secret = settings.security.secret_key
    app.extensions["principal_resolver"] = resolver

    @app.before_request
    async def _gate() -> Response | None:
        if request.method == "OPTIONS":
            return None  # CORS preflight carries no credentials
        policy = policy_for(request.method, request.path)
        if policy.auth == "none":
            return None
        types = ACCEPTED_TYPES.get(policy.auth)
        if types is None:
            return unauthorized_response()
        credential, via_cookie = _credential(allow_cookie=policy.auth == "jwt")
        if credential is None:
            return unauthorized_response()
        if via_cookie and request.method not in SAFE_METHODS and not _same_origin(allowed_origins):
            return forbidden_response()
        if not auth_service.precheck(credential, types, secret):
            return unauthorized_response()  # signature, age, AUTH-08 and shape: no database is touched (T-02-59)
        principal, failure = await _resolve(resolver, credential, types)
        if failure is not None:
            logger.error("auth gate: infrastructure failure", extra={"category": failure})
            return service_unavailable_response()
        if principal is None:
            return unauthorized_response()
        g.principal = principal
        return None
