#!/usr/bin/env python3
"""Documented pytest wrapper: -p/--parallel, -t/--test, -m/--markers, -i/--ignore, --coverage."""
from __future__ import annotations

import argparse
import subprocess
import sys


def build_argv(args: argparse.Namespace) -> list[str]:
    argv = [sys.executable, "-m", "pytest"]
    if args.markers:
        argv += ["-m", args.markers]
    if args.test:
        argv += ["-k", args.test]
    for path in args.ignore:
        argv += ["--ignore", path]
    if args.parallel:
        argv += ["-n", "auto"]
    if args.coverage:
        argv += ["--cov"]
    argv += args.passthrough
    return argv


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run the devRag Python tests through pytest.")
    ap.add_argument("-p", "--parallel", action="store_true", help="run in parallel (pytest-xdist, -n auto)")
    ap.add_argument("-t", "--test", help="select tests by name expression (pytest -k)")
    ap.add_argument("-m", "--markers", help="select tests by marker expression (pytest -m)")
    ap.add_argument("-i", "--ignore", action="append", default=[], help="path to ignore (repeatable)")
    ap.add_argument("--coverage", action="store_true", help="collect coverage (pytest-cov)")
    ap.add_argument("--dry-run", action="store_true", help="print the pytest argv and exit")
    ap.add_argument("passthrough", nargs="*", help="extra arguments passed to pytest")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    cmd = build_argv(args)
    if args.dry_run:
        print(" ".join(cmd[1:]))
        return 0
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
