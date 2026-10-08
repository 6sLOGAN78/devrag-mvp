"""Upload rules (plan 03-15): filename, extension, MIME, magic bytes, size, batch limits, rename, hashing."""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
import xxhash

from api.db.services import upload_rules as rules
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.settings import UploadSettings

pytestmark = pytest.mark.unit

LIMITS = UploadSettings()
SMALL = UploadSettings(max_file_bytes=1024)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
ZIP = b"PK\x03\x04" + b"\x00" * 16
PDF = b"%PDF-1.7\n%" + b"x" * 16


def _reject(call, reason: str, kind: Kind = Kind.INVALID) -> ServiceError:
    with pytest.raises(ServiceError) as info:
        call()
    assert info.value.reason == reason
    assert info.value.kind is kind
    return info.value


class ShortReader:
    """A stream that returns at most seven bytes per read, like a slow socket."""

    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._inner.read(7 if n < 0 else min(n, 7))

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._inner.seek(offset, whence)


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("  report.pdf\t", "report.pdf"),
        ("Re\u0301sume\u0301.docx", "R\u00e9sum\u00e9.docx"),
        ("R\u00e9sum\u00e9.docx", "R\u00e9sum\u00e9.docx"),
    ],
)
def test_normalize_filename_accepts_and_normalises(raw, expected):
    assert rules.normalize_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        ".",
        "..",
        "a/b.pdf",
        "a\\b.pdf",
        "../a.pdf",
        "a\x00.pdf",
        "a\x1f.pdf",
        "a\x7f.pdf",
        "a\nb.pdf",
        "C:evil.pdf",
        "C:\\x.pdf",
        "a" * 252 + ".pdf",
        ".pdf",
        "trailing.",
    ],
)
def test_bad_names_are_invalid_filename(raw):
    _reject(lambda: rules.normalize_filename(raw), reasons.INVALID_FILENAME)


def test_name_of_exactly_255_characters_is_accepted():
    name = "a" * 251 + ".pdf"
    assert len(name) == 255
    assert rules.normalize_filename(name) == name


def test_no_extension_is_unsupported_type():
    _reject(lambda: rules.validate_file("noext", "", PDF, 10, LIMITS), reasons.UNSUPPORTED_TYPE)


@pytest.mark.parametrize("name", ["a.pdf.exe", "x.gif", "x.bmp", "x.tiff", "x.tif", "x.webp", "x.doc", "x.ppt", "x.xls", "x.svg", "x.exe"])
def test_extension_outside_the_allow_list(name):
    _reject(lambda: rules.validate_file(name, "", PDF, 10, LIMITS), reasons.UNSUPPORTED_TYPE)


def test_extension_is_case_insensitive_and_lowered():
    got = rules.validate_file("X.PDF", "application/pdf", PDF, 10, LIMITS)
    assert got.extension == "pdf"
    assert got.name == "X.PDF"
    assert got.file_type == "pdf"


def test_configured_list_without_md_rejects_md():
    limits = UploadSettings(allowed_extensions=("pdf", "txt"))
    _reject(lambda: rules.validate_file("a.md", "text/markdown", b"# hi", 4, limits), reasons.UNSUPPORTED_TYPE)
    assert rules.validate_file("a.txt", "text/plain", b"hi", 2, limits).extension == "txt"


def test_configured_extension_without_a_mime_table_entry_is_refused():
    limits = UploadSettings(allowed_extensions=("pdf", "xyz"))
    _reject(lambda: rules.validate_file("a.xyz", "", b"abc", 3, limits), reasons.UNSUPPORTED_TYPE)


# ---------------------------------------------------------------- MIME


@pytest.mark.parametrize(
    ("name", "mime", "head"),
    [
        ("a.pdf", "application/pdf", PDF),
        ("a.pdf", "Application/PDF; charset=binary", PDF),
        ("a.md", "text/markdown", b"# t"),
        ("a.md", "text/plain", b"# t"),
        ("a.md", "application/octet-stream", b"# t"),
        ("a.md", "", b"# t"),
        ("a.csv", "application/vnd.ms-excel", b"a,b"),
        ("a.csv", "text/csv", b"a,b"),
    ],
)
def test_declared_mime_accepted(name, mime, head):
    assert rules.validate_file(name, mime, head, len(head), LIMITS).size == len(head)


@pytest.mark.parametrize(
    ("name", "mime", "head"),
    [
        ("a.pdf", "image/png", PDF),
        ("a.pdf", "application/x-msdownload", PDF),
        ("a.txt", "application/x-msdownload", b"hi"),
        ("a.png", "application/pdf", PNG),
    ],
)
def test_declared_mime_refused(name, mime, head):
    _reject(lambda: rules.validate_file(name, mime, head, len(head), LIMITS), reasons.UNSUPPORTED_TYPE)


def test_every_builtin_extension_has_a_mime_entry():
    from common.settings import DEFAULT_UPLOAD_EXTENSIONS

    for ext in DEFAULT_UPLOAD_EXTENSIONS:
        assert "" in rules.ALLOWED_MIME_BY_EXT[ext]
        assert "application/octet-stream" in rules.ALLOWED_MIME_BY_EXT[ext]


# ---------------------------------------------------------------- magic bytes and text


@pytest.mark.parametrize(
    ("ext", "head", "expected"),
    [
        ("pdf", PDF, True),
        ("png", PDF, False),
        ("pdf", ZIP, False),
        ("docx", ZIP, True),
        ("pptx", ZIP, True),
        ("xlsx", ZIP, True),
        ("epub", ZIP, True),
        ("docx", PDF, False),
        ("png", PNG, True),
        ("png", JPEG, False),
        ("jpg", JPEG, True),
        ("jpeg", JPEG, True),
        ("jpg", PNG, False),
        ("wav", b"RIFF\x01\x02\x03\x04WAVEfmt ", True),
        ("wav", b"RIFF\x01\x02\x03\x04AVI LIST", False),
        ("wav", b"RIFF", False),
        ("mp3", b"ID3\x03\x00\x00", True),
        ("mp3", b"\xff\xfb\x90\x00", True),
        ("mp3", b"\xff\x1b\x90\x00", False),
        ("mp3", b"\x00\x00\x00\x00", False),
        ("txt", b"plain utf-8 \xc3\xa9", True),
        ("txt", b"abc\x00def", False),
        ("txt", b"%PDF-1.7 still text", True),
        ("md", b"# title", True),
        ("csv", b"a,b\n1,2\n", True),
        ("csv", b"a,\x00b", False),
        ("json", b'{"a": 1}', True),
        ("html", b"<html></html>", True),
        ("htm", b"<html>\x00</html>", False),
        ("pdf", b"", False),
        ("txt", b"", False),
    ],
)
def test_check_magic(ext, head, expected):
    assert rules.check_magic(ext, head) is expected


def test_validate_file_refuses_content_that_does_not_match_the_type():
    _reject(lambda: rules.validate_file("a.pdf", "application/pdf", ZIP, 20, LIMITS), reasons.UNSUPPORTED_TYPE)
    _reject(lambda: rules.validate_file("a.txt", "text/plain", b"a\x00b", 3, LIMITS), reasons.UNSUPPORTED_TYPE)


def test_empty_head_is_empty_file():
    _reject(lambda: rules.validate_file("a.pdf", "application/pdf", b"", 10, LIMITS), reasons.EMPTY_FILE)


# ---------------------------------------------------------------- size and batch


def test_size_equal_to_limit_passes_and_one_over_is_413():
    assert rules.validate_file("a.pdf", "application/pdf", PDF, 1024, SMALL).size == 1024
    err = _reject(lambda: rules.validate_file("a.pdf", "application/pdf", PDF, 1025, SMALL), reasons.FILE_TOO_LARGE, Kind.PAYLOAD_TOO_LARGE)
    assert err.data == {"http_status": 413}


def test_zero_size_is_empty_file():
    _reject(lambda: rules.validate_file("a.pdf", "application/pdf", PDF, 0, LIMITS), reasons.EMPTY_FILE)


def test_check_batch():
    rules.check_batch(1, LIMITS)
    rules.check_batch(LIMITS.max_files_per_request, LIMITS)
    _reject(lambda: rules.check_batch(0, LIMITS), reasons.NO_FILES)
    _reject(lambda: rules.check_batch(LIMITS.max_files_per_request + 1, LIMITS), reasons.TOO_MANY_FILES)


def test_check_capacity():
    rules.check_capacity(9999, 1, LIMITS)
    rules.check_capacity(0, 0, LIMITS)
    _reject(lambda: rules.check_capacity(9999, 2, LIMITS), reasons.DATASET_LIMIT)
    small = replace(LIMITS, max_documents_per_dataset=3)
    rules.check_capacity(1, 2, small)
    _reject(lambda: rules.check_capacity(2, 2, small), reasons.DATASET_LIMIT)


@pytest.mark.parametrize(
    "call",
    [
        lambda: rules.validate_file("secret-name.exe", "", PDF, 5, LIMITS),
        lambda: rules.validate_file("secret-name.pdf", "image/png", PDF, 5, LIMITS),
        lambda: rules.validate_file("secret-name.pdf", "application/pdf", PNG, 5, LIMITS),
        lambda: rules.validate_file("secret-name.pdf", "application/pdf", PDF, 99999, SMALL),
        lambda: rules.validate_file("secret-name.pdf", "application/pdf", PDF, 0, LIMITS),
        lambda: rules.normalize_filename("secret/name.pdf"),
        lambda: rules.normalize_filename("secret-name."),
        lambda: rules.check_batch(99, LIMITS),
        lambda: rules.check_capacity(10000, 5, LIMITS),
    ],
)
def test_messages_never_echo_names_extensions_or_sizes(call):
    with pytest.raises(ServiceError) as info:
        call()
    text = f"{info.value.message} {info.value} {info.value.data}"
    for leak in ("secret", ".exe", "99999", "image/png", "10000"):
        assert leak not in text


# ---------------------------------------------------------------- rename


@pytest.mark.parametrize(
    ("name", "taken", "expected"),
    [
        ("report.pdf", set(), "report.pdf"),
        ("report.pdf", {"other.pdf"}, "report.pdf"),
        ("report.pdf", {"report.pdf"}, "report(1).pdf"),
        ("report.pdf", {"report.pdf", "report(1).pdf"}, "report(2).pdf"),
        ("report.pdf", {"report.pdf", "report(2).pdf"}, "report(1).pdf"),
        ("report.pdf", {"REPORT.PDF"}, "report(1).pdf"),
        ("report.pdf", {"report.pdf", "REPORT(1).PDF"}, "report(2).pdf"),
        ("archive.tar.gz", {"archive.tar.gz"}, "archive.tar(1).gz"),
    ],
)
def test_auto_rename(name, taken, expected):
    assert rules.auto_rename(name, taken) == expected


def test_auto_rename_keeps_total_length_within_255():
    name = "a" * 251 + ".pdf"
    got = rules.auto_rename(name, {name})
    assert got == "a" * 248 + "(1).pdf"
    assert len(got) == 255
    taken = {name, got}
    third = rules.auto_rename(name, taken)
    assert third.endswith("(2).pdf")
    assert len(third) == 255
    assert third.casefold() not in {t.casefold() for t in taken}


def test_auto_rename_batch_renames_names_of_one_request_against_each_other():
    got = rules.auto_rename_batch(["a.pdf", "A.pdf", "b.pdf", "a.pdf"], {"b.pdf"})
    assert got == ["a.pdf", "A(1).pdf", "b(1).pdf", "a(2).pdf"]


# ---------------------------------------------------------------- hashing


def test_hash_and_measure_matches_xxh64_and_rewinds():
    data = bytes((i * 31) % 251 for i in range(3 * 1024 * 1024))
    stream = io.BytesIO(data)
    digest, size, head = rules.hash_and_measure(stream)
    assert digest == xxhash.xxh64(data).hexdigest()
    assert len(digest) == 16
    assert size == len(data)
    assert head == data[:8192]
    assert stream.tell() == 0


def test_hash_and_measure_on_short_reads_and_small_input():
    data = b"hello world " * 3000
    stream = ShortReader(data)
    digest, size, head = rules.hash_and_measure(stream, chunk=1 << 20)
    assert digest == xxhash.xxh64(data).hexdigest()
    assert size == len(data)
    assert head == data[:8192]
    digest2, size2, head2 = rules.hash_and_measure(io.BytesIO(b"abc"))
    assert (digest2, size2, head2) == (xxhash.xxh64(b"abc").hexdigest(), 3, b"abc")


def test_hash_and_measure_starts_from_the_beginning():
    stream = io.BytesIO(b"abcdef")
    stream.seek(4)
    assert rules.hash_and_measure(stream)[1] == 6


def test_streams_equal():
    data = bytes(range(256)) * 20000
    a, b = io.BytesIO(data), ShortReader(data)
    assert rules.streams_equal(a, b, chunk=65536) is True
    assert a.tell() == 0
    assert b.read(3) == data[:3]

    flipped = bytearray(data)
    flipped[-1] ^= 1
    assert rules.streams_equal(io.BytesIO(data), io.BytesIO(bytes(flipped))) is False
    assert rules.streams_equal(io.BytesIO(data), io.BytesIO(data[:-1])) is False
    assert rules.streams_equal(io.BytesIO(data[:-1]), io.BytesIO(data)) is False
    assert rules.streams_equal(io.BytesIO(b""), io.BytesIO(b"")) is True


def test_streams_equal_leaves_streams_usable_after_a_mismatch():
    a, b = io.BytesIO(b"abcdef"), io.BytesIO(b"abcxyz")
    assert rules.streams_equal(a, b) is False
    assert a.read() == b"abcdef"
    assert b.read() == b"abcxyz"


# ---------------------------------------------------------------- file type


@pytest.mark.parametrize(
    ("ext", "expected"),
    [
        ("pdf", "pdf"),
        *[(e, "doc") for e in ("docx", "pptx", "xlsx", "txt", "md", "markdown", "csv", "json", "html", "htm", "epub")],
        *[(e, "visual") for e in ("jpg", "jpeg", "png")],
        *[(e, "aural") for e in ("mp3", "wav")],
    ],
)
def test_file_type_for(ext, expected):
    assert rules.file_type_for(ext) == expected
