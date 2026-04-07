# SKILLS.md — Agent Capability & Reward Engineering Guide
> **incident-response-env** · What separates a score of 0.48 from 1.00

This document maps agent skill levels to observed behaviors, and tells developers exactly how to improve LLM performance on this benchmark.

---

## Skill Taxonomy

### Level 0 — Random Walker (Score: 0.00–0.15)
**Behavior:** Issues repeated identical actions, ignores observations, never declares RCA.
**Signature log pattern:**
```
[STEP] action={"action_type":"check_metrics","target":"api-gateway"} reward=-0.0500
[STEP] action={"action_type":"check_metrics","target":"api-gateway"} reward=-0.0500
[STEP] action={"action_type":"check_metrics","target":"api-gateway"} reward=-0.0500
```
**Root cause:** LLM not receiving observation feedback, rate-limited and falling to fallback, or broken JSON parsing.
**Fix:** Verify observation history is passed in each prompt turn. Add anti-repetition rule to system prompt.

---

### Level 1 — Symptom Chaser (Score: 0.15–0.40)
**Behavior:** Reads gateway logs first (correct), then diffuses attention across all services without forming a hypothesis. Runs out of steps before declaring RCA.
**Signature log pattern:**
```
[STEP] action={"action_type":"read_logs","target":"api-gateway"} reward=0.0500
[STEP] action={"action_type":"check_metrics","target":"auth-service"} reward=0.0000
[STEP] action={"action_type":"check_health","target":"redis-cache"} reward=0.0000
[STEP] action={"action_type":"check_metrics","target":"postgres-db"} reward=0.0000
... (runs out of steps)
```
**Root cause:** No hypothesis formation. Model treats investigation as exhaustive search.
**Fix:** Add explicit instruction: "After 2 steps, form a hypothesis. After 4 steps, commit to a suspect. After gathering evidence, remediate."

---

### Level 2 — Structured Investigator (Score: 0.40–0.70)
**Behavior:** Correctly identifies the fault service, gathers evidence, but applies wrong fix type or delays RCA declaration too long. Passes easy tasks, fails hard tasks due to red herrings.
**Root cause:** Weak fault-type classification. Model finds the right service but chooses `restart_service` for a `bad_deployment` fault.
**Fix:** Add fault-type reasoning to system prompt. Include a decision tree: "If logs show missing env var → rollback. If OOM → restart. If connection pool → run_db_query."

---

### Level 3 — Expert SRE (Score: 0.70–1.00)
**Behavior:** Forms hypothesis within 2 steps. Gathers corroborating evidence. Applies correct fix. Declares RCA with time bonus. Resists red herrings.
**Signature log pattern:**
```
[STEP] action={"action_type":"check_health","target":"notification-service"} reward=0.0700
[STEP] action={"action_type":"read_logs","target":"notification-service"} reward=0.1000
[STEP] action={"action_type":"restart_service","target":"notification-service"} reward=0.2980
[STEP] action={"action_type":"declare_rca","target":"notification-service"} reward=0.8500
[END] success=true steps=4 score=1.0000
```

---

## Skill: Red Herring Resistance

The hardest skill tested by this benchmark. In `task_hard`, `order-service` shows CPU at 90%+ — a strong signal that misleads most models.

**Models that fail (Level 1–2):**
```
check_metrics → order-service   (sees high CPU, locks in)
restart_service → order-service  (wrong fix, −0.20)
```

**Models that pass (Level 3):**
```
check_metrics → order-service   (notes high CPU but stays open)
read_logs → order-service       (logs look normal — no errors)
check_metrics → redis-cache     (pivots to shared resource)
read_logs → redis-cache         (confirms connection exhaustion)
run_db_query → postgres-db      (confirms pool at 500/500)
declare_rca → redis-cache       (correct)
```

**Key insight:** High CPU without error logs = red herring. Always cross-reference metrics with logs before committing to a suspect.

---

## Skill: Temporal Reasoning (Time Pressure)

After 50% of step budget is consumed, a progressive time penalty applies:
```python
time_penalty = -0.01 * ((progress - 0.5) / 0.5)
```

This means at step 8 of 10 (80% progress), each action costs an additional −0.006 penalty regardless of its outcome.

**Skill requirement:** Agent must internalize urgency. Once sufficient evidence is gathered, declare RCA immediately — do not keep investigating.

**Prompt engineering tip:** Add "You are 60% through your step budget. Commit to your hypothesis now." as a dynamic message injected at the 50% threshold.

---

## Skill: Evidence Synthesis

The `declare_rca` bonus includes:
```python
evidence_bonus = len(relevant_evidence_found) * 0.03
```

Evidence types tracked:
- `logs_fault_svc` — read_logs on the actual fault service
- `logs_gateway` — read_logs on api-gateway
- `metrics_fault_svc` — check_metrics on fault service
- `health_fault_svc` — check_health on fault service
- `db_query` — run_db_query (only for connection_pool_exhausted tasks)

**Maximum evidence bonus: +0.15** (5 evidence types × 0.03)

An agent that collects all 3 core evidence types (logs + metrics + health on fault service) before declaring RCA will always outscore one that declares immediately after 1 evidence piece.

---

## Prompt Engineering Recommendations

### System Prompt Additions That Improve Score

**1. Anti-repetition rule (fixes Level 0):**
```
CRITICAL: You will be told which actions you have already taken.
NEVER repeat an action you have already taken. Repeating costs -0.05.
```

**2. Hypothesis forcing (fixes Level 1):**
```
After every 2 observations, state your current hypothesis.
After 4 observations, you must commit to a primary suspect.
```

**3. Fault-type decision tree (fixes Level 2):**
```
FAULT IDENTIFICATION:
- Logs show OutOfMemoryError / OOM killer → fault_type=oom_crash → fix=restart_service
- Logs show missing env var / connection refused to DB → fault_type=bad_deployment → fix=rollback_deployment
- Logs show connection pool exhausted / timeout waiting → fault_type=connection_pool_exhausted → fix=run_db_query then declare_rca
```

**4. Time pressure injection (improves Level 2→3):**
```python
# In run_episode(), inject at 50% threshold:
if step == max_steps // 2:
    history.append({
        "role": "user",
        "content": f"[TIME PRESSURE] You have used {step}/{max_steps} steps. Commit to your suspect and resolve the incident."
    })
```

**5. Action history injection (critical for all levels):**
```python
# Before each LLM call, prepend taken actions:
taken = ", ".join(actions_taken_so_far)
history[-1]["content"] += f"\n\n[ACTIONS ALREADY TAKEN — DO NOT REPEAT]: {taken}"
```

---

## Benchmark Skill Matrix

| Model | Red Herring Resist | Evidence Synthesis | Time Pressure | Fault Classification | Avg Score |
|---|---|---|---|---|---|
| Qwen2.5-72B | Partial | Good | Poor | Good | 0.48 |
| Llama-3.3-70B | TBD | TBD | TBD | TBD | — |
| Mistral-7B | TBD | TBD | TBD | TBD | — |
| Gemma-2-27B | TBD | TBD | TBD | TBD | — |
| Phi-3.5 | TBD | TBD | TBD | TBD | — |

*Run `python Inference.py` with each model to populate this table.*
