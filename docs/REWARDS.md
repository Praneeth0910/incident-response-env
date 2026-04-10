# REWARDS.md - Reward Engineering Deep Dive
> incident-response-env - Why the reward function is designed the way it is

This document mirrors the reward signals emitted by `environment.py` and consumed by `inference.py`. The baseline script reads the per-step reward from `/step` and treats a final `/grade` score >= 0.6 as a successful episode.

---

## Design Philosophy

### 1. Dense shaping with low-friction exploration
Unlike sparse environments, this benchmark gives a signal on every step. The signal is mostly positive, and bad actions fall back to a very small floor instead of large negative penalties. That makes the environment useful for LLM agents that need incremental feedback.

### 2. Investigate before remediation
The environment rewards evidence gathering more than blind fixing. Repeated actions and wrong targets still return a small floor, but the meaningful jumps come from finding the fault service and confirming the cause with logs, metrics, health checks, or DB queries.

### 3. Speed still matters
`declare_rca` rewards a correct answer more when it arrives earlier. The final episode score is also clamped, so the baseline can compare runs consistently without reward blow-ups.

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
| `restart_service` | right target, wrong fix | `+0.10` | 
| `restart_service` | wrong service | `+0.001 (minimum floor)` |
| `rollback_deployment` | correct service, `bad_deployment` | `+0.30` | Correct rollback |
| `rollback_deployment` | correct service, other fault | `+0.05` | Right target, wrong fix |
| `rollback_deployment` | wrong service | `+0.001 (minimum floor)` |
| `declare_rca` | correct service | `+0.50 + time bonus + evidence bonus` | Capped at `0.99` |
| `declare_rca` | wrong service | `+0.001` | Ends episode with a minimal floor |
| any non-RCA action, repeated | any | `+0.005 (minimum floor, no penalty by design)` | Re-checking is discouraged |

---

## Scoring Mechanics

Per-step rewards start at a small base value:

```python
reward_value = 0.001
```

The `declare_rca` bonus is:

```python
evidence_bonus = 0.03 * len(unique_evidence_found)
time_bonus = 0.4 * max(0.01, (max_steps - step_count) / max_steps)
correct_rca_reward = min(0.99, round(0.50 + time_bonus + evidence_bonus, 3))
```

Late in the episode, rewards are scaled down once the agent has used more than half of its steps:

```python
scale = 0.99 - 0.5 * ((progress - 0.5) / 0.5)
reward_value = max(0.001, round(reward_value * scale, 4))
```

That means:
- rewards after the halfway point get smaller
- rewards never drop below `0.001` after late-step scaling
- cumulative reward is clamped to `[0.001, 0.990]`
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

## Why No Negative Rewards?

The current design uses a floor instead of large punishments. Wrong service actions and wrong RCA answers do not crash the score into negative territory; they simply stay near zero. That keeps the agent exploring and avoids turning one bad guess into an unrecoverable episode.

This is also the behavior the inference baseline sees: the environment stays dense, final scores remain bounded, and the runner can compare episodes on a stable 0.01 to 0.99 scale.
