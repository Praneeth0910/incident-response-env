---
title: Incident Response Env
emoji: 🚨
colorFrom: red
colorTo: blue
sdk: docker
pinned: false
---

# Production Incident Response Environment

An OpenEnv-compliant RL environment where LLM agents act as on-call SREs,
investigating simulated microservices failures to identify root causes under
time pressure.

## Why this environment exists

Every tech company running software in production has incidents. A database
slows down, an API starts throwing 500 errors, users cannot log in. The
on-call engineer must investigate noisy, incomplete signals and identify the
root cause as fast as possible. This environment simulates that exact task.

## Action space

| Action | Description |
|---|---|
| `read_logs(service)` | Returns log lines from a service |
| `check_metrics(service)` | Returns latency, error_rate, cpu, memory |
| `check_health(service)` | Returns UP / DEGRADED / DOWN |
| `run_db_query(target)` | Runs diagnostic SQL against postgres |
| `restart_service(service)` | Restarts a service — penalized if wrong |
| `rollback_deployment(service)` | Rolls back — penalized if wrong |
| `declare_rca(service)` | Terminal action — declares root cause |

## Observation space

| Field | Type | Description |
|---|---|---|
| `message` | string | Current observation text |
| `step` | int | Current step number |
| `done` | bool | Episode finished |
| `alert` | string | Original incident alert |
| `metrics` | object | Service metrics (if requested) |

## Tasks

| Task | Difficulty | Max Steps | Description |
|---|---|---|---|
| `task_easy` | Easy | 10 | OOM crash on notification-service |
| `task_medium` | Medium | 15 | Bad deployment cascading failure |
| `task_hard` | Hard | 20 | Redis pool exhaustion + CPU red herring |

## Reward function

- `+0.05` to `+0.12` — relevant evidence found
- `+0.005` — redundant action (already checked)
- `+0.30` — correct intervention (restart/rollback)
- `+0.05` — wrong service restarted 
- `+0.01` — wrong service rolled back
- `+0.50` + time bonus + evidence bonus — correct RCA declared
- `+0.001` — wrong RCA
- Cumulative strictly clamped to `[0.01, 0.99]`

## Baseline scores

| Task | Random agent | LLM agent (Qwen2.5-72B) |
|---|---|---|
| task_easy | ~0.15 | ~0.75 |
| task_medium | ~0.08 | ~0.60 |
| task_hard | ~0.04 | ~0.45 |

## Setup
```bash
pip install -e .
```

## How to Run

### **Option 1: FastAPI + Gradio Dashboard (Recommended for Development)**

Start the server with the integrated web dashboard:

```bash
# Install dependencies
pip install -e .

# Start server
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Then open in your browser:
- **Dashboard UI**: http://localhost:7860/frontend
- **API Docs**: http://localhost:7860/docs (interactive Swagger UI)
- **API Health**: http://localhost:7860/health

**What you get:**
- Interactive Gradio dashboard for manual episode testing
- FastAPI REST API with full OpenEnv compatibility
- Real-time episode visualization
- Benchmark runner UI
- Leaderboard and statistics

---

### **Option 2: Docker (Production)**

```bash
# Build image
docker build -t incident-env .

# Run container
docker run -p 7860:7860 incident-env
```

The container:
- Starts uvicorn on port 7860
- Exposes the Gradio dashboard at `/frontend`
- Can run `inference.py` for benchmarking
- Stays alive after inference completes (via `wait` command)

---

### **Option 3: Gradio Dashboard Only (UI Testing)**

Run just the Gradio frontend without the FastAPI wrapper:

```bash
python -m server.gradio_app
```

Opens at http://localhost:7861 (default Gradio port).

---

### **Option 4: API-Only (Programmatic Access)**

For LLM agents or custom clients:

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Then call the REST API:
```bash
# Reset a task
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_easy"}'

# Execute an action
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "read_logs", "target": "api-gateway"}'

# Get current grade
curl http://localhost:7860/grade

# List all tasks
curl http://localhost:7860/tasks
```

---

## Running Benchmarks

### **From Python**

```bash
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="openai/gpt-4o"
export API_KEY="sk-..."
export ENV_BASE_URL="http://localhost:7860"

python inference.py
```

This:
1. Starts uvicorn in the background
2. Waits for the server to be healthy
3. Runs benchmarks on all three tasks
4. Writes results to `benchmark.json`
5. Keeps the container alive

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_BASE_URL` | *Required* | LLM endpoint (e.g., OpenAI, HuggingFace) |
| `MODEL_NAME` | *Required* | Model ID (e.g., `gpt-4o`, `Qwen/Qwen2.5-72B-Instruct`) |
| `API_KEY` | *Required* | API authentication key |
| `ENV_BASE_URL` | `http://localhost:7860` | Backend URL (for Docker/remote setups) |
| `DASHBOARD_PORT` | `7861` | Gradio-only dashboard port |

---

## Quick Verification

Test that everything is installed and working:

```bash
# Test environment module
python -c "from environment import IncidentResponseEnv; env = IncidentResponseEnv(); obs = env.reset(); print(f'✓ Environment OK - Alert: {obs.alert[:40]}...')"

# Test server imports
python -c "from server.app import app; print('✓ Server imports OK')"

# Test models
python -c "from models import Action, Observation; print('✓ Models OK')"

# Start server and test health (in separate terminal)
uvicorn server.app:app --host 0.0.0.0 --port 7860 &
sleep 2
curl http://localhost:7860/health
```

Expected output:
```json
{"status":"ok","env":"incident-response-env","version":"1.0.0"}
```

---

## Architecture

```
┌─────────────────────────────────┐
│   Gradio Web Dashboard          │
│   (Interactive episode runner)  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   FastAPI Server (port 7860)    │
│   - /reset, /step, /grade       │
│   - /tasks, /state, /health     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  IncidentResponseEnv            │
│  (Pydantic + State Machine)     │
└─────────────────────────────────┘
```

---

## File Structure

```
incident-response-env/
├── environment.py           # Core RL environment
├── models.py               # Pydantic schemas (Action, Observation, Reward)
├── inference.py            # LLM agent baseline + benchmark runner
├── benchmark_runner.py     # Metrics aggregation, leaderboard
├── server/
│   ├── app.py             # FastAPI entry point (uvicorn)
│   ├── dashboard_impl.py   # Gradio UI implementation
│   └── gradio_app.py      # Standalone Gradio launcher
├── docs/                   # Design specs and task documentation
├── pyproject.toml         # Dependencies (pip install -e .)
├── Dockerfile             # Container build
├── start.sh              # Container startup script
└── README.md             # This file
```

---

## Common Issues

### **Module Not Found: `environment`**
Ensure you're running from the project root:
```bash
cd incident-response-env
python -c "from environment import IncidentResponseEnv"
```

### **Port 7860 Already in Use**
Run on a different port:
```bash
uvicorn server.app:app --host 0.0.0.0 --port 8080
```

### **LLM Credentials Not Set**
The inference script requires valid credentials before running:
```bash
export API_BASE_URL="..."
export MODEL_NAME="..."
export API_KEY="..."
python inference.py
```

### **Docker Build Fails**
Ensure `pyproject.toml` is in the root and `README.md` exists:
```bash
ls pyproject.toml README.md
docker build -t incident-env .
```

---

## References and Documentation

For more details, see:
- [Design Specification](docs/DESIGN.md) — UI design system and component specs
- [Environment Documentation](docs/ENVIRONMENT.md) — Detailed task and reward specs
- [Benchmark Guide](docs/BENCHMARK.md) — Benchmarking and evaluation methodology
- [Top 50 Tasks](docs/TOP50_TASKS.txt) — Sample incident scenarios

---

## License

This environment is designed for the OpenEnv framework and hackathons.

