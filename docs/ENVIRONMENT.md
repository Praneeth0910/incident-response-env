# ENVIRONMENT.md — Full Environment Specification
> **incident-response-env** · OpenEnv-compliant · Apache 2.0

Complete technical reference for the environment. Read this before building a custom agent, extending the environment, or interpreting benchmark results.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   HuggingFace Space                  │
│                                                       │
│   ┌──────────────┐         ┌──────────────────────┐  │
│   │  FastAPI     │◄───────►│  IncidentResponseEnv │  │
│   │  server/     │  calls  │  environment.py      │  │
│   │  app.py      │         └──────────────────────┘  │
│   │  :7860       │                                    │
│   └──────┬───────┘                                   │
│          │ HTTP                                       │
│   ┌──────▼───────┐                                   │
│   │  Inference   │◄── LLM (HuggingFace / OpenAI)    │
│   │  .py         │         via OpenAI-compatible API │
│   └──────────────┘                                   │
└─────────────────────────────────────────────────────┘
```

---

## REST API Reference

Base URL: `http://localhost:7860` (local) or your HF Space URL.

### `POST /reset`
Start a new episode.

**Request:**
```json
{
  "task_id": "task_easy",   // "task_easy" | "task_medium" | "task_hard"
  "seed": 42                // optional int — for reproducible episodes
}
```

**Response:**
```json
{
  "message": "Incident active. Notification service crashed...",
  "step": 0,
  "done": false,
  "alert": "ALERT: High error rate detected. API gateway reporting 500s. Latency p99: 3.8s.",
  "metrics": null
}
```

---

### `POST /step`
Take one action in the current episode.

**Request:**
```json
{"action_type": "read_logs", "target": "notification-service"}
```

**Response:**
```json
{
  "observation": {
    "message": "Logs from notification-service:\n[ERROR] java.lang.OutOfMemoryError...",
    "step": 1,
    "done": false,
    "alert": "ALERT: High error rate detected...",
    "metrics": null
  },
  "reward": {
    "value": 0.1,
    "reason": "found fault evidence in notification-service logs"
  },
  "done": false,
  "info": {
    "step": 1,
    "cumulative_reward": 0.1,
    "evidence_found": ["logs_fault_svc"]
  }
}
```

---

### `GET /state`
Inspect current episode state (includes hidden ground truth — for debugging only).

**Response:**
```json
{
  "task_id": "task_easy",
  "task_name": "OOM crash — single service",
  "difficulty": "easy",
  "hidden_fault_service": "notification-service",
  "hidden_fault_type": "oom_crash",
  "step_count": 3,
  "max_steps": 10,
  "done": false,
  "cumulative_reward": 0.27,
  "evidence_found": ["logs_fault_svc", "health_fault_svc"]
}
```

> ⚠️ The agent should NEVER call `/state` during an episode — it exposes the answer. This endpoint is for debugging and visualization only.

---

### `GET /grade`
Get the final episode score.

**Response:**
```json
{"score": 0.8750}
```

Score is in `[0.0, 1.0]`. Only meaningful after `done=true`.

---

### `GET /health`
Liveness check.

**Response:**
```json
{"status": "ok", "env": "incident-response-env", "version": "1.0.0"}
```

---

### `GET /tasks`
List all available tasks.

**Response:**
```json
{
  "task_easy": {
    "name": "OOM crash — single service",
    "difficulty": "easy",
    "max_steps": 10,
    "description": "Notification service crashed due to out-of-memory error."
  },
  ...
}
```

---

## Task Definitions

### task_easy — OOM Crash
| Property | Value |
|---|---|
| Difficulty | Easy |
| Max Steps | 10 |
| Ideal Steps | 3–4 |
| Fault Service | `notification-service` |
| Fault Type | `oom_crash` |
| Red Herrings | None |
| Key Signal | `memory_pct: 99`, `error_rate: 1.0`, health=DOWN |
| Correct Fix | `restart_service` → `declare_rca` |

### task_medium — Bad Deployment
| Property | Value |
|---|---|
| Difficulty | Medium |
| Max Steps | 15 |
| Ideal Steps | 5–7 |
| Fault Service | `order-service` |
| Fault Type | `bad_deployment` |
| Red Herrings | `auth-service` (appears degraded) |
| Key Signal | Logs: `env var DB_HOST missing`, `circuit breaker open` |
| Correct Fix | `rollback_deployment` → `declare_rca` |

### task_hard — Connection Pool Exhaustion
| Property | Value |
|---|---|
| Difficulty | Hard |
| Max Steps | 20 |
| Ideal Steps | 7–10 |
| Fault Service | `redis-cache` |
| Fault Type | `connection_pool_exhausted` |
| Red Herrings | `order-service` (high CPU, looks suspicious) |
| Key Signal | DB query: `active_connections=500/500`, `waiting_queries=847` |
| Correct Fix | `run_db_query` to confirm → `declare_rca` |

---

## Reward Function — Full Specification

### Per-Action Rewards

```python
# read_logs
fault_service:   +0.10  # "found fault evidence in logs"
api-gateway:     +0.05  # "gateway logs show symptoms"
other:           +0.00  # "no relevant signal"

# check_metrics
fault_service:   +0.08  # "fault service metrics show anomaly"
red_herring:     +0.02  # "suspicious but not fault service"
other:           +0.00  # "metrics normal"

# check_health
fault_service (oom):      +0.07  # "found downed service"
fault_service (other):    +0.05  # "service degraded"
other:                    +0.00

# run_db_query
connection_pool task:     +0.12  # "confirms connection pool exhaustion"
other tasks:              +0.01  # "limited signal"

# restart_service
correct service + oom:    +0.30  # "correct — oom_crash resolved"
correct service + wrong:  +0.10  # "restarted but wrong fix type"
wrong service:            -0.20  # "wrong service — cascading risk"

# rollback_deployment
correct service + bad_dep: +0.30  # "correct rollback"
correct service + wrong:   +0.05  # "rollback completed but wrong fix"
wrong service:             -0.15  # "wrong target"

# any repeated action
                          -0.05  # "redundant action"

# declare_rca
correct service:   +0.50 + time_bonus + evidence_bonus  (max 1.0)
wrong service:     +0.00
```

### Time Bonus (declare_rca only)
```python
time_bonus = max(0.0, (max_steps - step_count) / max_steps) * 0.4
# Example: declare at step 4 of 10 → (10-4)/10 * 0.4 = 0.24
# Example: declare at step 9 of 10 → (10-9)/10 * 0.4 = 0.04
```

### Evidence Bonus (declare_rca only)
```python
evidence_bonus = len(relevant_evidence_found) * 0.03
# Max: 5 evidence types × 0.03 = 0.15
```

### Time Pressure (after 50% steps used)
```python
if progress > 0.5:
    time_penalty = -0.01 * ((progress - 0.5) / 0.5)
    reward_value += time_penalty
```

### Cumulative Reward
```python
cumulative = sum(all_step_rewards)
cumulative = max(-1.0, min(1.0, cumulative))  # clamped to [-1, 1]
```

### Final Grade
```python
score = max(0.0, min(1.0, cumulative_reward))
success = score >= 0.6
```

---

## Extending the Environment

### Adding a New Task

In `environment.py`, add to the `TASKS` dict:
```python
"task_yourname": {
    "name": "Human-readable name",
    "difficulty": "easy" | "medium" | "hard",
    "max_steps": 10 | 15 | 20,
    "description": "One sentence description of the fault scenario.",
    "alert": "ALERT: What the on-call engineer sees in their pager.",
    "fault_service": "service-name",        # must be in SERVICES list
    "fault_type": "oom_crash" | "bad_deployment" | "connection_pool_exhausted",
    "red_herrings": [],                     # list of service names
    "ideal_steps": 4,                       # expected optimal step count
},
```

Then update `openenv.yaml` and `Inference.py`'s `TASKS` list.

### Adding a New Fault Type

1. Add a new fault type string to the `fault_type` field
2. Update `_make_metrics()` to return anomalous metrics for that fault
3. Update `_make_logs()` to return appropriate log lines
4. Update the `step()` method's remediation logic to handle the new fix action
5. Update `AGENT.md` fault type table

### Adding a New Service

Add to the `SERVICES` list in `environment.py` and update `openenv.yaml`'s action space description.

---

## Reproducibility

Set `seed` in the `/reset` request for deterministic episodes:
```python
env_reset("task_hard", seed=42)
```

This seeds Python's `random` module, making all `_make_metrics()` random values deterministic for that episode.

---

## Known Limitations

- **Single-instance server:** The FastAPI app uses a single global `IncidentResponseEnv` instance. Concurrent agents will interfere with each other.
- **No persistent storage:** Benchmark results are not persisted across container restarts by default.
- **Simulated, not live:** All metrics and logs are procedurally generated — not from a real Kubernetes cluster.
- **Limited fault diversity:** Currently 3 fault types. See `SKILLS.md` for planned expansions.
