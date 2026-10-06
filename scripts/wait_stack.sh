#!/usr/bin/env bash
# Bounded readiness polling for the compose stack. This script is the only shell polling site
# (tests use test/helpers/wait.py). Usage: wait_stack.sh [--infra-only] [--timeout S] [--interval S]
# Waits until every long-running service of the project is healthy and any `init` service exited 0;
# unless --infra-only it also waits for HTTP 200 from /health and /api/v1/system/healthz on the web port.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/docker/.env"
TIMEOUT="${WAIT_STACK_TIMEOUT:-300}"
INTERVAL=2
INFRA_ONLY=0
PRINT_PROBES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --infra-only) INFRA_ONLY=1 ;;
    --timeout) TIMEOUT="$2"; shift ;;
    --interval) INTERVAL="$2"; shift ;;
    --print-probe-urls) PRINT_PROBES=1 ;;
    *) echo "usage: $0 [--infra-only] [--timeout S] [--interval S] [--print-probe-urls]" >&2; exit 2 ;;
  esac
  shift
done

env_value() {
  local v=""
  [ -f "$ENV_FILE" ] && v="$(grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  echo "${v:-$2}"
}

PROJECT="${COMPOSE_PROJECT_NAME:-$(env_value COMPOSE_PROJECT_NAME devrag-stack)}"
WEB_PORT="$(env_value SVR_WEB_HTTP_PORT 8080)"
TLS="${NGINX_TLS:-$(env_value NGINX_TLS 0)}"
if [ "$TLS" = "1" ]; then
  # TLS mode: probe the HTTPS port; -k because the dev certificate is self-signed (loopback readiness only).
  BASE_URL="https://127.0.0.1:$(env_value SVR_WEB_HTTPS_PORT 8443)"
  CURL_FLAGS=(-k)
else
  BASE_URL="http://127.0.0.1:${WEB_PORT}"
  CURL_FLAGS=()
fi

if [ "$PRINT_PROBES" -eq 1 ]; then
  echo "$BASE_URL/health ${CURL_FLAGS[*]:-}"
  echo "$BASE_URL/api/v1/system/healthz ${CURL_FLAGS[*]:-}"
  exit 0
fi

# Prints "name state health exitcode" per container of the project, one per line.
snapshot() {
  docker compose -p "$PROJECT" ps --all --format json 2>/dev/null | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
rows = []
if raw:
    try:
        data = json.loads(raw)
        rows = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
for r in rows:
    print(r.get("Service", "?"), r.get("State", "?"), r.get("Health") or "-", r.get("ExitCode", 0))
'
}

# Succeeds when the snapshot satisfies readiness. Services with no healthcheck must be running.
evaluate() {
  local rows="$1" ok=1 seen=0 name state health code
  while read -r name state health code; do
    [ -n "$name" ] || continue
    seen=1
    if [ "$name" = "init" ]; then
      [ "$state" = "exited" ] && [ "$code" = "0" ] || ok=0
    elif [ "$health" = "healthy" ]; then
      :
    elif [ "$health" = "-" ] && [ "$state" = "running" ]; then
      :
    else
      ok=0
    fi
  done <<< "$rows"
  [ "$seen" -eq 1 ] && [ "$ok" -eq 1 ]
}

http_ok() { [ "$(curl -s ${CURL_FLAGS[@]+"${CURL_FLAGS[@]}"} -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null)" = "200" ]; }

deadline=$(( $(date +%s) + TIMEOUT ))
while true; do
  rows="$(snapshot)"
  if evaluate "$rows"; then
    if [ "$INFRA_ONLY" -eq 1 ] || { http_ok "$BASE_URL/health" && http_ok "$BASE_URL/api/v1/system/healthz"; }; then
      echo "stack ready:"
      echo "$rows" | awk '{print "  " $1 ": " $2 " (" $3 ")"}'
      exit 0
    fi
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "TIMEOUT after ${TIMEOUT}s; last observed state per service:" >&2
    if [ -n "$rows" ]; then
      echo "$rows" | awk '{print "  " $1 ": state=" $2 " health=" $3 " exit=" $4}' >&2
    else
      echo "  (no containers for project $PROJECT)" >&2
    fi
    exit 1
  fi
  sleep "$INTERVAL"
done
