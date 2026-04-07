# REWARDS.md — Reward Engineering Deep Dive
> **incident-response-env** · Why the reward function is designed the way it is

This document explains the design philosophy behind every reward signal in the environment, and how to tune them for different training objectives.

---

## Design Philosophy

The reward function in `incident-response-env` is built on three principles:

### 1. Dense Rewards for Exploration
Unlike sparse reward environments (where the agent only gets a signal at the very end), this environment provides **partial rewards at every step**. This is essential for LLM-based agents that cannot learn from gradient signals — they need immediate feedback to adjust their next action.

```
Sparse (bad for LLMs):    0, 0, 0, 0, 0, 0, 0, +1.0
Dense (used here):        0.07, 0.10, 0.30, 0.00, -0.05, 0.85
```

### 2. Evidence-Gated Remediation
The reward structure deliberately makes "shoot first, ask questions later" unprofitable:
- `restart_service` on the wrong target: **−0.20**
- `rollback_deployment` on the wrong target: **−0.15**
- These penalties are large enough that a blind guess loses more than it could gain

This teaches the agent that investigation precedes action — a core SRE principle.

### 3. Speed as a Proxy for Competence
Real SREs are judged on Mean Time To Resolve (MTTR). The time bonus in `declare_rca` rewards faster resolution:
```
time_bonus = max(0.0, (max_steps - step_count) / max_steps) * 0.4
```
A model that finds the answer in 4 steps earns up to 0.24 more than one that finds it in 9 steps. This is intentional — memorizing all services exhaustively is penalized relative to forming a quick hypothesis.

---

## Reward Signal Map

```
Action                    Target              Reward    Signal Type
─────────────────────────────────────────────────────────────────
read_logs               fault_service        +0.10     strong positive
read_logs               api-gateway          +0.05     weak positive (symptom)
read_logs               other                +0.00     null
check_metrics           fault_service        +0.08     strong positive
check_metrics           red_herring          +0.02     weak positive (mislead)
check_metrics           other                +0.00     null
check_health            fault_service (oom)  +0.07     strong positive
check_health            fault_service (other)+0.05     moderate positive
check_health            other                +0.00     null
run_db_query            postgres (pool task) +0.12     strong positive
run_db_query            other                +0.01     near null
restart_service         correct + oom        +0.30     strong positive
restart_service         correct + wrong type +0.10     moderate (right place, wrong key)
restart_service         wrong service        -0.20     strong negative
rollback_deployment     correct + bad_deploy +0.30     strong positive
rollback_deployment     correct + wrong type +0.05     weak positive
rollback_deployment     wrong service        -0.15     strong negative
any action (repeated)   any                 -0.05     repetition penalty
declare_rca             correct              +0.50 + bonuses
declare_rca             wrong               +0.00     no partial credit for wrong RCA
```

---

## Tuning Guide

### Making the Environment Harder

**Option 1: Reduce evidence rewards**
```python
# In environment.py step() method
# Change from:
reward_value = 0.10  # read_logs on fault service
# To:
reward_value = 0.05  # forces agent to need multiple corroborating signals
```

**Option 2: Increase wrong-action penalties**
```python
# Change from:
reward_value = -0.20  # wrong restart
# To:
reward_value = -0.40  # more punishing for reckless action
```

**Option 3: Increase time pressure**
```python
# Change time penalty multiplier from:
time_penalty = -0.01 * ((progress - 0.5) / 0.5)
# To:
time_penalty = -0.03 * ((progress - 0.5) / 0.5)
```

### Making the Environment Easier

**Option 1: Reward gateway investigation more**
```python
# api-gateway logs reward (currently 0.05)
reward_value = 0.08  # encourage systematic triage from gateway
```

**Option 2: Reduce repetition penalty**
```python
reward_value = -0.02  # instead of -0.05
```

**Option 3: Add partial credit for wrong RCA**
```python
# In declare_rca logic, add:
elif action.target in task["red_herrings"]:
    reward_value = 0.05  # at least you found a suspicious service
    reward_reason = "wrong RCA but identified a suspicious service"
```

---

## Reward Shaping for RL Training

If you are using this environment for actual RL training (not just LLM inference), consider the following shaping additions:

### Curriculum Rewards
Start with only `task_easy`, then unlock harder tasks after the agent achieves avg score ≥ 0.7:
```python
# In training loop:
if avg_score_easy >= 0.7:
    TASKS_ENABLED.append("task_medium")
if avg_score_medium >= 0.7:
    TASKS_ENABLED.append("task_hard")
```

### Bonus for Minimal Steps
Add a step-efficiency bonus at episode end:
```python
efficiency_bonus = max(0, (ideal_steps - steps_taken) / ideal_steps) * 0.1
```

### Penalty for Premature RCA
If `declare_rca` is called before any remediation action on the correct service:
```python
if "restart_service" not in actions_taken and "rollback_deployment" not in actions_taken:
    reward_value *= 0.8  # 20% penalty for skipping remediation
```

---

## Why No Partial Credit for Wrong RCA?

A deliberate design choice: `declare_rca` on the wrong service scores exactly 0.00, not −0.20.

**Reasoning:**
- The agent already paid time cost (step penalty + time pressure) to get to RCA
- A wrong guess doesn't make the incident worse — it just means the incident is still ongoing
- Strong negative reward for wrong RCA would incentivize agents to never declare (risk aversion)
- 0.00 means "try again" without catastrophic episode collapse

This produces the desired behavior: agents declare RCA when they are confident, not when they are desperate.
