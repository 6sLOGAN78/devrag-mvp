#!/usr/bin/env python3
"""CI gate: generated files must match their sources (routes, and Go entities once plan 01-11 adds them)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args()
    root = Path(args.root)
    failed = 0
    for name in ("gen_routes.py", "gen_go_entities.py"):
        script = root / "scripts" / name
        if not script.exists():
            continue
        proc = subprocess.run([sys.executable, str(script), "--check", "--root", str(root)],
                              capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            failed += 1
            print(f"drift or error in {name}:\n{proc.stdout}{proc.stderr}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
