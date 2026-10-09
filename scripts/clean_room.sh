#!/usr/bin/env bash
# Phase exit gate (D-29, D-30): guarded clean-room rebuild of the devrag-stack project followed by the full
# test suites, repeated --runs N times. The single volume removal below runs only for project devrag-stack;
# any other project name is refused before Docker is invoked (B-05). No prune, image removal or cache
# commands exist in this script. Readiness is delegated to wait_stack.sh (no sleeps here).
# --runs must be a positive integer (exit 2 before Docker). A foreign same-name project is refused before stop.
# Usage: clean_room.sh [--runs N] [--no-record]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/compose_project.sh
. "$ROOT/scripts/lib/compose_project.sh"
PROJECT="$(resolve_compose_project "$ROOT")"
ALLOWED_PROJECT="devrag-stack"

if [ "$PROJECT" != "$ALLOWED_PROJECT" ]; then
  echo "REFUSED: clean_room.sh only operates on compose project '$ALLOWED_PROJECT', got '$PROJECT' (see BLOCKERS B-05)" >&2
  exit 3
fi

RUNS=1
RECORD=1
while [ $# -gt 0 ]; do
  case "$1" in
    --runs)
      [ $# -ge 2 ] || { echo "--runs must be a positive integer (missing value)" >&2; exit 2; }
      RUNS="$2"; shift ;;
    --no-record) RECORD=0 ;;
    *) echo "usage: $0 [--runs N] [--no-record]" >&2; exit 2 ;;
  esac
  shift
done

if ! [[ "$RUNS" =~ ^[1-9][0-9]*$ ]]; then
  echo "--runs must be a positive integer, got '$RUNS'" >&2
  exit 2
fi

cd "$ROOT"
# The Go e2e/manual tiers and the vitest live project take their base URL from the environment and default
# to port 8080. Derive it from docker/.env so the gate follows SVR_WEB_HTTP_PORT; caller-set values win.
WEB_PORT="$(grep -E '^SVR_WEB_HTTP_PORT=' docker/.env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
WEB_PORT="${WEB_PORT:-8080}"
export E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:${WEB_PORT}}"
export MANUAL_BASE_URL="${MANUAL_BASE_URL:-http://127.0.0.1:${WEB_PORT}}"
export LIVE_BASE_URL="${LIVE_BASE_URL:-http://127.0.0.1:${WEB_PORT}}"
# Host-run Go tiers read the rendered configuration and the administrative database account from the environment;
# without them the scratch-database tests skip and the fixture tests fail. The value is read from the git-ignored
# docker/.env and is never printed. Caller-set values win.
export SERVICE_CONF="${SERVICE_CONF:-$ROOT/conf/service_conf.yaml}"
if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then
  MYSQL_ROOT_PASSWORD="$(grep -E '^MYSQL_ROOT_PASSWORD=' docker/.env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
fi
export MYSQL_ROOT_PASSWORD
# The mail profile (dev file only) gives the password-reset e2e and live tests a real SMTP sink.
COMPOSE=(docker compose -p "$PROJECT" --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml --profile cpu --profile elasticsearch --profile mail)

step() { # step NAME CMD...
  local name="$1"
  shift
  echo "=== STEP $name: $*"
  if "$@"; then
    echo "PASS $name"
  else
    echo "FAIL $name" >&2
    exit 1
  fi
}

for run in $(seq 1 "$RUNS"); do
  echo "##### clean-room run $run of $RUNS ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  start="$(date +%s)"
  # Refuse before anything is stopped or removed when any container of this project name belongs to another
  # checkout (B-05): strict mode turns the preflight warning into a failure.
  step project-guard env PREFLIGHT_STRICT_PROJECT=1 COMPOSE_PROJECT_NAME="$PROJECT" scripts/preflight.sh --project-only
  # Stop this project's own containers first: preflight checks free ports and available RAM, and a
  # running devrag-stack would fail both against itself. Non-destructive (no volumes removed here).
  step stop "${COMPOSE[@]}" stop
  step preflight env PREFLIGHT_REQUIRE_LIVE_KEY=1 scripts/preflight.sh
  "${COMPOSE[@]}" down -v
  step up "${COMPOSE[@]}" up -d --build
  step wait_stack scripts/wait_stack.sh --timeout 600
  echo "time-to-healthy: $(( $(date +%s) - start ))s"
  step unit uv run python run_tests.py -m unit
  step integration uv run python run_tests.py -m integration
  step e2e uv run python run_tests.py -m "e2e and not serial"
  step e2e-serial uv run python run_tests.py -m "e2e and serial"
  step live-model uv run python run_tests.py -m live_model
  step go-race go test -race -count=1 ./internal/... ./cmd/...
  step go-tiers go test -count=1 -tags=integration,e2e ./...
  step go-manual go test -count=1 -tags=manual ./internal/testutil/...
  step go-cgo go test -count=1 -tags=cgo ./internal/testutil/...
  step vitest-unit bash -c 'cd web && npm run test -- --run'
  step vitest-live bash -c 'cd web && npm run test:live'
  df_line="$(df -BG / | awk 'NR==2 {print $4}')"
  if [ "$RECORD" -eq 1 ] && [ "$run" -eq "$RUNS" ]; then
    step memory uv run python scripts/record_memory.py --record --run "$run" --disk-free "$df_line"
  else
    step memory uv run python scripts/record_memory.py --run "$run" --disk-free "$df_line"
  fi
  echo "df after run $run:"
  df -BG /
  echo "##### run $run finished in $(( $(date +%s) - start ))s"
done
echo "clean-room: $RUNS run(s) passed"
