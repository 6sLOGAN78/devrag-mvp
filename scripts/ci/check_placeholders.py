#!/usr/bin/env python3
"""Gate: no placeholder, fake, mock or stub constructs in production trees (D-25).

Python is checked with ast and tokenize. Go and TS/TSX use a conservative scanner that
only looks at comments and identifier tokens (never string contents), so an HTML or JSX
``placeholder`` attribute is never flagged. A line may opt out with ``gate-ok: <reason>``
(the reason must be non-empty).
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

from _walk import PROD_DIRS, gate_ok, is_test_path, iter_files, prod_trees_present

MARKER = re.compile(r"\b(TODO|FIXME|XXX)\b")
FAKE_CLASS = re.compile(r"^_*(Fake|Mock|Stub)(?:[A-Z0-9_]|$)")
FAKE_FUNC = re.compile(r"^_*(stub|fake|mock)_", re.IGNORECASE)
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
GO_PANIC = re.compile(r'panic\(\s*"[^"]*not implemented', re.IGNORECASE)
Finding = tuple[int, str]


def python_findings(text: str) -> list[Finding]:
    out: list[Finding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [(exc.lineno or 1, f"cannot parse: {exc.msg}")]
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ClassDef) and FAKE_CLASS.match(node.name):
            out.append((line, f"fake/mock/stub class {node.name}"))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and FAKE_FUNC.match(node.name):
            out.append((line, f"stub/fake/mock function {node.name}"))
        elif isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                out.append((line, "raise NotImplementedError"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("mock", "unittest.mock"):
                    out.append((line, f"import of {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            names = {a.name for a in node.names}
            if node.module in ("mock", "unittest.mock") or (node.module == "unittest" and "mock" in names):
                out.append((line, "import of mock"))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and MARKER.search(tok.string):
                out.append((tok.start[0], f"{MARKER.search(tok.string).group(1)} comment"))  # type: ignore[union-attr]
    except (tokenize.TokenError, IndentationError):
        pass
    return out


def c_like_tokens(text: str, ts: bool):
    """Yield ("comment"|"ident", line, value) skipping string and rune literal contents."""
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "\n":
            line += 1
            i += 1
        elif c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j == -1 else j
            yield "comment", line, text[i:j]
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            chunk = text[i:j]
            for k, part in enumerate(chunk.split("\n")):
                yield "comment", line + k, part
            line += chunk.count("\n")
            i = j
        elif c in "\"'" or (c == "`"):
            multiline = c == "`"
            j = i + 1
            while j < n:
                if text[j] == "\\" and c != "`" or (text[j] == "\\" and ts):
                    j += 2
                    continue
                if text[j] == c:
                    break
                if text[j] == "\n":
                    if not multiline:
                        break
                    line += 1
                j += 1
            i = j + 1
        else:
            m = IDENT.match(text, i)
            if m:
                yield "ident", line, m.group(0)
                i = m.end()
            else:
                i += 1


def c_like_findings(text: str, ts: bool) -> list[Finding]:
    out: list[Finding] = []
    for kind, line, value in c_like_tokens(text, ts):
        if kind == "comment":
            m = MARKER.search(value)
            if m:
                out.append((line, f"{m.group(1)} comment"))
        elif FAKE_CLASS.match(value):
            out.append((line, f"fake/mock/stub identifier {value}"))
    if not ts:
        for idx, src in enumerate(text.split("\n"), 1):
            m = GO_PANIC.search(src)
            if m and "//" not in src[: m.start()]:
                out.append((idx, 'panic("not implemented")'))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    if not prod_trees_present(root):
        print("placeholders: skipped: tree absent")
        return 0
    findings = 0
    for relpath, path in iter_files(root, PROD_DIRS, (".py", ".go", ".ts", ".tsx", ".js", ".jsx")):
        if is_test_path(relpath):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        if path.suffix == ".py":
            found = python_findings(text)
        else:
            found = c_like_findings(text, ts=path.suffix != ".go")
        for idx, src in enumerate(lines, 1):
            if gate_ok(src) == "":
                found.append((idx, "gate-ok requires a non-empty reason"))
        for line, reason in sorted(set(found)):
            src = lines[line - 1] if 0 < line <= len(lines) else ""
            if gate_ok(src):
                continue
            print(f"{relpath}:{line}: {reason}")
            findings += 1
    if findings:
        print(f"placeholders: {findings} finding(s)")
        return 1
    print("placeholders OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
