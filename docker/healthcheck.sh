#!/usr/bin/env bash
# Container health: both backends are probed directly (Go /health, Python /api/v1/system/healthz must be 200)
# and Nginx on port 80 must answer 200, or 301 only in TLS mode. A 301 alone can never pass (WR-13).
set -uo pipefail

GO_PORT="${GO_API_PORT:-9384}"
PY_PORT="${SVR_HTTP_PORT:-9380}"

code_of() { curl -sS -o /dev/null -w '%{http_code}' --max-time 4 "$1" 2>/dev/null || true; }

expect() {
  local name="$1" url="$2" got
  shift 2
  got="$(code_of "$url")"
  for want in "$@"; do
    [ "$got" = "$want" ] && return 0
  done
  echo "healthcheck: $name $url returned ${got:-000}, expected $*" >&2
  exit 1
}

expect "go backend" "http://127.0.0.1:${GO_PORT}/health" 200
expect "python backend" "http://127.0.0.1:${PY_PORT}/api/v1/system/healthz" 200
if [ "${NGINX_TLS:-0}" = "1" ]; then
  expect "nginx" "http://127.0.0.1:80/" 301
else
  expect "nginx" "http://127.0.0.1:80/" 200
fi
