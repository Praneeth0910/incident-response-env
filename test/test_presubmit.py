#!/usr/bin/env python3
"""
test_presubmit.py — Local Pre-Submission Validator
====================================================
Mirrors every check the Scaler/OpenEnv hackathon validator runs in
Phase 1 and Phase 2, so you catch failures before you push.

Usage (from your repo root):
    pip install requests pytest
    pytest test_presubmit.py -v

Or run directly for a friendly summary:
    python test_presubmit.py

Environment variables you can set before running:
    SERVER_URL   — default http://localhost:7860  (must be running)
    START_SERVER — set to "1" to auto-start uvicorn before tests
    SKIP_DOCKER  — set to "1" to skip Docker build test (saves time)

Phase 1 checks (structural):
  ✓ inference.py at repo root
  ✓ Dockerfile at repo root
  ✓ openenv.yaml at repo root (openenv validate)
  ✓ POST /reset returns valid Observation JSON

Phase 2 checks (runtime):
  ✓ Docker build succeeds
  ✓ inference.py reads API_BASE_URL, MODEL_NAME, HF_TOKEN from env
  ✓ API_BASE_URL has a default value
  ✓ MODEL_NAME has a default value
  ✓ HF_TOKEN is required (raises if missing)
  ✓ Uses OpenAI client (not raw HTTP)
  ✓ [START] line format correct
  ✓ [STEP] line format correct
  ✓ [END] line format correct — NO extra fields like score=
  ✓ reward and rewards formatted to 2 decimal places
  ✓ done and success are lowercase booleans
  ✓ All task scores in (0.001, 0.990) — never 0.0 or 1.0
  ✓ /health returns {"status": "ok"}
  ✓ /tasks returns list of tasks
  ✓ /grade returns {"score": float} in (0.001, 0.999)
  ✓ /reset → /step → /grade full episode cycle
  ✓ Rewards formatted to 2dp in [END] line
  ✓ No hardcoded API keys or HF_TOKEN values in inference.py
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import time
import textwrap
from pathlib import Path

import pytest
import requests

# ── Config ────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent.parent.resolve()
SERVER_URL  = os.environ.get("SERVER_URL", "http://localhost:7860").rstrip("/")
SKIP_DOCKER = os.environ.get("SKIP_DOCKER", "0") == "1"
START_SERVER = os.environ.get("START_SERVER", "0") == "1"

# ANSI colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg: str) -> None: print(f"  {CYAN}ℹ{RESET} {msg}")

_failures: list[str] = []
_warnings: list[str] = []

def check(condition: bool, pass_msg: str, fail_msg: str, fatal: bool = False) -> bool:
    if condition:
        ok(pass_msg)
        return True
    else:
        fail(fail_msg)
        _failures.append(fail_msg)
        if fatal:
            print(f"\n{RED}{BOLD}FATAL — cannot continue without this.{RESET}\n")
            sys.exit(1)
        return False

def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

# ── Server management ─────────────────────────────────────────────────────────

_server_proc = None

def start_server() -> None:
    global _server_proc
    info("Starting uvicorn server in background...")
    _server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app",
         "--host", "0.0.0.0", "--port", "7860", "--log-level", "error"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        time.sleep(1)
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=2)
            if r.status_code == 200:
                ok("Server started successfully")
                return
        except Exception:
            pass
    fail("Server did not start within 30 seconds")
    _failures.append("Server failed to start")

def stop_server() -> None:
    if _server_proc:
        _server_proc.terminate()

def server_is_running() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — STRUCTURAL CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def phase1_file_structure() -> None:
    section("PHASE 1 — File Structure")

    check(
        (REPO_ROOT / "inference.py").exists(),
        "inference.py found at repo root",
        "inference.py MISSING from repo root — Phase 1 auto-fail",
        fatal=True,
    )
    check(
        (REPO_ROOT / "Dockerfile").exists(),
        "Dockerfile found at repo root",
        "Dockerfile MISSING from repo root — Phase 1 auto-fail",
        fatal=True,
    )
    check(
        (REPO_ROOT / "openenv.yaml").exists(),
        "openenv.yaml found at repo root",
        "openenv.yaml MISSING — Phase 1 auto-fail",
    )
    check(
        (REPO_ROOT / "requirements.txt").exists(),
        "requirements.txt found",
        "requirements.txt missing (not a hard fail but needed for Docker)",
    )


def phase1_openenv_validate() -> None:
    section("PHASE 1 — openenv validate")

    result = subprocess.run(
        ["openenv", "validate", str(REPO_ROOT / "openenv.yaml")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        ok("openenv validate passed")
    else:
        # openenv might not be installed locally — warn, don't fail
        if "command not found" in result.stderr.lower() or result.returncode == 127:
            warn("openenv CLI not installed locally — skipping validate (will run on server)")
        else:
            fail(f"openenv validate failed: {result.stderr.strip()}")
            _failures.append("openenv validate failed")


def phase1_reset_endpoint() -> None:
    section("PHASE 1 — OpenEnv Reset (POST OK)")

    if not server_is_running():
        warn(f"Server not running at {SERVER_URL} — skipping reset check")
        warn("Set START_SERVER=1 or start uvicorn manually before running this test")
        return

    try:
        r = requests.post(f"{SERVER_URL}/reset", json={"task_id": "task_easy"}, timeout=15)
        check(r.status_code == 200,
              f"POST /reset returned 200",
              f"POST /reset returned {r.status_code} — Phase 1 fail")

        data = r.json()
        for field in ("message", "step", "done", "alert"):
            check(field in data,
                  f"Observation has '{field}' field",
                  f"Observation missing '{field}' field — Phase 1 fail")

        check(isinstance(data.get("step"), int),
              "step is integer",
              "step is not integer")
        check(isinstance(data.get("done"), bool),
              "done is boolean",
              "done is not boolean")

    except Exception as exc:
        fail(f"POST /reset raised exception: {exc}")
        _failures.append("POST /reset exception")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — INFERENCE.PY STATIC ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def phase2_inference_static() -> None:
    section("PHASE 2 — inference.py Static Analysis")

    src = (REPO_ROOT / "inference.py").read_text()

    # Must use OpenAI client
    check(
        "from openai import OpenAI" in src or "import openai" in src,
        "Uses OpenAI client (not raw HTTP)",
        "Does NOT import OpenAI — Phase 2 fail (must use OpenAI SDK)",
    )

    # Must NOT use requests/httpx for LLM calls (env calls are fine)
    llm_http = bool(re.search(r'requests\.(post|get)\s*\(.*completions', src))
    check(
        not llm_http,
        "LLM calls go through OpenAI SDK (not raw requests)",
        "LLM calls use raw requests — use OpenAI client instead",
    )

    # API_BASE_URL must have default
    has_base_default = bool(re.search(
        r'API_BASE_URL\s*=\s*os\.(?:environ\.get|getenv)\s*\(\s*["\']API_BASE_URL["\'].*,',
        src
    ))
    check(
        has_base_default,
        "API_BASE_URL has a default value",
        "API_BASE_URL has NO default value — Phase 2 fail (required by spec)",
    )

    # MODEL_NAME must have default
    has_model_default = bool(re.search(
        r'MODEL_NAME\s*=\s*os\.(?:environ\.get|getenv)\s*\(\s*["\']MODEL_NAME["\'].*,',
        src
    ))
    check(
        has_model_default,
        "MODEL_NAME has a default value",
        "MODEL_NAME has NO default value — Phase 2 fail (required by spec)",
    )

    # HF_TOKEN must be read
    has_hf_token = "HF_TOKEN" in src
    check(
        has_hf_token,
        "HF_TOKEN is referenced in inference.py",
        "HF_TOKEN not found in inference.py — Phase 2 fail (mandatory)",
    )

    # HF_TOKEN should NOT have a hardcoded default value
    hf_hardcoded = bool(re.search(
        r'HF_TOKEN\s*=\s*["\'](?!None)[^"\']{4,}["\']',
        src
    ))
    check(
        not hf_hardcoded,
        "HF_TOKEN is not hardcoded",
        "HF_TOKEN appears hardcoded — security violation",
    )

    # No hardcoded API keys
    hardcoded_key = bool(re.search(
        r'(sk-[a-zA-Z0-9]{20,}|api_key\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\'])',
        src, re.IGNORECASE
    ))
    check(
        not hardcoded_key,
        "No hardcoded API keys found",
        "Hardcoded API key found — remove immediately",
    )

    # Must print [START], [STEP], [END]
    for tag in ("[START]", "[STEP]", "[END]"):
        check(
            tag in src,
            f"Output contains {tag} print statement",
            f"Missing {tag} print — Phase 2 output parsing will fail",
        )

    # [END] must NOT contain score= field
    end_lines = [l for l in src.splitlines() if "[END]" in l and "print" in l]
    if end_lines:
        for line in end_lines:
            has_score_field = bool(re.search(r'score\s*=', line))
            check(
                not has_score_field,
                "[END] print line has no extra score= field",
                f"[END] print has score= field — REMOVE it (spec violation): {line.strip()}",
            )
    else:
        warn("Could not find [END] print statement to verify format")


def phase2_inference_output_format() -> None:
    """Parse actual stdout from inference.py (dry run with mocked env)."""
    section("PHASE 2 — inference.py Output Format (dry run)")

    # We simulate what the evaluator sees by capturing a short run
    # We use a mock server that returns minimal valid responses
    # If server is running, we do a real short run; otherwise we parse source
    src = (REPO_ROOT / "inference.py").read_text()

    # Parse [START] format from source
    start_patterns = re.findall(r'print\s*\(\s*f?["\'].*\[START\].*["\']', src)
    if start_patterns:
        ok("Found [START] print statement")
        # Check it has required fields
        combined = " ".join(start_patterns)
        for field in ("task=", "env=", "model="):
            check(
                field in combined,
                f"[START] line includes {field} field",
                f"[START] line missing {field} field — spec requires task, env, model",
            )
    else:
        fail("[START] print statement not found in inference.py")

    # Parse [STEP] format
    step_patterns = re.findall(r'print\s*\(\s*f?["\'].*\[STEP\].*["\'][\s\S]{0,200}?(?=\n\s*[a-z])', src)
    if not step_patterns:
        step_patterns = re.findall(r'f"\[STEP\][^"]*"', src) + re.findall(r"f'\[STEP\][^']*'", src)

    found_step = any("[STEP]" in p for p in step_patterns) or "\\[STEP\\]" in src or '"[STEP]"' in src or "'[STEP]'" in src
    check(found_step,
          "Found [STEP] print statement",
          "[STEP] print not found")

    # Check rewards formatting — should be :.2f or :.4f (spec says 2dp but 4dp is also fine)
    reward_fmt = bool(re.search(r'reward.*:\.([24])f', src))
    check(
        reward_fmt,
        "reward formatted with :.2f or :.4f",
        "reward may not be formatted to decimal places — spec requires 2dp minimum",
    )

    # Check done/success are lowercase
    lower_bool = bool(re.search(r'str\(done\)\.lower\(\)|str\(success\)\.lower\(\)', src))
    check(
        lower_bool,
        "done/success converted to lowercase string (true/false not True/False)",
        "done/success not lowercased — spec requires lowercase booleans",
    )

    # Check [END] fields: success, steps, rewards — no score
    end_search = re.search(r'f["\'].*\[END\][^"\']*["\']', src, re.DOTALL)
    if end_search:
        end_str = end_search.group()
        for field in ("success=", "steps=", "rewards="):
            check(
                field in end_str,
                f"[END] line has {field}",
                f"[END] line missing {field}",
            )
        check(
            "score=" not in end_str,
            "[END] line has NO score= field (correct per spec)",
            "[END] has extra score= field — REMOVE IT — causes parse failure",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LIVE SERVER CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def phase2_health() -> None:
    section("PHASE 2 — /health endpoint")

    if not server_is_running():
        warn(f"Server not running at {SERVER_URL} — skipping live checks")
        return

    try:
        r = requests.get(f"{SERVER_URL}/health", timeout=5)
        check(r.status_code == 200,
              "/health returned 200",
              f"/health returned {r.status_code}")
        data = r.json()
        check("status" in data and data["status"] == "ok",
              '/health body has {"status": "ok"}',
              f'/health body is {data} — expected {{"status": "ok"}}')
    except Exception as exc:
        fail(f"/health check failed: {exc}")
        _failures.append("/health exception")


def phase2_tasks() -> None:
    section("PHASE 2 — /tasks endpoint")

    if not server_is_running():
        warn("Server not running — skipping /tasks check")
        return

    try:
        r = requests.get(f"{SERVER_URL}/tasks", timeout=5)
        check(r.status_code == 200,
              "/tasks returned 200",
              f"/tasks returned {r.status_code}")
        data = r.json()
        tasks = data.get("tasks", data) if isinstance(data, dict) else data
        check(isinstance(tasks, list) and len(tasks) > 0,
              f"/tasks returned {len(tasks) if isinstance(tasks, list) else 0} task(s)",
              "/tasks returned empty or invalid list")
        if isinstance(tasks, list) and tasks:
            first = tasks[0]
            for field in ("id", "name", "difficulty", "max_steps"):
                check(field in first,
                      f"Task object has '{field}' field",
                      f"Task object missing '{field}' field")
    except Exception as exc:
        fail(f"/tasks check failed: {exc}")


def phase2_full_episode() -> None:
    section("PHASE 2 — Full Episode Cycle (reset → step → grade)")

    if not server_is_running():
        warn("Server not running — skipping episode cycle check")
        return

    try:
        # Reset
        r = requests.post(f"{SERVER_URL}/reset", json={"task_id": "task_easy"}, timeout=15)
        check(r.status_code == 200, "POST /reset → 200", f"POST /reset → {r.status_code}")
        obs = r.json()

        # Step with a valid action
        action = {"action_type": "check_health", "target": "api-gateway"}
        r = requests.post(f"{SERVER_URL}/step", json=action, timeout=10)
        check(r.status_code == 200, "POST /step → 200", f"POST /step → {r.status_code}")

        step_data = r.json()
        for field in ("observation", "reward", "done", "info"):
            check(field in step_data,
                  f"StepResponse has '{field}'",
                  f"StepResponse missing '{field}'")

        reward_obj = step_data.get("reward", {})
        reward_val = reward_obj.get("value") if isinstance(reward_obj, dict) else reward_obj
        if reward_val is not None:
            check(
                -1.0 <= float(reward_val) <= 1.0,
                f"reward value {reward_val} in [-1.0, 1.0]",
                f"reward value {reward_val} OUT OF RANGE",
            )

        # Declare RCA to end episode
        rca = {"action_type": "declare_rca", "target": "notification-service"}
        r = requests.post(f"{SERVER_URL}/step", json=rca, timeout=10)
        check(r.status_code == 200, "POST /step (declare_rca) → 200",
              f"POST /step (declare_rca) → {r.status_code}")

        # Grade
        r = requests.get(f"{SERVER_URL}/grade", timeout=5)
        check(r.status_code == 200, "GET /grade → 200", f"GET /grade → {r.status_code}")
        grade_data = r.json()
        check("score" in grade_data,
              "GET /grade has 'score' field",
              "GET /grade missing 'score' field")

        score = grade_data.get("score", 0)
        check(
            0.001 <= float(score) <= 0.999,
            f"score {score:.4f} is in (0.001, 0.999)",
            f"score {score} is OUT OF RANGE — must be strictly in (0.001, 0.999)",
        )
        check(
            float(score) != 0.0 and float(score) != 1.0,
            "score is not exactly 0.0 or 1.0",
            "score is exactly 0.0 or 1.0 — auto-fail on evaluation",
        )

    except Exception as exc:
        fail(f"Episode cycle failed: {exc}")
        _failures.append(f"Episode cycle exception: {exc}")


def phase2_all_tasks_reset() -> None:
    section("PHASE 2 — All Task IDs Reset Without Error")

    if not server_is_running():
        warn("Server not running — skipping task reset checks")
        return

    # Get task list first
    try:
        r = requests.get(f"{SERVER_URL}/tasks", timeout=5)
        if r.status_code != 200:
            warn("Could not fetch /tasks — skipping per-task reset check")
            return
        data = r.json()
        tasks = data.get("tasks", data) if isinstance(data, dict) else data
        task_ids = [t["id"] for t in tasks if "id" in t]
    except Exception as exc:
        warn(f"Could not get task list: {exc}")
        return

    info(f"Testing reset for {len(task_ids)} task(s): {task_ids}")
    for tid in task_ids:
        try:
            r = requests.post(f"{SERVER_URL}/reset", json={"task_id": tid}, timeout=10)
            check(
                r.status_code == 200,
                f"  /reset task_id={tid} → 200",
                f"  /reset task_id={tid} → {r.status_code} (422 = Literal not updated in models.py)",
            )
        except Exception as exc:
            fail(f"  /reset task_id={tid} raised: {exc}")


def phase2_grade_score_range() -> None:
    section("PHASE 2 — Score Range Validation")

    if not server_is_running():
        warn("Server not running — skipping score range check")
        return

    try:
        r = requests.get(f"{SERVER_URL}/tasks", timeout=5)
        data = r.json()
        tasks = data.get("tasks", data) if isinstance(data, dict) else data
        task_ids = [t["id"] for t in (tasks or []) if "id" in t][:3]  # test first 3 only
    except Exception:
        task_ids = ["task_easy"]

    for tid in task_ids:
        try:
            requests.post(f"{SERVER_URL}/reset", json={"task_id": tid}, timeout=10)
            rca = {"action_type": "declare_rca", "target": "api-gateway"}
            requests.post(f"{SERVER_URL}/step", json=rca, timeout=10)
            r = requests.get(f"{SERVER_URL}/grade", timeout=5)
            score = r.json().get("score", 0.0)
            check(
                0.001 <= float(score) <= 0.999,
                f"  {tid}: score={score:.4f} in (0.001, 0.999)",
                f"  {tid}: score={score} OUT OF RANGE — validator will reject 0.0 and 1.0",
            )
        except Exception as exc:
            fail(f"  {tid}: grade check failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — DOCKER BUILD
# ══════════════════════════════════════════════════════════════════════════════

def phase2_docker_build() -> None:
    section("PHASE 2 — Docker Build")

    if SKIP_DOCKER:
        warn("SKIP_DOCKER=1 — skipping Docker build test")
        return

    dockerfile = REPO_ROOT / "Dockerfile"
    if not dockerfile.exists():
        fail("Dockerfile not found — skipping Docker build")
        return

    info("Running: docker build -t incident-presubmit-test . (this may take a few minutes)")
    start = time.time()
    result = subprocess.run(
        ["docker", "build", "-t", "incident-presubmit-test", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - start

    if result.returncode == 0:
        ok(f"Docker build succeeded in {elapsed:.0f}s")
    else:
        fail(f"Docker build FAILED (exit {result.returncode})")
        _failures.append("Docker build failed")
        # Show last 30 lines of build output for debugging
        lines = result.stderr.strip().splitlines()
        print(f"\n  {YELLOW}Last 30 lines of build output:{RESET}")
        for l in lines[-30:]:
            print(f"    {l}")


# ══════════════════════════════════════════════════════════════════════════════
# BONUS — Environment quality checks
# ══════════════════════════════════════════════════════════════════════════════

def bonus_environment_quality() -> None:
    section("BONUS — Environment Quality Checks")

    env_file = REPO_ROOT / "environment.py"
    if not env_file.exists():
        warn("environment.py not found — skipping quality checks")
        return

    src = env_file.read_text()

    # Seed is applied
    check(
        "random.seed" in src,
        "environment.py calls random.seed() for reproducibility",
        "random.seed() not found — runs are non-deterministic",
    )

    # Grade is clamped
    check(
        "0.001" in src and "0.999" in src,
        "Grade is clamped to (0.001, 0.999)",
        "Grade clamp values not found — may return 0.0 or 1.0",
    )

    # No hardcoded evaluation answers
    check(
        "fault_service" in src and "declare_rca" in src,
        "Reward logic uses fault_service (not hardcoded answers)",
        "Could not verify reward logic uses dynamic fault_service",
    )

    # Check requirements.txt doesn't include openenv-core
    req_file = REPO_ROOT / "requirements.txt"
    if req_file.exists():
        req_src = req_file.read_text()
        check(
            "openenv-core" not in req_src,
            "requirements.txt does NOT include openenv-core",
            "requirements.txt includes openenv-core — Phase 1 check may fail",
        )

    # Check models.py has correct Literal task IDs
    models_file = REPO_ROOT / "models.py"
    if models_file.exists() and env_file.exists():
        models_src = models_file.read_text()
        env_src = env_file.read_text()
        # Find TASKS dict keys in environment.py
        task_keys = re.findall(r'"(task_[a-z_]+)"', env_src)
        task_keys = list(set(task_keys))
        models_ok = all(tid in models_src for tid in task_keys)
        check(
            models_ok,
            f"models.py Literal covers all {len(task_keys)} task IDs from environment.py",
            f"models.py Literal is MISSING some task IDs — will cause 422 on /reset: "
            f"{[t for t in task_keys if t not in models_src]}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_all() -> None:
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  PRE-SUBMISSION VALIDATOR — Incident Response Env{RESET}")
    print(f"{BOLD}  Mirrors Phase 1 + Phase 2 hackathon checks{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")
    print(f"  Repo root : {REPO_ROOT}")
    print(f"  Server URL: {SERVER_URL}")
    print(f"  Skip Docker: {SKIP_DOCKER}")

    if START_SERVER and not server_is_running():
        start_server()

    # ── Phase 1 ──
    phase1_file_structure()
    phase1_openenv_validate()
    phase1_reset_endpoint()

    # ── Phase 2 static ──
    phase2_inference_static()
    phase2_inference_output_format()

    # ── Phase 2 live ──
    if server_is_running():
        phase2_health()
        phase2_tasks()
        phase2_full_episode()
        phase2_all_tasks_reset()
        phase2_grade_score_range()
    else:
        warn(f"Server not reachable at {SERVER_URL}")
        info("Start your server first:  uvicorn server.app:app --port 7860")
        info("Or set START_SERVER=1 to auto-start")

    # ── Docker ──
    phase2_docker_build()

    # ── Bonus ──
    bonus_environment_quality()

    # ── Summary ──
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    if not _failures:
        print(f"\n  {GREEN}{BOLD}✓ ALL CHECKS PASSED — Safe to submit!{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}✗ {len(_failures)} CHECK(S) FAILED:{RESET}")
        for i, f in enumerate(_failures, 1):
            print(f"    {i}. {f}")
        print(f"\n  {YELLOW}Fix all failures before submitting.{RESET}\n")

    if _warnings:
        print(f"  {YELLOW}Warnings ({len(_warnings)}):{RESET}")
        for w in _warnings:
            print(f"    • {w}")

    print()
    return len(_failures) == 0


# ── pytest-compatible test functions (run via: pytest test_presubmit.py -v) ──

def test_inference_exists():
    assert (REPO_ROOT / "inference.py").exists(), "inference.py must be at repo root"

def test_dockerfile_exists():
    assert (REPO_ROOT / "Dockerfile").exists(), "Dockerfile must be at repo root"

def test_openenv_yaml_exists():
    assert (REPO_ROOT / "openenv.yaml").exists(), "openenv.yaml must be at repo root"

def test_inference_uses_openai_client():
    src = (REPO_ROOT / "inference.py").read_text()
    assert "from openai import OpenAI" in src or "import openai" in src

def test_api_base_url_has_default():
    src = (REPO_ROOT / "inference.py").read_text()
    assert re.search(
        r'API_BASE_URL\s*=\s*os\.(?:environ\.get|getenv)\s*\(\s*["\']API_BASE_URL["\'].*,',
        src
    ), "API_BASE_URL must have a default value"

def test_model_name_has_default():
    src = (REPO_ROOT / "inference.py").read_text()
    assert re.search(
        r'MODEL_NAME\s*=\s*os\.(?:environ\.get|getenv)\s*\(\s*["\']MODEL_NAME["\'].*,',
        src
    ), "MODEL_NAME must have a default value"

def test_hf_token_present():
    src = (REPO_ROOT / "inference.py").read_text()
    assert "HF_TOKEN" in src, "HF_TOKEN must be referenced in inference.py"

def test_no_hardcoded_api_keys():
    src = (REPO_ROOT / "inference.py").read_text()
    assert not re.search(r'sk-[a-zA-Z0-9]{20,}', src), "Hardcoded API key found"

def test_end_line_no_score_field():
    src = (REPO_ROOT / "inference.py").read_text()
    end_match = re.search(r'f["\'].*\[END\](.*?)["\']', src, re.DOTALL)
    if end_match:
        assert "score=" not in end_match.group(1), "[END] print has score= field (remove it)"

def test_done_success_lowercased():
    src = (REPO_ROOT / "inference.py").read_text()
    assert re.search(r'\.lower\(\)', src), "done/success must be lowercased to true/false"

def test_openenv_core_not_in_requirements():
    req = (REPO_ROOT / "requirements.txt")
    if req.exists():
        assert "openenv-core" not in req.read_text(), \
            "requirements.txt must NOT include openenv-core"

def test_random_seeded():
    env = REPO_ROOT / "environment.py"
    if env.exists():
        assert "random.seed" in env.read_text(encoding='utf-8', errors='replace'), \
            "environment.py must call random.seed() for reproducibility"

def test_grade_clamp():
    env = REPO_ROOT / "environment.py"
    if env.exists():
        src = env.read_text(encoding='utf-8', errors='replace')
        assert "0.001" in src and "0.999" in src, \
            "Grade must be clamped to (0.001, 0.999)"

def test_all_task_ids_in_models():
    env = REPO_ROOT / "environment.py"
    models = REPO_ROOT / "models.py"
    if env.exists() and models.exists():
        env_src = env.read_text(encoding='utf-8', errors='replace')
        models_src = models.read_text(encoding='utf-8', errors='replace')
        task_keys = list(set(re.findall(r'"(task_[a-z_]+)"', env_src)))
        missing = [t for t in task_keys if t not in models_src]
        assert not missing, \
            f"models.py Literal missing task IDs (causes 422): {missing}"

@pytest.mark.skipif(not server_is_running(), reason="Server not running")
def test_health_endpoint():
    r = requests.get(f"{SERVER_URL}/health", timeout=5)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

@pytest.mark.skipif(not server_is_running(), reason="Server not running")
def test_reset_endpoint():
    r = requests.post(f"{SERVER_URL}/reset", json={"task_id": "task_cpu_spike"}, timeout=10)
    assert r.status_code == 200
    data = r.json()
    for field in ("message", "step", "done", "alert"):
        assert field in data, f"Observation missing '{field}'"

@pytest.mark.skipif(not server_is_running(), reason="Server not running")
def test_grade_in_valid_range():
    requests.post(f"{SERVER_URL}/reset", json={"task_id": "task_cpu_spike"}, timeout=10)
    requests.post(f"{SERVER_URL}/step",
                  json={"action_type": "declare_rca", "target": "api-gateway"}, timeout=10)
    r = requests.get(f"{SERVER_URL}/grade", timeout=5)
    score = r.json().get("score", 0)
    assert 0.001 <= float(score) <= 0.999, f"score {score} out of (0.001, 0.999)"
    assert float(score) not in (0.0, 1.0), "score must not be exactly 0.0 or 1.0"


# Add pytest import guard at bottom
try:
    import pytest
except ImportError:
    # pytest not installed — only direct run works
    pass

if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
def test_models_literal_matches_tasks():
    from environment import TASKS
    from models import ResetRequest
    import inspect, typing
    hints = typing.get_type_hints(ResetRequest)
    literal_args = set(typing.get_args(hints["task_id"]))
    assert set(TASKS.keys()) == literal_args, \
        f"Mismatch: env has {set(TASKS.keys()) - literal_args}, models has {literal_args - set(TASKS.keys())}"
