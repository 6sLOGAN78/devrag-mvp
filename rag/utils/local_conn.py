"""Local filesystem storage driver (plan 03-07, STOR-06, SEC-06).

Every path is built from a validated bucket and key, resolved (following symlinks) and required to stay under the resolved base
directory, so no key can address a file outside it. Directories are created 0o700, files 0o600, and writes go to a sibling
temp file that is atomically renamed, so a crash never leaves a partial target.
"""
from __future__ import annotations

import errno
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from rag.utils.storage_base import DEFAULT_CHUNK_SIZE, Storage, StorageError, StorageNotFound, StorageNotSupported, validate_bucket, validate_key

DIR_MODE = 0o700
FILE_MODE = 0o600


class LocalStorage(Storage):
    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self._base = Path(base_dir)

    # -- path handling -------------------------------------------------------------------------------------------------

    def sanitize_path(self, bucket: str, key: str | None = None) -> Path:
        """Resolved absolute path for ``bucket`` (and ``key``), guaranteed to be inside the base directory."""
        validate_bucket(bucket)
        if key is not None:
            validate_key(key)
        base = self._base.resolve()
        candidate = Path(base, bucket, key) if key is not None else Path(base, bucket)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(base) or (key is None and resolved == base):
            raise StorageError("path escapes the storage base directory")
        return resolved

    def _make_dirs(self, directory: Path) -> None:
        """Create ``directory`` and any missing parents inside the base directory, every new level 0o700."""
        base = self._base.resolve()
        missing: list[Path] = []
        current = directory
        while current != base and not current.exists():
            missing.append(current)
            current = current.parent
        if not self._base.exists():
            self._base.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
            os.chmod(self._base, DIR_MODE)
        for path in reversed(missing):
            try:
                path.mkdir(mode=DIR_MODE)
            except FileExistsError:
                continue
            os.chmod(path, DIR_MODE)

    # -- Storage -------------------------------------------------------------------------------------------------------

    def put(self, bucket: str, key: str, data: bytes | BinaryIO, length: int | None = None) -> None:
        target = self.sanitize_path(bucket, key)
        if target.is_dir():
            raise StorageError(f"write failed in bucket {bucket}")
        try:
            self._make_dirs(target.parent)
            tmp = target.parent / f".tmp.{uuid.uuid4().hex}"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        except OSError as exc:
            raise StorageError(f"write failed in bucket {bucket}") from exc
        try:
            with os.fdopen(fd, "wb") as handle:
                written = self._copy(data, handle)
            if length is not None and written != length:
                raise StorageError(f"write failed in bucket {bucket}: length mismatch")
            os.replace(tmp, target)
        except StorageError:
            tmp.unlink(missing_ok=True)
            raise
        except BaseException as exc:
            tmp.unlink(missing_ok=True)
            if isinstance(exc, OSError):
                raise StorageError(f"write failed in bucket {bucket}") from exc
            raise

    @staticmethod
    def _copy(data: bytes | BinaryIO, handle: BinaryIO) -> int:
        if isinstance(data, bytes | bytearray | memoryview):
            handle.write(data)
            return len(data)
        total = 0
        while chunk := data.read(DEFAULT_CHUNK_SIZE):
            handle.write(chunk)
            total += len(chunk)
        return total

    def get(self, bucket: str, key: str) -> bytes:
        path = self.sanitize_path(bucket, key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageNotFound(f"object not found in bucket {bucket}") from exc
        except OSError as exc:
            raise StorageError(f"read failed in bucket {bucket}") from exc

    def iter_chunks(self, bucket: str, key: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
        path = self.sanitize_path(bucket, key)  # validated eagerly, before the generator is created
        if chunk_size <= 0:
            raise StorageError("chunk size must be positive")
        try:
            handle = path.open("rb")
        except FileNotFoundError as exc:
            raise StorageNotFound(f"object not found in bucket {bucket}") from exc
        except OSError as exc:
            raise StorageError(f"read failed in bucket {bucket}") from exc
        return self._stream(handle, chunk_size, bucket)

    @staticmethod
    def _stream(handle: BinaryIO, chunk_size: int, bucket: str) -> Iterator[bytes]:
        with handle:
            try:
                while chunk := handle.read(chunk_size):
                    yield chunk
            except OSError as exc:
                raise StorageError(f"read failed in bucket {bucket}") from exc

    def rm(self, bucket: str, key: str) -> None:
        path = self.sanitize_path(bucket, key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if exc.errno not in (errno.ENOENT, errno.ENOTDIR):
                raise StorageError(f"remove failed in bucket {bucket}") from exc

    def exists(self, bucket: str, key: str) -> bool:
        return self.sanitize_path(bucket, key).is_file()

    def size(self, bucket: str, key: str) -> int | None:
        path = self.sanitize_path(bucket, key)
        try:
            return path.stat().st_size if path.is_file() else None
        except OSError:
            return None

    def bucket_exists(self, bucket: str) -> bool:
        return self.sanitize_path(bucket).is_dir()

    def presigned_get_url(self, bucket: str, key: str, expires_seconds: int = 3600) -> str:
        raise StorageNotSupported("the local driver does not support presigned URLs")

    def health(self) -> bool:
        try:
            return os.access(self._base if self._base.exists() else self._base.parent, os.W_OK)
        except OSError:
            return False
