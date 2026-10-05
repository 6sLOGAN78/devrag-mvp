#!/usr/bin/env python3
"""Run every scripts/ci/check_*.py and check_*.sh gate in sorted order; exit 1 if any fails."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def discover(scripts_dir: Path) -> list[Path]:
    return sorted([*scripts_dir.glob("check_*.py"), *scripts_dir.glob("check_*.sh")])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(HERE.parents[1]))
    ap.add_argument("--scripts-dir", default=str(HERE))
    args = ap.parse_args()
    gates = discover(Path(args.scripts_dir))
    if not gates:
        print("FAIL no gates discovered")
        return 1
    failed = 0
    for gate in gates:
        cmd = [sys.executable, str(gate)] if gate.suffix == ".py" else ["bash", str(gate)]
        try:
            proc = subprocess.run([*cmd, "--root", args.root], capture_output=True, text=True, timeout=300, check=False)
            code, output = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            code, output = 1, "timed out after 300s\n"
        name = gate.stem.removeprefix("check_")
        print(f"{'PASS' if code == 0 else 'FAIL'} {name}")
        if code != 0 or output.strip():
            for line in output.rstrip().split("\n"):
                print(f"    {line}")
        failed += code != 0
    print(f"{len(gates) - failed}/{len(gates)} gates passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
