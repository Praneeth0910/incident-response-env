#!/usr/bin/env python3
"""Verify all configured tasks are properly defined and resettable."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from environment import IncidentResponseEnv, TASKS
from models import ResetRequest
from task_config import ALL_TASKS

task_names = ALL_TASKS

print(f"Testing all {len(task_names)} configured tasks can be loaded:")
missing = []
for task_name in task_names:
    if task_name in TASKS:
        task = TASKS[task_name]
        diff = task["difficulty"]
        steps = task["max_steps"]
        name = task["name"]
        print(f"  OK {task_name:30} ({diff:6}, max_steps:{steps:2}) - {name}")
    else:
        missing.append(task_name)
        print(f"  !! {task_name:30} MISSING")

print(f"\nTotal tasks in TASKS dict: {len(TASKS)}")

print("\nTesting every configured task can be reset:")
reset_failures = []
for task_name in task_names:
    try:
        env = IncidentResponseEnv()
        obs = env.reset(task_name, seed=42)
        print(f"  OK {task_name:30} - Alert: {obs.alert[:50]}...")
    except Exception as exc:
        reset_failures.append(task_name)
        print(f"  !! {task_name:30} - Error: {str(exc)[:50]}")

print("\nTesting task_cpu_spike baseline expectations:")
task = TASKS["task_cpu_spike"]
print(f'  Difficulty: {task["difficulty"]} (should be "easy")')
print(f'  Max steps: {task["max_steps"]} (should be 10)')
if task["difficulty"] == "easy" and task["max_steps"] == 10:
    print("  ✓ task_cpu_spike correctly updated")
else:
    print("  ✗ task_cpu_spike update FAILED")

print("\nVerifying models.py ResetRequest:")
model_failures = []
for task_name in task_names:
    try:
        ResetRequest(task_id=task_name)
        print(f"  OK {task_name}")
    except Exception as exc:
        model_failures.append(task_name)
        print(f"  ✗ {task_name}: {exc}")

if not missing and not reset_failures and not model_failures:
    print(f"\n✓ Implementation complete: {len(TASKS)} tasks, all working")
else:
    print(
        "\n✗ Task verification failed: "
        f"missing={missing}, reset_failures={reset_failures}, model_failures={model_failures}"
    )
    sys.exit(1)
