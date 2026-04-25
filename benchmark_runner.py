from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_BENCHMARK_FILE = ROOT_DIR / "benchmark.json"

DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL")
DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
DEFAULT_API_KEY = (
    os.getenv("API_KEY")
    or os.getenv("HF_TOKEN")
    or os.getenv("OPENAI_API_KEY")
)
DEFAULT_ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")
BENCHMARK_FILE = Path(os.getenv("BENCHMARK_FILE", str(DEFAULT_BENCHMARK_FILE)))

BENCHMARK = "incident-response-env"
BENCHMARK_ID = f"{BENCHMARK}-v1"

from task_config import ALL_TASKS as TASKS

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
1. Respond with ONLY valid JSON - no explanation, no markdown.
2. Investigate before acting - read logs and metrics first.
3. Only call declare_rca when you are confident in the root cause.
4. Do not repeat actions you have already taken.
"""


def clamp_task_score(score: float) -> float:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        numeric = 0.001

    if not math.isfinite(numeric):
        numeric = 0.001

    return round(min(0.999, max(0.001, numeric)), 4)


def _timestamp_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _empty_benchmark_store() -> Dict[str, Any]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "updated_at": _timestamp_utc(),
        "latest_run": None,
        "leaderboard": [],
        "runs": [],
    }


def _build_leaderboard(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_model: Dict[str, Dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: item.get("timestamp", "")):
        model_name = run.get("model")
        if model_name:
            latest_by_model[model_name] = run

    leaderboard = []
    for run in latest_by_model.values():
        tasks = run.get("tasks", {})
        summary = run.get("summary", {})
        leaderboard.append(
            {
                "model": run.get("model", "unknown"),
                "timestamp": run.get("timestamp", ""),
                "api_base": run.get("api_base", ""),
                "average_score": clamp_task_score(summary.get("average_score", 0.001)),
                "total_score": round(float(summary.get("total_score", 0.0)), 4),
                "tasks_solved": int(summary.get("tasks_solved", 0)),
                "tasks_total": int(summary.get("tasks_total", len(TASKS))),
                "solve_rate": round(float(summary.get("solve_rate", 0.0)), 3),
                "task_scores": {
                    task_id: clamp_task_score(tasks.get(task_id, {}).get("score", 0.001))
                    for task_id in TASKS
                },
            }
        )

    leaderboard.sort(
        key=lambda item: (
            item["average_score"],
            item["tasks_solved"],
            item["timestamp"],
        ),
        reverse=True,
    )
    return leaderboard


def load_benchmark_store(path: Path | str = BENCHMARK_FILE) -> Dict[str, Any]:
    benchmark_path = Path(path)
    if not benchmark_path.exists():
        return _empty_benchmark_store()

    try:
        raw = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_benchmark_store()

    if isinstance(raw, dict) and "runs" in raw:
        runs = raw.get("runs", [])
    elif isinstance(raw, dict) and raw.get("model") and raw.get("tasks"):
        runs = [raw]
    else:
        return _empty_benchmark_store()

    runs = [
        run for run in runs
        if isinstance(run, dict) and run.get("model") and run.get("tasks")
    ]

    store = _empty_benchmark_store()
    store["runs"] = sorted(runs, key=lambda item: item.get("timestamp", ""), reverse=True)
    store["updated_at"] = raw.get("updated_at", store["updated_at"]) if isinstance(raw, dict) else store["updated_at"]
    store["leaderboard"] = _build_leaderboard(store["runs"])
    store["latest_run"] = store["runs"][0] if store["runs"] else None
    return store


def save_benchmark_report(
    report: Dict[str, Any],
    path: Path | str = BENCHMARK_FILE,
) -> Dict[str, Any]:
    benchmark_path = Path(path)
    store = load_benchmark_store(benchmark_path)
    runs = [
        run for run in store["runs"]
        if not (
            run.get("model") == report.get("model")
            and run.get("timestamp") == report.get("timestamp")
        )
    ]
    runs.append(report)
    runs = sorted(runs, key=lambda item: item.get("timestamp", ""), reverse=True)

    payload = {
        "benchmark_id": BENCHMARK_ID,
        "updated_at": _timestamp_utc(),
        "latest_run": runs[0] if runs else None,
        "leaderboard": _build_leaderboard(runs),
        "runs": runs,
    }

    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def emit_log(line: str, sink: Optional[List[str]] = None) -> None:
    print(line, flush=True)
    if sink is not None:
        sink.append(line)


def log_start(task: str, model: str, sink: Optional[List[str]] = None) -> None:
    emit_log(f"[START] task={task} env={BENCHMARK} model={model}", sink)


def log_step(
    step: int,
    action: Dict[str, Any],
    reward: float,
    done: bool,
    error: str = "null",
    sink: Optional[List[str]] = None,
) -> None:
    action_str = json.dumps(action).replace(" ", "")[:200]
    emit_log(
        (
            f"[STEP] step={step} action={action_str} "
            f"reward={reward:.4f} done={str(done).lower()} error={error}"
        ),
        sink,
    )


def log_end(
    success: bool,
    steps: int,
    score: float,
    rewards: List[float],
    sink: Optional[List[str]] = None,
) -> None:
    rewards_str = ",".join(f"{reward:.4f}" for reward in rewards)
    emit_log(
        (
            f"[END] success={str(success).lower()} steps={steps} "
            f"score={score:.4f} rewards={rewards_str}"
        ),
        sink,
    )


def env_reset(task_id: str, env_base_url: str) -> Dict[str, Any]:
    response = requests.post(
        f"{env_base_url}/reset",
        json={"task_id": task_id},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def env_step(action: Dict[str, Any], env_base_url: str) -> Dict[str, Any]:
    response = requests.post(
        f"{env_base_url}/step",
        json=action,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def env_grade(env_base_url: str) -> float:
    response = requests.get(f"{env_base_url}/grade", timeout=10)
    response.raise_for_status()
    return clamp_task_score(response.json().get("score", 0.001))


def parse_action(text: str) -> Dict[str, Any]:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part.strip().lstrip("json").strip()
            if "{" in candidate:
                text = candidate
                break

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return {"action_type": "check_metrics", "target": "api-gateway"}


def get_llm_action(
    client: OpenAI,
    history: List[Dict[str, str]],
    model_name: str,
    sink: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], str]:
    import time

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=history,
                max_tokens=200,
                temperature=0.0,
            )
            raw = response.choices[0].message.content or ""
            emit_log(f"[DEBUG] LLM raw response: {raw[:300]}", sink)
            action = parse_action(raw)
            if action == {"action_type": "check_metrics", "target": "api-gateway"} and "{" not in raw:
                emit_log("[WARN] parse fallback triggered - raw was empty or unparseable", sink)
            return action, raw
        except Exception as exc:
            emit_log(f"[ERROR] LLM call failed (attempt {attempt + 1}/3): {exc}", sink)
            time.sleep(5 * (attempt + 1))

    return {"action_type": "check_metrics", "target": "api-gateway"}, "LLM_ERROR"


def run_episode(
    client: OpenAI,
    task_id: str,
    model_name: str,
    env_base_url: str,
    sink: Optional[List[str]] = None,
) -> Dict[str, Any]:
    log_start(task=task_id, model=model_name, sink=sink)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.001
    success = False

    try:
        observation = env_reset(task_id, env_base_url=env_base_url)
        alert = observation.get("alert", "")
        message = observation.get("message", "")

        history: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"ALERT: {alert}\n\n{message}"},
        ]

        max_steps = 15  # All 9 incident tasks use same step limit

        for step in range(1, max_steps + 1):
            action, raw_response = get_llm_action(
                client,
                history,
                model_name=model_name,
                sink=sink,
            )

            if "action_type" not in action or "target" not in action:
                action = {"action_type": "check_metrics", "target": "api-gateway"}

            try:
                result = env_step(action, env_base_url=env_base_url)
                obs_data = result.get("observation", {})
                reward = float(result.get("reward", {}).get("value", 0.0))
                done = bool(result.get("done", False))
                error = obs_data.get("error", "null") or "null"

                rewards.append(reward)
                steps_taken = step

                log_step(
                    step=step,
                    action=action,
                    reward=reward,
                    done=done,
                    error=str(error),
                    sink=sink,
                )

                history.append({"role": "assistant", "content": raw_response})
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"Step {step} result:\n"
                            f"{obs_data.get('message', '')}\n\n"
                            f"Reward: {reward:.4f}\n"
                            f"Alert: {obs_data.get('alert', '')}"
                        ),
                    }
                )

                if done:
                    break

            except requests.HTTPError as exc:
                error_msg = str(exc)
                rewards.append(0.0)
                log_step(
                    step=step,
                    action=action,
                    reward=0.0,
                    done=False,
                    error=error_msg,
                    sink=sink,
                )
                history.append({"role": "assistant", "content": raw_response})
                history.append(
                    {
                        "role": "user",
                        "content": f"Error: {error_msg}. Try a different action.",
                    }
                )

        score = clamp_task_score(env_grade(env_base_url=env_base_url))
        success = score >= 0.6

    except Exception as exc:
        emit_log(f"[DEBUG] Episode error: {exc}", sink)
        fallback_score = sum(rewards) if rewards else 0.001
        score = clamp_task_score(fallback_score)

    finally:
        log_end(
            success=success,
            steps=steps_taken,
            score=score,
            rewards=rewards,
            sink=sink,
        )

    return {
        "task_id": task_id,
        "score": score,
        "steps": steps_taken,
        "success": success,
        "rewards": [round(float(reward), 4) for reward in rewards],
    }


def run_benchmark(
    model_name: Optional[str] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    env_base_url: Optional[str] = None,
    benchmark_file: Path | str = BENCHMARK_FILE,
) -> Dict[str, Any]:
    model_name = model_name or DEFAULT_MODEL_NAME
    api_base_url = api_base_url or DEFAULT_API_BASE_URL
    api_key = api_key or DEFAULT_API_KEY
    env_base_url = env_base_url or DEFAULT_ENV_BASE_URL

    if not model_name:
        raise ValueError("MODEL_NAME is required to run a benchmark.")
    if not api_base_url:
        raise ValueError("API_BASE_URL is required to run a benchmark.")
    if not api_key:
        raise ValueError("API key is required. Set API_KEY or HF_TOKEN.")

    client = OpenAI(base_url=api_base_url, api_key=api_key)
    log_lines: List[str] = []
    results = [
        run_episode(
            client,
            task_id=task_id,
            model_name=model_name,
            env_base_url=env_base_url,
            sink=log_lines,
        )
        for task_id in TASKS
    ]

    total_score = round(sum(result["score"] for result in results), 4)
    average_score = clamp_task_score(total_score / len(results))
    tasks_solved = sum(1 for result in results if result["success"])
    tasks_total = len(results)
    solve_rate = round(tasks_solved / tasks_total, 3)

    emit_log("", log_lines)
    emit_log("=" * 55, log_lines)
    emit_log("FINAL SUMMARY", log_lines)
    emit_log("=" * 55, log_lines)
    for result in results:
        status = "PASS" if result["success"] else "FAIL"
        emit_log(
            (
                f"  {result['task_id']:12} score={result['score']:.4f} "
                f"steps={result['steps']:3} [{status}]"
            ),
            log_lines,
        )
    emit_log("", log_lines)
    emit_log(f"  Average : {average_score:.4f}", log_lines)
    emit_log(f"  Total   : {total_score:.4f} / {tasks_total}", log_lines)
    emit_log(f"  Solved  : {tasks_solved} / {tasks_total}", log_lines)

    report = {
        "benchmark_id": BENCHMARK_ID,
        "timestamp": _timestamp_utc(),
        "model": model_name,
        "api_base": api_base_url,
        "env_base": env_base_url,
        "tasks": {
            result["task_id"]: {
                "score": result["score"],
                "steps": result["steps"],
                "success": result["success"],
                "rewards": result["rewards"],
            }
            for result in results
        },
        "summary": {
            "average_score": average_score,
            "total_score": total_score,
            "tasks_solved": tasks_solved,
            "tasks_total": tasks_total,
            "solve_rate": solve_rate,
        },
        "log_lines": log_lines,
        "benchmark_file": str(Path(benchmark_file).resolve()),
    }

    emit_log(f"[FILE] benchmark_json={Path(benchmark_file).resolve()}", log_lines)
    save_benchmark_report(report, path=benchmark_file)
    return report
