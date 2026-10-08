"""Pure upload rules (plan 03-15): what a file must satisfy before anything is stored.

Order of checks for one file (``validate_file``): file name, extension against the configured allow-list, declared MIME
type, zero size, size limit, then the leading bytes (magic bytes for binary types, no NUL byte for text types). The
request level checks (``check_batch``, ``check_capacity``) run before the per-file checks. Any failure rejects the whole
request; the caller stores nothing until every file has passed (success criterion 4).

Names are rejected, never sanitised, and a name is metadata only: it never reaches a path or an object key. Failures
raise ``ServiceError`` with a short fixed message that does not echo the file name, extension, MIME type or size.

The module imports no web framework, no ORM and no storage code. It works on plain binary file-like objects.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Protocol

import xxhash

from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.settings import UploadSettings

MAX_NAME_LENGTH = 255
HEAD_BYTES = 8192
CHUNK_BYTES = 1 << 20

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class SeekableReader(Protocol):
    def read(self, n: int = -1, /) -> bytes: ...

    def seek(self, offset: int, whence: int = 0, /) -> int: ...


@dataclass(frozen=True)
class ValidatedFile:
    name: str
    extension: str
    file_type: str
    size: int
    mime: str


_OCTET = "application/octet-stream"
_OPENXML = "application/vnd.openxmlformats-officedocument."


def _mimes(*types: str) -> frozenset[str]:
    return frozenset((*types, _OCTET, ""))


ALLOWED_MIME_BY_EXT: dict[str, frozenset[str]] = {
    "pdf": _mimes("application/pdf"),
    "docx": _mimes(_OPENXML + "wordprocessingml.document", "application/zip"),
    "pptx": _mimes(_OPENXML + "presentationml.presentation", "application/zip"),
    "xlsx": _mimes(_OPENXML + "spreadsheetml.sheet", "application/vnd.ms-excel", "application/zip"),
    "txt": _mimes("text/plain"),
    "md": _mimes("text/markdown", "text/x-markdown", "text/plain"),
    "markdown": _mimes("text/markdown", "text/x-markdown", "text/plain"),
    "csv": _mimes("text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"),
    "json": _mimes("application/json", "text/json", "text/plain"),
    "html": _mimes("text/html", "application/xhtml+xml", "text/plain"),
    "htm": _mimes("text/html", "application/xhtml+xml", "text/plain"),
    "epub": _mimes("application/epub+zip", "application/zip"),
    "jpg": _mimes("image/jpeg"),
    "jpeg": _mimes("image/jpeg"),
    "png": _mimes("image/png"),
    "mp3": _mimes("audio/mpeg", "audio/mp3"),
    "wav": _mimes("audio/wav", "audio/x-wav", "audio/wave"),
}

_TEXT_EXTENSIONS = frozenset({"txt", "md", "markdown", "csv", "json", "html", "htm"})
_ZIP_EXTENSIONS = frozenset({"docx", "pptx", "xlsx", "epub"})
_DOC_EXTENSIONS = _TEXT_EXTENSIONS | _ZIP_EXTENSIONS
_VISUAL_EXTENSIONS = frozenset({"jpg", "jpeg", "png"})
_AURAL_EXTENSIONS = frozenset({"mp3", "wav"})

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_ZIP_SIGNATURE = b"PK\x03\x04"


def _invalid(reason: str, message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


# ---------------------------------------------------------------- names


def normalize_filename(raw: str) -> str:
    """NFC-normalise and strip ``raw``; reject anything that is not a plain file name."""
    name = unicodedata.normalize("NFC", raw).strip()
    if not name or name in {".", ".."} or len(name) > MAX_NAME_LENGTH:
        raise _invalid(reasons.INVALID_FILENAME, "the file name is not valid")
    if "/" in name or "\\" in name or _DRIVE_PREFIX.match(name):
        raise _invalid(reasons.INVALID_FILENAME, "the file name is not valid")
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        raise _invalid(reasons.INVALID_FILENAME, "the file name is not valid")
    if name.endswith("."):
        raise _invalid(reasons.INVALID_FILENAME, "the file name is not valid")
    dot = name.rfind(".")
    if dot == 0 or (dot > 0 and not name[:dot].strip()):
        raise _invalid(reasons.INVALID_FILENAME, "the file name is not valid")
    return name


def split_name(name: str) -> tuple[str, str]:
    """Split on the last dot. ``("stem", "ext")`` with the extension lower-cased and without the dot; ext is ``""`` when none."""
    dot = name.rfind(".")
    if dot <= 0:
        return name, ""
    return name[:dot], name[dot + 1 :].lower()


def file_type_for(extension: str) -> str:
    ext = extension.lower()
    if ext == "pdf":
        return "pdf"
    if ext in _DOC_EXTENSIONS:
        return "doc"
    if ext in _VISUAL_EXTENSIONS:
        return "visual"
    if ext in _AURAL_EXTENSIONS:
        return "aural"
    return "other"


# ---------------------------------------------------------------- content


def check_magic(extension: str, head: bytes) -> bool:
    """True when the leading bytes fit the extension. Text types only need to be free of NUL bytes."""
    if not head:
        return False
    ext = extension.lower()
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext in _ZIP_EXTENSIONS:
        return head.startswith(_ZIP_SIGNATURE)
    if ext == "png":
        return head.startswith(_PNG_SIGNATURE)
    if ext in {"jpg", "jpeg"}:
        return head.startswith(_JPEG_SIGNATURE)
    if ext == "wav":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext == "mp3":
        return head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if ext in _TEXT_EXTENSIONS:
        return b"\x00" not in head[:HEAD_BYTES]
    return False


def validate_file(raw_name: str, declared_mime: str, head: bytes, size: int, limits: UploadSettings) -> ValidatedFile:
    """Run every per-file rule. ``size`` is the measured size of the spooled file, never a client header."""
    name = normalize_filename(raw_name)
    _, extension = split_name(name)
    if not extension or extension not in limits.allowed_extensions or extension not in ALLOWED_MIME_BY_EXT:
        raise _invalid(reasons.UNSUPPORTED_TYPE, "this file type is not supported")
    mime = (declared_mime or "").split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_MIME_BY_EXT[extension]:
        raise _invalid(reasons.UNSUPPORTED_TYPE, "this file type is not supported")
    if size <= 0:
        raise _invalid(reasons.EMPTY_FILE, "the file is empty")
    if size > limits.max_file_bytes:
        raise ServiceError(Kind.PAYLOAD_TOO_LARGE, reasons.FILE_TOO_LARGE, "the file is larger than the allowed size", data={"http_status": 413})
    if not head:
        raise _invalid(reasons.EMPTY_FILE, "the file is empty")
    if not check_magic(extension, head):
        raise _invalid(reasons.UNSUPPORTED_TYPE, "the file content does not match its type")
    return ValidatedFile(name=name, extension=extension, file_type=file_type_for(extension), size=size, mime=mime)


# ---------------------------------------------------------------- batch


def check_batch(count: int, limits: UploadSettings) -> None:
    if count <= 0:
        raise _invalid(reasons.NO_FILES, "no files were uploaded")
    if count > limits.max_files_per_request:
        raise _invalid(reasons.TOO_MANY_FILES, "too many files in one request")


def check_capacity(current_documents: int, new_files: int, limits: UploadSettings) -> None:
    if current_documents + new_files > limits.max_documents_per_dataset:
        raise _invalid(reasons.DATASET_LIMIT, "the dataset has reached its document limit")


# ---------------------------------------------------------------- rename


def auto_rename(name: str, taken: Collection[str]) -> str:
    """``report.pdf`` -> ``report(1).pdf``, ``report(2).pdf`` ... until the name is free (case-insensitive).

    Only the last extension is kept apart from the stem. The stem is trimmed so the whole name stays within 255 characters.
    """
    used = {t.casefold() for t in taken}
    if name.casefold() not in used:
        return name
    dot = name.rfind(".")
    stem, suffix = (name, "") if dot <= 0 else (name[:dot], name[dot:])
    counter = 1
    while True:
        tag = f"({counter})"
        room = MAX_NAME_LENGTH - len(suffix) - len(tag)
        candidate = f"{stem[: max(room, 1)]}{tag}{suffix}"
        if candidate.casefold() not in used:
            return candidate
        counter += 1


def auto_rename_batch(names: Sequence[str], taken: Collection[str]) -> list[str]:
    """Rename each name against ``taken`` and against the names already given earlier in the same request."""
    used = set(taken)
    result: list[str] = []
    for name in names:
        final = auto_rename(name, used)
        used.add(final)
        result.append(final)
    return result


# ---------------------------------------------------------------- hashing


def _read_full(stream: SeekableReader, size: int) -> bytes:
    """Read up to ``size`` bytes, looping over short reads; fewer bytes only at end of stream."""
    parts: list[bytes] = []
    remaining = size
    while remaining > 0:
        piece = stream.read(remaining)
        if not piece:
            break
        parts.append(piece)
        remaining -= len(piece)
    return parts[0] if len(parts) == 1 else b"".join(parts)


def hash_and_measure(stream: SeekableReader, chunk: int = CHUNK_BYTES) -> tuple[str, int, bytes]:
    """Stream ``stream`` once: ``(xxh64 hex, byte count, first 8192 bytes)``. The stream is rewound before and after."""
    stream.seek(0)
    digest = xxhash.xxh64()
    total = 0
    head = bytearray()
    try:
        while True:
            piece = stream.read(chunk)
            if not piece:
                break
            digest.update(piece)
            total += len(piece)
            if len(head) < HEAD_BYTES:
                head += piece[: HEAD_BYTES - len(head)]
    finally:
        stream.seek(0)
    return digest.hexdigest(), total, bytes(head)


def streams_equal(a: SeekableReader, b: SeekableReader, chunk: int = CHUNK_BYTES) -> bool:
    """Byte-for-byte comparison in lock step. A hash match alone is never trusted for dedupe."""
    a.seek(0)
    b.seek(0)
    try:
        while True:
            left = _read_full(a, chunk)
            right = _read_full(b, chunk)
            if left != right:
                return False
            if not left:
                return True
    finally:
        a.seek(0)
        b.seek(0)
