#!/usr/bin/env bash
# App container entrypoint: render config, start Nginx, the Go API and the Python API.
# Go and Python drop to the host UID/GID with setpriv (Pitfall 11); any child exiting ends the container.
set -euo pipefail

cd /ragflow
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
LOG_DIR="${LOG_DIR:-/ragflow/logs}"
export LOG_DIR SERVICE_CONF="${SERVICE_CONF:-/ragflow/conf/service_conf.yaml}"

python scripts/render_conf.py --out "$SERVICE_CONF"
chown "$APP_UID:$APP_GID" "$SERVICE_CONF"
mkdir -p "$LOG_DIR"

if [ "${NGINX_TLS:-0}" = "1" ] && [ -f /etc/nginx/certs/server.crt ] && [ -f /etc/nginx/certs/server.key ]; then
  cp /etc/nginx/ragflow.https.conf /etc/nginx/conf.d/ragflow.conf
fi

drop() { setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups "$@"; }

pids=()
stop_all() {
  trap - TERM INT
  kill "${pids[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 143
}
trap stop_all TERM INT

nginx -g 'daemon off;' & pids+=($!)
drop /ragflow/bin/ragflow_server --api & pids+=($!)
drop python -m api.ragflow_server & pids+=($!)

set +e
wait -n
code=$?
echo "entrypoint: a child process exited (status $code); stopping the container" >&2
kill "${pids[@]}" 2>/dev/null
wait 2>/dev/null
exit "$((code == 0 ? 1 : code))"
