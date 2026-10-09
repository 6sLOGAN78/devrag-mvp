"""File-row helpers for upload: find a stored blob with the same content, verify it byte for byte, or store a new one (plan 03-16; DOC-04, STOR-11, Pitfall 1, Pitfall 2).

* ``find_candidates`` looks a blob up by ``(workspace, xxh64, size)``. ``document`` has no tenant column, so the lookup joins
  ``file2document`` to ``file`` and filters ``file.tenant_id``; a blob of another workspace can never be a candidate.
* ``reuse_or_store`` runs inside the caller's transaction. A hash and size match is only a hint: xxh64 is not collision resistant, so a
  candidate is reused only after its stored bytes are compared with the upload (``streams_equal``). A crafted collision therefore stores a new blob
  and never links another member's file. The candidate's ``file`` row is locked ``FOR UPDATE`` first, so a delete that removes the last link
  and the blob either commits before the lookup (no candidate) or sees the new link (blob kept).
* ``release_blobs`` is the compensation: it removes the blobs a failed request created, best effort, and logs the operation only.
* ``release_files`` (plan 03-17) is the delete side: inside the caller's transaction it removes documents' tasks, links and rows, and returns the
  keys whose last link went. It takes the affected ``file`` rows ``FOR UPDATE`` first (sorted by id), so it serialises with ``reuse_or_store``
  on the same rows, and counts the remaining links with a locking read, so a link an upload committed while it waited is seen (a plain read
  would use the transaction's older snapshot and wrongly free a blob that was just reused).

The module imports no web framework. Storage drivers are blocking; callers run this in the storage executor.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from api.db.models import Document, File, File2Document, Task
from api.db.services.upload_rules import SeekableReader, streams_equal
from common.constants import BUCKET_NAME
from rag.utils.storage_base import DEFAULT_CHUNK_SIZE, Storage, StorageError, StorageNotFound, new_object_key

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 5


@dataclass(frozen=True)
class Candidate:
    file_id: str
    location: str


def find_candidates(tenant_id: str, content_hash: str, size: int, limit: int = CANDIDATE_LIMIT) -> list[Candidate]:
    """Files of ``tenant_id`` whose documents carry ``content_hash`` and ``size``, oldest first. Needs an open connection."""
    query = (
        File.select(File.id, File.location)
        .join(File2Document, on=(File2Document.file_id == File.id))
        .join(Document, on=(Document.id == File2Document.document_id))
        .where((File.tenant_id == tenant_id) & (Document.content_hash == content_hash) & (Document.size == size) & File.location.is_null(False))
        .group_by(File.id, File.location, File.create_time)
        .order_by(File.create_time, File.id)
        .limit(limit)
    )
    return [Candidate(row.id, row.location) for row in query]


class IterReader:
    """A stored object as a ``SeekableReader`` (``read`` and ``seek(0)`` only), fed by ``Storage.iter_chunks``.

    ``seek(0)`` drops the open stream and the next ``read`` opens a new one, so rewinding never holds a connection. ``close`` must always run:
    a MinIO read stream keeps a pooled connection until it is exhausted or closed.
    """

    def __init__(self, storage: Storage, bucket: str, key: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._storage = storage
        self._bucket = bucket
        self._key = key
        self._chunk_size = chunk_size
        self._stream: Iterator[bytes] | None = None
        self._buffer = bytearray()
        self._done = False

    def read(self, n: int = -1, /) -> bytes:
        if n == 0:
            return b""
        if self._stream is None and not self._done:
            self._stream = self._storage.iter_chunks(self._bucket, self._key, self._chunk_size)
        while self._stream is not None and (n < 0 or len(self._buffer) < n):
            try:
                self._buffer += next(self._stream)
            except StopIteration:
                self._finish()
        if n < 0:
            out, self._buffer = bytes(self._buffer), bytearray()
        else:
            out = bytes(self._buffer[:n])
            del self._buffer[:n]
        return out

    def seek(self, offset: int, whence: int = 0, /) -> int:
        if offset != 0 or whence != 0:
            raise ValueError("only seek(0) is supported")
        self.close()
        self._buffer = bytearray()
        self._done = False
        return 0

    def _finish(self) -> None:
        self.close()
        self._done = True

    def close(self) -> None:
        stream, self._stream = self._stream, None
        closer = getattr(stream, "close", None)
        if closer is not None:
            closer()


def _same_bytes(storage: Storage, candidate: Candidate, stream: SeekableReader, size: int) -> bool:
    """True when the stored blob holds exactly the upload's bytes. An absent or differently sized blob is simply not a match."""
    try:
        if storage.size(BUCKET_NAME, candidate.location) != size:
            return False
        reader = IterReader(storage, BUCKET_NAME, candidate.location)
        try:
            return streams_equal(stream, reader)
        finally:
            reader.close()
    except StorageNotFound:
        return False


def reuse_or_store(storage: Storage, tenant_id: str, stream: SeekableReader, content_hash: str, size: int, created_keys: list[str]) -> tuple[str | None, str, bool]:
    """``(reused file id or None, location, created)`` for one upload; call inside a transaction with an open connection.

    A verified candidate is reused: ``(file id, its location, False)``. Otherwise the stream is written under a fresh server-generated key,
    the key is appended to ``created_keys`` before the write (so a failed write is still cleaned up) and ``(None, key, True)`` is returned.
    """
    for candidate in find_candidates(tenant_id, content_hash, size):
        locked = File.select(File.id).where(File.id == candidate.file_id).for_update().first()
        if locked is None:  # removed by a delete that committed first: not a candidate any more
            continue
        if _same_bytes(storage, candidate, stream, size):
            return candidate.file_id, candidate.location, False
    key = new_object_key(tenant_id)
    created_keys.append(key)
    stream.seek(0)
    storage.put(BUCKET_NAME, key, stream, length=size)  # type: ignore[arg-type]  # a SeekableReader is a readable binary stream
    return None, key, True


def release_blobs(storage: Storage, keys: Sequence[str], operation: str = "upload") -> None:
    """Remove ``keys`` best effort. A failure is logged with the operation only (never the key) and does not stop the others."""
    for key in keys:
        try:
            storage.rm(BUCKET_NAME, key)
        except StorageError:
            logger.warning("%s cleanup could not remove a blob", operation)
        except Exception as exc:  # noqa: BLE001 - cleanup must reach the remaining keys whatever the driver raised
            logger.warning("%s cleanup failed unexpectedly error=%s", operation, type(exc).__name__)


def release_files(document_ids: Sequence[str]) -> list[str]:
    """Delete the tasks, links and rows of ``document_ids`` and return the blob keys nothing references any more.

    Call inside a transaction with an open connection. Order (it matters): lock the affected ``file`` rows sorted by id; delete tasks,
    ``file2document`` rows and documents; then, per file, count the links that remain (all datasets of the workspace, locking read) and delete
    the ``file`` row when none do. The returned keys are removed from storage by the caller after the commit.
    """
    ids = sorted(set(document_ids))
    if not ids:
        return []
    linked = File2Document.select(File2Document.file_id).where(File2Document.document_id.in_(ids))
    file_ids = sorted({link.file_id for link in linked if link.file_id})
    locations: dict[str, str | None] = {}
    if file_ids:
        locked = File.select(File.id, File.location).where(File.id.in_(file_ids)).order_by(File.id).for_update()
        locations = {row.id: row.location for row in locked}
    Task.delete().where(Task.doc_id.in_(ids)).execute()
    File2Document.delete().where(File2Document.document_id.in_(ids)).execute()
    Document.delete().where(Document.id.in_(ids)).execute()
    freed: list[str] = []
    for file_id in file_ids:
        if file_id not in locations:  # the row is already gone: nothing to free
            continue
        remaining = list(File2Document.select(File2Document.id).where(File2Document.file_id == file_id).limit(1).for_update())
        if remaining:
            continue
        File.delete().where(File.id == file_id).execute()
        if locations[file_id]:
            freed.append(str(locations[file_id]))
    return freed
