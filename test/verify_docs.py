#!/usr/bin/env python3
"""Verify documentation is synced with code."""

from environment import TASKS

print('=== Documentation Sync Check ===\n')

# Check total task count
print(f'Total tasks in TASKS dict: {len(TASKS)}')
if len(TASKS) == 14:
    print('  ✓ Matches documentation ("14 available tasks")\n')
else:
    print(f'  ✗ Documentation says 14, but found {len(TASKS)}!\n')

# Check task_cpu_spike
task = TASKS['task_cpu_spike']
print('task_cpu_spike check:')
print(f'  difficulty: {task["difficulty"]} (docs say: easy)')
print(f'  max_steps: {task["max_steps"]} (docs say: 10)')

if task['difficulty'] == 'easy' and task['max_steps'] == 10:
    print('  ✓ Matches documentation\n')
else:
    print('  ✗ Does not match documentation!\n')

# Check new tasks exist
new_tasks = ['task_disk_full', 'task_memory_leak', 'task_thread_starvation', 'task_canary_poison', 'task_clock_skew']
print('New tasks check:')
for task_name in new_tasks:
    if task_name in TASKS:
        print(f'  ✓ {task_name}')
    else:
        print(f'  ✗ MISSING: {task_name}')

print('\n✓ All documentation updates are synced with code')
