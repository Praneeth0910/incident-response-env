#!/usr/bin/env python3
"""Test full episode run on a new task."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from environment import IncidentResponseEnv, Action

print("=== Full Episode Test: task_canary_poison ===\n")

env = IncidentResponseEnv()
obs = env.reset('task_canary_poison', seed=42)

print(f"Task: task_canary_poison")
print(f"Alert: {obs.alert}\n")

# Simulate a good investigation path
steps = [
    Action(action_type='check_metrics', target='api-gateway'),           # Gateway shows symptoms
    Action(action_type='read_logs', target='api-gateway'),               # Gateway logs show canary
    Action(action_type='check_metrics', target='auth-service'),          # Auth-service shows 401s
    Action(action_type='read_logs', target='api-gateway'),               # Recheck - reduplicate
    Action(action_type='rollback_deployment', target='api-gateway'),     # Rollback the canary
    Action(action_type='declare_rca', target='api-gateway'),             # Declare correct RCA
]

cumulative = 0
for i, action in enumerate(steps, 1):
    obs, reward, done, info = env.step(action)
    cumulative = info['cumulative_reward']
    
    print(f"Step {i}: {action.action_type} → {action.target}")
    print(f"  Reward: {reward.value:6.4f} | {reward.reason}")
    print(f"  Cumulative: {cumulative:6.4f}")
    
    if done:
        print(f"\n✓ Episode complete at step {i}")
        print(f"Final score: {cumulative:6.4f}")
        if cumulative >= 0.60:
            print("✓ Success threshold (0.60) reached!")
        break
else:
    print(f"\n✗ Episode did not complete (ran {len(steps)} steps)")

print("\n" + "="*60)
print("=== Full Episode Test: task_clock_skew (declare only) ===\n")

env = IncidentResponseEnv()
obs = env.reset('task_clock_skew', seed=42)

print(f"Task: task_clock_skew")
print(f"Alert: {obs.alert}\n")

# For clock_skew, we just gather evidence and declare RCA (no restart/rollback)
steps = [
    Action(action_type='check_metrics', target='auth-service'),          # Should show clock_drift
    Action(action_type='read_logs', target='auth-service'),              # Should show NTP issue
    Action(action_type='check_metrics', target='redis-cache'),           # Red herring 
    Action(action_type='check_metrics', target='order-service'),         # Another red herring
    Action(action_type='declare_rca', target='auth-service'),            # Declare correct RCA
]

cumulative = 0
for i, action in enumerate(steps, 1):
    obs, reward, done, info = env.step(action)
    cumulative = info['cumulative_reward']
    
    print(f"Step {i}: {action.action_type} → {action.target}")
    print(f"  Reward: {reward.value:6.4f} | {reward.reason[:50]}")
    print(f"  Cumulative: {cumulative:6.4f}")
    
    if done:
        print(f"\n✓ Episode complete at step {i}")
        print(f"Final score: {cumulative:6.4f}")
        if cumulative >= 0.60:
            print("✓ Success threshold (0.60) reached!")
        break
else:
    print(f"\n✗ Episode did not complete (ran {len(steps)} steps)")

print("\n✓ Full episode tests complete")
