#!/usr/bin/env bash
# Self-signed certificate for tests and local dev only (B-10). Output is git-ignored.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/docker/nginx/certs"
force=0
[ "${1:-}" = "--force" ] && force=1

if [ -e "$out/server.crt" ] && [ "$force" -ne 1 ]; then
  echo "refusing to overwrite $out/server.crt (use --force)" >&2
  exit 1
fi
mkdir -p "$out"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  -keyout "$out/server.key" -out "$out/server.crt" 2>/dev/null
chmod 600 "$out/server.key"
chmod 644 "$out/server.crt"
echo "wrote $out/server.crt and server.key"
