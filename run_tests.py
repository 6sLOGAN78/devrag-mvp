#!/usr/bin/env python3
"""Documented pytest wrapper: -p/--parallel, -t/--test, -m/--markers, -i/--ignore, --coverage."""
from __future__ import annotations

import argparse
import subprocess
import sys


def build_argv(args: argparse.Namespace, markers: str | None = None, parallel: bool | None = None) -> list[str]:
    markers = args.markers if markers is None else markers
    parallel = args.parallel if parallel is None else parallel
    argv = [sys.executable, "-m", "pytest"]
    if markers:
        argv += ["-m", markers]
    if args.test:
        argv += ["-k", args.test]
    for path in args.ignore:
        argv += ["--ignore", path]
    if parallel:
        argv += ["-n", "auto"]
    if args.coverage:
        argv += ["--cov"]
    argv += args.passthrough
    return argv


def plan(args: argparse.Namespace) -> list[list[str]]:
    """Commands to run. In parallel mode, tests marked ``serial`` never share a run with xdist workers:
    they run in a second, non-parallel pass (destructive tests stop and restart live services)."""
    if not args.parallel:
        return [build_argv(args)]
    base = f"({args.markers}) and " if args.markers else ""
    return [build_argv(args, f"{base}not serial", True), build_argv(args, f"{base}serial", False)]


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run the devRag Python tests through pytest.")
    ap.add_argument("-p", "--parallel", action="store_true", help="run in parallel (pytest-xdist, -n auto)")
    ap.add_argument("-t", "--test", help="select tests by name expression (pytest -k)")
    ap.add_argument("-m", "--markers", help="select tests by marker expression (pytest -m)")
    ap.add_argument("-i", "--ignore", action="append", default=[], help="path to ignore (repeatable)")
    ap.add_argument("--coverage", action="store_true", help="collect coverage (pytest-cov)")
    ap.add_argument("--allow-empty", action="store_true", help="treat 'no tests collected' (pytest exit 5) as success")
    ap.add_argument("--dry-run", action="store_true", help="print the pytest argv and exit")
    ap.add_argument("passthrough", nargs="*", help="extra arguments passed to pytest")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    commands = plan(args)
    if args.dry_run:
        for cmd in commands:
            print(" ".join(cmd[1:]))
        return 0
    worst = 0
    for index, cmd in enumerate(commands):
        code = subprocess.run(cmd, check=False).returncode  # noqa: S603
        # pytest exit code 5 means "no tests collected". It is a failure (a gate must not pass by selecting
        # nothing) unless --allow-empty is given, or this is the serial second pass of a parallel run, where
        # an empty selection is normal.
        serial_pass = len(commands) == 2 and index == 1
        if code == 5 and (args.allow_empty or serial_pass):
            continue
        if code != 0:
            worst = worst or code
    return worst


if __name__ == "__main__":
    sys.exit(main())
