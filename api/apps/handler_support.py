"""Shared plumbing for workspace-scoped handlers (plan 03-12; D-20, D-26, TEN-13).

* ``acting_scope``: the workspace a request acts in. An absent id is the caller's own workspace; a named workspace is honoured only for a
  signed-in member of it. ``None`` means "answer the one not-found body": it covers a malformed id, a foreign workspace, a pending
  invitation and a token asking for any workspace but its own.
* ``forbid_unless``: the coarse permission check against ``conf/permissions.yaml``.
* ``credentials_visible``: the single place that decides whether a response may show an address and ``last4``.
"""
from __future__ import annotations

import re

from quart import Response, g

from api.apps.errors import forbidden_response
from api.apps.permissions_gen import allowed
from api.db.services import tenant_scope
from api.db.services.tenant_scope import ActingScope
from api.utils.blocking import DB_EXECUTOR, run_blocking

_TENANT_ID = re.compile(r"[0-9a-f]{32}")
_LOOKUP_TIMEOUT_SECONDS = 5.0
_CREDENTIAL_SUBJECTS = frozenset({"owner", "admin"})


async def acting_scope(requested_tenant_id: str | None) -> ActingScope | None:
    """Resolve the workspace for the authenticated principal on ``g``; see the module note for ``None``."""
    if requested_tenant_id is not None and _TENANT_ID.fullmatch(requested_tenant_id) is None:
        return None
    return await run_blocking(DB_EXECUTOR, tenant_scope.resolve_scope, g.principal, requested_tenant_id, timeout=_LOOKUP_TIMEOUT_SECONDS)


def forbid_unless(scope: ActingScope, area: str, action: str) -> Response | None:
    """``None`` when the scope's subject may do ``action`` in ``area``, else the 403 answer."""
    return None if allowed(scope.subject, area, action) else forbidden_response()


def credentials_visible(scope: ActingScope) -> bool:
    """Whether a view may carry the provider address and ``last4``.

    Decided by the permission subject, never by the role: an API-token principal inherits its workspace owner's role, but its
    subject is ``api_token`` (or ``beta_token``), and a token must never read credentials (D-26, Pitfall 6).
    """
    return scope.subject in _CREDENTIAL_SUBJECTS
