# REWARDS.md - Reward Engineering Deep Dive
> incident-response-env - Why the reward function is designed the way it is

This document mirrors the reward signals emitted by `environment.py` and consumed by `inference.py`. The baseline script reads the per-step reward from `/step` and treats a final `/grade` score >= 0.6 as a successful episode.

---

## Design Philosophy

### 1. High-stakes SRE consequences
This environment mirrors real-world incident response where **wrong actions have serious consequences**. Restarting the wrong service or rolling back the wrong deployment incurs a `-0.30` penalty — not because we're cruel, but because blind guessing in production has massive cost. This forces agents to develop genuine causal reasoning rather than pattern-matching lucky guesses.

### 2. Dense shaping with evidence-driven signals
The environment gives a signal on every step. Evidence gathering (logs, metrics, health checks) rewards the reasoning process, while wrong interventions carry hard penalties. This creates a clear incentive structure: investigate thoroughly before acting. Redundant actions return minimal reward (`+0.005`), further discouraging blind repetition.

### 3. Speed matters only after the right answer
`declare_rca` rewards correct answers more when they arrive earlier, reflecting real incidents where faster resolution is better. But speed is only valuable if the answer is **right** — wrong RCA ends the episode with minimal credit (`+0.001`), ensuring the agent can't luck into high scores.

---

## Reward Signal Map

| Action | Target / condition | Reward | Notes |
| --- | --- | --- | --- |
| `read_logs` | fault service | `+0.10` | Strongest log evidence |
| `read_logs` | `api-gateway` | `+0.05` | Symptom only, not root cause |
| `read_logs` | other service | `+0.01` | Limited signal |
| `check_metrics` | fault service | `+0.08` | Strong anomaly signal |
| `check_metrics` | red herring | `+0.02` | Suspicious but not causal |
| `check_metrics` | other service | `+0.01` | Limited signal |
| `check_health` | fault service, `oom_crash` | `+0.07` | Service is down |
| `check_health` | fault service, other fault | `+0.05` | Service is degraded |
| `check_health` | other service | `+0.01` | Limited signal |
| `run_db_query` | `postgres-db`, `connection_pool_exhausted` | `+0.12` | Confirms pool exhaustion |
| `run_db_query` | `postgres-db`, `disk_full` | `+0.12` | Confirms WAL / disk overflow |
| `run_db_query` | other target or fault type | `+0.01` | Limited signal |
| `restart_service` | correct service, `oom_crash` | `+0.30` | Correct fix for crash |
| `restart_service` | right target, wrong fix | `+0.10` | Partial credit |
| `restart_service` | wrong service | `-0.30` | **Hard penalty — forces causal reasoning** |
| `rollback_deployment` | correct service, `bad_deployment` | `+0.30` | Correct rollback |
| `rollback_deployment` | correct service, other fault | `-0.10` | Right target, wrong fix type |
| `rollback_deployment` | wrong service | `-0.30` | **Hard penalty — forces causal reasoning** |
| `declare_rca` | correct service | `0.50×seq_bonus + time_bonus + evidence` (up to 0.999) | RCA gated by evidence |
| `declare_rca` | partial (found some) | `+0.10` | Partial credit |
| `declare_rca` | wrong service | `-0.40` | **Hard penalty — overconfident guessing** |
| any non-RCA action, repeated | any | `+0.005` | **Discourages blind repetition** |

---

## Scoring Mechanics

Per-step evidence rewards start at a base value:

```python
reward_value = 0.001  # default for non-evidence actions
```

The `declare_rca` bonus (correct RCA only) is computed as:

```python
evidence_bonus = 0.04 * len(unique_evidence_types_found)  # max 0.20 (5 types × 0.04)
time_bonus = 0.40 * max(0.0, (max_steps - step_count) / max_steps)
seq_bonus = _compute_sequence_bonus(evidence_found, action_type)  # 0.2 or 1.0
correct_rca_reward = 0.50 * seq_bonus + time_bonus + evidence_bonus
correct_rca_reward = min(correct_rca_reward, 0.999)  # cap at 0.999
```

**Example (Correct RCA at step 4 of 10 with 3 evidence types and seq_bonus=1.0):**
```
evidence_bonus = 0.04 × 3 = 0.12
time_bonus = 0.40 × (10-4)/10 = 0.24
correct_rca_reward = 0.50 × 1.0 + 0.24 + 0.12 = 0.86
```

**Wrong RCA penalty:**
```python
wrong_rca_reward = -0.40  # Real penalty for overconfident guessing
```

Late in the episode, non-RCA rewards are scaled down once the agent has used more than half of its steps:

```python
if progress > 0.5:
    scale = 0.99 - 0.5 * ((progress - 0.5) / 0.5)
    reward_value = max(0.001, round(reward_value * scale, 4))
```

That means:
- evidence rewards after the halfway point get smaller
- rewards never drop below `0.001` after late-step scaling
- cumulative reward is clamped to `[0.001, 0.999]`
- `grade()` returns `0.001` until the episode is done, then returns the clamped cumulative score

The baseline in `inference.py` marks a run as successful when:

```python
score >= 0.6
```

---

## Tuning Guide

### Make the environment harder
- Reduce `read_logs` and `check_metrics` rewards on the fault service.
- Lower the `restart_service` and `rollback_deployment` rewards for correct remediation.
- Reduce the `0.03` evidence bonus or the `0.4` time bonus in `declare_rca`.
- Tighten the late-step scale so rewards decay faster after the halfway point.

### Make the environment easier
- Increase the evidence rewards for fault-service logs or metrics.
- Raise the partial-credit rewards for the correct service but wrong fix.
- Increase the `declare_rca` evidence bonus if you want final reasoning to matter more.
- Relax the late-step decay if you want longer investigations to stay competitive.

---

## Why Hard Penalties for Wrong Interventions?

**Real SRE incidents have real consequences.** Wrong service restarts and blind rollbacks are expensive mistakes in production. Our penalty structure (`-0.30` for wrong targets, `-0.10` for wrong fix types) forces agents to develop **causal reasoning** rather than blind guessing.

### The Design Trade-off

- **Soft floor approach (not used):** Wrong actions return `+0.001`. This keeps agents exploring but allows lucky guesses to eventually succeed. Agents learn pattern-matching over causality.
- **Hard penalty approach (used):** Wrong actions return `-0.30`. This makes the cost of being wrong obvious and immediate. Agents **must** gather evidence (logs, metrics, health checks) before intervening to avoid catastrophic penalties.

### Why This Matters for Evaluation

The Environment Innovation criteria (40%) explicitly values environments that **"meaningfully test the agent's behavior."** Our hard penalties create meaningful test scenarios:

1. **Measures causal reasoning:** An agent that reads logs first then acts correctly earns high rewards. An agent that guesses blindly hits `-0.30` penalties. The difference is stark and teaches the distinction.

2. **Stability under adversarial agents:** A soft-floor design could allow an agent to wander randomly and eventually luck into the right answer. Hard penalties ensure that only **systematic approaches** achieve competitive scores.

3. **Realism:** In real-world SRE, wrong actions have exponential cost (cascading failures, customer impact, incident duration). Our penalties model this authentically.

### Episode Recovery

Note that `-0.30` is not unrecoverable — the total episode is clamped to `[0.001, 0.999]`, so a single wrong action doesn't end all possibility of a decent final score. But it **does** make success significantly harder, forcing the agent to make informed decisions for the remainder of the episode.
