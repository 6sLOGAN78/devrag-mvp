#!/usr/bin/env python3
"""Gate: no fixed sleep or setTimeout waits in test trees (D-30).

Tests wait on readiness through exactly three helper files. Production trees are not
scanned by this gate.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _walk import is_test_path, iter_files

ALLOWED = {"test/helpers/wait.py", "internal/testutil/wait.go", "web/src/test/wait-until.ts"}
PATTERN = re.compile(r"\b(?:sleep|Sleep)\s*\(|\bsetTimeout\s*\(")
COMMENT_ONLY = re.compile(r"^\s*(#|//|\*|/\*)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    count = 0
    for relpath, path in iter_files(root, None, (".py", ".go", ".ts", ".tsx", ".js", ".jsx")):
        if not is_test_path(relpath) or relpath in ALLOWED:
            continue
        for idx, src in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            if COMMENT_ONLY.match(src):
                continue
            if PATTERN.search(src):
                print(f"{relpath}:{idx}: fixed sleep/setTimeout in a test; use the wait helper")
                count += 1
    if count:
        print(f"no_sleep: {count} finding(s)")
        return 1
    print("no_sleep OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
