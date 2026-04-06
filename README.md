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
- `-0.05` — redundant action (already checked)
- `+0.30` — correct intervention (restart/rollback)
- `-0.20` — wrong service restarted
- `+0.50` + time bonus — correct RCA declared
- `0.0` — wrong RCA (not penalized, just no reward)
- Cumulative clamped to `[-1.0, 1.0]`

## Baseline scores

| Task | Random agent | LLM agent (Qwen2.5-72B) |
|---|---|---|
| task_easy | ~0.15 | ~0.75 |
| task_medium | ~0.08 | ~0.60 |
| task_hard | ~0.04 | ~0.45 |

## Setup
```bash
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

## Docker
```bash
docker build -t incident-env .
docker run -p 7860:7860 incident-env
```

## API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/reset` | POST | Start episode |
| `/step` | POST | Execute action |
| `/state` | GET | Ground truth state |
| `/grade` | GET | Episode score 0.0–1.0 |
| `/tasks` | GET | List all tasks |

## Inference
```bash
export HF_TOKEN=your_token
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export API_BASE_URL=https://router.huggingface.co/v1
python Inference.py
```