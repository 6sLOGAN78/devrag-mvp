#!/usr/bin/env bash
# Host readiness checks before bringing the stack up (D-29, R-62). Never prunes Docker and never
# changes sysctl: it only measures and prints what to do. Each failure prints
# "FAIL <check>: <measured>" followed by "ACTION: <step>"; exit 1 if any check failed.
# Thresholds are overridable through the PREFLIGHT_* environment variables below.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/docker/.env"

env_value() { # env_value KEY DEFAULT
  local v=""
  if [ -f "$ENV_FILE" ]; then
    v="$(grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  fi
  echo "${v:-$2}"
}

MIN_DISK_GB="${PREFLIGHT_MIN_DISK_GB:-3}"
MIN_MAP_COUNT="${PREFLIGHT_MIN_MAP_COUNT:-262144}"
MIN_RAM_MB="${PREFLIGHT_MIN_RAM_MB:-4096}"
# shellcheck source=lib/compose_project.sh
. "$ROOT/scripts/lib/compose_project.sh"
PROJECT="$(resolve_compose_project "$ROOT")"
PORTS="${PREFLIGHT_PORTS-$(env_value SVR_WEB_HTTP_PORT 8080) $(env_value MYSQL_PORT 3306) $(env_value REDIS_PORT 6380) $(env_value MINIO_PORT 9000) $(env_value MINIO_CONSOLE_PORT 9001) $(env_value ES_PORT 9200) 9380 9381 9382 9383 9384}"
OVERRIDE_LOG="$ROOT/ragflow-logs/preflight-overrides.log"

FAILED=0
mkdir -p "$ROOT/ragflow-logs"

record_override() { # record_override NAME MEASURED THRESHOLD
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1 measured=$2 threshold=$3" >> "$OVERRIDE_LOG"
  echo "OVERRIDE recorded: $1 (measured $2, threshold $3) logged to ragflow-logs/preflight-overrides.log"
}

fail() { # fail CHECK MEASURED ACTION
  echo "FAIL $1: $2"
  echo "ACTION: $3"
  FAILED=1
}

# Compose project collisions. Every distinct working-dir label of the project is checked (labels may hold
# spaces or '@', so the loop reads whole lines). A foreign label is a WARNING by default and a FAIL with
# PREFLIGHT_STRICT_PROJECT=1 (clean_room.sh sets it: it removes volumes). Foreign resources are never touched.
check_project() {
  docker info >/dev/null 2>&1 || return 0
  local filter="label=com.docker.compose.project=$PROJECT" count wd foreign="" foreign_n=0
  count="$(docker ps -a --filter "$filter" --format '{{.ID}}' 2>/dev/null | wc -l)"
  if [ "$count" -eq 0 ]; then
    echo "OK project: no containers named '$PROJECT'"
    return 0
  fi
  while IFS= read -r wd; do
    if [ -n "$wd" ] && [ "$wd" != "$ROOT/docker" ]; then
      foreign="${foreign:+$foreign, }$wd"
      foreign_n=$((foreign_n + 1))
    fi
  done < <(docker ps -a --filter "$filter" --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null | sort -u)
  if [ "$foreign_n" -eq 0 ]; then
    echo "OK project: $count existing container(s) of '$PROJECT' belong to this checkout"
  elif [ "${PREFLIGHT_STRICT_PROJECT:-0}" = "1" ]; then
    fail "project name collision" "$count container(s) of project '$PROJECT' belong to another checkout: $foreign (see BLOCKERS B-05)" "choose another COMPOSE_PROJECT_NAME, or stop that checkout's stack yourself; this checkout will not touch it"
  else
    echo "WARNING project name collision: $count container(s) of project '$PROJECT' belong to $foreign (see BLOCKERS B-05); choose another COMPOSE_PROJECT_NAME"
  fi
}

case "${1:-}" in
  "") ;;
  --project-only)
    check_project
    if [ "$FAILED" -ne 0 ]; then
      echo "preflight project check FAILED"
      exit 1
    fi
    echo "preflight project check passed"
    exit 0
    ;;
  *) echo "usage: $0 [--project-only]" >&2; exit 2 ;;
esac

# Docker compose availability
if docker compose version >/dev/null 2>&1; then
  echo "OK compose: $(docker compose version --short 2>/dev/null)"
else
  fail compose "docker compose is not available" "install Docker Engine with the compose v2 plugin"
fi

# Free disk on the Docker root and on the repository partition
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
MIN_FREE_KB=""
for path in "$ROOT" "${DOCKER_ROOT:-/}"; do
  [ -d "$path" ] || continue
  kb="$(df -Pk "$path" 2>/dev/null | awk 'NR==2 {print $4}')"
  [ -n "$kb" ] || continue
  if [ -z "$MIN_FREE_KB" ] || [ "$kb" -lt "$MIN_FREE_KB" ]; then MIN_FREE_KB="$kb"; fi
done
if [ -n "$MIN_FREE_KB" ]; then
  FREE_GB="$(awk -v k="$MIN_FREE_KB" 'BEGIN {printf "%.1f", k/1048576}')"
  if awk -v f="$FREE_GB" -v t="$MIN_DISK_GB" 'BEGIN {exit !(f+0 >= t+0)}'; then
    echo "OK disk: ${FREE_GB} GB free (need ${MIN_DISK_GB} GB)"
  elif [ "${PREFLIGHT_ALLOW_LOW_DISK:-0}" = "1" ]; then
    echo "WARNING disk: only ${FREE_GB} GB free, threshold ${MIN_DISK_GB} GB"
    record_override PREFLIGHT_ALLOW_LOW_DISK "${FREE_GB}GB" "${MIN_DISK_GB}GB"
  else
    fail disk "${FREE_GB} GB free, need ${MIN_DISK_GB} GB" "free disk space yourself (Docker is never pruned automatically), or set PREFLIGHT_ALLOW_LOW_DISK=1 to record an override"
  fi
fi

# vm.max_map_count
MAP_COUNT="$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo 0)"
if [ "$MAP_COUNT" -ge "$MIN_MAP_COUNT" ]; then
  echo "OK vm.max_map_count: $MAP_COUNT"
elif [ "${PREFLIGHT_ALLOW_LOW_MAP_COUNT:-0}" = "1" ]; then
  echo "WARNING vm.max_map_count: $MAP_COUNT is below $MIN_MAP_COUNT"
  record_override PREFLIGHT_ALLOW_LOW_MAP_COUNT "$MAP_COUNT" "$MIN_MAP_COUNT"
else
  fail vm.max_map_count "$MAP_COUNT, need $MIN_MAP_COUNT" "run: sudo sysctl -w vm.max_map_count=262144 (or set PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 to record an override)"
fi

# RAM
AVAIL_MB="$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
if [ "$AVAIL_MB" -ge "$MIN_RAM_MB" ]; then
  echo "OK RAM: ${AVAIL_MB} MB available"
else
  fail RAM "${AVAIL_MB} MB available, need ${MIN_RAM_MB} MB" "stop other workloads to free memory or lower PREFLIGHT_MIN_RAM_MB"
fi

# Published ports
LISTEN="$(ss -ltnH 2>/dev/null || true)"
for port in $PORTS; do
  if echo "$LISTEN" | awk '{print $4}' | grep -Eq "[:.]${port}\$"; then
    owner="$(ss -ltnpH "sport = :${port}" 2>/dev/null | awk '{print $NF}' | head -n1)"
    fail "port $port" "port $port is already in use${owner:+ (owner: $owner)}" "stop the listener or change the port variable in docker/.env"
  else
    echo "OK port $port: free"
  fi
done

# Provider key (D-04, D-29): only presence is reported, never the value. The value is not stored in a variable.
# The gate sets PREFLIGHT_REQUIRE_LIVE_KEY=1, because the live_model step fails without the key; otherwise the
# check is informational so `make up` still works on a machine with no provider account.
if [ -n "$(env_value OPENROUTER_API_KEY '')" ]; then
  echo "OK openrouter key: present"
elif [ "${PREFLIGHT_REQUIRE_LIVE_KEY:-0}" = "1" ]; then
  fail "openrouter key" "missing" "add OPENROUTER_API_KEY to docker/.env (see docker/.env.example)"
else
  echo "INFO openrouter key: missing (the live_model tier and the Phase 3 gate need OPENROUTER_API_KEY in docker/.env)"
fi

check_project

if [ "$FAILED" -ne 0 ]; then
  echo "preflight FAILED"
  exit 1
fi
echo "preflight passed"
