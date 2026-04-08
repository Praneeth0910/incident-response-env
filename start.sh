#!/bin/bash
uvicorn server.app:app --host 0.0.0.0 --port 7860 &
UVICORN_PID=$!

echo "Waiting for server to start..."
until curl -sf http://localhost:7860/health > /dev/null; do
  sleep 1
done

ENV_BASE_URL=http://localhost:7860 python3 inference.py

# Keep the container running by waiting on the background API process
wait $UVICORN_PID