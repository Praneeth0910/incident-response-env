#!/bin/bash
uvicorn server.app:app --host 0.0.0.0 --port 7860 &

echo "Waiting for server to start..."
until curl -sf http://localhost:7860/health > /dev/null; do
  sleep 1
done

ENV_BASE_URL=http://localhost:7860 python3 inference.py