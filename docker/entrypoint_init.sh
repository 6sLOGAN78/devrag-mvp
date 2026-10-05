#!/usr/bin/env bash
# One-shot init job: render config, apply Python migrations, ensure the bucket, verify the schema from Go.
# Dependencies are gated by compose healthchecks (service_healthy), so no waiting happens here.
set -euo pipefail

cd /ragflow
export SERVICE_CONF="${SERVICE_CONF:-/ragflow/conf/service_conf.yaml}"
python scripts/render_conf.py --out "$SERVICE_CONF"
python -m api.db.init_db
python -m common.bootstrap.ensure_bucket
/ragflow/bin/ragflow_server --migrate
