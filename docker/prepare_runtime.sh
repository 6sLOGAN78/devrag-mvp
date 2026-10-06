#!/usr/bin/env bash
# Pre-start step run by entrypoint.sh before any child process starts.
#  1. Log directory: create it and hand it to the dropped APP_UID:APP_GID (WR-11).
#  2. TLS: NGINX_TLS=1 requires server.crt and server.key; otherwise exit 1. Never fall back to HTTP (WR-12).
# Paths are env-overridable so the script is unit-testable with fake binaries.
set -euo pipefail

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
LOG_DIR="${LOG_DIR:-/ragflow/logs}"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx/conf.d}"
NGINX_CERT_DIR="${NGINX_CERT_DIR:-/etc/nginx/certs}"
NGINX_HTTPS_CONF="${NGINX_HTTPS_CONF:-/etc/nginx/ragflow.https.conf}"

mkdir -p "$LOG_DIR"
chown "$APP_UID:$APP_GID" "$LOG_DIR"

if [ "${NGINX_TLS:-0}" = "1" ]; then
  if [ ! -f "$NGINX_CERT_DIR/server.crt" ] || [ ! -f "$NGINX_CERT_DIR/server.key" ]; then
    echo "prepare_runtime: NGINX_TLS=1 but certificate or key is missing in $NGINX_CERT_DIR (need server.crt and server.key); refusing to serve plain HTTP" >&2
    exit 1
  fi
  cp "$NGINX_HTTPS_CONF" "$NGINX_CONF_DIR/ragflow.conf"
fi
