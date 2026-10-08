#!/usr/bin/env bash
# Create docker/.env from docker/.env.example with generated secrets (SEC-04, R-61, R-96).
# Secret keys are the ones preceded by a "# secret" comment line and left empty in the example.
# SECRET_KEY is generated as 64 hex characters; LLM_KEY_ENCRYPTION_KEY as 32 random bytes in URL-safe base64;
# operator-supplied secrets (SUPERUSER_PASSWORD, SMTP_PASSWORD, OPENROUTER_API_KEY) are never generated and stay empty.
# Without a flag: refuses to overwrite an existing .env. With --append-missing: appends only the keys the
# existing .env lacks and never rewrites or regenerates an existing line (safe against live volumes).
# Never prints secret values. ENV_EXAMPLE / ENV_TARGET override the paths (tests).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="${ENV_EXAMPLE:-$ROOT/docker/.env.example}"
TARGET="${ENV_TARGET:-$ROOT/docker/.env}"

FORCE=0
APPEND=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --append-missing) APPEND=1 ;;
    *) echo "usage: $0 [--force | --append-missing]" >&2; exit 2 ;;
  esac
done

if [ "$APPEND" -ne 1 ] && [ -e "$TARGET" ] && [ "$FORCE" -ne 1 ]; then
  echo "docker/.env already exists; keeping it (run '$0 --append-missing' to add newly catalogued keys)."
  exit 0
fi

[ -f "$EXAMPLE" ] || { echo "missing $EXAMPLE" >&2; exit 1; }

umask 077
EXAMPLE="$EXAMPLE" TARGET="$TARGET" APPEND="$APPEND" python3 - <<'PY'
import base64
import os
import secrets

example = os.environ["EXAMPLE"]
target = os.environ["TARGET"]
append = os.environ["APPEND"] == "1"
# Supplied by the operator, never generated.
OPERATOR_SUPPLIED = {"SUPERUSER_PASSWORD", "SMTP_PASSWORD", "OPENROUTER_API_KEY"}


def generated(key: str) -> str:
    if key == "LLM_KEY_ENCRYPTION_KEY":
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    return secrets.token_hex(32) if key == "SECRET_KEY" else secrets.token_hex(16)


existing: set[str] = set()
existing_text = ""
if append and os.path.exists(target):
    with open(target, encoding="utf-8") as fh:
        existing_text = fh.read()
    for raw in existing_text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            existing.add(line.partition("=")[0].strip())

out: list[str] = []
filled = 0
added = 0
marker = False
pending_comments: list[str] = []
with open(example, encoding="utf-8") as fh:
    for raw in fh.read().splitlines():
        line = raw.rstrip()
        if line.strip() == "# secret":
            marker = True
            pending_comments.append(line)
            continue
        is_key = bool(line.strip()) and not line.lstrip().startswith("#") and "=" in line
        if is_key:
            key, _, value = line.partition("=")
            if marker and value == "" and key not in OPERATOR_SUPPLIED:
                line = f"{key}={generated(key)}"
                filled += 1
            if append:
                if key not in existing:
                    out.extend(pending_comments)
                    out.append(line)
                    added += 1
                pending_comments = []
                marker = False
                continue
            out.extend(pending_comments)
            pending_comments = []
            out.append(line)
            marker = False
            continue
        out.extend(pending_comments)
        pending_comments = []
        if line.strip():
            marker = False
        if not append:
            out.append(line)
        # In append mode, plain comments and blank lines of the example are not copied.

if append:
    if added:
        prefix = existing_text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(prefix + "\n".join(out) + "\n")
    print(f"docker/.env: appended {added} missing keys ({filled} generated secrets, values not shown)")
else:
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote docker/.env with {filled} generated secrets (values not shown)")
PY
chmod 600 "$TARGET"
