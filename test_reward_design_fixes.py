"""
Test to verify all 4 reward design issues are fixed.

Issue A: Time pressure no longer penalizes correct late actions
Issue B: Wrong RCA evidence credit (no change needed - working as intended)
Issue C: Sequence bonus floor is 0.0 for blind actions (not 0.2)
Issue D: rollback_fixes only includes deployment-related faults
"""

from environment import IncidentResponseEnv, Action, TASKS


def test_issue_a_time_pressure():
    """
    Issue A: Verify positive rewards are NOT scaled down in late steps.
    At step 14/15, a correct restart_service should still give full reward.
    """
    print("=== Issue A: Time Pressure Fix ===")
    env = IncidentResponseEnv()
    env.reset("task_cpu_spike", seed=42)  # max_steps=10
    
    # Gather evidence first
    env.step(Action(action_type="read_logs", target="auth-service"))
    env.step(Action(action_type="check_metrics", target="auth-service"))
    
    # Now at step 3/10, restart - should get full reward
    obs, reward_early, done, info = env.step(Action(action_type="restart_service", target="auth-service"))
    early_reward = reward_early.value
    
    # Reset and test late restart
    env.reset("task_cpu_spike", seed=42)
    env.step(Action(action_type="read_logs", target="auth-service"))
    env.step(Action(action_type="check_metrics", target="auth-service"))
    # Waste steps to get to late in episode
    for i in range(5):
        env.step(Action(action_type="check_health", target="order-service"))  # irrelevant service
    
    # Now at step 8/10 (80% progress), restart - should STILL get similar reward
    obs, reward_late, done, info = env.step(Action(action_type="restart_service", target="auth-service"))
    late_reward = reward_late.value
    
    print(f"  Early restart (step 3/10): {early_reward:.4f}")
    print(f"  Late restart (step 8/10):  {late_reward:.4f}")
    print(f"  Difference: {abs(early_reward - late_reward):.4f}")
    
    # With the fix, late positive rewards should NOT be scaled down significantly
    # They should be similar (small difference due to reward.py possibly)
    if late_reward >= early_reward * 0.85:  # Allow small variation
        print("  [OK] PASS - Late correct actions not heavily penalized\n")
        return True
    else:
        print(f"  [X] FAIL - Late reward ({late_reward:.4f}) is {(1 - late_reward/early_reward)*100:.1f}% lower\n")
        return False


def test_issue_c_blind_action_penalty():
    """
    Issue C: Verify blind restart/rollback gets 0.0 reward, not positive reward.
    """
    print("=== Issue C: Blind Action Penalty ===")
    env = IncidentResponseEnv()
    env.reset("task_cpu_spike", seed=42)
    
    # Restart without any evidence gathering
    obs, reward, done, info = env.step(Action(action_type="restart_service", target="auth-service"))
    
    print(f"  Blind restart reward: {reward.value}")
    print(f"  Reason: {reward.reason[:60]}")
    
    if reward.value == 0.0:
        print("  [OK] PASS - Blind actions get 0.0 reward\n")
        return True
    else:
        print(f"  [X] FAIL - Expected 0.0, got {reward.value}\n")
        return False


def test_issue_d_rollback_fixes_list():
    """
    Issue D: Verify rollback_fixes only includes deployment-related faults.
    Should NOT include: connection_pool_exhausted, cert_expired, rate_limit_exceeded,
                        slow_query, clock_skew
    Should ONLY include: bad_deployment, canary_misconfiguration
    """
    print("=== Issue D: Rollback Fixes List ===")
    
    # Read environment.py to check _rollback_fixes
    with open('environment.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the _rollback_fixes definition
    import re
    match = re.search(r'_rollback_fixes = \((.*?)\)', content, re.DOTALL)
    if not match:
        print("  [X] FAIL - Could not find _rollback_fixes definition\n")
        return False
    
    fixes_str = match.group(1)
    
    # Check for invalid entries
    invalid_entries = [
        "connection_pool_exhausted",
        "cert_expired", 
        "rate_limit_exceeded",
        "slow_query",
        "clock_skew",
        "disk_full"
    ]
    
    found_invalid = [entry for entry in invalid_entries if entry in fixes_str]
    
    # Check for required entries
    required_entries = ["bad_deployment", "canary_misconfiguration"]
    found_required = [entry for entry in required_entries if entry in fixes_str]
    
    print(f"  Required entries found: {found_required}")
    print(f"  Invalid entries found: {found_invalid or 'None'}")
    
    if len(found_required) == 2 and len(found_invalid) == 0:
        print("  [OK] PASS - rollback_fixes correctly contains only deployment faults\n")
        return True
    else:
        print("  [X] FAIL - rollback_fixes list is incorrect\n")
        return False


def test_issue_c_evidence_based_rewards():
    """
    Verify that actions WITH evidence get appropriate rewards.
    """
    print("=== Issue C Verification: Evidence-Based Rewards ===")
    env = IncidentResponseEnv()
    env.reset("task_cpu_spike", seed=42)
    
    # Gather evidence
    env.step(Action(action_type="read_logs", target="auth-service"))
    env.step(Action(action_type="check_metrics", target="auth-service"))
    
    # Now restart WITH evidence - should get full reward
    obs, reward, done, info = env.step(Action(action_type="restart_service", target="auth-service"))
    
    print(f"  Restart with evidence reward: {reward.value}")
    print(f"  Reason: {reward.reason[:60]}")
    
    # With evidence, should get positive reward (0.15 from reward.py or 0.35 from env.py)
    # The key is it's NOT 0.0 like blind actions
    if reward.value > 0.05:
        print("  [OK] PASS - Evidence-based actions get positive rewards\n")
        return True
    else:
        print(f"  [X] FAIL - Expected >0.05, got {reward.value}\n")
        return False


def test_negative_reward_scaling():
    """
    Verify that negative rewards still get WORSE under time pressure.
    """
    print("=== Verify Negative Reward Scaling ===")
    env = IncidentResponseEnv()
    env.reset("task_cpu_spike", seed=42)
    
    # Early wrong action
    obs, reward_early, done, info = env.step(Action(action_type="restart_service", target="order-service"))
    early_penalty = reward_early.value
    
    # Reset and test late wrong action
    env.reset("task_cpu_spike", seed=42)
    for i in range(7):  # Get to step 8/10
        env.step(Action(action_type="check_health", target="redis-cache"))
    
    obs, reward_late, done, info = env.step(Action(action_type="restart_service", target="order-service"))
    late_penalty = reward_late.value
    
    print(f"  Early wrong restart (step 1/10): {early_penalty:.4f}")
    print(f"  Late wrong restart (step 8/10):  {late_penalty:.4f}")
    print(f"  Difference: {abs(early_penalty - late_penalty):.4f}")
    
    if late_penalty < early_penalty:  # Late penalty should be worse (more negative)
        print("  [OK] PASS - Negative rewards get worse under time pressure\n")
        return True
    else:
        print("  [X] FAIL - Late penalty should be worse than early\n")
        return False


if __name__ == "__main__":
    print("="*70)
    print("TESTING REWARD DESIGN FIXES")
    print("="*70)
    print()
    
    results = []
    results.append(("Issue A: Time Pressure", test_issue_a_time_pressure()))
    results.append(("Issue C: Blind Action", test_issue_c_blind_action_penalty()))
    results.append(("Issue C: Evidence Rewards", test_issue_c_evidence_based_rewards()))
    results.append(("Issue D: Rollback Fixes", test_issue_d_rollback_fixes_list()))
    results.append(("Negative Scaling", test_negative_reward_scaling()))
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "[OK] PASS" if passed else "[X] FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED!")
    else:
        print(f"\n[WARN] {sum(1 for r in results if not r[1])} test(s) failed")
    
    print("="*70)

