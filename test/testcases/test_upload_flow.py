"""Document upload end to end through Nginx, on the real stack (plan 03-16; E2E-04, DOC-01..07, DOC-16, STOR-01, STOR-11, SEC-06, TEN-13, D-09, D-11, D-14, D-20).

Nothing of devRag is replaced: the app, Nginx, MySQL, MinIO, Elasticsearch and Valkey are the running stack; the recording fake provider is only the
third party's end of the wire that a provider save needs. Every rejection is proven the same way: the MinIO listing under the tenant's prefix and the
dataset row counts are read before and after, and must be identical. Large bodies are written to a temporary file by block and removed after use.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.uploads import object_bytes, pdf_bytes, snapshot, sql, tenant_object_keys, tenant_row_counts, text_bytes
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import DATASETS, assert_clean, create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, api, join, keys_of, ok, registry  # noqa: F401  (registry is a fixture)

pytestmark = pytest.mark.e2e

UPLOAD = "/api/v1/documents/upload"
MIB = 1024 * 1024
MAX_FILE = 100 * MIB
DOC_KEYS = {"id", "name", "size", "type", "suffix", "run", "progress", "dataset_id", "created_by", "parser_id", "chunk_num", "token_num", "create_time", "update_time"}
BANNED = {"status", "source", "location", "thumbnail", "bucket", "key"}
STORAGE_KEY = re.compile(r"[0-9a-f]{32}/[0-9a-f]{32}")
LARGE = httpx.Timeout(600.0, connect=10.0)


def post_files(ingress: httpx.Client, token: str, dataset_id: str | None, files: list[tuple[str, tuple[str, Any, str]]], *, params: dict[str, str] | None = None) -> httpx.Response:
    """One multipart POST through Nginx. The answer must come from Python (Nginx's own refusals are asserted separately)."""
    ingress.cookies.clear()
    query = dict(params or {})
    if dataset_id is not None:
        query["dataset_id"] = dataset_id
    resp = ingress.post(UPLOAD, headers=_bearer(token), params=query, files=files, timeout=LARGE)
    assert resp.headers.get("x-api-source") == "python", (resp.status_code, resp.text[:200])
    return resp


def one(name: str, data: bytes | Any, mime: str = "application/pdf") -> tuple[str, tuple[str, Any, str]]:
    return ("file", (name, data, mime))


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def assert_no_storage_detail(resp: httpx.Response, tenant_id: str) -> None:
    assert keys_of(resp.json()).isdisjoint(BANNED), (keys_of(resp.json()) & BANNED, resp.text)
    assert STORAGE_KEY.search(resp.text) is None and f"{tenant_id}/" not in resp.text and "ragflow" not in resp.text.lower()
    assert_clean(resp)


def dataset_doc_num(ingress: httpx.Client, who: Account, dataset_id: str) -> int:
    return int(ok(api(ingress, "GET", f"{DATASETS}/{dataset_id}", who.token))["doc_num"])


@pytest.fixture
def space(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> tuple[Account, str]:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "upflow")
    return owner, ok(create(ingress, owner))["id"]


def printable_file(directory: Path, size: int) -> Path:
    """A text file of exactly ``size`` bytes written block by block (no NUL byte, so the text rule passes)."""
    block = (b"lorem ipsum dolor sit amet, consectetur adipiscing elit\n" * 20000)[:MIB]
    path = directory / f"body-{size}.txt"
    with path.open("wb") as handle:
        remaining = size
        while remaining > 0:
            piece = min(remaining, len(block))
            handle.write(block[:piece])
            remaining -= piece
    return path


@pytest.fixture
def big_dir(tmp_path: Path) -> Iterator[Path]:
    made = tmp_path / "big"
    made.mkdir()
    try:
        yield made
    finally:
        for leftover in made.iterdir():
            leftover.unlink()
        made.rmdir()


# ----------------------------------------------------------------------------- the happy path


def test_a_member_uploads_files_and_they_are_stored_under_generated_keys(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    pdf, txt = pdf_bytes("flow", 500), text_bytes("flow", 500)
    resp = post_files(ingress, owner.token, dataset_id, [one("Quarterly Plan.pdf", pdf), one("notes.txt", txt, "text/plain")])
    docs = ok(resp)
    assert [d["name"] for d in docs] == ["Quarterly Plan.pdf", "notes.txt"]
    assert all(set(d) == DOC_KEYS for d in docs)
    assert all(d["run"] == "0" and d["progress"] == 0.0 and d["dataset_id"] == dataset_id and d["created_by"] == owner.user_id for d in docs)
    assert docs[0]["size"] == len(pdf) and docs[0]["suffix"] == "pdf" and docs[1]["suffix"] == "txt" and docs[0]["parser_id"] == "naive"
    assert_no_storage_detail(resp, owner.tenant_id)

    keys = tenant_object_keys(owner.tenant_id)
    assert len(keys) == 2 and all(re.fullmatch(f"{owner.tenant_id}/[0-9a-f]" + "{32}", k) for k in keys)
    assert not any("quarterly" in k.lower() for k in keys), "the client name is never part of a key"
    assert {object_bytes(k) for k in keys} == {pdf, txt}
    assert tenant_row_counts(owner.tenant_id) == {"file": 2, "document": 2, "file2document": 2, "doc_num": 2}
    assert dataset_doc_num(ingress, owner, dataset_id) == 2
    assert sql("SELECT COUNT(*) FROM `document` WHERE `kb_id` = %s AND `run` = '0' AND `progress` = 0", (dataset_id,))[0][0] == 2


def test_identical_content_and_repeated_names_over_http(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    data = pdf_bytes("dup", 400)
    first = ok(post_files(ingress, owner.token, dataset_id, [one("report.pdf", data)]))
    second = ok(post_files(ingress, owner.token, dataset_id, [one("report.pdf", data)]))
    assert first[0]["name"] == "report.pdf" and second[0]["name"] == "report(1).pdf", "kept and renamed, never overwritten"
    assert len(tenant_object_keys(owner.tenant_id)) == 1, "identical bytes share one verified blob"
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}

    both = ok(post_files(ingress, owner.token, dataset_id, [one("x.pdf", pdf_bytes("a")), one("x.pdf", pdf_bytes("b"))]))
    assert [d["name"] for d in both] == ["x.pdf", "x(1).pdf"]
    assert len(tenant_object_keys(owner.tenant_id)) == 3


def test_a_per_document_parser_override_is_taken_from_the_query(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    plain = ok(post_files(ingress, owner.token, dataset_id, [one("a.pdf", pdf_bytes("a"))]))[0]
    over = ok(post_files(ingress, owner.token, dataset_id, [one("b.pdf", pdf_bytes("b"))], params={"parser_id": "book", "parser_config": '{"chunk_token_num": 128}'}))[0]
    assert plain["parser_id"] == "naive" and over["parser_id"] == "book"
    before = snapshot(owner.tenant_id)
    for params in ({"parser_id": "bogus"}, {"parser_config": "not json"}, {"parser_config": "[1]"}, {"parser_config": '{"k": "' + "v" * 4100 + '"}'}):
        bad = post_files(ingress, owner.token, dataset_id, [one("c.pdf", pdf_bytes("c"))], params=params)
        assert bad.status_code == 400 and reason_of(bad) == "parser_invalid", (params, bad.text[:200])
    assert snapshot(owner.tenant_id) == before


def test_parallel_uploads_of_one_name_give_x_and_x_1(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space

    def attempt(tag: str) -> httpx.Response:
        with httpx.Client(base_url=BASE_URL, timeout=LARGE) as client:
            return client.post(UPLOAD, headers=_bearer(owner.token), params={"dataset_id": dataset_id}, files=[one("x.pdf", pdf_bytes(tag))])

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(attempt, ["left", "right"]))
    assert [a.status_code for a in answers] == [200, 200], [a.text[:200] for a in answers]
    assert sorted(ok(a)[0]["name"] for a in answers) == ["x(1).pdf", "x.pdf"]
    assert dataset_doc_num(ingress, owner, dataset_id) == 2


# ----------------------------------------------------------------------------- rejections store nothing

BAD_UPLOADS = [
    pytest.param("run.exe", b"MZ\x90\x00binary", "application/octet-stream", "unsupported_type", id="exe"),
    pytest.param("pic.gif", b"GIF89a" + b"\x00" * 20, "image/gif", "unsupported_type", id="gif-is-not-allowed"),
    pytest.param("invoice.pdf.exe", b"%PDF-1.4\nabc", "application/pdf", "unsupported_type", id="double-extension"),
    pytest.param("fake.pdf", b"this is not a pdf", "application/pdf", "unsupported_type", id="wrong-magic"),
    pytest.param("notes.txt", b"abc\x00def", "text/plain", "unsupported_type", id="nul-in-text"),
    pytest.param("../../etc/passwd.pdf", b"%PDF-1.4\nabc", "application/pdf", "invalid_filename", id="traversal"),
    pytest.param("..\\..\\boot.pdf", b"%PDF-1.4\nabc", "application/pdf", "invalid_filename", id="backslash-traversal"),
    pytest.param("empty.pdf", b"", "application/pdf", "empty_file", id="empty-file"),
]


@pytest.mark.parametrize(("name", "data", "mime", "reason"), BAD_UPLOADS)
def test_a_refused_file_is_400_with_a_reason_and_nothing_is_stored(ingress: httpx.Client, space, name: str, data: bytes, mime: str, reason: str) -> None:
    owner, dataset_id = space
    before = snapshot(owner.tenant_id)
    resp = post_files(ingress, owner.token, dataset_id, [one(name, data, mime)])
    assert resp.status_code == 400 and reason_of(resp) == reason, resp.text[:300]
    assert snapshot(owner.tenant_id) == before, "the MinIO listing and the row counts are unchanged"
    assert "passwd" not in resp.text and "boot" not in resp.text, "the message does not echo the file name"


def test_one_bad_file_rejects_the_whole_request(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    before = snapshot(owner.tenant_id)
    resp = post_files(ingress, owner.token, dataset_id, [one("good.pdf", pdf_bytes("g")), one("bad.exe", b"MZ", "application/octet-stream"), one("good2.txt", text_bytes("g2"), "text/plain")])
    assert resp.status_code == 400 and reason_of(resp) == "unsupported_type"
    assert snapshot(owner.tenant_id) == before
    assert dataset_doc_num(ingress, owner, dataset_id) == 0


def test_no_files_and_malformed_bodies_are_400_no_files(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    before = snapshot(owner.tenant_id)
    ingress.cookies.clear()
    headers = _bearer(owner.token)
    cases = {
        "json body": {"content": b'{"a": 1}', "headers": {**headers, "Content-Type": "application/json"}},
        "multipart without a boundary": {"content": b"--x\r\n\r\n", "headers": {**headers, "Content-Type": "multipart/form-data"}},
        "truncated multipart": {
            "content": b'--B\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n%PDF-1.4 par',
            "headers": {**headers, "Content-Type": "multipart/form-data; boundary=B"},
        },
        "empty body": {"content": b"", "headers": {**headers, "Content-Type": "multipart/form-data; boundary=B"}},
    }
    for label, request in cases.items():
        resp = ingress.post(UPLOAD, params={"dataset_id": dataset_id}, timeout=LARGE, **request)
        assert resp.status_code == 400 and reason_of(resp) == "no_files", (label, resp.status_code, resp.text[:200])
        assert resp.headers.get("x-api-source") == "python"
    wrong_field = ingress.post(UPLOAD, headers=headers, params={"dataset_id": dataset_id}, files=[("files", ("a.pdf", pdf_bytes("w"), "application/pdf"))], timeout=LARGE)
    assert wrong_field.status_code == 400 and reason_of(wrong_field) == "no_files"
    assert snapshot(owner.tenant_id) == before


def test_too_many_files_is_400_and_nothing_is_stored(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    limit = int(ok(api(ingress, "GET", f"{DATASETS}/{dataset_id}", owner.token))["upload_limits"]["max_files_per_request"])
    before = snapshot(owner.tenant_id)
    resp = post_files(ingress, owner.token, dataset_id, [one(f"f{i}.txt", text_bytes(str(i), 80), "text/plain") for i in range(limit + 1)])
    assert resp.status_code == 400 and reason_of(resp) == "too_many_files", resp.text[:200]
    assert snapshot(owner.tenant_id) == before


# ----------------------------------------------------------------------------- size limits


def test_a_file_one_byte_over_100_mib_is_413_file_too_large_from_the_server(ingress: httpx.Client, space, big_dir: Path) -> None:
    owner, dataset_id = space
    before = snapshot(owner.tenant_id)
    path = printable_file(big_dir, MAX_FILE + 1)
    with path.open("rb") as handle:
        resp = post_files(ingress, owner.token, dataset_id, [one("over.txt", handle, "text/plain")])
    assert resp.status_code == 413 and reason_of(resp) == "file_too_large", resp.text[:300]
    assert snapshot(owner.tenant_id) == before, "nothing was stored"
    assert dataset_doc_num(ingress, owner, dataset_id) == 0


def test_a_file_of_exactly_100_mib_is_accepted_and_not_cut_by_a_body_limit(ingress: httpx.Client, space, big_dir: Path) -> None:
    owner, dataset_id = space
    path = printable_file(big_dir, MAX_FILE)
    with path.open("rb") as handle:
        resp = post_files(ingress, owner.token, dataset_id, [one("limit.txt", handle, "text/plain")])
    docs = ok(resp)
    assert docs[0]["size"] == MAX_FILE and docs[0]["name"] == "limit.txt"
    (key,) = tenant_object_keys(owner.tenant_id)
    from test.helpers.uploads import minio_client

    stat = minio_client().stat_object("ragflow", key)
    assert stat.size == MAX_FILE
    assert dataset_doc_num(ingress, owner, dataset_id) == 1


def test_a_102_mib_body_is_refused_by_nginx_before_python(ingress: httpx.Client, space, big_dir: Path) -> None:
    owner, dataset_id = space
    before = snapshot(owner.tenant_id)
    path = printable_file(big_dir, 102 * MIB)
    ingress.cookies.clear()
    with path.open("rb") as handle:
        resp = ingress.post(UPLOAD, headers=_bearer(owner.token), params={"dataset_id": dataset_id}, files=[one("huge.txt", handle, "text/plain")], timeout=LARGE)
    assert resp.status_code == 413, resp.text[:200]
    assert resp.json() == {"code": 400, "message": "payload too large", "data": None}
    assert "x-api-source" not in resp.headers, "Nginx refused the body; the application never saw it"
    assert snapshot(owner.tenant_id) == before


# ----------------------------------------------------------------------------- who may upload where


def test_a_foreign_or_private_or_unknown_dataset_is_the_one_404_and_stores_nothing(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "upfor")
    member, stranger = registry.register(prefix="upmem"), registry.register(prefix="upstr")
    join(ingress, owner, member)
    private = ok(create(ingress, owner, "owner-private"))["id"]
    before_owner, before_stranger = snapshot(owner.tenant_id), snapshot(stranger.tenant_id)

    for who, dataset_id in [(stranger, private), (member, private), (owner, "0" * 32), (owner, "not-an-id"), (owner, "x" * 300)]:
        resp = post_files(ingress, who.token, dataset_id, [one("a.pdf", pdf_bytes("n"))])
        assert resp.json() == NOT_FOUND and resp.status_code == 404, (who.email, dataset_id)
    assert post_files(ingress, owner.token, None, [one("a.pdf", pdf_bytes("n"))]).json() == NOT_FOUND, "a missing dataset_id is the same 404"
    assert snapshot(owner.tenant_id) == before_owner and snapshot(stranger.tenant_id) == before_stranger
    assert tenant_object_keys(member.tenant_id) == []
    assert dataset_doc_num(ingress, owner, private) == 0


def test_a_404_does_not_wait_for_the_body_and_never_reads_it(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, big_dir: Path) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "upauth")
    stranger = registry.register(prefix="upauth2")
    private = ok(create(ingress, owner, "private"))["id"]
    path = printable_file(big_dir, 20 * MIB)
    with path.open("rb") as handle:
        resp = post_files(ingress, stranger.token, private, [one("big.txt", handle, "text/plain")])
    assert resp.json() == NOT_FOUND
    assert tenant_object_keys(owner.tenant_id) == [] and tenant_object_keys(stranger.tenant_id) == []


def test_a_team_member_uploads_into_a_team_dataset_but_not_into_anothers_private_one(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "upteam")
    member = registry.register(prefix="upteam2")
    join(ingress, owner, member)
    team = ok(create(ingress, owner, "shared", permission="team"))["id"]
    private = ok(create(ingress, owner, "mine"))["id"]

    by_member = post_files(ingress, member.token, team, [one("from-member.pdf", pdf_bytes("m"))])
    docs = ok(by_member)
    assert docs[0]["created_by"] == member.user_id and docs[0]["dataset_id"] == team
    assert len(tenant_object_keys(owner.tenant_id)) == 1 and tenant_object_keys(member.tenant_id) == [], "the blob belongs to the dataset's workspace"
    refused = post_files(ingress, member.token, private, [one("no.pdf", pdf_bytes("n"))])
    assert refused.json() == NOT_FOUND
    assert dataset_doc_num(ingress, owner, private) == 0


def test_an_api_token_uploads_into_its_own_workspace_only(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "uptok")
    other = workspace(ingress, registry, fake_provider_stack, "uptok2")
    mine, theirs = ok(create(ingress, owner))["id"], ok(create(ingress, other))["id"]
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]

    docs = ok(post_files(ingress, token, mine, [one("by-token.pdf", pdf_bytes("t"))]))
    assert docs[0]["dataset_id"] == mine and docs[0]["created_by"] == owner.user_id
    before = snapshot(other.tenant_id)
    foreign = post_files(ingress, token, theirs, [one("x.pdf", pdf_bytes("x"))])
    assert foreign.json() == NOT_FOUND and snapshot(other.tenant_id) == before
    assert len(tenant_object_keys(owner.tenant_id)) == 1


def test_an_upload_without_a_credential_is_refused(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    ingress.cookies.clear()
    before = snapshot(owner.tenant_id)
    resp = ingress.post(UPLOAD, params={"dataset_id": dataset_id}, files=[one("a.pdf", pdf_bytes("a"))], timeout=LARGE)
    assert resp.status_code == 401
    assert snapshot(owner.tenant_id) == before
