"""RetCode values must be equal across Python, Go and TypeScript (D-13, R-73)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from common.constants import RetCode

ROOT = Path(__file__).resolve().parents[2]
GO_FILE = ROOT / "internal" / "common" / "error_code.go"
TS_FILE = ROOT / "web" / "src" / "constants" / "retcode.ts"

pytestmark = pytest.mark.unit


def python_codes() -> dict[str, int]:
    return {member.name: int(member.value) for member in RetCode}


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).upper()


def go_codes(text: str) -> dict[str, int]:
    pairs = re.findall(r"^\s*Code([A-Za-z]+)\s+RetCode\s*=\s*(\d+)\s*$", text, re.MULTILINE)
    return {_snake(name): int(value) for name, value in pairs}


def ts_codes(text: str) -> dict[str, int]:
    body = re.search(r"export enum RetCode \{(.*?)\n\}", text, re.DOTALL)
    assert body, "RetCode enum not found in retcode.ts"
    return {name: int(value) for name, value in re.findall(r"^\s*([A-Z_]+)\s*=\s*(\d+),?\s*$", body.group(1), re.MULTILINE)}


def diff(left: dict[str, int], right: dict[str, int]) -> dict[str, tuple[int | None, int | None]]:
    keys = set(left) | set(right)
    return {k: (left.get(k), right.get(k)) for k in sorted(keys) if left.get(k) != right.get(k)}


def test_python_members_are_parsed() -> None:
    assert len(python_codes()) == 18


def test_go_constants_equal_python() -> None:
    assert diff(python_codes(), go_codes(GO_FILE.read_text())) == {}


def test_ts_enum_equals_python() -> None:
    assert diff(python_codes(), ts_codes(TS_FILE.read_text())) == {}


def test_parity_helper_detects_a_changed_ts_value() -> None:
    mutated = TS_FILE.read_text().replace("NOT_FOUND = 404", "NOT_FOUND = 405")
    assert mutated != TS_FILE.read_text()
    assert diff(python_codes(), ts_codes(mutated)) == {"NOT_FOUND": (404, 405)}


def test_parity_helper_detects_a_changed_go_value() -> None:
    mutated = GO_FILE.read_text().replace("CodeConflict            RetCode = 409", "CodeConflict            RetCode = 410")
    assert mutated != GO_FILE.read_text()
    assert diff(python_codes(), go_codes(mutated)) == {"CONFLICT": (409, 410)}
