#!/usr/bin/env python3
"""
Incident Response Environment — Baseline Inference Script

Mandatory environment variables:
    API_BASE_URL   LLM proxy endpoint (injected by validator)
    MODEL_NAME     Model identifier (e.g. Qwen/Qwen2.5-72B-Instruct)
    API_KEY        LLM proxy key (injected by validator)
"""

import json
import math
import os
import sys
import requests
from openai import OpenAI

from benchmark_runner import run_benchmark

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL")
MODEL_NAME   = os.getenv("MODEL_NAME")
API_KEY      = os.getenv("API_KEY")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")
BENCHMARK    = "incident-response-env"

TASKS = ["task_easy", "task_medium", "task_hard"]

SERVICES = [
    "api-gateway", "auth-service", "order-service",
    "notification-service", "redis-cache", "postgres-db",
]

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer responding to a production incident.

You must investigate a microservices system and find the root cause of the failure.

Available actions (respond with JSON only):
- {"action_type": "read_logs",         "target": "<service>"}
- {"action_type": "check_metrics",     "target": "<service>"}
- {"action_type": "check_health",      "target": "<service>"}
- {"action_type": "run_db_query",      "target": "postgres-db"}
- {"action_type": "restart_service",   "target": "<service>"}
- {"action_type": "rollback_deployment","target": "<service>"}
- {"action_type": "declare_rca",       "target": "<service>"}

Available services: api-gateway, auth-service, order-service,
                    notification-service, redis-cache, postgres-db

Rules:
1. Respond with ONLY valid JSON — no explanation, no markdown.
2. Investigate before acting — read logs and metrics first.
3. Only call declare_rca when you are confident in the root cause.
4. Do not repeat actions you have already taken.
"""


# ── Logging (mandatory format) ────────────────────────────────────────────────

def log_start(task: str, model: str) -> None:
    print(f"[START] task={task} env={BENCHMARK} model={model}", flush=True)


def log_step(step: int, action: dict, reward: float,
             done: bool, error: str = "null") -> None:
    action_str = json.dumps(action).replace(" ", "")[:200]
    print(
        f"[STEP] step={step} action={action_str} "
        f"reward={reward:.4f} done={str(done).lower()} error={error}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float,
            rewards: list) -> None:
    rewards_str = ",".join(f"{r:.4f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.4f} rewards={rewards_str}",
        flush=True,
    )


# ── Env helpers ───────────────────────────────────────────────────────────────

def env_reset(task_id: str) -> dict:
    r = requests.post(
        f"{ENV_BASE_URL}/reset",
        json={"task_id": task_id},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def env_step(action: dict) -> dict:
    r = requests.post(
        f"{ENV_BASE_URL}/step",
        json=action,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def env_grade() -> float:
    r = requests.get(f"{ENV_BASE_URL}/grade", timeout=10)
    r.raise_for_status()
    return clamp_task_score(r.json().get("score", 0.001))


def clamp_task_score(score: float) -> float:
    """Keep validator-facing task scores strictly inside the open interval (0, 1)."""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        numeric = 0.001

    if not math.isfinite(numeric):
        numeric = 0.001

    return round(min(0.999, max(0.001, numeric)), 4)


# ── LLM action parsing ────────────────────────────────────────────────────────

def parse_action(text: str) -> dict:
    """Extract JSON action from LLM response."""
    text = text.strip()
    # strip markdown code fences if present
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip().lstrip("json").strip()
            if "{" in part:
                text = part
                break
    # find first { ... }
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    # fallback — check metrics on gateway
    return {"action_type": "check_metrics", "target": "api-gateway"}


def get_llm_action(client: OpenAI, history: list) -> tuple[dict, str]:
    import time
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                max_tokens=200,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or ""
            print(f"[DEBUG] LLM raw response: {raw[:300]}", flush=True)
            action = parse_action(raw)
            # If fallback triggered, log it clearly
            if action == {"action_type": "check_metrics", "target": "api-gateway"} and "{" not in raw:
                print(f"[WARN] parse fallback triggered — raw was empty or unparseable", flush=True)
            return action, raw
        except Exception as e:
            print(f"[ERROR] LLM call failed (attempt {attempt+1}/3): {e}", flush=True)
            time.sleep(5 * (attempt + 1))  # backoff: 5s, 10s, 15s
    # all retries failed
    return {"action_type": "check_metrics", "target": "api-gateway"}, "LLM_ERROR"


# ── Episode runner ────────────────────────────────────────────────────────────

def run_episode(client: OpenAI, task_id: str) -> dict:
    log_start(task=task_id, model=MODEL_NAME)

    rewards = []
    steps_taken = 0
    score = 0.001
    success = False

    try:
        obs = env_reset(task_id)
        alert   = obs.get("alert", "")
        message = obs.get("message", "")

        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"ALERT: {alert}\n\n{message}"},
        ]

        max_steps = {"task_easy": 10, "task_medium": 15, "task_hard": 20}[task_id]

        for step in range(1, max_steps + 1):
            action, raw_response = get_llm_action(client, history)

            # validate action fields
            if "action_type" not in action or "target" not in action:
                action = {"action_type": "check_metrics", "target": "api-gateway"}

            try:
                result   = env_step(action)
                obs_data = result.get("observation", {})
                reward   = result.get("reward", {}).get("value", 0.0)
                done     = result.get("done", False)
                error    = obs_data.get("error", "null") or "null"

                rewards.append(reward)
                steps_taken = step

                log_step(
                    step=step,
                    action=action,
                    reward=reward,
                    done=done,
                    error=str(error),
                )

                # add assistant + env response to history
                history.append({"role": "assistant", "content": raw_response})
                history.append({
                    "role": "user",
                    "content": (
                        f"Step {step} result:\n"
                        f"{obs_data.get('message', '')}\n\n"
                        f"Reward: {reward:.4f}\n"
                        f"Alert: {obs_data.get('alert', '')}"
                    ),
                })

                if done:
                    break

            except requests.HTTPError as e:
                error_msg = str(e)
                rewards.append(0.0)
                log_step(step=step, action=action, reward=0.0,
                         done=False, error=error_msg)
                history.append({"role": "assistant", "content": raw_response})
                history.append({"role": "user",
                                "content": f"Error: {error_msg}. Try a different action."})

        score   = clamp_task_score(env_grade())
        success = score >= 0.6

    except Exception as e:
        print(f"[DEBUG] Episode error: {e}", flush=True)
        fallback_score = sum(rewards) if rewards else 0.001
        score = clamp_task_score(fallback_score)

    finally:
        log_end(
            success=success,
            steps=steps_taken,
            score=score,
            rewards=rewards,
        )

    return {"task_id": task_id, "score": score,
            "steps": steps_taken, "success": success}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        run_benchmark(
            model_name=MODEL_NAME,
            api_base_url=API_BASE_URL,
            api_key=API_KEY,
            env_base_url=ENV_BASE_URL,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
