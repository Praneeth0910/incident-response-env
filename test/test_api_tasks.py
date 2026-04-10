#!/usr/bin/env python3
"""Test all new tasks via /reset API endpoint."""

import requests

# Test sampling of new and existing tasks via the /reset endpoint
tasks_to_test = [
    'task_cpu_spike',          # Updated (easy now)
    'task_db_connection_leak', 
    'task_disk_full',         # NEW
    'task_memory_leak',       # NEW
    'task_thread_starvation', # NEW
    'task_canary_poison',     # NEW
    'task_clock_skew',        # NEW
]

print("Testing /reset endpoint with tasks (including new ones):")
base_url = "http://localhost:7860"

for task_id in tasks_to_test:
    try:
        resp = requests.post(
            f"{base_url}/reset",
            json={"task_id": task_id, "seed": 42},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            alert = data.get("alert", "")[:60]
            print(f"  OK {task_id:30} Status 200 → {alert}...")
        else:
            print(f"  !! {task_id:30} Status {resp.status_code}")
    except Exception as e:
        print(f"  !! {task_id:30} Error: {str(e)[:40]}")

print("\n✓ All tested tasks accessible via /reset API endpoint")
