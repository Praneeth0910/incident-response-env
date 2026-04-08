# AGENT.md — AI Agent Operational Guide
> **incident-response-env** · OpenEnv-compliant RL Benchmark · v1.0.0

This document is the primary operating manual for any AI agent (LLM-based or otherwise) interacting with this environment. Read it fully before issuing a single action.

---:

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
| `oom_crash` | memory_pct=99, error_rate=1.0, service DOWN | `restart_service` |
| `bad_deployment` | high latency, env var errors in logs, circuit breaker | `rollback_deployment` |
| `connection_pool_exhausted` | active_connections=max_connections, timeouts | `run_db_query` to confirm, then `declare_rca` |

### Red Herrings
Hard and medium tasks contain **deliberately misleading signals**:
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
- **Never repeat an action** you have already taken — penalty is −0.05 per repeat
- **Never restart or rollback** before you have evidence — wrong target = −0.15 to −0.20
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

Ideal episode = **3–8 steps**. Max steps = 10/15/20 depending on difficulty.

---

## 5. Reward Signal Interpretation

| Reward Range | Meaning | What To Do |
|---|---|---|
| `+0.08` to `+0.12` | You found relevant evidence | Continue investigating same service |
| `+0.05` | Weak signal (gateway logs, health check) | Don't stop here — dig deeper |
| `0.00` | No signal — wrong service | Pivot to a different service |
| `−0.05` | Repeated action | You already checked this — move on |
| `−0.15` to `−0.20` | Wrong fix (restart/rollback wrong service) | Episode recovery is difficult now |
| `+0.30` | Correct remediation | Proceed to declare_rca immediately |
| `+0.50` to `+1.00` | Correct RCA declared | Episode complete |

**Time penalty** activates after 50% of steps are used. After that, every step costs an additional small negative reward. Be decisive.

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

## 9. Example Episode (task_easy — optimal)

```
ALERT: High error rate detected. API gateway reporting 500s.

Step 1: {"action_type": "check_health", "target": "notification-service"}
→ Reward: +0.07 | Health: DOWN

Step 2: {"action_type": "read_logs", "target": "notification-service"}
→ Reward: +0.10 | [ERROR] OutOfMemoryError: Java heap space. Killed by OOM killer.

Step 3: {"action_type": "restart_service", "target": "notification-service"}
→ Reward: +0.30 | Service restarted successfully.

Step 4: {"action_type": "declare_rca", "target": "notification-service"}
→ Reward: +0.85 | Correct. Episode complete. Score: 1.00
```

Total: 4 steps. Score: 1.00. This is what optimal looks like.
