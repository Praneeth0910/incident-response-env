---
title: Incident Response Env
emoji: 🚨
colorFrom: red
colorTo: blue
sdk: docker
pinned: false
license: apache-2.0
short_description: LLM agents act as on-call SREs.
---
<div align="center">

# 🚨 Incident Response Environment

### *The benchmark where AI becomes your on-call engineer*

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compliant-brightgreen?style=for-the-badge)](https://openenv.dev)
[![HuggingFace](https://img.shields.io/badge/🤗-Live%20Demo-yellow?style=for-the-badge)](https://huggingface.co/spaces/ZenkuIshigami09/incident-response-env)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker)](Dockerfile)
[![Blog](https://img.shields.io/badge/Blog-Read%20Now-purple?style=for-the-badge&logo=markdown)](docs/blog.md)


**An OpenEnv-compliant reinforcement learning benchmark where LLM agents must diagnose cascading microservices failures — just like a real Site Reliability Engineer would.**

✅ **Phase 1-5 Complete** — Full environment with RL training, multi-LLM support, and trajectory logging.

[🎮 Live Demo](https://huggingface.co/spaces/ZenkuIshigami09/incident-response-env) · [📖 Environment Docs](docs/ENVIRONMENT.md) · [📊 Benchmark Guide](docs/BENCHMARK.md) · [🤖 Agent Guide](docs/AGENT.md) · [🏆 Reward Design](docs/REWARDS.md)

</div>

---

# Production Incident Response Environment

An OpenEnv-compliant RL environment where LLM agents act as on-call SREs,
investigating simulated microservices failures to identify root causes under
time pressure.

## Why this environment exists

Every tech company running software in production has incidents. A database
slows down, an API starts throwing 500 errors, users cannot log in. The
on-call engineer must investigate noisy, incomplete signals and identify the
root cause as fast as possible. This environment simulates that exact task.

---

## 🌍 Why This Problem Matters

> **Every major tech company loses an average of $300,000 per hour during production incidents.**
> *(Gartner, 2023 — IT Downtime Cost Report)*

When production goes down, an on-call SRE receives a pager alert at 3 AM. They have minutes — not hours — to investigate a cascade of noisy, incomplete signals across dozens of microservices, form a hypothesis, apply the right fix, and declare a root cause. **Getting it wrong means extended downtime, lost revenue, and user churn.**

This is not a solved problem. Current AI systems cannot reliably perform sequential diagnostic reasoning under:
- **Partial observability** — you only see what you query
- **Active deception** — red herrings are deliberately placed to mislead
- **Time pressure** — every wasted step increases downtime
- **Cascading failures** — victims look like culprits

**`incident-response-env` is the first OpenEnv-compliant RL benchmark built around this exact challenge.**

---

## 🎯 What Makes This Different

| Benchmark Type | What It Tests | Limitation |
|---|---|---|
| Static Q&A | Knowledge recall | No sequential decisions |
| Code generation | Single-turn output | No feedback loop |
| Tool-use benchmarks | Tool calling | No partial observability |
| **incident-response-env** | **Sequential diagnosis under uncertainty** | **None — this is real SRE work** |

Unlike benchmarks where the agent sees everything at once, here the agent **only knows what it queries**. It must build a mental model of a broken system step by step — exactly as a human engineer would.

---

## 🆕 Recent Enhancements (Phase 1-5)

### Multi-LLM Support with Resilient Fallbacks
- **OpenAI & Anthropic Integration** — Full support for GPT-4, GPT-4o, Claude-3 families
- **Retry Logic** — Exponential backoff with configurable retries for API failures
- **Fallback Mechanisms** — Graceful degradation across multiple LLM providers
- **LiteLLM Proxy Compatible** — Works with standardized OpenAI-compatible APIs

### Trajectory Logging & SFT Data Collection
- **JSONL Trajectories** — Every episode saved as `trajectories.jsonl` for supervised fine-tuning
- **Structured Trajectories** — Each trajectory includes:
  - Step-by-step actions and observations
  - Per-step rewards and judge feedback
  - Total accumulated reward
  - Final score and RCA correctness flag
- **Reward Metrics** — Full visibility into reward signals for training LLMs with reward modeling

### Enhanced Service Simulation
- **Kafka Simulator** — Event streaming tasks for complex incident scenarios
- **Improved Health Monitoring** — Status management with failure injection capabilities
- **Service Registry** — Comprehensive dependency graph and service metadata
- **Cascading Failures** — Multi-level fault propagation for realistic incident patterns

### Phase 4 Domain-Aware Reward System
- **reward.py integration** — Domain-dispatched reward functions (microservices, CI/CD, Kafka)
- **Evidence tracking** — Domain-specific evidence counters (logs, metrics, integrity checks, lag analysis)
- **Adaptive penalties** — Redundancy penalties that scale with episode progress (early: gentle, late: harsh)
- **RCA scoring** — Efficiency bonus + evidence bonus for time-aware reward computation

### Phase 1-2 Experimental Extensions
- **CI/CD Simulator** — GitHub Actions/GitLab CI incident scenarios (reward dispatch ready, integration pending)
- **Kafka Simulator** — Message streaming failure patterns (reward dispatch ready, integration pending)
- **Expert Agent** — Rule-based agent for SFT data generation
- **Trajectory logging** — Full episode paths saved as JSONL for supervised fine-tuning

See [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md#-phase-1-2-simulators--experimental-extensions) for simulator roadmap.

---

## 🎮 Action Space

The agent has 7 distinct action types, each with a specific diagnostic or remediation purpose:

```json
{"action_type": "read_logs",           "target": "<service>"}
{"action_type": "check_metrics",       "target": "<service>"}
{"action_type": "check_health",        "target": "<service>"}
{"action_type": "run_db_query",        "target": "postgres-db"}
{"action_type": "restart_service",     "target": "<service>"}
{"action_type": "rollback_deployment", "target": "<service>"}
{"action_type": "declare_rca",         "target": "<service>"}
```

**Available services:** `api-gateway` · `auth-service` · `order-service` · `notification-service` · `redis-cache` · `postgres-db`

## Observation space
Every action returns a rich observation:
| Field | Type | Description |
|---|---|---|
| `message` | string | Current observation text |
| `step` | int | Current step number |
| `done` | bool | Episode finished |
| `alert` | string | Original incident alert |
| `metrics` | object | Service metrics (if requested) |

## 📋 Task Suite

**16 carefully crafted incident scenarios** of increasing difficulty, from shallow (10 steps) to **long-horizon planning** (50 steps):

| Task | Difficulty | Max Steps | Description |
|---|---|---|---|
| `task_cpu_spike` | Easy | 10 | Auth service CPU hot loop |
| `task_disk_full` | Easy | 12 | Disk space exhaustion on postgres |
| `task_db_connection_leak` | Medium | 15 | Order-service connection pool exhaustion |
| `task_redis_memory_eviction` | Medium | 15 | Redis memory threshold eviction cascade |
| `task_api_rate_limit` | Medium | 12 | API gateway rate limiter misconfiguration |
| `task_deadlock_order_service` | Medium | 15 | Database deadlock in order-service |
| `task_ssl_cert_expired` | Hard | 18 | SSL certificate expiration cascade |
| `task_slow_query_postgres` | Hard | 18 | Slow query blocking connection pool |
| `task_auth_service_500` | Hard | 20 | Auth service internal server errors |
| `task_k8s_pod_crashloop` | Hard | 20 | Kubernetes pod crash loop |
| `task_memory_leak` | Hard | 20 | Service memory leak causing OOM |
| `task_thread_starvation` | Hard | 20 | Thread pool starvation in microservice |
| `task_canary_poison` | Expert | 25 | Canary deployment strips auth headers |
| `task_clock_skew` | Expert | 25 | System clock skew across services |
| `task_expert` | Expert | 25 | Multi-root-cause: Redis + Auth failures |
| **`task_expert_long_horizon`** | **Expert** | **50** | **Long-horizon cascade: Latent secondary fault at step 35+** |

### 🚀 Long-Horizon Planning Test: `task_expert_long_horizon`

**Addresses Hackathon Theme #2: Long-Horizon Planning**

This 50-step task forces agents beyond shallow next-token reasoning:

- **Initial fault:** Postgres slow query causing gradual degradation
- **Red herring:** Agent might fix it at step 10–15 with a quick restart
- **Latent secondary fault:** The quick fix introduces a query planner bug
- **Cascade trigger:** At step 35+, order-service cascades due to secondary fault
- **Required skill:** Agent must track state over 50-step trajectory, recognize the latent bug, and implement the correct fix rather than jumping to quick conclusions

**Why this matters:** Tests whether agent can maintain context, plan ahead, and avoid optimization traps. A 50-step episode reveals whether the agent develops genuine SRE reasoning vs. pattern-matching lucky guesses.

### 🟡 Sample Scenario: Bad Deployment Cascade (Red Herring)
> *"Order service started failing after the 14:30 deployment. Auth service appears degraded."*

A bad deployment on `order-service` cascades to make `auth-service` appear broken — a deliberate red herring. Logs show missing environment variables. The correct fix is **rollback**.
**Tests:** Red herring resistance, multi-service correlation.

---

## 🔬 The Simulated Microservices System

The agent investigates a 6-service production stack comprising an `api-gateway` (always a victim), `auth-service`, `order-service`, `notification-service`, `redis-cache`, and `postgres-db`.

**Key design principle:** The gateway is **always a victim, never the root cause**. This forces agents to trace causality upstream.

---

## Reward function

- `+0.05` to `+0.12` — relevant evidence found
- `+0.005` — redundant action (already checked)
- `+0.30` — correct intervention (restart/rollback)
- `+0.05` — wrong service restarted 
- `+0.01` — wrong service rolled back
- `+0.50` + time bonus + evidence bonus — correct RCA declared
- `+0.001` — wrong RCA
- Cumulative strictly clamped to `[0.01, 0.99]`

## 📊 Baseline Performance

| Model | task_easy | task_medium | task_hard | Avg Score | Solved |
|---|---|---|---|---|---|
| Random agent | ~0.15 | ~0.08 | ~0.04 | ~0.09 | 0/3 |
| Qwen2.5-72B | ~0.75 | ~0.60 | ~0.45 | ~0.60 | 2/3 |
| *Human expert* | *~0.95* | *~0.90* | *~0.85* | *~0.90* | *3/3* |

**The human-AI gap on `task_hard` is 0.40 points.** Closing it requires genuine sequential reasoning, not pattern matching.

## 🤖 Agent Skill Taxonomy

The benchmark cleanly separates agents into four capability tiers:

| Level | Score | Behavior |
|---|---|---|
| **0 — Random Walker** | 0.00–0.15 | Repeats same action, never declares RCA |
| **1 — Symptom Chaser** | 0.15–0.40 | Reads gateway logs, then diffuses across all services exhaustively |
| **2 — Structured Investigator** | 0.40–0.70 | Finds right service, applies wrong fix type or declares too late |
| **3 — Expert SRE** | 0.70–1.00 | 3-step hypothesis, corroborating evidence, correct fix, time bonus |

The gap between Level 2 and Level 3 is **red herring resistance** — the most discriminative signal in this benchmark.

---

## 📊 Getting Started with Baselines

The environment ships with `inference.py`, a reference baseline agent that uses chain-of-thought prompting.

### Supported LLM Endpoints

The baseline works with any OpenAI-compatible endpoint. **OpenAI (GPT-4o) is the recommended baseline.**

#### 🌟 **Quick Start with OpenAI (Recommended)**

**Bash:**
```bash
export API_BASE_URL="https://api.openai.com/v1"
export API_KEY="sk_YOUR_OPENAI_KEY"
export MODEL_NAME="gpt-4o"

python inference.py
```

**PowerShell:**
```powershell
$env:API_BASE_URL="https://api.openai.com/v1"
$env:API_KEY="sk_YOUR_OPENAI_KEY"
$env:MODEL_NAME="gpt-4o"

python inference.py
```

---

#### Other Supported Providers

To use other providers, change the `API_BASE_URL`, `API_KEY`, and `MODEL_NAME` accordingly.

| Provider | Endpoint | Model Example | Setup |
|---|---|---|---|
| **OpenAI** ⭐ | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4-turbo` | [Get API key](https://platform.openai.com/api/keys) |
| **Anthropic (Claude)** | Proxy via LiteLLM | `claude-3-opus` | [Install LiteLLM](https://docs.litellm.ai/docs/) |
| **HuggingFace Inference** | `https://api-inference.huggingface.co/v1` | `meta-llama/Llama-2-70b` | [Get token](https://huggingface.co/settings/tokens) |
| **Together AI** | `https://api.together.xyz/v1` | `mistralai/Mixtral-8x7B` | [Get API key](https://together.ai) |
| **Ollama (local)** | `http://localhost:11434/v1` | Any local model | [Install Ollama](https://ollama.ai) |

---

## 📈 Interpreting Results

### Score Breakdown

Each task returns a score in `[0.0, 1.0]`. Higher is better. Scores are computed as:

$$\text{score} = \text{clamp}(0.01, \text{evidence\_bonus} + \text{fix\_bonus} + \text{rca\_bonus} + \text{time\_bonus}, 0.99)$$

**Breaking it down:**

| Component | Impact | Notes |
|---|---|---|
| **Evidence Bonus** | ±0.30 | +0.05–0.12 per unique evidence type (logs, metrics, health, query) |
| **Fix Bonus** | +0.30 | Given only if the correct service is restarted/rolled back **before** declaring RCA |
| **RCA Bonus** | +0.50 | Awarded only if declared RCA matches ground truth |
| **Time Bonus** | 0 to −0.15 | Linear penalty starting at step 10; reaches −0.15 at step budget limit |

**Examples:**

- **Perfect solve (0.95):** Find all 4 evidence types, apply correct fix, declare RCA at step 8
  - Evidence: +0.12 + 0.10 + 0.08 + 0.05 = +0.35
  - Fix: +0.30
  - RCA: +0.50
  - Time: −0.02 (step 8 vs limit 10)
  - **Total: 0.95**

- **Late but correct (0.80):** Find 3 evidence types, correct fix at step 14, declare RCA at step 16
  - Evidence: +0.12 + 0.10 + 0.08 = +0.30
  - Fix: +0.30
  - RCA: +0.50
  - Time: −0.30 (step 16 vs limit 15)
  - **Total: 0.80**

- **Wrong service fixed (0.55):** Restart auth-service (red herring), then declare correct RCA
  - Evidence: +0.30
  - Fix: +0.05 (wrong service, minor credit)
  - RCA: +0.50
  - Time: 0
  - **Total: 0.85** — but clamped or penalties applied

### Interpreting the Leaderboard

The leaderboard ranks agents by **average score across all three tasks:**

```json
{
  "agent": "Qwen2.5-72B-Instruct",
  "scores": {
    "task_easy": 0.92,
    "task_medium": 0.68,
    "task_hard": 0.41
  },
  "average": 0.67,
  "solved": 2,  // tasks with score >= 0.70
  "rank": 5
}
```

**Performance tiers:**
- **0.85+:** Expert SRE — rare; requires strong long-horizon planning
- **0.70–0.85:** Competent investigator — solves most easy/medium tasks
- **0.40–0.70:** Symptom chaser — finds right service but wrong fix or timing
- **0.15–0.40:** Red herring victim — exhausts all services without focus
- **0.00–0.15:** Random walker — no coherent strategy

### Common Failure Patterns

- **Exhaustive search without focus:** Checks all 6 services before declaring RCA (high time penalty)
- **Red herring trap:** Fixes auth-service instead of order-service on `task_medium` (wrong fix bonus, severe penalty)
- **Premature RCA:** Declares at step 4 with only 1 evidence type (low RCA bonus, but no time penalty — can still score 0.60–0.70)
- **Missing evidence:** Finds the right service but never gathers supporting logs/metrics (evidence bonus capped, RCA bonus only; total ~0.70)

---

## 🔗 Integration and CI/CD

Embed the benchmark in GitHub Actions to test your agents automatically on every PR.

```yaml
# .github/workflows/benchmark.yml
name: Benchmark Agent
on: [pull_request]
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - run: pip install -e .
      - env:
          API_BASE_URL: ${{ secrets.OPENAI_BASE_URL }}
          API_KEY: ${{ secrets.OPENAI_API_KEY }}
          MODEL_NAME: gpt-4o
        run: |
          uvicorn server.app:app --host 0.0.0.0 --port 7860 &
          sleep 3
          python inference.py > benchmark.json
```

---

## 🚀 Quick Start & Benchmarking

### 1. Local Setup

Clone the repository and start the FastAPI + Gradio server:

**Bash/PowerShell:**
```sh
git clone https://github.com/Praneeth0910/incident-response-env
cd incident-response-env
pip install -e .
uvicorn server.app:app --host 0.0.0.0 --port 7860
```
*Open [http://localhost:7860/dashboard](http://localhost:7860/dashboard) to play manually.*

### 2. Docker (Production)

```bash
docker-compose up --build
```
*See `docker-compose.yml` for port mappings.*

### 3. Run the LLM Agent Baseline

Configure your environment variables and run `inference.py`.

**Unix / Bash:**
```bash
export API_BASE_URL="https://api.openai.com/v1"
export API_KEY="sk_YOUR_OPENAI_KEY"
export MODEL_NAME="gpt-4o"
python inference.py
```

**Windows / PowerShell:**
```powershell
$env:API_BASE_URL="https://api.openai.com/v1"
$env:API_KEY="sk_YOUR_OPENAI_KEY"
$env:MODEL_NAME="gpt-4o"
python inference.py
```

### 4. Direct API Usage (Programmatic)

Send REST commands directly to evaluate custom agents without `inference.py`:

```bash
# Start an episode
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{"task_id": "task_easy"}'

# Take step
curl -X POST http://localhost:7860/step -H "Content-Type: application/json" -d '{"action_type": "read_logs", "target": "api-gateway"}'

# Get score
curl http://localhost:7860/grade
```

---

## 🏗️ Architecture

The environment is built with a **modular domain-aware architecture** supporting multiple incident types:

```
┌─────────────────────────────────────────────────────────┐
│         User Interface (Gradio Dashboard)               │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│         FastAPI Server (port 7860)                      │
│  /reset, /step, /grade, /tasks, /state, /health        │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│      IncidentResponseEnv (State Machine)                │
│  Management, task dispatch, trajectory logging          │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Reward System (Phase 4 — Domain-Aware)                │
│  • Reward.py: Domain-dispatched reward functions        │
│  • EvidenceTracker: Multi-type evidence collection      │
│  • Support for: CI/CD, Kafka, Microservices             │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Simulators (Phase 1-2 Extensions — Experimental)      │
│  • cicd_simulator.py: GitHub Actions/GitLab CI          │
│  • kafka_simulator.py: Apache Kafka state machine       │
│  • Status: Integrated into reward.py, optional in env   │
└─────────────────────────────────────────────────────────┘

Current (Phase 1-5): Microservices incidents only.
Phase 1-2 simulators available via reward.py routing (see docs/ for roadmap).
```

---

## 📁 Repository Structure

```
incident-response-env/
├── environment.py          # Core RL environment (primary)
├── models.py               # Pydantic data models
├── reward.py               # Domain-aware reward functions
├── task_config.py          # Task ID registry
├── inference.py            # Benchmark inference script
├── benchmark_runner.py     # Full benchmark orchestration
├── app.py                  # Gradio entry point
├── start.sh                # Docker startup script
│
├── server/
│   ├── app.py              # FastAPI application + REST endpoints
│   ├── dashboard_impl.py   # Gradio terminal dashboard
│   └── gradio_app.py       # Standalone Gradio launcher
│
├── judge/
│   ├── llm_client.py       # LLM client (OpenAI / Anthropic / mock)
│   └── llm_judge.py        # Adversarial phase-aware judge
│
├── simulators/
│   ├── cicd_simulator.py   # CI/CD pipeline state machine
│   └── kafka_simulator.py  # Kafka cluster state machine
│
├── training/
│   ├── expert_agent.py     # Rule-based expert for SFT data generation
│   └── generate_data.py    # SFT dataset generator
│
├── tasks/
│   ├── cicd_tasks.json     # CI/CD task definitions
│   └── kafka_tasks.json    # Kafka task definitions
│
├── docs/
│   ├── AGENT.md            # Full agent operating manual
│   ├── ENVIRONMENT.md      # Complete environment specification
│   ├── BENCHMARK.md        # Multi-model benchmarking guide
│   ├── REWARDS.md          # Reward engineering deep dive
│   ├── SKILLS.md           # Agent capability taxonomy + prompt engineering
│   └── blog.md             # Technical blog — SRE AI innovation story
│
├── sft_data/               # Generated training trajectories
├── test/                   # Integration tests
├── tests/                  # Unit tests (pytest)
├── Dockerfile              # Production container
├── openenv.yaml            # OpenEnv specification manifest
└── README.md               # This file
```
---

## 🔌 REST API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/reset` | POST | Start a new episode (`{"task_id": "task_easy"}`) |
| `/step` | POST | Execute one action |
| `/grade` | GET | Get final episode score `[0.0, 1.0]` |
| `/state` | GET | Ground truth state (debug only — spoils the answer) |
| `/tasks` | GET | List all available tasks |

**Example session (Bash):**
```bash
# Start episode
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_hard"}'

# Take action
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "read_logs", "target": "redis-cache"}'

# Get score
curl http://localhost:7860/grade
```

**Example session (PowerShell):**
```powershell
# Start episode
$body = @{task_id = "task_hard"} | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:7860/reset" -Method POST -ContentType "application/json" -Body $body

# Take action
$body = @{action_type = "read_logs"; target = "redis-cache"} | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:7860/step" -Method POST -ContentType "application/json" -Body $body

# Get score
Invoke-WebRequest http://localhost:7860/grade
```

---

##  Real-World Impact

**Who benefits from solving this benchmark?**

- **Cloud providers** (AWS, GCP, Azure) — automated incident triage could reduce MTTR by 60–80%
- **DevOps teams** — AI co-pilot for on-call engineers reduces alert fatigue
- **SRE platforms** (PagerDuty, OpsGenie, Datadog) — intelligent root cause suggestion as a product feature
- **AI safety researchers** — a reproducible benchmark for measuring agent causal reasoning under partial observability

The global Site Reliability Engineering market is valued at **$8.7 billion** (2024) and growing at 15% CAGR. Every percentage point improvement in automated incident resolution translates directly to engineering hours saved and service reliability improved.

---

## 📚 Documentation

| Document | Description |
|---|---|
| [AGENT.md](docs/AGENT.md) | Complete agent operating manual — optimal strategies, anti-patterns, example episodes |
| [ENVIRONMENT.md](docs/ENVIRONMENT.md) | Full API reference, task definitions, extending the environment |
| [BENCHMARK.md](docs/BENCHMARK.md) | Multi-model benchmarking, supported endpoints, result interpretation |
| [REWARDS.md](docs/REWARDS.md) | Reward engineering philosophy, tuning guide, RL training tips |
| [SKILLS.md](docs/SKILLS.md) | Agent skill taxonomy, prompt engineering recommendations |

---

## 🤝 Contributing

Want to add new fault types, tasks, or services? See [ENVIRONMENT.md](docs/ENVIRONMENT.md#extending-the-environment) for the extension guide.

Pull requests welcome for:
- New fault scenarios (network partition, disk full, certificate expiry)
- Additional services (message queues, CDN, load balancer)
- Improved baseline agents
- Multi-agent collaborative diagnosis

---

## 📄 License

Apache 2.0 — free for research, commercial use, and derivative works.

---

<div align="center">

**Built for the OpenEnv × Scaler Hackathon 2026**

*Making AI reliable enough to be your on-call engineer.*

</div>

