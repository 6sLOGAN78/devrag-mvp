"""Shared helpers for the CI gates: tree lists, test-path predicate, gate-ok parser."""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

PROD_DIRS = ("api", "common", "rag", "deepdoc", "agent", "cmd", "internal", "web/src")
SKIP_DIRS = {"docs", ".venv", "node_modules", ".git", ".serena", "__pycache__", ".pytest_cache", ".ruff_cache"}
SKIP_PREFIXES = ("web/dist/",)
TEST_DIR_NAMES = {"test", "tests"}
TEST_SUFFIXES = ("_test.go", ".test.ts", ".test.tsx")
GATE_OK = re.compile(r"gate-ok:(.*)$")


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def is_test_path(relpath: str) -> bool:
    parts = relpath.split("/")
    if any(p in TEST_DIR_NAMES for p in parts[:-1]):
        return True
    return relpath.endswith(TEST_SUFFIXES)


def _skipped(relpath: str) -> bool:
    parts = relpath.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return True
    return relpath.startswith(SKIP_PREFIXES)


def iter_files(root: Path, base_dirs: tuple[str, ...] | None, exts: tuple[str, ...]) -> Iterator[tuple[str, Path]]:
    """Yield (relative posix path, absolute path) for files under base_dirs (or the whole root)."""
    bases = [root / b for b in base_dirs] if base_dirs is not None else [root]
    for base in bases:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in exts:
                continue
            relpath = rel(root, path)
            if _skipped(relpath):
                continue
            yield relpath, path


def prod_trees_present(root: Path) -> bool:
    return any((root / d).is_dir() for d in PROD_DIRS)


def gate_ok(line: str) -> str | None:
    """Return the gate-ok reason when present and non-empty, "" when present but empty, None when absent."""
    m = GATE_OK.search(line)
    if m is None:
        return None
    return m.group(1).strip()
