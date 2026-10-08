"""MinIO storage driver against the live compose MinIO (plan 03-07, STOR-02, STOR-08, STOR-10).

Every bucket and object created here is recorded and removed by its recorded name only.
"""
from __future__ import annotations

import io
import threading
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from minio import Minio
from minio.error import S3Error
from rag.utils.minio_conn import MinioStorage
from rag.utils.storage_base import StorageError, StorageNotFound, new_object_key

from common.settings import MinioSettings
from test.conftest import stack_env

pytestmark = pytest.mark.integration

TENANT = "0123456789abcdef0123456789abcdef"
# S3 error codes a losing bucket-creation race returns: BucketAlreadyOwnedByYou (MinIO) or BucketAlreadyExists (other S3 servers).


@pytest.fixture(scope="module")
def minio_settings():
    env = stack_env()
    password = env.get("MINIO_PASSWORD")
    if not password:
        pytest.skip("docker/.env has no MINIO_PASSWORD")
    return MinioSettings(user=env.get("MINIO_USER", "rag_flow"), password=password, host="127.0.0.1", port=int(env.get("MINIO_PORT", "9000")))


@pytest.fixture(scope="module")
def admin(minio_settings):
    return Minio(f"{minio_settings.host}:{minio_settings.port}", access_key=minio_settings.user, secret_key=minio_settings.password, secure=False)


@pytest.fixture
def storage(minio_settings):
    class _Settings:
        minio = minio_settings

    return MinioStorage(_Settings())


@pytest.fixture
def temp_bucket(admin):
    """A bucket name that does not exist yet; whatever the test created is removed afterwards."""
    name = f"rf-test-{uuid.uuid4().hex[:8]}"
    created_keys: list[str] = []
    yield name, created_keys
    try:
        if admin.bucket_exists(name):
            for key in created_keys:
                admin.remove_object(name, key)
            admin.remove_bucket(name)
    except S3Error:
        pass
    assert not admin.bucket_exists(name), "test bucket was not cleaned up"


def test_first_write_creates_the_missing_bucket(storage, admin, temp_bucket):
    bucket, keys = temp_bucket
    assert admin.bucket_exists(bucket) is False
    assert storage.bucket_exists(bucket) is False
    key = new_object_key(TENANT)
    keys.append(key)
    storage.put(bucket, key, b"hello minio")
    assert admin.bucket_exists(bucket) is True
    assert storage.bucket_exists(bucket) is True


def test_round_trip_size_exists_rm(storage, temp_bucket):
    bucket, keys = temp_bucket
    key = new_object_key(TENANT)
    keys.append(key)
    payload = b"0123456789" * 1000
    assert storage.exists(bucket, key) is False
    assert storage.size(bucket, key) is None
    storage.put(bucket, key, payload)
    assert storage.get(bucket, key) == payload
    assert storage.size(bucket, key) == len(payload)
    assert storage.exists(bucket, key) is True
    chunks = list(storage.iter_chunks(bucket, key, chunk_size=4096))
    assert b"".join(chunks) == payload and max(len(c) for c in chunks) <= 4096
    storage.rm(bucket, key)
    assert storage.exists(bucket, key) is False
    storage.rm(bucket, key)  # idempotent: NoSuchKey is ignored


def test_missing_object_is_not_found(storage, temp_bucket):
    bucket, keys = temp_bucket
    key = new_object_key(TENANT)
    keys.append(key)
    storage.put(bucket, key, b"x")
    with pytest.raises(StorageNotFound):
        storage.get(bucket, new_object_key(TENANT))


def test_stream_with_known_length(storage, temp_bucket):
    bucket, keys = temp_bucket
    key = new_object_key(TENANT)
    keys.append(key)
    storage.put(bucket, key, io.BytesIO(b"streamed bytes"), length=len(b"streamed bytes"))
    assert storage.get(bucket, key) == b"streamed bytes"


def test_stream_with_unknown_length(storage, temp_bucket):
    bucket, keys = temp_bucket
    key = new_object_key(TENANT)
    keys.append(key)
    storage.put(bucket, key, io.BytesIO(b"unknown length"))
    assert storage.get(bucket, key) == b"unknown length"


def test_presigned_url_downloads_the_bytes_and_expires_in_3600(storage, temp_bucket):
    bucket, keys = temp_bucket
    key = new_object_key(TENANT)
    keys.append(key)
    storage.put(bucket, key, b"presigned payload")
    url = storage.presigned_get_url(bucket, key)
    assert parse_qs(urlsplit(url).query)["X-Amz-Expires"] == ["3600"]
    response = httpx.get(url, timeout=10)
    assert response.status_code == 200 and response.content == b"presigned payload"
    short = storage.presigned_get_url(bucket, key, expires_seconds=60)
    assert parse_qs(urlsplit(short).query)["X-Amz-Expires"] == ["60"]


def test_concurrent_first_writes_to_a_missing_bucket_both_succeed(minio_settings, admin, temp_bucket):
    """Two drivers race to create the bucket; the loser sees BucketAlreadyOwnedByYou or BucketAlreadyExists and must carry on."""
    bucket, keys = temp_bucket

    class _Settings:
        minio = minio_settings

    drivers = [MinioStorage(_Settings()), MinioStorage(_Settings())]
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    written = [new_object_key(TENANT), new_object_key(TENANT)]
    keys.extend(written)

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            drivers[index].put(bucket, written[index], f"writer-{index}".encode())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert drivers[0].get(bucket, written[1]) == b"writer-1"
    assert drivers[1].get(bucket, written[0]) == b"writer-0"
    assert admin.bucket_exists(bucket)


def test_losing_the_creation_race_is_tolerated(storage, admin, temp_bucket, monkeypatch):
    """Force the 'exists' check to say no after the bucket exists: make_bucket then returns BucketAlreadyOwnedByYou (or Exists)."""
    bucket, keys = temp_bucket
    admin.make_bucket(bucket)
    key = new_object_key(TENANT)
    keys.append(key)
    client = storage._client  # the one client the driver uses
    monkeypatch.setattr(client, "bucket_exists", lambda _name: False)
    storage.put(bucket, key, b"raced")
    monkeypatch.undo()
    assert storage.get(bucket, key) == b"raced"


def test_errors_do_not_leak_credentials_or_keys(minio_settings):
    class _Bad:
        minio = MinioSettings(user=minio_settings.user, password="definitely-wrong-password", host=minio_settings.host, port=minio_settings.port)

    driver = MinioStorage(_Bad())
    key = new_object_key(TENANT)
    with pytest.raises(StorageError) as info:
        driver.put("rf-test-denied", key, b"x")
    message = str(info.value)
    assert "definitely-wrong-password" not in message and key not in message and minio_settings.password not in message
