#!/usr/bin/env python3
"""Gate: no untrusted-deserialization primitives (SEC-05, R-38).

Production trees reject pickle, dill, cloudpickle, joblib.load, read_pickle,
numpy.load(allow_pickle=True), shelve and marshal loads outright. Test trees may use
them only on a line carrying ``gate-ok: <reason>``. No allow-list helper exists by design.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from _walk import PROD_DIRS, gate_ok, is_test_path, iter_files

BANNED_MODULES = {"dill", "cloudpickle", "cPickle"}
BANNED_CALLS = {
    "pickle.loads", "pickle.load", "pickle.Unpickler", "_pickle.loads", "_pickle.load", "_pickle.Unpickler",
    "joblib.load", "pandas.read_pickle", "shelve.open", "marshal.loads", "marshal.load",
}
TARGETS = (*PROD_DIRS, "test", "tests")


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def findings_for(text: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [(exc.lineno or 1, f"cannot parse: {exc.msg}")]
    alias: dict[str, str] = {}
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                if a.name.split(".")[0] in BANNED_MODULES:
                    out.append((node.lineno, f"import of {a.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in BANNED_MODULES:
                out.append((node.lineno, f"import from {node.module}"))
            for a in node.names:
                alias[a.asname or a.name] = f"{node.module}.{a.name}"
                if f"{node.module}.{a.name}" in BANNED_CALLS:
                    out.append((node.lineno, f"import of {node.module}.{a.name}"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if name is None:
            continue
        head, _, rest = name.partition(".")
        resolved = alias.get(head, head) + ("." + rest if rest else "")
        if resolved.split(".")[0] in BANNED_MODULES:
            out.append((node.lineno, f"call to {resolved}"))
        elif resolved in BANNED_CALLS:
            out.append((node.lineno, f"call to {resolved}"))
        elif resolved.endswith(".read_pickle") or resolved == "read_pickle":
            out.append((node.lineno, "call to read_pickle"))
        elif resolved in ("numpy.load", "np.load"):
            for kw in node.keywords:
                if kw.arg == "allow_pickle" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    out.append((node.lineno, "numpy.load(allow_pickle=True)"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    if not any((root / d).is_dir() for d in TARGETS):
        print("pickle: skipped: tree absent")
        return 0
    count = 0
    for relpath, path in iter_files(root, TARGETS, (".py",)):
        lines = (text := path.read_text(encoding="utf-8", errors="replace")).split("\n")
        in_test = is_test_path(relpath)
        for line, reason in sorted(set(findings_for(text))):
            src = lines[line - 1] if 0 < line <= len(lines) else ""
            if in_test and gate_ok(src):
                continue
            print(f"{relpath}:{line}: {reason}")
            count += 1
    if count:
        print(f"pickle: {count} finding(s)")
        return 1
    print("pickle OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
