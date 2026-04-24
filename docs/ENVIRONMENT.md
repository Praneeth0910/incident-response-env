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
  "task_id": "task_cpu_spike",   // Choose from the 14 available tasks
  "seed": 42                     // optional int — for reproducible episodes
}
```

**Response:**
```json
{
  "message": "Incident active. A hot loop in JWT validation is pegging auth-service CPU at 99%...",
  "step": 0,
  "done": false,
  "alert": "ALERT: Login latency p99 > 8s. Auth service CPU at 99%. Users cannot sign in.",
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
  "task_id": "task_cpu_spike",
  "task_name": "Auth service CPU hard loop",
  "difficulty": "easy",
  "hidden_fault_service": "auth-service",
  "hidden_fault_type": "cpu_spike",
  "step_count": 3,
  "max_steps": 10,
  "done": false,
  "cumulative_reward": 0.27,
  "evidence_found": ["logs_fault_svc", "metrics_fault_svc"]
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
  "task_cpu_spike": {
    "name": "Auth service CPU hard loop",
    "difficulty": "easy",
    "max_steps": 10,
    "description": "A hot loop in JWT validation is pegging auth-service CPU at 99%."
  }
}
```

---

## Task Definitions

### 1. task_cpu_spike — Auth Service CPU hard loop
| Property | Value |
|---|---|
| Difficulty | Easy |
| Max Steps | 10 |
| Ideal Steps | 5 |
| Fault Service | `auth-service` |
| Fault Type | `cpu_spike` |
| Red Herrings | None |
| Key Signal | `cpu_pct: 99`, Logs: `hot loop detected in JWTValidator.validate()` |
| Correct Fix | `restart_service` → `declare_rca` |

### 2. task_db_connection_leak — Database connection pool exhaustion
| Property | Value |
|---|---|
| Difficulty | Medium |
| Max Steps | 15 |
| Ideal Steps | 6 |
| Fault Service | `order-service` |
| Fault Type | `connection_pool_exhausted` |
| Red Herrings | `postgres-db` (appears to be failing) |
| Key Signal | DB Query: `active_connections: 500` / `waiting_queries: 847` |
| Correct Fix | `run_db_query` to confirm → `declare_rca` |

### 3. task_redis_memory_eviction — Redis cache memory eviction cascade
| Property | Value |
|---|---|
| Difficulty | Medium |
| Max Steps | 15 |
| Ideal Steps | 5 |
| Fault Service | `redis-cache` |
| Fault Type | `memory_eviction` |
| Red Herrings | `api-gateway` |
| Key Signal | Cache miss rate: `89%`, API latency high |
| Correct Fix | `restart_service` → `declare_rca` |

### 4. task_disk_full — PostgreSQL WAL overflow (ENOSPC)
| Property | Value |
|---|---|
| Difficulty | Easy |
| Max Steps | 10 |
| Ideal Steps | 4 |
| Fault Service | `postgres-db` |
| Fault Type | `disk_full` |
| Red Herrings | None |
| Key Signal | Logs: `ENOSPC: No space left on device`, Metrics: `disk_used_pct: 100`, `wal_size_gb: 48` |
| Correct Fix | `declare_rca` (disk_full) |

### 5. task_memory_leak — Notification Service GC Pauses
| Property | Value |
|---|---|
| Difficulty | Medium |
| Max Steps | 15 |
| Ideal Steps | 6 |
| Fault Service | `notification-service` |
| Fault Type | `memory_leak` |
| Red Herrings | None |
| Key Signal | Metrics: `memory_pct: 98`, `gc_pause_ms: 8000-14000`, Logs: `Email Template Cache holding 3.4GB` |
| Correct Fix | `restart_service` → `declare_rca` |

### 6. task_thread_starvation — Auth Service Thread Pool Exhaustion (OAuth)
| Property | Value |
|---|---|
| Difficulty | Medium |
| Max Steps | 15 |
| Ideal Steps | 6 |
| Fault Service | `auth-service` |
| Fault Type | `thread_pool_exhausted` |
| Red Herrings | None |
| Key Signal | Metrics: `thread_pool_active: 200/200`, `latency_p99_ms: 30000`, Logs: `OAuthIdentityClient timeout after 30000ms` |
| Correct Fix | `declare_rca` (thread_starvation) |

### 7. task_canary_poison — API Gateway v2.1 Strips Auth Headers
| Property | Value |
|---|---|
| Difficulty | Hard |
| Max Steps | 20 |
| Ideal Steps | 5 |
| Fault Service | `api-gateway` |
| Fault Type | `canary_misconfiguration` |
| Red Herrings | `order-service`, `auth-service` (see 401 errors) |
| Key Signal | 10% of requests fail with 401, Logs: `canary v2.1 stripping Authorization header` |
| Correct Fix | `declare_rca` (canary_poison) |

### 8. task_clock_skew — NTP Drift, JWT iat Rejected
| Property | Value |
|---|---|
| Difficulty | Hard |
| Max Steps | 20 |
| Ideal Steps | 6 |
| Fault Service | `auth-service` |
| Fault Type | `clock_skew` |
| Red Herrings | `redis-cache` (cache miss rate 68%), `order-service` (25% rejections) |
| Key Signal | Metrics: `clock_drift_seconds: 480`, Logs: `JWT iat is in the future`, `NTP daemon not running` |
| Correct Fix | `declare_rca` (clock_skew) |

### *Additional Tasks Available:*
* `task_api_rate_limit` (api-gateway misconfiguration)
* `task_deadlock_order_service` (database deadlock)
* `task_ssl_cert_expired` (x509 cert expired)
* `task_slow_query_postgres` (missing db index)
* `task_auth_service_500` (null pointer exception)
* `task_k8s_pod_crashloop` (unhandled exception in pod)

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
wrong service:            -0.30  # "WRONG TARGET — serious penalty teaches caution"

# rollback_deployment
correct service + bad_dep: +0.30  # "correct rollback"
correct service + wrong:   -0.10  # "rollback completed but wrong fix type"
wrong service:             -0.30  # "WRONG TARGET — serious penalty teaches caution"

# any repeated action
                          +0.005  # "redundant action (minimum reward)"

# declare_rca
correct service:   0.50 × seq_bonus + time_bonus + evidence_bonus  (up to 0.999)
partial match:     +0.10
wrong service:     -0.40  # Hard penalty for overconfident guessing

# DESIGN PHILOSOPHY: Hard SRE penalties enforce causal reasoning
# Wrong interventions (wrong service/wrong fix) carry real cost (-0.10 to -0.30)
# This forces agents to gather evidence before acting, not blind guessing.
# All rewards are clamped to [0.001, 0.999] per competition rules, so no catastrophic spirals.
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
    scale = 0.99 - 0.5 * ((progress - 0.5) / 0.5)
    reward_value = max(0.001, round(reward_value * scale, 4))
```

### Cumulative Reward
```python
cumulative = sum(all_step_rewards)  # can be negative due to hard penalties
cumulative = max(0.001, min(0.999, cumulative))  # clamped to [0.001, 0.999]
```

### Final Grade
```python
score = cumulative_reward (already clamped to [0.001, 0.999])
success = score >= 0.6  # success threshold
```

---

## Why Hard Penalties?

The hard penalty design (`-0.30` for wrong service, `-0.10` for wrong fix type) creates a high-stakes environment that **meaningfully tests the agent's behavior:**

- **Causal reasoning:** Agents that read logs/metrics first and then act correctly earn high scores. Agents that guess blindly hit hard penalties.
- **Realism:** In real SRE, wrong actions have exponential costs (cascading failures, customer impact). Our penalties model this authentically.
- **Stability:** Hard penalties ensure only systematic approaches achieve competitive scores, not random wandering.

The clamping to `[0.001, 0.999]` ensures no single mistake is unrecoverable — agents can learn and succeed in the same episode if they adjust course after a wrong action.

## Extending the Environment

### Adding a New Task

In `environment.py`, add to the `TASKS` dict:
```python
"task_yourname": {
    "name": "Human-readable name",
    "difficulty": "medium",
    "max_steps": 15,
    "description": "One sentence description of the fault scenario.",
    "alert": "ALERT: What the on-call engineer sees in their pager.",
    "fault_service": "service-name",        # must be in SERVICES list
    "fault_type": "oom_crash" | "cpu_spike" | "connection_pool_exhausted",
    "red_herrings": [],                     # list of service names
    "ideal_steps": 4,                       # expected optimal step count
},
```

Then update `openenv.yaml`, `inference.py`, `models.py` and `dashboard_impl.py`'s `TASKS` lists.

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
env_reset("task_cpu_spike", seed=42)
```

This seeds Python's `random` module, making all `_make_metrics()` random values deterministic for that episode.

---

## Known Limitations

- **Single-instance server:** The FastAPI app uses a single global `IncidentResponseEnv` instance. Concurrent agents will interfere with each other.
- **No persistent storage:** Benchmark results are not persisted across container restarts by default.
- **Simulated, not live:** All metrics and logs are procedurally generated — not from a real Kubernetes cluster.
- **Limited fault diversity:** Currently 9 fault types. See `SKILLS.md` for planned expansions.
