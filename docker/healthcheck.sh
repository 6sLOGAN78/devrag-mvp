#!/usr/bin/env bash
# Combined probe through Nginx: Go /health and Python /api/v1/system/healthz must both return 200.
set -euo pipefail
curl -fsS -o /dev/null --max-time 4 http://127.0.0.1:80/health
curl -fsS -o /dev/null --max-time 4 http://127.0.0.1:80/api/v1/system/healthz
