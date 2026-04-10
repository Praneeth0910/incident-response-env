# fixes.md — In-depth improvement guide for `incident-response-env`

> Repo: https://github.com/Praneeth0910/incident-response-env  
> Context: Meta × PyTorch × Hugging Face OpenEnv Hackathon 2026 (Scaler SST)  
> Judged by Meta's global AI team on: domain novelty, environment design quality, baseline agent quality, technical execution, and documentation/reproducibility.

---

## Fix 1 — Make the world state dynamic (cascading degradation)

### Why this matters

The single biggest weakness in the current design is that the environment is **fully static** — no matter what the agent does or doesn't do, the services stay in the same state until `declare_rca` or `max_steps`. This means the environment is a fixed-graph investigation puzzle, not a sequential decision problem. RL environments get their value from the agent's actions affecting future observations. Judges from Meta will immediately spot that the world doesn't change based on delay.

### What to implement

After a configurable number of idle steps (e.g. step 6 for `task_hard`), if the agent has not yet called `declare_rca`, a secondary downstream service degrades. This creates two key effects: the agent gets noisy new signals that may mislead it, and the correct RCA becomes harder to identify from metrics alone. This is exactly the "cascade" mechanic that makes SRE investigation non-trivial.

### Code changes — `environment.py`

Add a `_cascade_triggered` flag and cascade config to each task:

```python
TASKS = {
    "task_easy": {
        ...
        "cascade_step": None,          # no cascade on easy
        "cascade_service": None,
        "cascade_fault": None,
    },
    "task_medium": {
        ...
        "cascade_step": 9,             # after step 9, if not resolved
        "cascade_service": "postgres-db",
        "cascade_fault": "connection_timeout",
    },
    "task_hard": {
        ...
        "cascade_step": 6,             # early cascade pressure
        "cascade_service": "api-gateway",
        "cascade_fault": "upstream_overload",
    },
}
```

In `IncidentResponseEnv.__init__`, add:

```python
self._cascade_triggered: bool = False
```

In `reset()`, reset it:

```python
self._cascade_triggered = False
```

At the bottom of `step()`, before building the `Observation`, add cascade logic:

```python
cascade_step = task.get("cascade_step")
cascade_svc = task.get("cascade_service")
if (
    cascade_step is not None
    and not self._cascade_triggered
    and self._step_count >= cascade_step
    and not done
):
    self._cascade_triggered = True
    cascade_note = (
        f"\n[CASCADE] {cascade_svc} is now DEGRADED — "
        f"new errors propagating. Investigate urgently."
    )
    message += cascade_note
```

Update `_make_metrics` and `_make_logs` to respect the cascade flag by adding a parameter:

```python
def _make_metrics(service: str, task: dict, cascade_triggered: bool = False) -> dict:
    ...
    cascade_svc = task.get("cascade_service")
    if cascade_triggered and service == cascade_svc:
        base.update({
            "latency_p99_ms": random.randint(3000, 6000),
            "error_rate": round(random.uniform(0.4, 0.7), 3),
            "cpu_pct": random.randint(70, 90),
        })
    ...
```

Pass `self._cascade_triggered` when calling these helpers inside `step()`.

### Prompt to give Claude Code / Cursor

> "In `environment.py`, add a cascade mechanic: each task in `TASKS` gets three new keys — `cascade_step` (int or None), `cascade_service` (str or None), `cascade_fault` (str or None). Add a `_cascade_triggered: bool` instance variable, reset to False in `reset()`. In `step()`, after computing reward and before building the Observation, check if `self._step_count >= task['cascade_step']` and `not self._cascade_triggered` and `not done` — if so, set `_cascade_triggered = True` and append a warning to `message`. Update `_make_metrics` and `_make_logs` to accept a `cascade_triggered` parameter and return degraded metrics/logs for `cascade_service` when triggered. Pass `self._cascade_triggered` to these helpers everywhere they are called in `step()`."

---

## Fix 2 — Add a test suite

### Why this matters

Zero tests is a critical credibility gap. A hackathon judged on "real infrastructure" by Meta engineers will expect at least basic pytest coverage. The Destroyerved submission ships 232 passing tests — even 20–30 focused tests would show this is a production-quality environment and not just a demo.

### What to implement

Create a `tests/` directory with `conftest.py` and `test_environment.py`.

### File structure

```
tests/
├── conftest.py
└── test_environment.py
```

### `tests/conftest.py`

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from environment import IncidentResponseEnv

@pytest.fixture
def env():
    return IncidentResponseEnv()

@pytest.fixture
def easy_env(env):
    env.reset("task_easy", seed=42)
    return env

@pytest.fixture
def hard_env(env):
    env.reset("task_hard", seed=42)
    return env
```

### `tests/test_environment.py`

```python
from environment import IncidentResponseEnv
from models import Action


# ── reset ──────────────────────────────────────────────────────────────────

def test_reset_returns_observation(env):
    obs = env.reset("task_easy", seed=0)
    assert obs.step == 0
    assert obs.done is False
    assert "notification-service" in obs.message or "Incident" in obs.message

def test_reset_is_deterministic(env):
    obs1 = env.reset("task_hard", seed=99)
    obs2 = env.reset("task_hard", seed=99)
    assert obs1.message == obs2.message

def test_reset_clears_prior_state(env):
    env.reset("task_easy", seed=0)
    env.step(Action(action_type="read_logs", target="api-gateway"))
    env.reset("task_easy", seed=0)
    assert env._step_count == 0
    assert env._cumulative_reward == 0.0
    assert len(env._actions_taken) == 0


# ── step ───────────────────────────────────────────────────────────────────

def test_step_increments_count(easy_env):
    obs, rew, done, info = easy_env.step(
        Action(action_type="check_health", target="api-gateway")
    )
    assert info["step"] == 1

def test_step_before_reset_raises(env):
    import pytest
    with pytest.raises(RuntimeError):
        env.step(Action(action_type="check_health", target="api-gateway"))

def test_redundant_action_penalised(easy_env):
    a = Action(action_type="check_health", target="api-gateway")
    easy_env.step(a)
    _, rew, _, _ = easy_env.step(a)
    assert rew.value == -0.05

def test_correct_rca_gives_positive_reward(env):
    env.reset("task_easy", seed=0)
    _, rew, done, _ = env.step(
        Action(action_type="declare_rca", target="notification-service")
    )
    assert rew.value > 0.0
    assert done is True

def test_wrong_rca_gives_minimal_reward(env):
    env.reset("task_easy", seed=0)
    _, rew, done, _ = env.step(
        Action(action_type="declare_rca", target="api-gateway")
    )
    assert rew.value <= 0.01
    assert done is True


# ── fault-specific checks ──────────────────────────────────────────────────

def test_easy_fault_is_oom(env):
    env.reset("task_easy", seed=0)
    _, _, _, _ = env.step(Action(action_type="check_health", target="notification-service"))
    state = env.state()
    assert state["hidden_fault_service"] == "notification-service"
    assert state["hidden_fault_type"] == "oom_crash"

def test_hard_fault_is_redis(env):
    env.reset("task_hard", seed=0)
    state = env.state()
    assert state["hidden_fault_service"] == "redis-cache"

def test_restart_correct_service_oom(env):
    env.reset("task_easy", seed=0)
    _, rew, _, _ = env.step(
        Action(action_type="restart_service", target="notification-service")
    )
    assert rew.value == 0.30

def test_rollback_correct_service_medium(env):
    env.reset("task_medium", seed=0)
    _, rew, _, _ = env.step(
        Action(action_type="rollback_deployment", target="order-service")
    )
    assert rew.value == 0.30


# ── grader ──────────────────────────────────────────────────────────────────

def test_grade_before_done_returns_low(env):
    env.reset("task_easy", seed=0)
    assert env.grade() == 0.001

def test_grade_after_correct_rca_is_reasonable(env):
    env.reset("task_easy", seed=0)
    env.step(Action(action_type="read_logs", target="notification-service"))
    env.step(Action(action_type="check_metrics", target="notification-service"))
    env.step(Action(action_type="declare_rca", target="notification-service"))
    score = env.grade()
    assert 0.5 < score < 1.0

def test_grade_clamped_to_range(env):
    env.reset("task_hard", seed=0)
    env.step(Action(action_type="declare_rca", target="wrong-service"))
    score = env.grade()
    assert 0.001 <= score <= 0.999


# ── max steps ───────────────────────────────────────────────────────────────

def test_episode_ends_at_max_steps(env):
    env.reset("task_easy", seed=0)
    done = False
    for _ in range(15):
        services = ["api-gateway", "auth-service", "order-service",
                    "notification-service", "redis-cache", "postgres-db"]
        import itertools
        for svc in itertools.cycle(services):
            _, _, done, _ = env.step(
                Action(action_type="check_health", target=svc)
            )
            if done:
                break
        if done:
            break
    assert done is True
```

Run with:

```bash
pip install pytest
pytest tests/ -v
```

### Prompt to give Claude Code / Cursor

> "Create a `tests/` directory with `conftest.py` and `test_environment.py`. `conftest.py` should add the project root to sys.path and provide `env`, `easy_env`, and `hard_env` pytest fixtures that return `IncidentResponseEnv` instances (reset with seed=42 where appropriate). `test_environment.py` should cover: reset determinism, reset state clearing, step counter increment, RuntimeError before reset, redundant action penalty (-0.05), correct RCA positive reward and done=True, wrong RCA minimal reward, fault service/type correctness for all three tasks, correct intervention rewards (restart for oom, rollback for bad_deployment), grader returning 0.001 before done, grader in range (0.5, 1.0) after a correct investigation sequence on task_easy, and episode terminating at max_steps. All tests must pass with the existing environment.py without modification."

---

## Fix 3 — Improve the grader to gate on RCA correctness

### Why this matters

The current `grade()` function just clamps `_cumulative_reward` to `[0.001, 0.999]`. This creates a serious problem: an agent that is methodical about evidence collection but then declares the *wrong* root cause can still score 0.5–0.7. This is wrong. The declared RCA should be the most important signal, not just one more step reward. Judges will test this.

### Code changes — `environment.py`

Add an `_rca_correct` flag:

```python
# in __init__ and reset():
self._rca_correct: bool = False
self._rca_declared: bool = False
```

In the `declare_rca` branch of `step()`:

```python
elif action.action_type == "declare_rca":
    done = True
    self._done = True
    self._rca_declared = True
    evidence_bonus = len(self._relevant_evidence_found) * 0.03
    time_bonus = max(0.01, (max_steps - self._step_count) / max_steps) * 0.4

    if action.target == fault_svc:
        self._rca_correct = True
        reward_value = round(0.50 + time_bonus + evidence_bonus, 3)
        reward_value = min(reward_value, 0.99)
        ...
    else:
        self._rca_correct = False
        reward_value = 0.001
        ...
```

Update `grade()`:

```python
def grade(self) -> float:
    """
    Deterministic grader.
    - If RCA was never declared: 0.001
    - If RCA was declared wrong: cap at 0.30 regardless of evidence collected
    - If RCA was declared correctly: scale cumulative reward, capped at 0.999
    """
    if not self._done or not self._rca_declared:
        return 0.001

    raw = max(0.0, min(1.0, self._cumulative_reward))

    if not self._rca_correct:
        # Wrong RCA: credit partial investigation, cap at 0.30
        evidence_credit = len(self._relevant_evidence_found) * 0.04
        return round(min(0.30, max(0.001, evidence_credit)), 4)

    score = max(0.001, min(0.999, raw))
    return round(score, 4)
```

This makes the grader semantically correct: good investigation with the wrong answer is still a fail, matching how real SRE incidents work.

### Prompt to give Claude Code / Cursor

> "In `environment.py`, add two boolean instance variables: `_rca_correct` and `_rca_declared`, both set to False in `__init__` and `reset()`. In the `declare_rca` branch of `step()`, set `_rca_declared = True` always, and `_rca_correct = True` only when `action.target == fault_svc`. Rewrite `grade()` so that: if `not self._done or not self._rca_declared` returns 0.001; if `_rca_declared` and `not _rca_correct`, compute `evidence_credit = len(self._relevant_evidence_found) * 0.04` and return `min(0.30, max(0.001, evidence_credit))`; otherwise clamp `_cumulative_reward` to [0.001, 0.999] and return it. Update the docstring to document the three scoring cases."

---

## Fix 4 — Add more tasks and richer scenario variety

### Why this matters

Three tasks with very similar structure (one fault, 1–2 red herrings, `declare_rca` terminal) limits what the environment teaches an RL agent. The graders will also notice there is no `task_expert` or multi-fault scenario. Adding just one more task and one structural novelty (e.g. a flapping service or a multi-root-cause) significantly raises the environment's training value.

### What to add

**`task_expert`** — a multi-root-cause incident where both `redis-cache` (connection pool) and `auth-service` (bad config deploy) are failing simultaneously. The agent must identify both before declaring RCA, and gets penalized for declaring only one.

```python
"task_expert": {
    "name": "Multi-root-cause: Redis + Auth config failure",
    "difficulty": "expert",
    "max_steps": 25,
    "description": (
        "Two independent failures: Redis connection pool exhausted "
        "AND auth-service misconfigured after deploy. Both must be identified."
    ),
    "alert": (
        "ALERT: Login failures 62%. Order completions 0%. "
        "On-call paged. Multiple cascading signals."
    ),
    "fault_service": "redis-cache",           # primary fault
    "fault_service_2": "auth-service",        # secondary fault
    "fault_type": "connection_pool_exhausted",
    "fault_type_2": "bad_deployment",
    "red_herrings": ["order-service", "notification-service"],
    "ideal_steps": 12,
    "cascade_step": 8,
    "cascade_service": "api-gateway",
    "cascade_fault": "upstream_overload",
},
```

Update `declare_rca` logic to accept a comma-separated target (e.g. `"redis-cache,auth-service"`) and award full score only when both faults are named:

```python
elif action.action_type == "declare_rca":
    done = True
    self._done = True
    self._rca_declared = True
    declared_services = set(s.strip() for s in action.target.split(","))
    fault_services = {task["fault_service"]}
    if task.get("fault_service_2"):
        fault_services.add(task["fault_service_2"])

    overlap = declared_services & fault_services
    self._rca_correct = overlap == fault_services  # full match required

    if self._rca_correct:
        ...  # full reward
    elif overlap:
        # partial credit: identified some but not all faults
        reward_value = 0.15
        reward_reason = f"partial RCA: found {overlap}, missed {fault_services - overlap}"
        message = f"Partial credit. You found {overlap} but missed {fault_services - overlap}."
    else:
        reward_value = 0.001
        ...
```

### Prompt to give Claude Code / Cursor

> "Add a `task_expert` entry to `TASKS` with `fault_service='redis-cache'`, `fault_service_2='auth-service'`, two red herrings, `max_steps=25`, and a `cascade_step=8`. Update the `declare_rca` branch of `step()` to parse `action.target` as a comma-separated list of service names. Compute `declared_services` as a set. `fault_services` is the set of `task['fault_service']` plus `task.get('fault_service_2')` if present. If `declared_services == fault_services` → full reward and `_rca_correct = True`. If partial overlap → reward 0.15 with a partial-credit message. If no overlap → reward 0.001. Update `_make_metrics` and `_make_logs` to handle `fault_service_2` the same way they handle `fault_service`."

---

## Fix 5 — Clean up the repository

### Why this matters

Committed `.vscode/` settings and `incident_response_env.egg-info/` are the most visible signs that the repo was pushed carelessly. Judges browse the file tree before reading code — this signals low production discipline.

### Steps

**1. Update `.gitignore`** (create or append):

```
# editor
.vscode/
.idea/

# python packaging artifacts
*.egg-info/
dist/
build/
__pycache__/
*.pyc
.eggs/

# environment
.env
.env.*
*.local

# test cache
.pytest_cache/
.coverage
htmlcov/
```

**2. Remove already-committed files from git tracking:**

```bash
git rm -r --cached .vscode/
git rm -r --cached incident_response_env.egg-info/
git add .gitignore
git commit -m "chore: remove editor and build artifacts, update .gitignore"
```

**3. Remove `.vscode/` from the remote:**

```bash
git push origin main
```

### Prompt to give Claude Code / Cursor

> "Create a `.gitignore` file in the repo root that ignores: `.vscode/`, `.idea/`, `*.egg-info/`, `dist/`, `build/`, `__pycache__/`, `*.pyc`, `.eggs/`, `.env`, `.env.*`, `*.local`, `.pytest_cache/`, `.coverage`, `htmlcov/`. Then run `git rm -r --cached .vscode/ incident_response_env.egg-info/` and commit with message 'chore: remove editor and build artifacts, update .gitignore'."

---

## Fix 6 — Flesh out `openenv.yaml`

### Why this matters

The `openenv.yaml` is the machine-readable contract for the OpenEnv ecosystem. Judges and the HuggingFace hub use it to understand action/observation schema at a glance. The current file is nearly empty (just Spaces metadata). Filling it in properly signals that you understand the spec and are contributing a reusable, standard-compliant environment.

### Full `openenv.yaml`

```yaml
title: Incident Response Env
emoji: 🚨
colorFrom: red
colorTo: blue
sdk: docker
pinned: false

# ── OpenEnv metadata ──────────────────────────────────────────────────────

env_id: incident-response-env
version: "1.0.0"
author: Praneeth0910
license: MIT
tags:
  - sre
  - incident-response
  - root-cause-analysis
  - microservices
  - reinforcement-learning

description: >
  An OpenEnv-compliant RL environment where LLM agents act as on-call SREs,
  investigating simulated microservice failures to identify root causes under
  time pressure. Features cascading world state, red herrings, and
  multi-tool investigation actions.

# ── Interface ─────────────────────────────────────────────────────────────

api:
  reset:
    method: POST
    path: /reset
    body:
      task_id: { type: string, enum: [task_easy, task_medium, task_hard, task_expert] }
      seed:    { type: integer, required: false }

  step:
    method: POST
    path: /step
    body:
      action_type: { type: string, enum: [read_logs, check_metrics, check_health, run_db_query, restart_service, rollback_deployment, declare_rca] }
      target:      { type: string, description: "Service name or comma-separated list for declare_rca" }

  grade:
    method: GET
    path: /grade

  state:
    method: GET
    path: /state
    note: "Exposes ground truth — for debugging/evaluation only"

# ── Spaces ─────────────────────────────────────────────────────────────────

observation_space:
  type: dict
  fields:
    message: { type: string, description: "Observation text for current step" }
    step:    { type: integer }
    done:    { type: boolean }
    alert:   { type: string, description: "Original incident alert (constant per episode)" }
    metrics: { type: object, nullable: true, description: "Service metrics dict, populated by check_metrics" }

action_space:
  type: discrete
  actions:
    - read_logs
    - check_metrics
    - check_health
    - run_db_query
    - restart_service
    - rollback_deployment
    - declare_rca

reward_range: [-1.0, 1.0]
cumulative_reward_range: [-1.0, 1.0]

# ── Tasks ──────────────────────────────────────────────────────────────────

tasks:
  task_easy:
    difficulty: easy
    max_steps: 10
    ideal_steps: 3
    description: "OOM crash on notification-service. Unambiguous signals."

  task_medium:
    difficulty: medium
    max_steps: 15
    ideal_steps: 6
    description: "Bad deployment on order-service with one red herring (auth-service)."

  task_hard:
    difficulty: hard
    max_steps: 20
    ideal_steps: 8
    description: "Redis connection pool exhaustion. CPU spike on order-service is a red herring. Cascade triggers at step 6."

  task_expert:
    difficulty: expert
    max_steps: 25
    ideal_steps: 12
    description: "Multi-root-cause: redis-cache pool exhaustion AND auth-service bad config deploy. Both must be identified."

# ── Baseline scores ────────────────────────────────────────────────────────

baselines:
  - model: Qwen/Qwen2.5-72B-Instruct
    scores:
      task_easy:   0.75
      task_medium: 0.60
      task_hard:   0.45
  - model: random_agent
    scores:
      task_easy:   0.15
      task_medium: 0.08
      task_hard:   0.04
```

### Prompt to give Claude Code / Cursor

> "Replace the contents of `openenv.yaml` with a fully populated OpenEnv metadata file. Include: `env_id`, `version`, `author`, `license`, `tags`, `description`, `api` section documenting `/reset`, `/step`, `/grade`, `/state` endpoints with their request bodies and field types, `observation_space` and `action_space` schemas, `reward_range: [-1.0, 1.0]`, a `tasks` section with `difficulty`, `max_steps`, `ideal_steps`, and `description` for each task, and a `baselines` section with Qwen2.5-72B and random agent scores."

---

## Fix 7 — Write a richer README with architecture diagram and differentiation argument

### Why this matters

The current README is functional but thin. Judges from Meta read dozens of READMEs in quick succession. The missing pieces are: a worked example showing what a good agent actually does step-by-step, an explicit argument for why this environment is novel (the "gap it fills" argument), a short architecture section, and the differentiation from similar envs. These are exactly what the Destroyerved submission does well.

### Sections to add

**Add after the existing intro:**

```markdown
## Why this environment doesn't exist elsewhere

Existing OpenEnv and OpenAI Gym environments for system operations focus on:
- Static log classification (no live state, no agent-environment interaction)
- Single-tool alert triage (no multi-step investigation loop)
- Fixed-difficulty scenarios with no cascade pressure

This environment fills the gap by modelling the *full* on-call SRE workflow:
the agent must gather evidence across multiple tools in a specific logical order,
survive red herrings designed to waste steps, and declare a root cause before
the world state degrades further. The cascading dynamic (Fix 1) makes delay
directly costly, creating a genuine sequential decision problem for RL training.
```

**Add a worked example trace:**

```markdown
## Example: optimal trace on `task_hard`

```
Step 1 → check_health("redis-cache")       # DEGRADED — first signal
Step 2 → check_metrics("redis-cache")      # active_connections: 500/500
Step 3 → run_db_query("postgres-db")       # 847 queries waiting — confirms pool exhaustion
Step 4 → read_logs("redis-cache")          # "connection pool exhausted (500/500)"
Step 5 → check_metrics("order-service")    # CPU 92% — looks alarming
Step 6 → read_logs("order-service")        # logs show it's a downstream victim, not origin
Step 7 → declare_rca("redis-cache")        # correct — episode ends, full time bonus
```

The agent that skips Step 6 and declares `order-service` at Step 5 gets penalized — 
this is the red herring trap the hard task is designed around.
```

**Add an architecture section:**

```markdown
## Architecture

```
POST /reset  ──►  IncidentResponseEnv.reset()
POST /step   ──►  IncidentResponseEnv.step()
GET  /state  ──►  IncidentResponseEnv.state()    # ground truth, debug only
GET  /grade  ──►  IncidentResponseEnv.grade()

IncidentResponseEnv
├── TASKS dict          — deterministic scenario definitions
├── _make_metrics()     — simulated service metrics per task/cascade state
├── _make_logs()        — simulated log output per service/fault type
├── _make_db_query_result() — diagnostic SQL results
└── grade()             — RCA-gated cumulative reward scorer
```
```

### Prompt to give Claude Code / Cursor

> "Extend `README.md` with three new sections placed after the existing intro: (1) 'Why this environment doesn't exist elsewhere' — a 4–6 sentence argument explaining the gap in existing OpenEnv/Gym environments that this project fills, specifically mentioning static log classification, single-tool triage, and the lack of cascade pressure in comparable envs; (2) 'Example: optimal trace on task_hard' — a numbered step-by-step trace showing the 7 optimal actions an agent takes to solve task_hard correctly, with one-line comments explaining the reasoning at each step, and a closing note explaining what the red herring trap is; (3) 'Architecture' — a text-art diagram of the FastAPI endpoints mapping to IncidentResponseEnv methods, with a tree listing the key internal helpers. Keep all three sections concise (under 30 lines total)."

---

## Fix 8 — Add a `/tasks` endpoint and improve the `/grade` endpoint response

### Why this matters

The README lists a `/tasks` GET endpoint but it's either missing or very thin in the server. Judges will hit the live API — if advertised endpoints 404 or return empty responses, it hurts the technical execution score significantly. The `/grade` endpoint also currently just returns a float; returning a structured JSON with `score`, `rca_correct`, `rca_declared`, and `evidence_found` makes it dramatically more useful for agent authors.

### Code changes — `server/app.py`

```python
from environment import IncidentResponseEnv, TASKS

@app.get("/tasks")
def list_tasks():
    """Return task metadata without exposing ground truth."""
    return {
        task_id: {
            "name": task["name"],
            "difficulty": task["difficulty"],
            "max_steps": task["max_steps"],
            "ideal_steps": task.get("ideal_steps"),
            "description": task["description"],
        }
        for task_id, task in TASKS.items()
    }

@app.get("/grade")
def grade():
    """Return structured grading result."""
    score = env.grade()
    state = env.state()
    return {
        "score": score,
        "rca_declared": getattr(env, "_rca_declared", False),
        "rca_correct": getattr(env, "_rca_correct", False),
        "evidence_found": state.get("evidence_found", []),
        "step_count": state.get("step_count", 0),
        "max_steps": state.get("max_steps"),
    }
```

### Prompt to give Claude Code / Cursor

> "In `server/app.py`, add a `GET /tasks` endpoint that returns a dict keyed by task_id, each value containing `name`, `difficulty`, `max_steps`, `ideal_steps`, and `description` — but NOT `fault_service`, `fault_type`, or `red_herrings` (keep ground truth hidden). Update the existing `GET /grade` endpoint to return a JSON object with keys: `score` (float), `rca_declared` (bool), `rca_correct` (bool), `evidence_found` (list of str), `step_count` (int), `max_steps` (int). Import `TASKS` from `environment` for the `/tasks` handler."

---

## Summary of all fixes

| Fix | Impact | Effort |
|-----|--------|--------|
| 1. Cascade mechanic | High — makes it a true RL env | Medium |
| 2. Test suite (20–30 tests) | High — credibility with Meta judges | Medium |
| 3. RCA-gated grader | High — fixes scoring correctness | Low |
| 4. task_expert + multi-fault | Medium — training value | Medium |
| 5. Repo hygiene (.gitignore) | Low-Medium — first impressions | Low |
| 6. Full openenv.yaml | Medium — ecosystem compliance | Low |
| 7. README depth | Medium — judge readability | Low |
| 8. /tasks + /grade endpoints | Low-Medium — API completeness | Low |

Fixes 1, 2, and 3 are the highest priority — they address the three most likely deductions from Meta's engineering judges. Fixes 5, 6, and 8 are quick wins that take under an hour and visibly raise the polish level of the submission.
