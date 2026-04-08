#!/usr/bin/env python3
"""
Local Evaluator Test — Gemini 2.5 Pro
======================================
Mirrors the hackathon Phase 2 pipeline locally so you can validate
before submitting.

Setup:
    pip install openai requests

Environment variables (set before running):
    GEMINI_API_KEY   Your Google AI Studio API key  (required)
    ENV_BASE_URL     Your local server URL           (default: http://localhost:7860)

Run:
    GEMINI_API_KEY=your_key_here python test.py
"""

import json
import os
import sys
import time

import requests
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

# Google Generative AI (free tier)
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL_NAME   = "gemini-2.5-flash"   # Latest fast model

GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("API_KEY")       # also works if you rename it
)

ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:7860")
TASKS        = ["task_easy", "task_medium", "task_hard"]

# ── System prompt (same as Inference.py) ─────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer responding to a production incident.

You must investigate a microservices system and find the root cause of the failure.

Available actions (respond with JSON only):
- {"action_type": "read_logs",          "target": "<service>"}
- {"action_type": "check_metrics",      "target": "<service>"}
- {"action_type": "check_health",       "target": "<service>"}
- {"action_type": "run_db_query",       "target": "postgres-db"}
- {"action_type": "restart_service",    "target": "<service>"}
- {"action_type": "rollback_deployment","target": "<service>"}
- {"action_type": "declare_rca",        "target": "<service>"}

Available services: api-gateway, auth-service, order-service,
notification-service, redis-cache, postgres-db

Rules:
1. Respond with ONLY valid JSON — no explanation, no markdown.
2. Investigate before acting — read logs and metrics first.
3. Only call declare_rca when you are confident in the root cause.
4. Do not repeat actions you have already taken.
"""

# ── Logging (mandatory format — same as evaluator expects) ───────────────────

def log_start(task: str, model: str) -> None:
    print(f"\n[START] task={task} env=incident-response-env model={model}", flush=True)


def log_step(step: int, action: dict, reward: float,
             done: bool, error: str = "null") -> None:
    action_str = json.dumps(action).replace(" ", "")[:200]
    print(
        f"[STEP]  step={step} action={action_str} "
        f"reward={reward:.4f} done={str(done).lower()} error={error}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list) -> None:
    rewards_str = ",".join(f"{r:.4f}" for r in rewards)
    print(
        f"[END]   success={str(success).lower()} steps={steps} "
        f"score={score:.4f} rewards={rewards_str}",
        flush=True,
    )

# ── Environment helpers ───────────────────────────────────────────────────────

def env_reset(task_id: str) -> dict:
    r = requests.post(f"{ENV_BASE_URL}/reset", json={"task_id": task_id}, timeout=30)
    r.raise_for_status()
    return r.json()


def env_step(action: dict) -> dict:
    r = requests.post(f"{ENV_BASE_URL}/step", json=action, timeout=30)
    r.raise_for_status()
    return r.json()


def env_grade() -> float:
    r = requests.get(f"{ENV_BASE_URL}/grade", timeout=10)
    r.raise_for_status()
    return r.json().get("score", 0.0)

# ── Action parsing ────────────────────────────────────────────────────────────

def parse_action(text: str) -> dict:
    """Extract the first valid JSON action from the LLM response."""
    text = text.strip()
    # Strip markdown code fences if Gemini adds them
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
    # Safe fallback
    return {"action_type": "check_metrics", "target": "api-gateway"}


def get_llm_action(client: OpenAI, history: list) -> tuple[dict, str]:
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                max_tokens=512,
                temperature=0.0,
            )
            raw    = resp.choices[0].message.content or ""
            print(f"  [DEBUG] Gemini raw: {raw[:300]}", flush=True)
            action = parse_action(raw)
            if action == {"action_type": "check_metrics", "target": "api-gateway"} and "{" not in raw:
                print("  [WARN] parse fallback triggered", flush=True)
            return action, raw
        except Exception as e:
            print(f"  [ERROR] LLM call failed (attempt {attempt+1}/3): {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    return {"action_type": "check_metrics", "target": "api-gateway"}, "LLM_ERROR"

# ── Episode runner ────────────────────────────────────────────────────────────

def run_episode(client: OpenAI, task_id: str) -> dict:
    log_start(task=task_id, model=MODEL_NAME)

    rewards     = []
    steps_taken = 0
    score       = 0.0
    success     = False

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
            
            # Rate limit to ~5 RPM (12 sec per request)
            time.sleep(12)

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

                log_step(step=step, action=action, reward=reward,
                         done=done, error=str(error))

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
                err_msg = str(e)
                rewards.append(0.0)
                log_step(step=step, action=action, reward=0.0,
                         done=False, error=err_msg)
                history.append({"role": "assistant", "content": raw_response})
                history.append({"role": "user",
                                "content": f"Error: {err_msg}. Try a different action."})

        score   = env_grade()
        success = score >= 0.6

    except Exception as e:
        print(f"  [DEBUG] Episode error: {e}", flush=True)
        score = max(0.0, min(1.0, sum(rewards))) if rewards else 0.0

    finally:
        log_end(success=success, steps=steps_taken,
                score=score, rewards=rewards)

    return {"task_id": task_id, "score": score,
            "steps": steps_taken, "success": success}

# ── Health check ──────────────────────────────────────────────────────────────

def check_server() -> bool:
    print(f"[PREFLIGHT] Checking environment server at {ENV_BASE_URL} ...", flush=True)
    try:
        r = requests.get(f"{ENV_BASE_URL}/health", timeout=5)
        print(f"[PREFLIGHT] Server responded: {r.status_code}", flush=True)
        return True
    except Exception:
        # /health may not exist — try /reset with a dummy to see if server is up
        try:
            requests.post(f"{ENV_BASE_URL}/reset",
                          json={"task_id": "task_easy"}, timeout=5)
            print("[PREFLIGHT] Server is up ✅", flush=True)
            return True
        except Exception as e:
            print(f"[PREFLIGHT] Server NOT reachable: {e}", flush=True)
            return False


def check_gemini(client: OpenAI) -> bool:
    print(f"[PREFLIGHT] Testing Gemini API connection ...", flush=True)
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": 'Reply with exactly: {"action_type":"check_metrics","target":"api-gateway"}'}],
            max_tokens=50,
        )
        raw = resp.choices[0].message.content or ""
        print(f"[PREFLIGHT] Gemini response: {raw[:100]}", flush=True)
        print("[PREFLIGHT] Gemini API ✅", flush=True)
        return True
    except Exception as e:
        print(f"[PREFLIGHT] Gemini API FAILED: {e}", flush=True)
        return False

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  LOCAL EVALUATOR — Gemini 2.5 Pro")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("ERROR: Set GEMINI_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(
        api_key  = GEMINI_API_KEY,
        base_url = API_BASE_URL,
    )

    # Preflight checks
    gemini_ok = check_gemini(client)
    server_ok = check_server()

    if not gemini_ok:
        print("\n❌ Aborting — Gemini API is not reachable.", file=sys.stderr)
        sys.exit(1)
    if not server_ok:
        print("\n❌ Aborting — Environment server is not reachable.", file=sys.stderr)
        sys.exit(1)

    print("\n[INFO] Both checks passed. Starting full evaluation...\n")

    # Run all 3 tasks
    results = []
    for task_id in TASKS:
        result = run_episode(client, task_id)
        results.append(result)
        print(f"  → {task_id}: score={result['score']:.4f} "
              f"steps={result['steps']} "
              f"{'✅ PASS' if result['success'] else '❌ FAIL'}\n")

    # Final summary
    total  = sum(r["score"] for r in results)
    avg    = total / len(results)
    solved = sum(1 for r in results if r["success"])

    print("=" * 60)
    print("  FINAL SUMMARY")
    print("=" * 60)
    for r in results:
        status = "PASS ✅" if r["success"] else "FAIL ❌"
        print(f"  {r['task_id']:14} score={r['score']:.4f}  "
              f"steps={r['steps']:3}  [{status}]")
    print(f"\n  Average  : {avg:.4f}")
    print(f"  Total    : {total:.4f} / {len(results)}")
    print(f"  Solved   : {solved} / {len(results)}")
    print("=" * 60)

    # Exit code mirrors pass/fail for CI use
    sys.exit(0 if solved == len(results) else 1)


if __name__ == "__main__":
    main()
