# AGENT.md — AI Agent Operational Guide
> **incident-response-env** · OpenEnv-compliant RL Benchmark · v1.0.0 (Phase 1-5 Complete)

This document is the primary operating manual for any AI agent (LLM-based or otherwise) interacting with this environment. Read it fully before issuing a single action.

**Current System:** Microservices incident diagnosis. Phase 1-2 CI/CD and Kafka extension simulators available experimentally. See [DESIGN.md](DESIGN.md) for roadmap.

---

## 📊 Trajectory Logging

Every episode you complete is automatically recorded to `sft_data/trajectories.jsonl` with:
- Your actions and observations at each step
- Rewards received for each action
- Judge scores and feedback
- Final RCA score and correctness

This data enables supervised fine-tuning of new models. Your best episodes will train the next generation of incident response agents.

---## Quick Sanity Check

## 1. What You Are Doing

You are a **Site Reliability Engineer (SRE)** responding to a live production incident in a simulated microservices system. Services are failing. Users are affected. You have a limited number of steps to:

1. **Investigate** — gather evidence from logs, metrics, health checks
2. **Identify** — pinpoint the root cause service and fault type
3. **Remediate** — apply the correct fix (restart, rollback, or query)
4. **Declare** — issue a Root Cause Analysis (RCA) naming the faulty service

You are scored on **accuracy**, **speed**, and **evidence quality**. Every wasted step costs you.

---

## 2. The Environment

### Services Available
```
api-gateway          ← always shows symptoms (victim, not cause)
auth-service         ← may appear affected, rarely the root cause
order-service        ← common fault target in medium tasks
notification-service ← common fault target in easy tasks
redis-cache          ← common fault target in hard tasks
postgres-db          ← check with run_db_query for connection issues
```

### Fault Types You Will Encounter
| Fault | Signature | Correct Fix |
|---|---|---|
| `cpu_spike` | cpu_pct=99, error_rate=0.9+, service degraded | `restart_service` |
| `connection_pool_exhausted` | active_connections=max_connections, timeouts | `run_db_query` to confirm, then `declare_rca` |
| `memory_eviction` | cache miss rate high, latency spikes | `restart_service` -> `declare_rca` |
| `deadlock` | postgres throwing deadlock errors | `run_db_query` to confirm -> `declare_rca` |

### Red Herrings
Tasks contain **deliberately misleading signals**:
- A service with high CPU that is NOT the root cause
- The `api-gateway` always looks bad — it is a **victim**, never the cause
- Do not let a single anomalous metric send you down the wrong path

---

## 3. Action Space

```json
{"action_type": "read_logs",          "target": "<service>"}
{"action_type": "check_metrics",      "target": "<service>"}
{"action_type": "check_health",       "target": "<service>"}
{"action_type": "run_db_query",       "target": "postgres-db"}
{"action_type": "restart_service",    "target": "<service>"}
{"action_type": "rollback_deployment","target": "<service>"}
{"action_type": "declare_rca",        "target": "<service>"}
```

**CRITICAL RULES:**
- Respond with **ONLY valid JSON** — no prose, no markdown fences, no explanation
- **Never repeat an action** you have already taken — early repeats: -0.08, late repeats: -0.20
- **Never restart or rollback** before you have evidence — wrong target = -0.30
- **Never declare RCA** unless you have corroborating evidence from at least 2 action types

---

## 4. Optimal Investigation Strategy

### Phase 1: Triage (steps 1–3)
```
1. check_health → api-gateway        (confirm gateway is victim)
2. read_logs → api-gateway           (identify which upstream is failing)
3. check_health → <suspected service> (confirm degraded/down)
```

### Phase 2: Evidence (steps 4–6)
```
4. read_logs → <suspected service>   (look for ERROR lines, OOM, missing env vars)
5. check_metrics → <suspected service> (confirm anomalous numbers)
6. run_db_query → postgres-db        (if connection errors appear in logs)
```

### Phase 3: Remediate + Declare (steps 7–8)
```
7. restart_service OR rollback_deployment → <confirmed faulty service>
8. declare_rca → <confirmed faulty service>
```

Ideal episode = **3–8 steps**. Max steps varies by difficulty:
- **Easy tasks** (task_cpu_spike, task_disk_full): 10 steps
- **Medium tasks** (most tasks): 15 steps
- **Hard tasks** (task_canary_poison, task_clock_skew): 20 steps
- **Multi-fault** (task_expert): 25 steps
- **Long-horizon** (task_expert_long_horizon): 50 steps

---

## 5. Reward Signal Interpretation

| Reward Range | Meaning | What To Do |
|---|---|---|
| `+0.08` to `+0.18` | You found relevant evidence | Continue investigating same service |
| `+0.05` | Weak signal (gateway logs, health check) | Don't stop here — dig deeper |
| `0.00` to `+0.01` | No signal — wrong service | Pivot to a different service |
| `-0.08` to `-0.20` | Redundant action (early or late repeats) | Move on to new actions |
| `-0.30` | Wrong service restart/rollback | Serious mistake — gather evidence first next time |
| `-0.40` | Wrong RCA declared | Overconfident diagnosis cost you |
| `+0.30` | Correct restart/rollback | Good! Proceed to declare_rca |
| `+0.50` to `+0.99` | Correct RCA declared | Episode complete |

---

## 6. Anti-Patterns to Avoid

```
❌ Checking api-gateway metrics more than once
❌ Checking every service before forming a hypothesis
❌ Restarting a service without log evidence
❌ Declaring RCA on api-gateway (it is never the root cause)
❌ Running db_query when logs show no connection errors
❌ Checking the same service with the same action twice
❌ Declaring RCA before applying a fix (for oom/bad_deployment tasks)
```

---

## 7. Response Format Contract

Every response must be exactly this shape:
```json
{"action_type": "ACTION", "target": "SERVICE"}
```

No other text. No explanation. No markdown. The parser extracts JSON from your response — anything that is not parseable JSON causes a fallback to `check_metrics → api-gateway`, wasting a step and scoring 0.

---

## 8. Self-Checklist Before Each Action

Before outputting your JSON, run through this internally:

- [ ] Have I already taken this action on this target? If yes → choose differently
- [ ] Do I have enough evidence to remediate? If no → gather more first
- [ ] Am I about to act on api-gateway? If yes → stop, it is never the root cause
- [ ] Am I past 50% of my step budget? If yes → be more decisive
- [ ] Does my action follow logically from the last observation? If no → reconsider

---

## 9. Example Episode (task_cpu_spike — optimal)

```
ALERT: Login latency p99 > 8s. Auth service CPU at 99%. Users cannot sign in.

Step 1: {"action_type": "check_metrics", "target": "auth-service"}
→ Reward: +0.08 | CPU 99%, Thread Pool Active: 200

Step 2: {"action_type": "read_logs", "target": "auth-service"}
→ Reward: +0.10 | [ERROR] thread saturation — 200/200 threads active. Hot loop detected in JWTValidator

Step 3: {"action_type": "restart_service", "target": "auth-service"}
→ Reward: +0.30 | Service restarted successfully.

Step 4: {"action_type": "declare_rca", "target": "auth-service"}
→ Reward: +0.85 | Correct. Episode complete. Score: 1.00
```

Total: 4 steps. Score: 1.00. This is what optimal looks like.

---

## 10. Phase 1-5 Improvements

### Multi-LLM Support
This environment now supports agents running on:
- **OpenAI models** — GPT-4, GPT-4o, GPT-4o-mini
- **Anthropic models** — Claude-3 family
- **Open-source models** — Qwen, Llama, Mistral (via HuggingFace router or Groq)
- **Custom endpoints** — Any OpenAI-compatible API

### Resilient API Integration
- **Exponential backoff** — Retries transient failures (rate limits, timeouts)
- **Multi-provider fallback** — Degrades to secondary LLM provider on primary failure
- **LiteLLM compatibility** — Works with any standardized OpenAI-compatible proxy

### Trajectory Data for SFT
Every episode is recorded for supervised fine-tuning:

```python
# Load your past episodes
import json
with open("sft_data/trajectories.jsonl") as f:
    episodes = [json.loads(line) for line in f]

# Best episodes teach new models
best = [e for e in episodes if e["final_score"] > 0.9]
print(f"Train on {len(best)} high-quality trajectories")
```

Use this data to fine-tune base models into incident response specialists.

