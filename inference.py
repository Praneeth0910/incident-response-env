#!/usr/bin/env python3
"""
Incident Response Environment — Baseline Inference Script

CRITICAL for hackathon validator:
  - Must use API_BASE_URL and API_KEY from environment (injected by LiteLLM proxy)
  - Must NOT hardcode keys or use own credentials
  - ENV_BASE_URL defaults to http://localhost:7860 (matches Docker EXPOSE)
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests
from openai import OpenAI

# ── Config — READ FROM ENV, never hardcode ─────────────────────────────────────
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
# Hackathon injects API_KEY; fall back to HF_TOKEN / OPENAI_API_KEY for local testing
API_KEY      = (
    os.environ.get("API_KEY")
    or os.environ.get("HF_TOKEN")
    or os.environ.get("OPENAI_API_KEY")
)
MODEL_NAME   = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
# Port 7860 matches the Docker CMD / uvicorn --port 7860
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:7860")

BENCHMARK = "incident-response-env"
TASKS     = ["task_easy", "task_medium", "task_hard"]

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

# ── Logging (mandatory OpenEnv format) ───────────────────────────────────────

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
        f"score={score:.4f} rewards={rewards_str}",
        flush=True,
    )

# ── Env helpers ───────────────────────────────────────────────────────────────

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
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                max_tokens=200,
                temperature=0.0,
            )
            raw    = resp.choices[0].message.content or ""
            print(f"[DEBUG] LLM raw: {raw[:300]}", flush=True)
            action = parse_action(raw)
            return action, raw
        except Exception as exc:
            print(f"[ERROR] LLM call failed (attempt {attempt+1}/3): {exc}", flush=True)
            time.sleep(5 * (attempt + 1))
    return {"action_type": "check_metrics", "target": "api-gateway"}, "LLM_ERROR"

# ── Episode runner ────────────────────────────────────────────────────────────

def run_episode(client: OpenAI, task_id: str) -> dict:
    log_start(task=task_id, model=MODEL_NAME)
    rewards, steps_taken, score, success = [], 0, 0.0, False

    try:
        obs     = env_reset(task_id)
        alert   = obs.get("alert", "")
        message = obs.get("message", "")

        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"ALERT: {alert}\n\n{message}"},
        ]
        max_steps = {"task_easy": 10, "task_medium": 15, "task_hard": 20}[task_id]

        for step in range(1, max_steps + 1):
            action, raw_response = get_llm_action(client, history)

            if "action_type" not in action or "target" not in action:
                action = {"action_type": "check_metrics", "target": "api-gateway"}

            try:
                result   = env_step(action)
                obs_data = result.get("observation", {})
                reward_obj = result.get("reward", {})
                reward   = reward_obj.get("value", 0.0) if isinstance(reward_obj, dict) else float(reward_obj)
                done     = result.get("done", False)
                error    = obs_data.get("error") or "null"

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
        print(f"[DEBUG] Episode error: {exc}", flush=True)
        score = max(0.0, min(1.0, sum(rewards))) if rewards else 0.0

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return {"task_id": task_id, "score": score, "steps": steps_taken, "success": success}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        print(
            "ERROR: API_KEY (or HF_TOKEN / OPENAI_API_KEY) not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[INFO] API_BASE_URL = {API_BASE_URL}", flush=True)
    print(f"[INFO] ENV_BASE_URL = {ENV_BASE_URL}", flush=True)
    print(f"[INFO] MODEL_NAME   = {MODEL_NAME}",   flush=True)

    # Build OpenAI client using injected env vars — required for hackathon LiteLLM proxy
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    results = []
    for task_id in TASKS:
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