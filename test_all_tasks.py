#!/usr/bin/env python3
"""Test all tasks including task_expert to verify grades."""

import sys
sys.path.insert(0, ".")

from environment import IncidentResponseEnv, TASKS
from training.expert_agent import ExpertAgent


def test_all_tasks():
    """Run expert agent on all tasks and report grades."""
    print("\n" + "="*80)
    print("TESTING ALL TASKS WITH EXPERT AGENT")
    print("="*80)
    
    results = []
    for task_id in TASKS.keys():
        task = TASKS[task_id]
        env = IncidentResponseEnv()
        obs = env.reset(task_id=task_id)
        
        # Create expert agent and get plan
        expert = ExpertAgent(task)
        domain = task.get("domain", "cicd")
        
        if domain == "cicd":
            plan = expert._cicd_plan(task.get("fault_type"))
        elif domain == "kafka":
            plan = expert._kafka_plan(task.get("fault_type"))
        else:
            print(f"SKIP: {task_id} (unknown domain: {domain})")
            continue
        
        # Execute plan
        done = False
        for action_dict in plan:
            if done:
                break
            from models import Action
            action_obj = Action(**action_dict)
            obs, reward, done, info = env.step(action_obj)
        
        # Get final grade
        grade = env.grade()
        rca_correct = env._rca_correct
        steps = env._step_count
        
        # Determine pass/fail
        threshold = 0.70
        status = "PASS" if grade >= threshold else "FAIL"
        
        results.append({
            "task_id": task_id,
            "grade": grade,
            "rca_correct": rca_correct,
            "steps": steps,
            "status": status
        })
        
        # Print result
        marker = "PASS" if grade >= threshold else "FAIL"
        print(f"[{marker}] {task_id:30s} grade={grade:.4f} rca_correct={rca_correct} steps={steps}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    
    print(f"Total tasks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print("\nFailed tasks:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  - {r['task_id']}: grade={r['grade']:.4f}")
        return False
    
    print("\nALL TASKS PASSED!")
    return True


if __name__ == "__main__":
    success = test_all_tasks()
    sys.exit(0 if success else 1)
