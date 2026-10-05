#!/usr/bin/env python3
"""CI gate: generated files must match their sources (routes, schema export, Go entities), in dependency order."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _command(root: Path, name: str) -> list[str]:
    script = str(root / "scripts" / name)
    if name == "export_schema.py":
        return [sys.executable, script, "--check", "--out", str(root / "conf" / "schema.json")]
    return [sys.executable, script, "--check", "--root", str(root)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args()
    root = Path(args.root)
    for name in ("gen_routes.py", "export_schema.py", "gen_go_entities.py"):
        if not (root / "scripts" / name).exists():
            print(f"missing generator {name}")
            return 1
        proc = subprocess.run(_command(root, name), capture_output=True, text=True, timeout=120, check=False)  # noqa: S603
        if proc.returncode != 0:
            print(f"drift or error in {name}:\n{proc.stdout}{proc.stderr}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
