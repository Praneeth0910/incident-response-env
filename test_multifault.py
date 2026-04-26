#!/usr/bin/env python3
"""Quick test of multi-fault task_expert handling."""

import sys
sys.path.insert(0, ".")

from environment import IncidentResponseEnv, TASKS
from training.expert_agent import ExpertAgent


def test_task_expert():
    """Test that expert agent properly handles multi-fault task."""
    task_expert = TASKS["task_expert"]
    
    print("\n=== TASK_EXPERT DEFINITION ===")
    print(f"Task name: {task_expert.get('name')}")
    print(f"Fault service 1: {task_expert.get('fault_service')} ({task_expert.get('fault_type')})")
    print(f"Fault service 2: {task_expert.get('fault_service_2')} ({task_expert.get('fault_type_2')})")
    print(f"Ideal steps: {task_expert.get('ideal_steps')}")
    print(f"Max steps: {task_expert.get('max_steps')}")
    
    # Create expert agent
    expert = ExpertAgent(task_expert)
    
    # Generate plan
    print("\n=== EXPERT PLAN ===")
    plan = expert._cicd_plan(task_expert.get("fault_type"))
    for i, action in enumerate(plan, 1):
        print(f"Step {i}: {action['action_type']} on {action['target']}")
    
    # Run episode
    print("\n=== RUNNING EPISODE ===")
    env = IncidentResponseEnv()
    obs = env.reset(task_id="task_expert")
    
    cumulative_reward = 0.0
    for step_count, action_dict in enumerate(plan, 1):
        print(f"\nStep {step_count}: {action_dict['action_type']} -> {action_dict['target']}")
        try:
            action = next((a for a in [
                {"action_type": action_dict["action_type"], "target": action_dict["target"]}
            ]), None)
            if not action:
                raise ValueError("Failed to create action")
            
            # Convert dict to Action model
            from models import Action
            action_obj = Action(**action)
            obs, reward, done, info = env.step(action_obj)
            cumulative_reward += reward.value
            print(f"  Reward: {reward.value:.4f}, Cumulative: {cumulative_reward:.4f}")
            if done:
                print(f"  Episode DONE!")
                break
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Check final score by calling grade() method
    final_grade = env.grade()
    print(f"\n=== FINAL RESULTS ===")
    print(f"Total steps: {step_count}")
    print(f"Cumulative reward: {cumulative_reward:.4f}")
    print(f"Final grade: {final_grade:.4f}")
    print(f"RCA correct: {env._rca_correct}")
    print(f"Done: {done}")
    print(f"RCA declared: {env._rca_declared}")
    
    print(f"\n=== DEBUG INFO ===")
    print(f"Full info dict: {info}")
    print(f"Cumulative reward from env: {env._cumulative_reward:.4f}")
    print(f"Wrong interventions: {env._wrong_interventions}")
    
    if final_grade >= 0.70:
        print(f"\nSUCCESS: task_expert grade {final_grade:.4f} >= 0.70")
        return True
    else:
        print(f"\nFAILURE: task_expert grade {final_grade:.4f} < 0.70")
        return False


if __name__ == "__main__":
    success = test_task_expert()
    sys.exit(0 if success else 1)
