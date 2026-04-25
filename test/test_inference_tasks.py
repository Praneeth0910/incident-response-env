#!/usr/bin/env python3
"""Verify benchmark runner can load every configured task."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from environment import IncidentResponseEnv, TASKS
from task_config import ALL_TASKS

print("=== Benchmark Runner Task Verification ===\n")

# Load inference TASKS list directly without importing inference.py, which
# requires environment variables.
all_task_ids = ALL_TASKS

print(f"Tasks to verify: {len(all_task_ids)}")
print(f"Tasks in environment.TASKS: {len(TASKS)}\n")

print("Testing environment reset on each task:")
env = IncidentResponseEnv()
success_count = 0

for index, task_id in enumerate(all_task_ids, 1):
    try:
        env.reset(task_id, seed=42)
        task_info = TASKS[task_id]
        diff = task_info["difficulty"]
        steps = task_info["max_steps"]
        print(f"  {index:2}. {task_id:30} OK ({diff:6}, {steps:2} steps)")
        success_count += 1
    except Exception as exc:
        print(f"  {index:2}. {task_id:30} !! Error: {str(exc)[:40]}")

print(f"\nOK - {success_count}/{len(all_task_ids)} tasks loadable\n")

if success_count == len(all_task_ids):
    print(f"✓ Benchmark runner TASKS list is ready for all {len(all_task_ids)} tasks")
else:
    print(f"✗ {len(all_task_ids) - success_count} tasks failed")
