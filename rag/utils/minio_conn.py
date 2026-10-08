"""MinIO / S3 storage driver (plan 03-07, STOR-02, STOR-08, STOR-10).

The bucket is created on the first write (tolerating the BucketAlreadyOwnedByYou and BucketAlreadyExists race codes). Every
call runs through one pooled client with explicit connect and read timeouts and a small bounded retry.

Presigned GET URLs are implemented and tested but no public route exposes them in Phase 3: the URL embeds the internal MinIO
endpoint (host and port from the settings), which clients cannot reach and which must not be disclosed.

Error messages name the operation and bucket only; keys, credentials and server responses are never included.
"""
from __future__ import annotations

import io
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, BinaryIO

import urllib3
from minio import Minio
from minio.error import MinioException, S3Error

from rag.utils.storage_base import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PRESIGN_SECONDS,
    Storage,
    StorageError,
    StorageNotFound,
    validate_bucket,
    validate_key,
)

logger = logging.getLogger(__name__)

BUCKET_RACE_CODES = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")
ABSENT_CODES = ("NoSuchKey", "NoSuchObject", "NoSuchBucket", "NotFound")
PART_SIZE = 10 * 1024 * 1024
MAX_PRESIGN_SECONDS = 7 * 24 * 3600


class MinioStorage(Storage):
    def __init__(self, settings: Any) -> None:
        mn = settings.minio
        http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=30), retries=urllib3.Retry(total=2, backoff_factor=0.5))
        self._client = Minio(f"{mn.host}:{mn.port}", access_key=mn.user, secret_key=mn.password, secure=False, http_client=http)
        self._ready: set[str] = set()  # buckets known to exist; only successes are cached
        self._lock = threading.Lock()

    # -- helpers -------------------------------------------------------------------------------------------------------

    @contextmanager
    def _guard(self, operation: str, bucket: str) -> Iterator[None]:
        try:
            yield
        except StorageError:
            raise
        except S3Error as exc:
            logger.warning("storage %s failed", operation, extra={"bucket": bucket, "s3_code": exc.code})
            if exc.code in ABSENT_CODES:
                raise StorageNotFound(f"object not found in bucket {bucket}") from None
            raise StorageError(f"storage {operation} failed in bucket {bucket}") from None
        except (MinioException, urllib3.exceptions.HTTPError, OSError) as exc:
            logger.warning("storage %s failed", operation, extra={"bucket": bucket, "error_type": type(exc).__name__})
            raise StorageError(f"storage {operation} failed in bucket {bucket}") from None

    def _ensure_bucket(self, bucket: str) -> None:
        if bucket in self._ready:
            return
        with self._lock:
            if bucket in self._ready:
                return
            if not self._client.bucket_exists(bucket):
                try:
                    self._client.make_bucket(bucket)
                except S3Error as exc:
                    if exc.code not in BUCKET_RACE_CODES:  # lost a creation race: the bucket exists, carry on
                        raise
            self._ready.add(bucket)

    # -- Storage -------------------------------------------------------------------------------------------------------

    def put(self, bucket: str, key: str, data: bytes | BinaryIO, length: int | None = None) -> None:
        validate_bucket(bucket)
        validate_key(key)
        with self._guard("write", bucket):
            self._ensure_bucket(bucket)
            if isinstance(data, bytes | bytearray | memoryview):
                payload = bytes(data)
                self._client.put_object(bucket, key, io.BytesIO(payload), len(payload))
            elif length is not None:
                self._client.put_object(bucket, key, data, length)
            else:
                self._client.put_object(bucket, key, data, -1, part_size=PART_SIZE)

    def get(self, bucket: str, key: str) -> bytes:
        validate_bucket(bucket)
        validate_key(key)
        with self._guard("read", bucket):
            response = self._client.get_object(bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

    def iter_chunks(self, bucket: str, key: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
        validate_bucket(bucket)
        validate_key(key)
        if chunk_size <= 0:
            raise StorageError("chunk size must be positive")
        with self._guard("read", bucket):
            response = self._client.get_object(bucket, key)
        return self._stream(response, chunk_size, bucket)

    def _stream(self, response: Any, chunk_size: int, bucket: str) -> Iterator[bytes]:
        try:
            with self._guard("read", bucket):
                yield from response.stream(chunk_size)
        finally:
            response.close()
            response.release_conn()

    def rm(self, bucket: str, key: str) -> None:
        validate_bucket(bucket)
        validate_key(key)
        try:
            with self._guard("remove", bucket):
                self._client.remove_object(bucket, key)
        except StorageNotFound:
            return

    def _stat(self, bucket: str, key: str) -> Any | None:
        validate_bucket(bucket)
        validate_key(key)
        try:
            with self._guard("stat", bucket):
                return self._client.stat_object(bucket, key)
        except StorageNotFound:
            return None

    def exists(self, bucket: str, key: str) -> bool:
        return self._stat(bucket, key) is not None

    def size(self, bucket: str, key: str) -> int | None:
        stat = self._stat(bucket, key)
        return None if stat is None else int(stat.size)

    def bucket_exists(self, bucket: str) -> bool:
        validate_bucket(bucket)
        with self._guard("stat", bucket):
            return bool(self._client.bucket_exists(bucket))

    def presigned_get_url(self, bucket: str, key: str, expires_seconds: int = DEFAULT_PRESIGN_SECONDS) -> str:
        validate_bucket(bucket)
        validate_key(key)
        if not 1 <= expires_seconds <= MAX_PRESIGN_SECONDS:
            raise StorageError("invalid presigned URL lifetime")
        with self._guard("presign", bucket):
            return self._client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires_seconds))

    def health(self) -> bool:
        try:
            self._client.list_buckets()
        except (MinioException, urllib3.exceptions.HTTPError, OSError):
            return False
        return True
