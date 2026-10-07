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
import uuid
from collections.abc import Mapping
from pathlib import Path

import yaml

DEFAULT_TEMPLATE = "conf/service_conf.yaml.template"
DEFAULT_OUT = "conf/service_conf.yaml"

_TOKEN = re.compile(r"\$\$|\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<op>[-?])(?P<arg>[^}]*))?\}")


class RenderError(Exception):
    """Base error. Messages name the variable only, never its value."""


class MissingVariable(RenderError):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"{name}: {message}")
        self.name = name
        self.detail = message


class InvalidValue(RenderError):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"{name}: {reason}")
        self.name = name
        self.detail = reason


def _has_control_char(value: str) -> bool:
    # C0/DEL plus the Unicode line breaks YAML 1.1 loaders treat as newlines (NEL, LS, PS).
    return any(ord(ch) < 32 and ch != "\t" or ord(ch) == 127 or ch in "\u0085\u2028\u2029" for ch in value)


def _in_single_quotes(template: str, pos: int) -> bool:
    """True when ``pos`` sits inside a single-quoted YAML scalar (odd quote count earlier on its line)."""
    line_start = template.rfind("\n", 0, pos) + 1
    return template.count("'", line_start, pos) % 2 == 1


def _escape(name: str, value: str, quoted: bool) -> str:
    if _has_control_char(value):
        raise InvalidValue(name, "value contains a control character (newline, carriage return, ...)")
    if quoted:
        return value.replace("'", "''")
    if "'" in value or '"' in value:
        raise InvalidValue(name, "value contains a quote character but is substituted in an unquoted YAML position")
    return value


def render(template: str, env: Mapping[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        if match.group(0) == "$$":
            return "$$"
        name = match.group("name")
        op = match.group("op")
        arg = match.group("arg") or ""
        value = env.get(name, "")
        quoted = _in_single_quotes(template, match.start())
        if value != "":
            return _escape(name, value, quoted)
        if op == "-":
            return _escape(name, arg, quoted)
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
    except RenderError as exc:
        print(f"render_conf: unsafe value for variable {exc}", file=sys.stderr)
        return 1
    try:
        yaml.safe_load(rendered)
    except yaml.YAMLError:
        print("render_conf: rendered output is not valid YAML (stage: post-render validation); nothing written", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Write to a 0600 temp file in the target directory, then atomically replace: no partial file, never world-readable.
    tmp_name = str(out.parent / f".render_conf.{uuid.uuid4().hex}")
    fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(tmp_name, out)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
