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

**Current Status:** Microservices tasks only. CI/CD and Kafka simulators available via `reward.py` routing (experimental).

### `POST /reset`
Start a new episode.

**Request:**
```json
{
  "task_id": "task_cpu_spike",   // Choose from the 16 available microservices tasks
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

Score is in `[0.001, 0.999]`. Only meaningful after `done=true`. Clamped to this range to ensure meaningful differentiation between episodes.

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
    "description": "A hot loop in JWT validation is pegging auth-service CPU at 99%.",
    "ideal_steps": 5,
    "fault_service": "auth-service",
    "fault_type": "cpu_spike",
    "red_herrings": [],
    "cascade_step": null
  },
  ...
}
```

**All 16 tasks:**
1. `task_cpu_spike` — Easy (10 steps) — Auth CPU hot loop
2. `task_disk_full` — Easy (10 steps) — Postgres WAL overflow
3. `task_db_connection_leak` — Medium (15 steps) — Connection pool exhausted + cascade
4. `task_redis_memory_eviction` — Medium (15 steps) — Cache eviction cascade
5. `task_api_rate_limit` — Medium (15 steps) — Rate limiter misconfiguration
6. `task_deadlock_order_service` — Medium (15 steps) — Database deadlock
7. `task_ssl_cert_expired` — Medium (15 steps) — TLS certificate expiration
8. `task_slow_query_postgres` — Medium (15 steps) — Missing database index
9. `task_auth_service_500` — Medium (15 steps) — Internal server errors
10. `task_k8s_pod_crashloop` — Medium (15 steps) — Pod crash loop
11. `task_memory_leak` — Medium (15 steps) — Memory exhaustion + GC pauses
12. `task_thread_starvation` — Medium (15 steps) — Thread pool exhaustion
13. `task_canary_poison` — Hard (20 steps) — Canary deployment stripping headers + 2 red herrings
14. `task_clock_skew` — Hard (20 steps) — NTP drift causing token rejections + 2 red herrings
15. `task_expert` — Hard (25 steps) — **Multi-fault: Redis + Auth** + 2 red herrings
16. `task_expert_long_horizon` — Hard (50 steps) — **Long-horizon with latent secondary fault at step 35+**

---

## LLM Client Integration (Phase 1-5)

### Supported Providers

The environment's LLM client supports multiple providers with failover logic:

| Provider | Models | Retry Logic | Fallback |
|---|---|---|---|
| **OpenAI** | GPT-4, GPT-4o, GPT-4-turbo | ✓ Exponential backoff | Anthropic |
| **Anthropic** | Claude-3, Claude-3.5 | ✓ Exponential backoff | HuggingFace |
| **HuggingFace Router** | Qwen, Llama, Mistral | ✓ Retry on rate limit | Groq |
| **Groq** | Llama, Mixtral, Gemma | ✓ Fast (no rate limit) | OpenAI |

### Configuration

Set these environment variables to control LLM behavior:

```bash
# Required
export API_BASE_URL="https://api.openai.com/v1"      # or other provider
export API_KEY="sk_..."                              # API credentials

# Optional
export MODEL_NAME="gpt-4o"                           # Model identifier
export RETRY_ATTEMPTS=5                              # Max retries
export RETRY_BACKOFF_FACTOR=2                        # Exponential backoff multiplier
export TIMEOUT_SECONDS=30                            # Request timeout
```

### Resilience Features

- **Exponential backoff** — Retries on transient failures (429, 500-599)
- **Provider failover** — Falls back to secondary provider on persistent failure
- **Timeout handling** — Configurable request timeout with fallback
- **Rate-limit aware** — Detects and respects rate-limit headers

---

## 🔮 Phase 1-2 Simulators — Experimental Extensions

The codebase includes experimental simulators for additional incident domains. These are **not yet integrated into the main environment** but are available for future use and currently power the domain-aware reward system backend.

### CI/CD Pipeline Simulator (`simulators/cicd_simulator.py`)

Models GitHub Actions / GitLab CI incidents from real-world 2025–2026 failure patterns:

**Fault Types:**
- Secret rotation failures / token expiration
- Corrupt action (tag overwrite, dependency injection)
- OIDC authentication misconfig
- Runner queue saturation (pickup latency)
- Workflow injection via PR title
- Audit log manipulation

**Incident Examples:**
- "Deploy job failed: Cannot authenticate to AWS (OIDC audience mismatch)"
- "Build stuck in queue: 47 jobs ahead, no idle runners"
- "Production secret not found: last rotation failed 2 hours ago"

**Status:** Reward dispatch ready. Awaiting simulator ↔ environment integration.

### Kafka Cluster Simulator (`simulators/kafka_simulator.py`)

Models Apache Kafka message streaming incidents:

**Fault Types:**
- Consumer lag buildup (lagging consumers)
- Partition replica imbalance  
- Broker rebalance storm
- Schema incompatibility
- Message loss/ non-idempotent producer

**Incident Examples:**
- "Orders topic consumer lag: 1.2M messages. Processing stalled."
- "Partition 3 stuck during rebalance. No leader elected (>10s)"
- "Schema evolution incompatibility detected. Deserialization errors 98%"

**Status:** Reward dispatch ready. Awaiting simulator ↔ environment integration.

### Future Roadmap

- **Phase 1-3:** Integrate CI/CD simulator into environment
- **Phase 1-4:** Integrate Kafka simulator into environment
- **Phase 1-5:** Multi-incident scenarios (mixing CI/CD + Kafka failures)

---

## Enhanced Service Simulation (Phase 1-5)

### Service Health Monitoring
Each service maintains a comprehensive health state including:

- **Status** — UP, DEGRADED, DOWN, CRASHED
- **CPU & Memory** — Real-time utilization tracking
- **Error Rate** — Per-service error percentage
- **Latency** — p50, p99 latency percentiles
- **Thread Pool** — Active vs. max thread counts
- **Connection Pool** — Database connection utilization

### Service Registry & Dependency Graph
Services are registered with metadata:

```
api-gateway (victim only)
├── auth-service (victim or culprit)
├── order-service (victim or culprit)
└── notification-service (victim or culprit)

auth-service
├── redis-cache (session data)
└── postgres-db (user credentials)

order-service
├── redis-cache (order cache)
└── postgres-db (order data)

notification-service
└── postgres-db (notification queue)
```

### Cascading Failure Simulation
When a service fails, downstream effects propagate:

1. **Service A fails** → logs show fault
2. **Clients of A degrade** → metrics show latency spike
3. **Clients' clients affected** → api-gateway shows worst symptoms
4. **Timeout cascade** → Red herring: api-gateway looks like culprit

---

## Kafka Simulator (Phase 1-5)

Event streaming tasks use embedded Kafka simulation for incident scenarios involving:

- **Event lag buildup** — Consumer lag exceeding thresholds
- **Broker rebalancing** — Replica election delays
- **Message loss events** — Simulated Kafka rebalance storms
- **Topic partition imbalance** — Uneven load distribution

Example task: `task_kafka_broker_failure` (coming in phase 2)

---

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

### 9. task_expert — Multi-Root-Cause: Redis + Auth Failures
| Property | Value |
|---|---|
| Difficulty | Expert |
| Max Steps | 25 |
| Ideal Steps | 12 |
| Fault Services | `redis-cache` (connection_pool_exhausted) AND `auth-service` (bad_deployment) |
| Cascade | At step 8, `api-gateway` cascades due to upstream overload |
| Red Herrings | `order-service`, `notification-service` |
| Key Signal | Login failures 62%, orders failing 0%, multiple cascading signals |
| Correct Fix | Must identify BOTH redis and auth issues, declare both in RCA |
| Difficulty | Tests: Multi-root-cause diagnosis, understanding cascading signals |

### 10. task_expert_long_horizon — Long-Horizon Cascade: Latent Secondary Fault (🚀 50 STEPS)
| Property | Value |
|---|---|
| Difficulty | Expert |
| Max Steps | **50** |
| Ideal Steps | 25 |
| Initial Fault | `postgres-db` slow_query causing gradual degradation |
| Cascade Trigger | **At step 35** (not step 8), `order-service` cascades |
| Root Cause | Quick restart (step 10–15) seems to fix it, but introduces query planner bug → secondary cascade |
| Red Herrings | `api-gateway`, `redis-cache` |
| Key Signal | Order latency steadily increasing: 500ms → 2000ms → 8000ms |
| **Why Long-Horizon** | **Tests extended state tracking, planning over 50-step trajectory, avoiding quick-fix optimization traps** |
| Challenge | Agent must distinguish between immediate symptom fix vs. correct structural fix; latent bug manifests much later |
| Correct Fix | Deep investigation (15–25 steps) to identify secondary root cause, implement correct fix, avoid cascade |
| Theme Alignment | **Hackathon Theme #2: Long-Horizon Planning** — pushes agents beyond shallow next-token reasoning |

### *Additional Tasks Available (not detailed):*
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
early (before 50%):      -0.08   # "early redundancy penalty"
late (after 50%):        -0.20   # "late redundancy penalty"

# declare_rca
correct service:   0.50 + efficiency_bonus + evidence_bonus  (up to 0.999)
wrong service:     -0.40  # Hard penalty for overconfident guessing

# DESIGN PHILOSOPHY: Hard SRE penalties enforce causal reasoning
# Wrong interventions (wrong service/wrong fix) carry real cost (-0.10 to -0.30)
# This forces agents to gather evidence before acting, not blind guessing.
# All rewards are clamped to [0.001, 0.999] per competition rules, so no catastrophic spirals.
```

### Efficiency Bonus (declare_rca only)
```python
efficiency_bonus = max(0.0, (max_steps - step_count) / max_steps) * 0.30
# Example: declare at step 4 of 10 → (10-4)/10 * 0.30 = 0.18
# Example: declare at step 9 of 10 → (10-9)/10 * 0.30 = 0.03
```

### Evidence Bonus (declare_rca only)
```python
evidence_bonus = min(len(relevant_evidence_found) * 0.05, 0.20)
# Max: 4 evidence types × 0.05 = 0.20
```

### Cumulative Reward
```python
cumulative = sum(all_step_rewards)  # can be negative due to hard penalties
final_score = max(0.001, min(0.999, cumulative))  # clamped to [0.001, 0.999]
```

### Final Grade
```python
score = final_score  # Already clamped to [0.001, 0.999]
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
