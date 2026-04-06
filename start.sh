#!/bin/bash
# Start the FastAPI server in background
uvicorn server.app:app --host 0.0.0.0 --port 7860 &

# Wait for server to be ready
echo "Waiting for server to start..."
sleep 5

# Run inference with correct port
ENV_BASE_URL=http://localhost:7860 python inference.py
