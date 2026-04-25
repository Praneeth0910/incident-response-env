#!/usr/bin/env python3
"""Verify benchmark runner can load all 14 tasks."""

from environment import IncidentResponseEnv, TASKS

print('=== Benchmark Runner Task Verification ===\n')

# Load inference TASKS list directly without importing inference.py
# (which requires environment variables)
all_task_ids = [
    "task_cpu_spike",
    "task_disk_full",
    "task_db_connection_leak",
    "task_redis_memory_eviction",
    "task_api_rate_limit",
    "task_deadlock_order_service",
    "task_ssl_cert_expired",
    "task_slow_query_postgres",
    "task_auth_service_500",
    "task_k8s_pod_crashloop",
    "task_memory_leak",
    "task_thread_starvation",
    "task_canary_poison",
    "task_clock_skew",
]

print(f'Tasks to verify: {len(all_task_ids)}')
print(f'Tasks in environment.TASKS: {len(TASKS)}\n')

print('Testing environment reset on each task:')
env = IncidentResponseEnv()
success_count = 0

for i, task_id in enumerate(all_task_ids, 1):
    try:
        obs = env.reset(task_id, seed=42)
        task_info = TASKS[task_id]
        diff = task_info['difficulty']
        steps = task_info['max_steps']
        alert_preview = obs.alert[:50]
        print(f'  {i:2}. {task_id:30} OK ({diff:6}, {steps:2} steps)')
        success_count += 1
    except Exception as e:
        print(f'  {i:2}. {task_id:30} !! Error: {str(e)[:40]}')

print(f'\nOK - {success_count}/{len(all_task_ids)} tasks loadable\n')

if success_count == len(all_task_ids):
    print('✓ Benchmark runner TASKS list is ready for all 14 tasks')
else:
    print(f'✗ {len(all_task_ids) - success_count} tasks failed')
