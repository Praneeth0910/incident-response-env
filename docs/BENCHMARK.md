# BENCHMARK.md — Multi-LLM Benchmark Guide
> **incident-response-env** · How to run, record, and interpret benchmark results

---

## Quick Start

```bash
# Run benchmark with default model (Qwen2.5-72B via HuggingFace)
export HF_TOKEN=hf_your_token
python inference.py

# Run with a specific model
MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct python inference.py

# Run with Groq (faster, free tier)
API_BASE_URL=https://api.groq.com/openai/v1 \
HF_TOKEN=gsk_your_groq_key \
MODEL_NAME=llama-3.3-70b-versatile \
python inference.py
```

---

## Supported Model Endpoints

### HuggingFace Router (default)
```bash
API_BASE_URL=https://router.huggingface.co/v1
HF_TOKEN=hf_...
```
Available models:
- `Qwen/Qwen2.5-72B-Instruct` (default baseline)
- `meta-llama/Llama-3.3-70B-Instruct`
- `mistralai/Mistral-7B-Instruct-v0.3`
- `google/gemma-2-27b-it`
- `microsoft/Phi-3.5-mini-instruct`

### Groq (fastest free option)
```bash
API_BASE_URL=https://api.groq.com/openai/v1
HF_TOKEN=gsk_...  # Groq API key
```
Available models:
- `llama-3.3-70b-versatile`
- `mixtral-8x7b-32768`
- `gemma2-9b-it`

### OpenAI
```bash
API_BASE_URL=https://api.openai.com/v1
HF_TOKEN=sk_...
```
Available models:
- `gpt-4o`
- `gpt-4o-mini`
- `gpt-3.5-turbo`

---

## Running the Full Benchmark Suite

### Step 1: Start the environment server
```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Step 2: Run each model
```bash
# Model 1: Qwen2.5-72B
MODEL_NAME=Qwen/Qwen2.5-72B-Instruct \
API_BASE_URL=https://router.huggingface.co/v1 \
HF_TOKEN=$HF_TOKEN \
python inference.py

# Model 2: Llama 3.3-70B (via Groq)
MODEL_NAME=llama-3.3-70b-versatile \
API_BASE_URL=https://api.groq.com/openai/v1 \
HF_TOKEN=$GROQ_KEY \
python inference.py

# Model 3: Mixtral
MODEL_NAME=mixtral-8x7b-32768 \
API_BASE_URL=https://api.groq.com/openai/v1 \
HF_TOKEN=$GROQ_KEY \
python inference.py

# Model 4: GPT-4o-mini
MODEL_NAME=gpt-4o-mini \
API_BASE_URL=https://api.openai.com/v1 \
HF_TOKEN=$OPENAI_KEY \
python inference.py

# Model 5: Gemma2-9B
MODEL_NAME=gemma2-9b-it \
API_BASE_URL=https://api.groq.com/openai/v1 \
HF_TOKEN=$GROQ_KEY \
python inference.py
```

Every benchmark run now writes or updates `benchmark.json` automatically in the repo root. The dashboard reads that file directly for summary stats, leaderboard rows, and the latest benchmark log.

---

## benchmark.json Schema

`benchmark.json` is now a persistent benchmark store. It keeps:

- `latest_run` for the newest model execution
- `leaderboard` for the latest run per model
- `runs[]` as the historical list of benchmark executions

Each run object stored in `latest_run` and `runs[]` uses this shape:

```json
{
  "benchmark_id": "incident-response-env-v1",
  "timestamp": "2026-04-08T10:30:00Z",
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "api_base": "https://router.huggingface.co/v1",
  "tasks": {
    "task_cpu_spike": {
      "score": 0.9990,
      "steps": 4,
      "success": true,
      "rewards": [0.07, 0.10, 0.30, 0.85]
    },
    "task_db_connection_leak": {
      "score": 0.4373,
      "steps": 15,
      "success": false,
      "rewards": [0.05, 0.08, 0.10, 0.00, 0.00, 0.30, -0.05, 0.05]
    },
    "task_redis_memory_eviction": {
      "score": 0.0010,
      "steps": 15,
      "success": false,
      "rewards": [0.00, -0.05, -0.05]
    }
  },
  "summary": {
    "average_score": 0.4791,
    "total_score": 1.4373,
    "tasks_solved": 1,
    "tasks_total": 9,
    "solve_rate": 0.111
  }
}
```

---

## Interpreting Results

### Score Bands
| Score | Interpretation |
|---|---|
| `0.00–0.20` | Model failed completely — stuck in loop, no valid actions |
| `0.20–0.40` | Model investigates but cannot find root cause |
| `0.40–0.60` | Model solves easy tasks, struggles with medium |
| `0.60–0.80` | Competent SRE — solves most tasks, misses hard |
| `0.80–1.00` | Expert SRE — fast, accurate, resists red herrings |

### What This Benchmark Measures

Unlike simple Q&A benchmarks, incident-response-env tests:

1. **Sequential decision-making** — each action must build on the previous
2. **Partial observability** — agent never sees the full system state
3. **Noise resistance** — red herrings actively mislead
4. **Efficiency** — faster correct answers score higher
5. **Fault classification** — choosing the right fix, not just the right service

### Why Average Score Matters More Than Task Count

A model that scores 0.95 / 0.95 / 0.10 (avg 0.67) is arguably better than one that scores 0.65 / 0.65 / 0.60 (avg 0.63 but 3/3 passing). Look at both metrics.

---

## Reference Leaderboard

| Rank | Model | CPU Spike | DB Leak | Mem Evict | Avg | Solved |
|---|---|---|---|---|---|---|
| 1 | — | — | — | — | — | — |
| 2 | — | — | — | — | — | — |
| 3 | Qwen2.5-72B | 1.00 | 0.44 | 0.00 | 0.48 | 1/9 |

*Run your own models and submit results to update this table.*
