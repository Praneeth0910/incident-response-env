#!/usr/bin/env python3
"""Verify TASKS list in inference.py matches environment.py."""

import re
from environment import TASKS as env_tasks

# Read inference.py
with open('inference.py', 'r') as f:
    content = f.read()

# Extract TASKS list
tasks_match = re.search(r'TASKS = \[(.*?)\]', content, re.DOTALL)
if tasks_match:
    tasks_str = tasks_match.group(1)
    # Extract task names
    task_names = re.findall(r'"(task_[\w]+)"', tasks_str)
    
    print('=== TASKS List Verification ===\n')
    print(f'Total tasks in inference.py: {len(task_names)}')
    print(f'Total tasks in environment.py: {len(env_tasks)}\n')
    
    expected = sorted(env_tasks.keys())
    found = sorted(task_names)
    
    if found == expected:
        print('OK - All 14 tasks match!\n')
        print('Inference.py TASKS list (in order):')
        for i, task in enumerate(task_names, 1):
            task_obj = env_tasks[task]
            diff = task_obj['difficulty']
            steps = task_obj['max_steps']
            print(f'  {i:2}. {task:30} ({diff:6}, max_steps={steps:2})')
    else:
        missing = set(expected) - set(found)
        extra = set(found) - set(expected)
        print('!! Tasks do not match!')
        if missing:
            print(f'Missing: {missing}')
        if extra:
            print(f'Extra: {extra}')
else:
    print('!! Could not find TASKS list in inference.py')
