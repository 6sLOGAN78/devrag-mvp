#!/usr/bin/env python3
"""Gate: no default or hard-coded secret literals in tracked or unignored files (D-26, D-28).

The file list comes from git (so an ignored .env is never read). Paths under ``docs/`` are
rejected before any open call: that tree may hold credential material and must never be read.
Tooling that necessarily names the patterns (``scripts/ci/``) and planning prose
(``.planning/``) are excluded.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from _walk import is_test_path

NEVER_OPEN_PREFIXES = ("docs/",)
EXCLUDED_PREFIXES = ("scripts/ci/", ".planning/", ".serena/")
EXEMPT_SUFFIXES = (".example", ".sample", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip", ".gz")
DEFAULT_LITERAL = re.compile(r"infini_rag_flow")
DEFAULT_PASSWORD = re.compile(r"(?:password|passwd|pwd)\w*[\"']?\s*[:=]\s*[\"']?rag_flow\b", re.IGNORECASE)
LITERAL_ASSIGN = re.compile(r"(?:password|passwd|secret|api_?key)\w*[\"']?\s*[:=]\s*([\"'])([^\"'\n]+)\1", re.IGNORECASE)
PLACEHOLDER_START = ("$", "<", "{", "%")
MAX_BYTES = 1_000_000


def listed_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, check=True, timeout=60,
    ).stdout
    return sorted({p for p in out.decode("utf-8", "replace").split("\0") if p})


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for relpath in listed_files(root):
        if relpath.startswith(NEVER_OPEN_PREFIXES):
            continue
        if relpath.startswith(EXCLUDED_PREFIXES) or relpath.endswith(EXEMPT_SUFFIXES):
            continue
        path = root / relpath
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue
        text = path.read_bytes().decode("utf-8", "ignore")
        in_test = is_test_path(relpath)
        for idx, src in enumerate(text.split("\n"), 1):
            if DEFAULT_LITERAL.search(src) or DEFAULT_PASSWORD.search(src):
                findings.append(f"{relpath}:{idx}: known default secret literal")
                continue
            if in_test:
                continue
            m = LITERAL_ASSIGN.search(src)
            if m and not m.group(2).startswith(PLACEHOLDER_START):
                findings.append(f"{relpath}:{idx}: hard-coded secret literal")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    try:
        findings = scan(root)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"secrets: cannot list files via git: {exc}")
        return 1
    for f in findings:
        print(f)
    if findings:
        print(f"secrets: {len(findings)} finding(s)")
        return 1
    print("secrets OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
