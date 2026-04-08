#!/bin/bash
set -e

echo "[start.sh] Starting Incident Response Environment on port 7860..."
echo "[start.sh] API_BASE_URL = ${API_BASE_URL:-not set (will be injected)}"
echo "[start.sh] MODEL_NAME   = ${MODEL_NAME:-not set}"

exec uvicorn server.app:app --host 0.0.0.0 --port 7860