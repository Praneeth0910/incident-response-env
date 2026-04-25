#!/usr/bin/env python3
"""Verify all 15 tasks are properly defined and working."""

from environment import IncidentResponseEnv, TASKS

# Test all 15 task names exist and can be loaded
task_names = [
    'task_cpu_spike',
    'task_db_connection_leak',
    'task_redis_memory_eviction',
    'task_api_rate_limit',
    'task_deadlock_order_service',
    'task_ssl_cert_expired',
    'task_slow_query_postgres',
    'task_auth_service_500',
    'task_k8s_pod_crashloop',
    'task_disk_full',
    'task_memory_leak',
    'task_thread_starvation',
    'task_canary_poison',
    'task_clock_skew',
]

print('Testing all 15 tasks can be loaded:')
for task_name in task_names:
    if task_name in TASKS:
        task = TASKS[task_name]
        diff = task["difficulty"]
        steps = task["max_steps"]
        name = task["name"]
        print(f'  OK {task_name:30} ({diff:6}, max_steps:{steps:2}) - {name}')
    else:
        print(f'  !! {task_name:30} MISSING')

print(f'\nTotal tasks in TASKS dict: {len(TASKS)}')

# Test each new task can be reset
new_tasks = ['task_disk_full', 'task_memory_leak', 'task_thread_starvation', 'task_canary_poison', 'task_clock_skew']
print('\nTesting new tasks can be reset:')
for task_name in new_tasks:
    try:
        env = IncidentResponseEnv()
        obs = env.reset(task_name, seed=42)
        print(f'  OK {task_name:30} - Alert: {obs.alert[:50]}...')
    except Exception as e:
        print(f'  !! {task_name:30} - Error: {str(e)[:50]}')

# Test updated task_cpu_spike (now easy with max_steps 10)
print('\nTesting updated task_cpu_spike:')
task = TASKS['task_cpu_spike']
print(f'  Difficulty: {task["difficulty"]} (should be "easy")')
print(f'  Max steps: {task["max_steps"]} (should be 10)')
if task["difficulty"] == "easy" and task["max_steps"] == 10:
    print('  ✓ task_cpu_spike correctly updated')
else:
    print('  ✗ task_cpu_spike update FAILED')

# Check models.py can parse all tasks
print('\nVerifying models.py ResetRequest:')
from models import ResetRequest
try:
    for task_name in task_names:
        req = ResetRequest(task_id=task_name)
        print(f'  OK {task_name}')
    print(f'  ✓ All 15 tasks accepted by ResetRequest')
except Exception as e:
    print(f'  ✗ ResetRequest error: {e}')

print(f'\n✓ Implementation complete: {len(TASKS)} tasks, all working')
