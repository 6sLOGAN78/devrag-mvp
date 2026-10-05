"""Render conf/service_conf.yaml from its template using environment variables.

Supported forms: ``${VAR:-default}`` (default when unset or empty) and
``${VAR:?message}`` (exit 1 naming VAR and message when unset or empty).
A literal ``$$`` is left untouched and never starts a substitution.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

DEFAULT_TEMPLATE = "conf/service_conf.yaml.template"
DEFAULT_OUT = "conf/service_conf.yaml"

_TOKEN = re.compile(r"\$\$|\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<op>[-?])(?P<arg>[^}]*))?\}")


class MissingVariable(Exception):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"{name}: {message}")
        self.name = name
        self.detail = message


def render(template: str, env: Mapping[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        if match.group(0) == "$$":
            return "$$"
        name = match.group("name")
        op = match.group("op")
        arg = match.group("arg") or ""
        value = env.get(name, "")
        if value != "":
            return value
        if op == "-":
            return arg
        if op == "?":
            raise MissingVariable(name, arg or "required variable is not set")
        return ""

    return _TOKEN.sub(sub, template)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    text = Path(args.template).read_text(encoding="utf-8")
    try:
        rendered = render(text, os.environ)
    except MissingVariable as exc:
        print(f"render_conf: missing required variable {exc.name}: {exc.detail}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    out.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
