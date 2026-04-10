#!/usr/bin/env python3
"""
Incident Response Environment — Baseline Inference Script

CRITICAL for hackathon validator:
  - Must use API_BASE_URL and API_KEY from environment (injected by LiteLLM proxy)
  - Must NOT hardcode keys or use own credentials (no HF_TOKEN, no OPENAI_API_KEY)
  - ENV_BASE_URL defaults to http://localhost:7860 (matches Docker EXPOSE)
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests
from openai import OpenAI

# ── Config — READ STRICTLY FROM ENV (evaluator injection) ─────────────────────
print("[BOOTSTRAP] Checking for required environment variables...", flush=True)

if "API_BASE_URL" not in os.environ:
    print("[CRITICAL] API_BASE_URL not set in environment", file=sys.stderr, flush=True)
    sys.exit(1)
API_BASE_URL = os.environ["API_BASE_URL"]
print(f"[BOOTSTRAP] API_BASE_URL = {API_BASE_URL}", flush=True)

if "API_KEY" not in os.environ:
    print("[CRITICAL] API_KEY not set in environment", file=sys.stderr, flush=True)
    sys.exit(1)
API_KEY = os.environ["API_KEY"]
print(f"[BOOTSTRAP] API_KEY set (length={len(API_KEY)})", flush=True)

MODEL_NAME   = os.environ.get("MODEL_NAME", "gpt-4-turbo")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:7860")

print(f"[BOOTSTRAP] MODEL_NAME = {MODEL_NAME}", flush=True)
print(f"[BOOTSTRAP] ENV_BASE_URL = {ENV_BASE_URL}", flush=True)

BENCHMARK = "incident-response-env"
TASKS = [
    "task_cpu_spike", "task_db_connection_leak", "task_redis_memory_eviction",
    "task_api_rate_limit", "task_deadlock_order_service", "task_ssl_cert_expired",
    "task_slow_query_postgres", "task_auth_service_500", "task_k8s_pod_crashloop",
]

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer responding to a production incident.
You must investigate a microservices system and find the root cause of the failure.

Available actions (respond with JSON only):
- {"action_type": "read_logs",           "target": "<service>"}
- {"action_type": "check_metrics",       "target": "<service>"}
- {"action_type": "check_health",        "target": "<service>"}
- {"action_type": "run_db_query",        "target": "postgres-db"}
- {"action_type": "restart_service",     "target": "<service>"}
- {"action_type": "rollback_deployment", "target": "<service>"}
- {"action_type": "declare_rca",         "target": "<service>"}

Available services: api-gateway, auth-service, order-service,
notification-service, redis-cache, postgres-db

Rules:
1. Respond with ONLY valid JSON — no explanation, no markdown.
2. Investigate before acting — read logs and metrics first.
3. Only call declare_rca when you are confident in the root cause.
4. Do not repeat actions you have already taken.
"""

# ── Logging (mandatory OpenEnv format) ────────────────────────────────────────

def log_start(task: str, model: str) -> None:
    print(f"[START] task={task} env={BENCHMARK} model={model}", flush=True)


def log_step(step: int, action: dict, reward: float, done: bool, error: str = "null") -> None:
    action_str = json.dumps(action).replace(" ", "")[:200]
    print(
        f"[STEP] step={step} action={action_str} "
        f"reward={reward:.4f} done={str(done).lower()} error={error}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list) -> None:
    rewards_str = ",".join(f"{r:.4f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"rewards={rewards_str}",
        flush=True,
    )

# ── Env helpers ────────────────────────────────────────────────────────────────

def env_reset(task_id: str) -> dict:
    try:
        r = requests.post(f"{ENV_BASE_URL}/reset", json={"task_id": task_id}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[ERROR] env_reset failed: {exc}", flush=True)
        raise


def env_step(action: dict) -> dict:
    try:
        r = requests.post(f"{ENV_BASE_URL}/step", json=action, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[ERROR] env_step failed: {exc}", flush=True)
        raise


def env_grade() -> float:
    try:
        r = requests.get(f"{ENV_BASE_URL}/grade", timeout=10)
        r.raise_for_status()
        return r.json().get("score", 0.0)
    except Exception as exc:
        print(f"[ERROR] env_grade failed: {exc}", flush=True)
        return 0.0

# ── LLM helpers ───────────────────────────────────────────────────────────────

def parse_action(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            if "{" in part:
                text = part
                break
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {"action_type": "check_metrics", "target": "api-gateway"}


def get_llm_action(client: OpenAI, history: list) -> tuple[dict, str]:
    """Call LLM API through evaluator-injected proxy using API_KEY."""
    print(f"[API_CALL] Invoking LLM via {API_BASE_URL}", flush=True)
    print(f"[API_CALL] Model: {MODEL_NAME}", flush=True)
    print(f"[API_CALL] Messages in history: {len(history)}", flush=True)

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                max_tokens=200,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or ""
            print(f"[API_CALL] Response received ({len(raw)} chars)", flush=True)
            action = parse_action(raw)
            print(f"[API_CALL] Parsed action: {action}", flush=True)
            return action, raw
        except Exception as exc:
            print(f"[ERROR] LLM call failed (attempt {attempt+1}/3): {exc}", flush=True)
            time.sleep(5 * (attempt + 1))

    # all retries failed — use safe fallback
    print("[ERROR] All LLM retries exhausted, using fallback action", flush=True)
    return {"action_type": "check_metrics", "target": "api-gateway"}, "LLM_ERROR"

# ── Episode runner ─────────────────────────────────────────────────────────────

def run_episode(client: OpenAI, task_id: str) -> dict:
    log_start(task=task_id, model=MODEL_NAME)
    rewards, steps_taken, score, success = [], 0, 0.0, False

    try:
        print(f"[EPISODE] Resetting environment for {task_id}", flush=True)
        obs     = env_reset(task_id)
        alert   = obs.get("alert", "")
        message = obs.get("message", "")

        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"ALERT: {alert}\n\n{message}"},
        ]
        max_steps = 15  # All 9 incident tasks use same step limit

        for step in range(1, max_steps + 1):
            print(f"[EPISODE] Step {step}/{max_steps}", flush=True)
            action, raw_response = get_llm_action(client, history)

            if "action_type" not in action or "target" not in action:
                action = {"action_type": "check_metrics", "target": "api-gateway"}

            try:
                result     = env_step(action)
                obs_data   = result.get("observation", {})
                reward_obj = result.get("reward", {})
                reward     = reward_obj.get("value", 0.0) if isinstance(reward_obj, dict) else float(reward_obj)
                done       = result.get("done", False)
                error      = obs_data.get("error") or "null"

                rewards.append(reward)
                steps_taken = step
                log_step(step=step, action=action, reward=reward, done=done, error=str(error))

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

            except requests.HTTPError as exc:
                err_msg = str(exc)
                rewards.append(0.0)
                log_step(step=step, action=action, reward=0.0, done=False, error=err_msg)
                history.append({"role": "assistant", "content": raw_response})
                history.append({"role": "user", "content": f"Error: {err_msg}. Try a different action."})

        score   = env_grade()
        success = score >= 0.6

    except Exception as exc:
        print(f"[ERROR] Episode failed: {exc}", flush=True)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return {"task_id": task_id, "score": score, "steps": steps_taken, "success": success}

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"[MAIN] Starting benchmark runner...", flush=True)
    print(f"[MAIN] API_BASE_URL = {API_BASE_URL}", flush=True)
    print(f"[MAIN] ENV_BASE_URL = {ENV_BASE_URL}", flush=True)
    print(f"[MAIN] MODEL_NAME   = {MODEL_NAME}", flush=True)

    # CRITICAL: use API_KEY (evaluator-injected), never HF_TOKEN or own credentials
    print(f"[CLIENT_INIT] Creating OpenAI client with evaluator-provided API_KEY...", flush=True)
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    print(f"[CLIENT_INIT] ✓ OpenAI client created", flush=True)

    results = []
    for task_id in TASKS:
        print(f"[EPISODE] Running {task_id}...", flush=True)
        result = run_episode(client, task_id)
        results.append(result)

    print("\n" + "=" * 55, flush=True)
    print("FINAL SUMMARY", flush=True)
    print("=" * 55, flush=True)
    total  = sum(r["score"] for r in results)
    avg    = total / len(results)
    solved = sum(1 for r in results if r["success"])
    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(f"  {r['task_id']:12} score={r['score']:.4f} steps={r['steps']:3} [{status}]", flush=True)
    print(f"\n  Average : {avg:.4f}", flush=True)
    print(f"  Total   : {total:.4f} / {len(results)}", flush=True)
    print(f"  Solved  : {solved} / {len(results)}", flush=True)


if __name__ == "__main__":
    main()