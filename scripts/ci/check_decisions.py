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
# 2026-10-07, Phase 2 discuss session and post-research approval (D-01..D-16, D-20..D-23), user's own answers:
#   33 token format (D-09..D-11), 36 owner-only invites (D-13), 91 cookie fallback (D-21), 95 dev mail catcher (D-05, D-20),
#   98 en/zh languages (D-23), 100 REGISTER_ENABLED (D-01), 101 password rule (D-02), 102 first superuser (D-03),
#   103 generic login failure (D-04), 104 reset code policy (D-05..D-08), 105 API/shared tokens (D-10, D-12),
#   106 invitations and membership (D-14..D-16), 108 default model ids (D-22), 109 approved dependencies (D-20).
# Rows decided by research, the planner or the orchestrator (D-24..D-31, R-112..R-114) are never listed here.
CONFIRMED = {3, 17, 18, 48, 49, 87, 33, 36, 91, 95, 98, 100, 101, 102, 103, 104, 105, 106, 108, 109}
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
