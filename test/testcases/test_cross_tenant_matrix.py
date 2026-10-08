"""Cross-tenant isolation matrix, generated from the endpoints registry in conf/routes.yaml (plan 02-25).

Success criterion 5, TEN-01, TEN-02 (D-30, R-93): tenant B asking for tenant A's resource by A's real id receives exactly the
(status, code, message) it receives for a random nonexistent id, and A's data is unchanged afterwards. The rows are the registry's
implemented scope-tenant rows; a row with no fixture fails (T-02-121), and the guard itself is proven below against a synthetic
registry copy.

Callers tried against every row that carries an id: a stranger, a user with only a pending invitation to A, B's API token, and
(where the route has a tenant in the path) an admin and a normal member of A that lack the route's role. Ids are also supplied
in the other positions (query and body) and with B's own tenant in the path.
"""
from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import running_stack_fake_provider
from test.testcases._matrix_fixtures import (
    BUILDERS,
    NO_ID_CHECKS,
    Row,
    Target,
    World,
    build_world,
    coverage_problems,
    load_tenant_rows,
    random_value,
    resource_of,
    triple,
)
from test.testcases._routes import ROUTES_FILE
from test.testcases.conftest import BASE_URL

ROWS = load_tenant_rows()
ID_ROWS = [r for r in ROWS if r.params]
NO_ID_ROWS = [r for r in ROWS if not r.params]


@pytest.fixture(scope="module")
def world(ingress: httpx.Client) -> Iterator[World]:
    registry = AccountRegistry(BASE_URL)
    # A's provider points at the stack-mode fake provider, which lives as long as the world (the matrix is about isolation, not about a model).
    with running_stack_fake_provider() as fake, httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=False) as client:
        try:
            yield build_world(client, registry, fake)
        finally:
            registry.cleanup()


def _problems_for(row: Row) -> list[str]:
    return [p for p in coverage_problems([row]) if p.startswith(f"{row.key}:")]


def _random_ids(row: Row) -> list[dict[str, str]]:
    """Two or more complete sets of nonexistent ids (the token placeholder also has a well-formed variant)."""
    n = max(len(random_value(p)) for p in row.params)
    return [{p: random_value(p)[min(i, len(random_value(p)) - 1)] for p in row.params} for i in range(n)]


def _mixes(row: Row, real: dict[str, str]) -> Iterator[dict[str, str]]:
    """Every id set that contains at least one real id of A's, the others random (path position)."""
    names = list(row.params)
    for size in range(1, len(names) + 1):
        for chosen in itertools.combinations(names, size):
            yield {p: (real[p] if p in chosen else random_value(p)[0]) for p in names}


# --- the guard --------------------------------------------------------------------------------------------------


@pytest.mark.unit
def test_every_implemented_tenant_row_has_a_fixture() -> None:
    assert len(ROWS) >= 8, "the registry should list at least the eight Phase 2 scope-tenant rows"
    assert coverage_problems(ROWS) == []


@pytest.mark.unit
def test_guard_fails_a_row_with_path_parameters_and_no_builder(tmp_path: Path) -> None:
    rows = load_tenant_rows(_registry_with(tmp_path, {"method": "GET", "path": "/api/v1/synthetic/{thing_id}"}))
    problems = coverage_problems(rows)
    assert len(problems) == 1
    assert "GET /api/v1/synthetic/{thing_id}" in problems[0] and "BUILDERS" in problems[0]


@pytest.mark.unit
def test_guard_fails_a_row_without_path_parameters_and_no_isolation_check(tmp_path: Path) -> None:
    rows = load_tenant_rows(_registry_with(tmp_path, {"method": "POST", "path": "/api/v1/synthetic"}))
    problems = coverage_problems(rows)
    assert len(problems) == 1
    assert "POST /api/v1/synthetic" in problems[0] and "NO_ID_CHECKS" in problems[0]


@pytest.mark.unit
def test_guard_ignores_unimplemented_and_other_scopes_but_flags_stale_fixture_keys(tmp_path: Path) -> None:
    extra = [
        {"method": "GET", "path": "/api/v1/synthetic/{thing_id}", "implemented": False},
        {"method": "GET", "path": "/api/v1/synthetic-other/{thing_id}", "scope": "none"},
    ]
    assert coverage_problems(load_tenant_rows(_registry_with(tmp_path, *extra))) == []
    stale = coverage_problems(ROWS, {**BUILDERS, "GET /gone/{x}": BUILDERS["PATCH /api/v1/tenants/{tenant_id}"]}, NO_ID_CHECKS)
    assert len(stale) == 1 and "GET /gone/{x}" in stale[0]


def _registry_with(tmp_path: Path, *extra: dict[str, Any]) -> Path:
    data = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
    for row in extra:
        data["endpoints"].append({"owner": "go", "auth": "jwt", "roles": ["owner"], "scope": "tenant", "implemented": True, **row})
    out = tmp_path / "routes.yaml"
    out.write_text(yaml.safe_dump(data), encoding="utf-8")
    return out


# --- rows with path parameters ----------------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("row", ID_ROWS, ids=lambda r: r.key)
def test_cross_tenant_matrix_outsiders_see_the_not_found_answer(world: World, row: Row) -> None:
    problems = _problems_for(row)
    assert not problems, "; ".join(problems)
    target: Target = BUILDERS[row.key](world)
    before = world.snapshot()
    resource = resource_of(row)
    assert target.snapshot() == before[resource]
    client = world.client

    callers = [("stranger", world.b.token), ("b-api-token", world.b_api_token)]
    if "invite" not in row.roles:  # PATCH /tenants/{id} is the pending invitee's own route: answering is its purpose
        callers.append(("pending-invite", world.pending.token))
    for label, token in callers:
        variants = [triple(target.send(client, token, ids)) for ids in _random_ids(row)]
        baseline = variants[0]
        assert all(v == baseline for v in variants), f"{row.key} as {label}: the answer for a nonexistent id varies with the id: {variants}"
        if label == "b-api-token":
            # no tenant row accepts an API token (registry auth is jwt): the credential is refused before any lookup
            expected = 401 if row.auth == "jwt" else 404
            assert baseline[0] == expected, (row.key, label, baseline)
        else:
            assert baseline[0] == 404, (row.key, label, baseline)
        for ids in _mixes(row, target.real):
            got = triple(target.send(client, token, ids))
            assert got == baseline, f"{row.key} as {label} with real ids {sorted(k for k in ids if ids[k] == target.real.get(k))}: {got} differs from the nonexistent-id answer {baseline}"

    assert world.snapshot() == before, f"{row.key} changed tenant A's data"
    assert target.snapshot() == before[resource]


@pytest.mark.e2e
@pytest.mark.parametrize("row", ID_ROWS, ids=lambda r: r.key)
def test_cross_tenant_matrix_ids_in_other_positions_and_own_tenant_reach_nothing(world: World, row: Row) -> None:
    problems = _problems_for(row)
    assert not problems, "; ".join(problems)
    target = BUILDERS[row.key](world)
    client = world.client
    before = world.snapshot()
    smuggle_query = {"tenant_id": world.a.tenant_id, "user_id": world.victim.user_id, "token": str(world.a_tokens[0]["token"])}
    smuggle_body = {"tenant_id": world.a.tenant_id, "user_id": world.victim.user_id, "id": world.a.tenant_id, "owner_id": world.a.user_id}

    baseline = triple(target.send(client, world.b.token, _random_ids(row)[0]))
    # A's ids in query and body positions, with A's real ids in the path: still the nonexistent-id answer
    for kwargs in ({"query": smuggle_query}, {"extra_body": smuggle_body}, {"query": smuggle_query, "extra_body": smuggle_body}):
        assert triple(target.send(client, world.b.token, target.real, **kwargs)) == baseline, (row.key, sorted(kwargs))

    # B's own tenant in the path with A's other ids: may succeed for B's own data, must never touch or reveal A's
    if "tenant_id" in row.params:
        for ids in ({**target.real, "tenant_id": world.b.tenant_id}, {**{p: random_value(p)[0] for p in row.params}, "tenant_id": world.b.tenant_id}):
            for kwargs in ({}, {"query": smuggle_query, "extra_body": smuggle_body}):
                resp = target.send(client, world.b.token, ids, **kwargs)
                assert resp.status_code < 500, (row.key, resp.status_code)
                leaked = [v for v in world.a_identifiers() if v in resp.text]
                assert not leaked, f"{row.key} with B's own tenant revealed {len(leaked)} value(s) of tenant A"
    assert world.snapshot() == before, f"{row.key} changed tenant A's data"


@pytest.mark.e2e
@pytest.mark.parametrize("row", [r for r in ID_ROWS if "tenant_id" in r.params], ids=lambda r: r.key)
def test_cross_tenant_matrix_members_without_the_role_are_refused(world: World, row: Row) -> None:
    """An admin or normal member of A that lacks the route's role gets 403 (or 404 when nothing is pending), and nothing changes."""
    target = BUILDERS[row.key](world)
    before = world.snapshot()
    tried = 0
    for role, who in (("admin", world.admin), ("normal", world.normal)):
        if role in row.roles:
            continue
        expected = 403 if any(r in row.roles for r in ("owner", "admin", "normal")) else 404
        resp = target.send(world.client, who.token, target.real)
        assert resp.status_code == expected, f"{row.key} as {role}: HTTP {resp.status_code}, expected {expected}"
        tried += 1
    assert tried or {"admin", "normal"} <= set(row.roles), f"{row.key}: no authorisation variant ran"
    assert world.snapshot() == before


# --- rows without a path parameter ------------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("row", NO_ID_ROWS, ids=lambda r: r.key)
def test_cross_tenant_matrix_list_isolation_for_rows_without_ids(world: World, row: Row) -> None:
    problems = _problems_for(row)
    assert not problems, "; ".join(problems)
    before = world.snapshot()
    NO_ID_CHECKS[row.key](world)
    assert world.snapshot() == before, f"{row.key} changed tenant A's data"
