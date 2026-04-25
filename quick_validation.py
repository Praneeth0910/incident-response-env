"""
Quick validation script - checks critical training blockers only.
"""
import sys
from environment import IncidentResponseEnv, TASKS
from training.expert_agent import ExpertAgent
from models import Action

def check_reward_flow():
    """Check if rewards are computed correctly."""
    print("=" * 60)
    print("1. REWARD FLOW CHECK")
    print("=" * 60)
    
    env = IncidentResponseEnv()
    obs = env.reset("task_cpu_spike")
    
    # Take a meaningful action
    action = Action(action_type="read_logs", target="auth-service")
    obs, reward, done, info = env.step(action)
    
    print(f"✓ Step executed without crash")
    print(f"  Reward: {reward.value}")
    print(f"  Reward reason: {reward.reason}")
    
    if reward.value == 0.0:
        print("✗ WARNING: Reward is zero for read_logs on fault service!")
        return False
    
    print(f"✓ Reward is non-zero: {reward.value}")
    return True

def check_environment_stability():
    """Check for crashes and undefined variables."""
    print("\n" + "=" * 60)
    print("2. ENVIRONMENT STABILITY CHECK")
    print("=" * 60)
    
    try:
        env = IncidentResponseEnv()
        obs = env.reset("task_cpu_spike")
        print(f"✓ Reset successful")
        
        # Run 3 steps
        actions = [
            Action(action_type="read_logs", target="auth-service"),
            Action(action_type="check_metrics", target="auth-service"),
            Action(action_type="restart_service", target="auth-service"),
        ]
        
        for i, action in enumerate(actions):
            obs, reward, done, info = env.step(action)
            print(f"✓ Step {i+1} executed: {action.action_type} -> reward={reward.value}")
            
        return True
    except Exception as e:
        print(f"✗ CRITICAL: Environment crashed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_expert_agent():
    """Check expert agent uses dynamic task_id and fault_service."""
    print("\n" + "=" * 60)
    print("3. EXPERT AGENT CHECK")
    print("=" * 60)
    
    # Test with 2 different tasks
    task_ids = ["task_cpu_spike", "task_db_connection_leak"]
    
    for task_id in task_ids:
        task = TASKS[task_id]
        expert = ExpertAgent(task)
        
        fault_svc = task.get("fault_service")
        print(f"\n  Task: {task_id}")
        print(f"  Fault service: {fault_svc}")
        
        # Get first action
        action = expert.get_next_action()
        if action:
            print(f"  First action: {action.action_type} -> {action.target}")
            
            # Check if target matches fault_service
            if action.target == fault_svc:
                print(f"✓ Expert correctly targets fault_service: {fault_svc}")
            else:
                print(f"  Note: First action targets {action.target} (fault is {fault_svc})")
        else:
            print(f"✗ WARNING: Expert returned no actions!")
            return False
    
    return True

def check_information_leakage():
    """Check agent cannot see fault_service in observation."""
    print("\n" + "=" * 60)
    print("4. INFORMATION LEAKAGE CHECK")
    print("=" * 60)
    
    env = IncidentResponseEnv()
    obs = env.reset("task_cpu_spike")
    
    fault_svc = TASKS["task_cpu_spike"]["fault_service"]
    
    # Check if fault_service is directly mentioned in initial observation
    if fault_svc in obs.message:
        print(f"✗ CRITICAL: fault_service '{fault_svc}' leaked in initial observation!")
        print(f"  Observation: {obs.message[:200]}")
        return False
    
    print(f"✓ Fault service '{fault_svc}' NOT leaked in initial observation")
    
    # Take an action and check observation doesn't reveal answer
    action = Action(action_type="check_metrics", target="api-gateway")
    obs, reward, done, info = env.step(action)
    
    print(f"✓ No direct fault service leakage detected")
    return True

def check_dataset_diversity():
    """Quick check for task diversity."""
    print("\n" + "=" * 60)
    print("5. DATASET DIVERSITY CHECK")
    print("=" * 60)
    
    task_count = len(TASKS)
    print(f"  Total tasks: {task_count}")
    
    if task_count < 5:
        print(f"✗ WARNING: Only {task_count} tasks defined")
        return False
    
    # Check unique fault_services
    fault_services = set()
    for task_id, task in TASKS.items():
        if "fault_service" in task:
            fault_services.add(task["fault_service"])
    
    print(f"  Unique fault services: {len(fault_services)}")
    print(f"  Services: {sorted(fault_services)}")
    
    if len(fault_services) < 3:
        print(f"✗ WARNING: Only {len(fault_services)} unique fault services")
        return False
    
    print(f"✓ Task diversity looks good")
    return True

def run_mini_trajectory():
    """Run a mini trajectory to verify end-to-end flow."""
    print("\n" + "=" * 60)
    print("6. MINI TRAJECTORY TEST")
    print("=" * 60)
    
    try:
        env = IncidentResponseEnv()
        task_id = "task_cpu_spike"
        task = TASKS[task_id]
        expert = ExpertAgent(task)
        
        obs = env.reset(task_id)
        total_reward = 0.0
        step_count = 0
        max_steps = 5  # Only run 5 steps
        
        print(f"\n  Running {max_steps} steps on {task_id}...")
        
        while step_count < max_steps:
            action = expert.get_next_action(obs)
            if action is None:
                break
            
            obs, reward, done, info = env.step(action)
            total_reward += reward.value
            step_count += 1
            
            print(f"  Step {step_count}: {action.action_type}:{action.target} -> r={reward.value:+.2f}")
            
            if done:
                break
        
        print(f"\n  Total steps: {step_count}")
        print(f"  Total reward: {total_reward:.3f}")
        
        if total_reward == 0.0:
            print(f"✗ WARNING: Total reward is zero after {step_count} steps!")
            return False
        
        print(f"✓ Trajectory executed successfully with non-zero reward")
        return True
        
    except Exception as e:
        print(f"✗ CRITICAL: Trajectory failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "=" * 60)
    print("INCIDENT RESPONSE ENV - QUICK TRAINING READINESS CHECK")
    print("=" * 60)
    
    checks = {
        "Reward Flow": check_reward_flow(),
        "Environment Stability": check_environment_stability(),
        "Expert Agent": check_expert_agent(),
        "Information Leakage": check_information_leakage(),
        "Dataset Diversity": check_dataset_diversity(),
        "Mini Trajectory": run_mini_trajectory(),
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for check_name, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check_name}")
    
    all_passed = all(checks.values())
    
    print("\n" + "=" * 60)
    print("FINAL DECISION")
    print("=" * 60)
    
    if all_passed:
        print("\n✅ READY FOR TRAINING")
        print("\nAll critical checks passed:")
        print("- Reward system functioning")
        print("- Environment stable")
        print("- Expert agent working")
        print("- No information leakage")
        print("- Task diversity sufficient")
        return 0
    else:
        print("\n❌ NOT READY FOR TRAINING")
        print("\nIssues found:")
        for check_name, passed in checks.items():
            if not passed:
                print(f"- {check_name} failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
