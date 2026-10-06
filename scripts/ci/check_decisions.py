#!/usr/bin/env python3
"""Gate: DECISIONS.md must cover every R-ID in research/SUMMARY.md with valid statuses."""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ALLOWED = {"user-confirmed", "accepted (auto, not user-reviewed)", "open"}
# Rows the user decided in person. 3, 17, 18, 48: scope answers on 2026-10-05. 49: docs/apikey llm.md reviewed
# and released, 2026-10-07. 87: dev web port, 2026-10-07.
CONFIRMED = {3, 17, 18, 48, 49, 87}
ROW = re.compile(r"^\| R-(\d+) \|")


def rows(path: Path) -> list[tuple[int, list[str], str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            out.append((int(m.group(1)), cells, line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    summary = root / ".planning" / "research" / "SUMMARY.md"
    decisions = root / ".planning" / "DECISIONS.md"
    for p in (summary, decisions):
        if not p.is_file():
            print(f"missing file: {p}")
            return 1

    errors: list[str] = []
    expected = {n for n, _, _ in rows(summary)}
    expected |= set(range(53, 74))
    found = rows(decisions)
    counts = Counter(n for n, _, _ in found)

    for n in sorted(expected):
        if counts[n] == 0:
            errors.append(f"R-{n:02d}: missing")
    for n, c in counts.items():
        if c > 1:
            errors.append(f"R-{n:02d}: duplicated ({c} rows)")

    for n, cells, line in found:
        tag = f"R-{n:02d}"
        if len(cells) < 5:
            errors.append(f"{tag}: expected 5 columns, got {len(cells)}")
            continue
        resolution, status = cells[2], cells[3]
        if status not in ALLOWED:
            errors.append(f"{tag}: invalid status {status!r}")
        if not resolution:
            errors.append(f"{tag}: empty resolution")
        if n in CONFIRMED and status != "user-confirmed":
            errors.append(f"{tag}: must be user-confirmed")
        if n not in CONFIRMED and status == "user-confirmed":
            errors.append(f"{tag}: must not be user-confirmed")
        if re.search(r"\bproposed\b", line, re.I):
            errors.append(f"{tag}: contains 'proposed'")

    if errors:
        for e in errors:
            print(e)
        return 1
    print(f"decisions OK: {len(found)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
