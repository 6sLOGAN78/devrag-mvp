"""Local storage driver and the shared key scheme (plan 03-07, STOR-06, STOR-11, SEC-06)."""
from __future__ import annotations

import io
import os
import re
import stat

import pytest
from rag.utils.local_conn import LocalStorage
from rag.utils.storage_base import Storage, StorageError, StorageNotFound, StorageNotSupported, new_object_key, validate_key

pytestmark = pytest.mark.unit

TENANT = "0123456789abcdef0123456789abcdef"
BUCKET = "ragflow"
BAD_KEYS = ["../x", "a/../../x", "a/./b", "/abs", "a\\b", "a\x00b", "a\nb", "", "a//b", "a/", "x" * 300]


@pytest.fixture
def store(tmp_path):
    return LocalStorage(tmp_path / "base")


def test_is_a_storage(store):
    assert isinstance(store, Storage)


def test_round_trip(store):
    key = new_object_key(TENANT)
    assert store.exists(BUCKET, key) is False
    assert store.size(BUCKET, key) is None
    store.put(BUCKET, key, b"hello world")
    assert store.get(BUCKET, key) == b"hello world"
    assert store.exists(BUCKET, key) is True
    assert store.size(BUCKET, key) == 11
    store.rm(BUCKET, key)
    assert store.exists(BUCKET, key) is False
    store.rm(BUCKET, key)  # idempotent


def test_put_overwrites(store):
    key = new_object_key(TENANT)
    store.put(BUCKET, key, b"one")
    store.put(BUCKET, key, b"two-longer")
    assert store.get(BUCKET, key) == b"two-longer"


def test_put_stream_and_length_check(store):
    key = new_object_key(TENANT)
    store.put(BUCKET, key, io.BytesIO(b"abcdef"), length=6)
    assert store.get(BUCKET, key) == b"abcdef"
    other = new_object_key(TENANT)
    with pytest.raises(StorageError):
        store.put(BUCKET, other, io.BytesIO(b"abcdef"), length=99)
    assert store.exists(BUCKET, other) is False


def test_get_missing_is_not_found(store):
    with pytest.raises(StorageNotFound):
        store.get(BUCKET, new_object_key(TENANT))
    with pytest.raises(StorageNotFound):
        list(store.iter_chunks(BUCKET, new_object_key(TENANT)))


def test_iter_chunks_yields_requested_sizes(store):
    key = new_object_key(TENANT)
    payload = bytes(range(256)) * 10
    store.put(BUCKET, key, payload)
    chunks = list(store.iter_chunks(BUCKET, key, chunk_size=1000))
    assert [len(c) for c in chunks] == [1000, 1000, 560]
    assert b"".join(chunks) == payload
    with pytest.raises(StorageError):
        store.iter_chunks(BUCKET, key, chunk_size=0)


@pytest.mark.parametrize("bad", BAD_KEYS)
def test_bad_keys_are_rejected_before_any_filesystem_call(store, tmp_path, bad):
    with pytest.raises(StorageError):
        validate_key(bad)
    for call in (
        lambda: store.put(BUCKET, bad, b"x"),
        lambda: store.get(BUCKET, bad),
        lambda: store.rm(BUCKET, bad),
        lambda: store.exists(BUCKET, bad),
        lambda: store.size(BUCKET, bad),
        lambda: store.iter_chunks(BUCKET, bad),
    ):
        with pytest.raises(StorageError):
            call()
    assert not (tmp_path / "base").exists()


@pytest.mark.parametrize("bad", ["", "..", "A", "a/b", "../etc", "ab", "-abc", "x" * 64, "a\x00bc"])
def test_bad_buckets_are_rejected(store, bad):
    with pytest.raises(StorageError):
        store.put(bad, new_object_key(TENANT), b"x")
    with pytest.raises(StorageError):
        store.bucket_exists(bad)


def test_error_messages_do_not_echo_the_key(store):
    secret = "../super-secret-name"
    with pytest.raises(StorageError) as info:
        store.get(BUCKET, secret)
    assert secret not in str(info.value)


def test_symlinked_directory_pointing_outside_is_rejected(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim").write_bytes(b"secret")
    store.put(BUCKET, f"{TENANT}/seed", b"x")  # creates the bucket directory
    (tmp_path / "base" / BUCKET / "evil").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError):
        store.get(BUCKET, "evil/victim")
    with pytest.raises(StorageError):
        store.put(BUCKET, "evil/new", b"x")
    assert not (outside / "new").exists()
    assert (outside / "victim").read_bytes() == b"secret"
    with pytest.raises(StorageError):
        store.rm(BUCKET, "evil/victim")
    assert (outside / "victim").exists()


def test_symlinked_file_pointing_outside_is_rejected(store, tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"secret")
    store.put(BUCKET, f"{TENANT}/seed", b"x")
    (tmp_path / "base" / BUCKET / TENANT / "link").symlink_to(target)
    with pytest.raises(StorageError):
        store.get(BUCKET, f"{TENANT}/link")
    with pytest.raises(StorageError):
        store.put(BUCKET, f"{TENANT}/link", b"overwritten")
    assert target.read_bytes() == b"secret"


def test_symlinked_bucket_pointing_outside_is_rejected(store, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    (base / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError):
        store.put("linked", f"{TENANT}/k", b"x")
    assert list(outside.iterdir()) == []


def test_directories_are_0700_and_files_0600(store, tmp_path):
    key = new_object_key(TENANT)
    store.put(BUCKET, key, b"x")
    base = tmp_path / "base"
    for directory in (base, base / BUCKET, base / BUCKET / TENANT):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700, directory
    assert stat.S_IMODE((base / BUCKET / key).stat().st_mode) == 0o600


def test_crash_before_replace_leaves_no_partial_target(store, tmp_path, monkeypatch):
    key = new_object_key(TENANT)

    def boom(*_args, **_kwargs):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(StorageError):
        store.put(BUCKET, key, b"payload")
    monkeypatch.undo()
    assert store.exists(BUCKET, key) is False
    assert list((tmp_path / "base" / BUCKET / TENANT).iterdir()) == []


def test_crash_keeps_the_previous_content(store, monkeypatch):
    key = new_object_key(TENANT)
    store.put(BUCKET, key, b"old")
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("simulated crash")))
    with pytest.raises(StorageError):
        store.put(BUCKET, key, b"new")
    monkeypatch.undo()
    assert store.get(BUCKET, key) == b"old"


def test_presigned_urls_are_not_supported(store):
    with pytest.raises(StorageNotSupported):
        store.presigned_get_url(BUCKET, new_object_key(TENANT))


def test_bucket_exists_and_health(store, tmp_path):
    assert store.bucket_exists(BUCKET) is False
    store.put(BUCKET, new_object_key(TENANT), b"x")
    assert store.bucket_exists(BUCKET) is True
    assert store.health() is True


def test_new_object_key_shape_and_uniqueness():
    keys = {new_object_key(TENANT) for _ in range(50)}
    assert len(keys) == 50
    assert all(re.fullmatch(r"[0-9a-f]{32}/[0-9a-f]{32}", k) for k in keys)
    assert all(k.startswith(TENANT + "/") for k in keys)
    validate_key(next(iter(keys)))


@pytest.mark.parametrize("tenant", ["", "short", TENANT.upper(), TENANT + "0", "../" + TENANT[3:], "g" * 32])
def test_new_object_key_rejects_bad_tenant_ids(tenant):
    with pytest.raises(StorageError):
        new_object_key(tenant)
