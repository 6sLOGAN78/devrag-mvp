#!/usr/bin/env python3
"""Measure per-container memory of the devrag-stack project against its mem_limit (R-72).

Fails when any container exceeds its limit or the total exceeds the dev budget. With --record the
measured table replaces the body under 'Dev memory budget (measured)' in .planning/DECISIONS.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / ".planning" / "DECISIONS.md"
HEADING = "## Dev memory budget (measured)"
BUDGET_MIB = 3891  # 3.8 GiB
UNITS = {"B": 1 / 1048576, "KIB": 1 / 1024, "MIB": 1.0, "GIB": 1024.0, "KB": 1 / 1000 * 0.953674, "MB": 0.953674, "GB": 953.674}


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT).stdout  # noqa: S603


def to_mib(text: str) -> float:
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text)
    if not m:
        raise ValueError(f"unparseable size: {text!r}")
    return float(m.group(1)) * UNITS[m.group(2).upper()]


def project_containers(project: str) -> list[tuple[str, str]]:
    out = run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}} {{.Label \"com.docker.compose.service\"}}"])
    return [tuple(line.split(" ", 1)) for line in out.splitlines() if line.strip()]  # type: ignore[misc]


def measure(project: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cid, service in project_containers(project):
        limit = int(run(["docker", "inspect", "--format", "{{.HostConfig.Memory}}", cid]).strip() or 0) / 1048576
        running = run(["docker", "inspect", "--format", "{{.State.Running}}", cid]).strip() == "true"
        used: float | None = None
        if running:
            stats = json.loads(run(["docker", "stats", "--no-stream", "--format", "json", cid]).splitlines()[0])
            used = to_mib(str(stats["MemUsage"]).split("/")[0])
        rows.append({"service": service, "limit_mib": round(limit), "used_mib": None if used is None else round(used, 1), "running": running})
    return sorted(rows, key=lambda r: str(r["service"]))


def free_ram_mib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) // 1024
    return 0


def render(rows: list[dict[str, object]], total: float, disk: str, run_no: str) -> str:
    today = dt.date.today().isoformat()
    lines = [
        f"Measured with `docker stats --no-stream` on {today}, on this development host only (run {run_no}, after the full suites). Not a portable figure.",
        "",
        "| Container | Limit MiB | Measured MiB |",
        "|---|---|---|",
    ]
    for r in rows:
        limit = r["limit_mib"] or "none"
        used = "not running (one-shot, exited)" if r["used_mib"] is None else r["used_mib"]
        lines.append(f"| {r['service']} | {limit} | {used} |")
    lines += [
        "",
        f"Total measured: {total:.1f} MiB (budget {BUDGET_MIB} MiB). Host available RAM at measurement: {free_ram_mib()} MiB. Host free disk after the run: {disk or 'unknown'}.",
    ]
    return "\n".join(lines)


def record(body: str) -> None:
    text = DECISIONS.read_text()
    idx = text.index(HEADING)
    nxt = re.search(r"^## ", text[idx + len(HEADING):], re.M)
    end = idx + len(HEADING) + nxt.start() if nxt else len(text)
    DECISIONS.write_text(text[: idx + len(HEADING)] + "\n\n" + body + "\n" + ("\n" + text[end:] if nxt else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="devrag-stack")
    ap.add_argument("--record", action="store_true", help="write the table into .planning/DECISIONS.md")
    ap.add_argument("--run", default="1")
    ap.add_argument("--disk-free", default="")
    args = ap.parse_args()
    rows = measure(args.project)
    if not rows:
        print(f"no containers for project {args.project}", file=sys.stderr)
        return 1
    total = sum(float(r["used_mib"]) for r in rows if r["used_mib"] is not None)
    out_dir = ROOT / "ragflow-logs"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"clean-room-memory-{stamp}.json").write_text(json.dumps({"rows": rows, "total_mib": total}, indent=2))
    failures = []
    for r in rows:
        print(f"{r['service']}: {r['used_mib']} MiB (limit {r['limit_mib']})")
        if r["used_mib"] is not None and r["limit_mib"] and float(r["used_mib"]) > float(r["limit_mib"]):  # type: ignore[arg-type]
            failures.append(f"{r['service']} exceeds its limit")
    print(f"total: {total:.1f} MiB (budget {BUDGET_MIB})")
    if total > BUDGET_MIB:
        failures.append("total exceeds budget")
    if args.record:
        record(render(rows, total, args.disk_free, args.run))
    if failures:
        print("FAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
