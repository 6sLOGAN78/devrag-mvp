#!/usr/bin/env bash
# Create docker/.env from docker/.env.example with generated secrets (SEC-04, R-61).
# Secret keys are the ones preceded by a "# secret" comment line and left empty in the example.
# Refuses to overwrite an existing .env unless --force. Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$ROOT/docker/.env.example"
TARGET="$ROOT/docker/.env"

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) echo "usage: $0 [--force]" >&2; exit 2 ;;
  esac
done

if [ -e "$TARGET" ] && [ "$FORCE" -ne 1 ]; then
  echo "docker/.env already exists; keeping it (use --force to regenerate secrets)."
  exit 0
fi

[ -f "$EXAMPLE" ] || { echo "missing $EXAMPLE" >&2; exit 1; }

umask 077
EXAMPLE="$EXAMPLE" TARGET="$TARGET" python3 - <<'PY'
import os
import secrets

example = os.environ["EXAMPLE"]
target = os.environ["TARGET"]
out: list[str] = []
filled = 0
marker = False
with open(example, encoding="utf-8") as fh:
    for raw in fh.read().splitlines():
        line = raw.rstrip()
        if line.strip() == "# secret":
            marker = True
            out.append(line)
            continue
        if marker and "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            if value == "":
                line = f"{key}={secrets.token_hex(16)}"
                filled += 1
        if line.strip():
            marker = False
        out.append(line)
with open(target, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
print(f"wrote docker/.env with {filled} generated secrets (values not shown)")
PY
chmod 600 "$TARGET"
