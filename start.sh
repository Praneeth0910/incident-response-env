#!/bin/bash
set -e

echo "[start.sh] Starting Incident Response Environment on port 7860..."
echo "[start.sh] API_BASE_URL = ${API_BASE_URL:-not set (will be injected)}"
echo "[start.sh] MODEL_NAME   = ${MODEL_NAME:-not set}"

# Start the uvicorn server in the background
uvicorn server.app:app --host 0.0.0.0 --port 7860 &
SERVER_PID=$!

echo "[start.sh] Waiting for server to be ready on port 7860..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:7860/health > /dev/null 2>&1; then
        echo "[start.sh] Server is ready."
        break
    fi
    echo "[start.sh] Waiting... ($i/30)"
    sleep 2
done

# Now run inference.py (makes LLM API calls through the proxy)
echo "[start.sh] Running inference.py..."
python inference.py

echo "[start.sh] inference.py finished. Keeping server alive..."
wait $SERVER_PID