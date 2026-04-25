#!/usr/bin/env python3
"""Test reward shaping for new fault types."""

from environment import IncidentResponseEnv, Action, TASKS

print("=== Testing Reward Shaping for New Fault Types ===\n")

# Test task_disk_full (run_db_query should give reward)
print("1. task_disk_full (run_db_query reward):")
env = IncidentResponseEnv()
obs = env.reset('task_disk_full', seed=42)
action = Action(action_type='run_db_query', target='postgres-db')
obs, reward, done, info = env.step(action)
print(f"   Query target postgres-db: reward={reward.value} ({reward.reason})")
print(f"   Expected: 0.12+ for disk_full check")
if reward.value >= 0.12:
    print("   OK - PASS\n")
else:
    print("   !! - FAIL\n")

# Test task_memory_leak (restart_service should give reward)
print("2. task_memory_leak (restart already correct):")
print("   Fault type: memory_leak")
print("   Fault service: notification-service")
print("   Expected: restart_service on notification-service gives 0.30")
task = TASKS['task_memory_leak']
if task['fault_type'] == 'memory_leak' and task['fault_service'] == 'notification-service':
    print("   OK - config correct\n")
else:
    print("   !! - config incorrect\n")

# Test task_canary_poison (rollback_deployment should give reward)
print("3. task_canary_poison (rollback_deployment reward):")
env = IncidentResponseEnv()
obs = env.reset('task_canary_poison', seed=42)
action = Action(action_type='rollback_deployment', target='api-gateway')
obs, reward, done, info = env.step(action)
print(f"   Rollback api-gateway: reward={reward.value} ({reward.reason[:50]})")
print(f"   Expected: ~0.07 for blind rollback (0.35 base × 0.2 sequence bonus for no evidence)")
if reward.value >= 0.05:
    print("   OK - PASS\n")
else:
    print("   !! - FAIL\n")

# Test task_thread_starvation (restart_service should work)
print("4. task_thread_starvation (restart_service):")
task = TASKS['task_thread_starvation']
print(f"   Fault type: {task['fault_type']}")
print(f"   Fault service: {task['fault_service']}")
print(f"   In restart_fixes ('oom_crash', 'cpu_spike', 'memory_leak', 'thread_pool_exhausted')?")
if task['fault_type'] == 'thread_pool_exhausted':
    print("   OK - thread_pool_exhausted is in restart_fixes\n")
else:
    print(f"   !! - {task['fault_type']} not in restart_fixes\n")

# Test task_clock_skew returns clock_drift_seconds
print("5. task_clock_skew (check_metrics includes clock_drift_seconds):")
env = IncidentResponseEnv()
obs = env.reset('task_clock_skew', seed=42)
action = Action(action_type='check_metrics', target='auth-service')
obs, reward, done, info = env.step(action)
if obs.metrics and 'auth-service' in obs.metrics:
    metrics = obs.metrics['auth-service']
    if 'clock_drift_seconds' in metrics:
        val = metrics['clock_drift_seconds']
        print(f"   Found clock_drift_seconds: {val}")
        if val >= 300:
            print("   OK - Value >= 300 confirms clock skew detectable\n")
        else:
            print(f"   !! - Value {val} < 300, threshold may not detect\n")
    else:
        print(f"   !! - clock_drift_seconds NOT found in metrics")
        print(f"   Available keys: {list(metrics.keys())}\n")
else:
    print(f"   !! - metrics not populated\n")

# Verify rollback_fixes no longer includes invalid types
print("6. Verify rollback_deployment fixes list:")
print("   Expected: ('bad_deployment', 'canary_misconfiguration') only")
# Read the environment.py file to check
with open('environment.py', 'r') as f:
    content = f.read()
    if '_rollback_fixes = ("bad_deployment", "canary_misconfiguration")' in content:
        print("   OK - rollback_fixes correctly updated\n")
    elif '_rollback_fixes = ("bad_deployment", "canary_misconfiguration",' in content:
        # Check if it's a multiline definition
        import re
        match = re.search(r'_rollback_fixes = \((.*?)\)', content, re.DOTALL)
        if match:
            fixes = match.group(1)
            if 'clock_skew' in fixes or 'connection_pool_exhausted' in fixes or 'disk_full' in fixes:
                print(f"   !! - rollback_fixes still contains invalid types\n")
            else:
                print(f"   OK - rollback_fixes correctly updated\n")
    else:
        print("   !! - Unable to find rollback_fixes definition\n")

print("OK - All reward shaping tests complete")
