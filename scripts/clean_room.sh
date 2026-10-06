#!/usr/bin/env bash
# Phase exit gate (D-29, D-30): guarded clean-room rebuild of the devrag-stack project followed by the full
# test suites, repeated --runs N times. The single volume removal below runs only for project devrag-stack;
# any other project name is refused before Docker is invoked (B-05). No prune, image removal or cache
# commands exist in this script. Readiness is delegated to wait_stack.sh (no sleeps here).
# Usage: clean_room.sh [--runs N] [--no-record]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-devrag-stack}"
ALLOWED_PROJECT="devrag-stack"

if [ "$PROJECT" != "$ALLOWED_PROJECT" ]; then
  echo "REFUSED: clean_room.sh only operates on compose project '$ALLOWED_PROJECT', got '$PROJECT' (see BLOCKERS B-05)" >&2
  exit 3
fi

RUNS=1
RECORD=1
while [ $# -gt 0 ]; do
  case "$1" in
    --runs) RUNS="$2"; shift ;;
    --no-record) RECORD=0 ;;
    *) echo "usage: $0 [--runs N] [--no-record]" >&2; exit 2 ;;
  esac
  shift
done

cd "$ROOT"
COMPOSE=(docker compose -p "$PROJECT" --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml --profile cpu --profile elasticsearch)

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
  # Stop this project's own containers first: preflight checks free ports and available RAM, and a
  # running devrag-stack would fail both against itself. Non-destructive (no volumes removed here).
  step stop "${COMPOSE[@]}" stop
  step preflight scripts/preflight.sh
  "${COMPOSE[@]}" down -v
  step up "${COMPOSE[@]}" up -d --build
  step wait_stack scripts/wait_stack.sh --timeout 600
  echo "time-to-healthy: $(( $(date +%s) - start ))s"
  step unit uv run python run_tests.py -m unit
  step integration uv run python run_tests.py -m integration
  step e2e uv run python run_tests.py -m "e2e and not serial"
  step e2e-serial uv run python run_tests.py -m "e2e and serial"
  step go-race go test -race ./internal/... ./cmd/...
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
