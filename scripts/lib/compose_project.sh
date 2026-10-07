#!/usr/bin/env bash
# Single compose project name resolver shared by clean_room.sh and preflight.sh (WR-16).
# Precedence: COMPOSE_PROJECT_NAME in the environment (what `docker compose` itself honours), then the last
# assignment in docker/.env, then the default devrag-stack. Both scripts must agree on the name, otherwise the
# guard can inspect one project while `down -v` removes another.
# Usage (after sourcing): resolve_compose_project ROOT

resolve_compose_project() {
  local root="$1" file="" v=""
  if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
    printf '%s\n' "$COMPOSE_PROJECT_NAME"
    return 0
  fi
  file="$root/docker/.env"
  if [ -f "$file" ]; then
    v="$(grep -E '^[[:space:]]*COMPOSE_PROJECT_NAME=' "$file" | tail -n1 | cut -d= -f2- | tr -d '\r' || true)"
    case "$v" in
      \"*) v="${v#\"}"; v="${v%%\"*}" ;;
      \'*) v="${v#\'}"; v="${v%%\'*}" ;;
      *) v="${v%%[[:space:]]#*}"; v="${v%"${v##*[![:space:]]}"}" ;;
    esac
    v="${v#"${v%%[![:space:]]*}"}"
  fi
  printf '%s\n' "${v:-devrag-stack}"
}
