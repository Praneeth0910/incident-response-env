"""
Integration Test Suite — Task-Service Graph Binding
===================================================

Comprehensive tests demonstrating task-service integration:
  1. Task loading and enrichment
  2. Observation generation with service metrics
  3. Cascade simulation
  4. Red herring detection
  5. End-to-end episode runs

Run: python test_task_integration.py
"""

import sys
import pytest
from environment_integrated import IntegratedIncidentEnv
from models import Action
from task_integration import TaskLoader, ObservationGenerator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@pytest.fixture
def loader():
    """Shared task loader for pytest collection."""
    return TaskLoader()


def _load_and_print_tasks():
    print("\n" + "=" * 70)
    print("TEST 1: Task Loading")
    print("=" * 70)

    loader = TaskLoader()
    print(f"✓ Loaded {len(loader.tasks)} tasks from tasks.json")

    # Test filtering
    easy = loader.list_tasks_by_difficulty("easy")
    medium = loader.list_tasks_by_difficulty("medium")
    hard = loader.list_tasks_by_difficulty("hard")

    print(f"  - Easy: {len(easy)} tasks")
    print(f"  - Medium: {len(medium)} tasks")
    print(f"  - Hard: {len(hard)} tasks")

    # Test domains
    domains = set(task.domain for task in loader.tasks.values())
    print(f"  - Domains: {', '.join(sorted(domains))}")

    return loader


def test_task_loading():
    """Test loading tasks from JSON."""
    loader = _load_and_print_tasks()
    assert loader.tasks


def test_observation_generation(loader):
    """Test dynamic observation generation."""
    print("\n" + "=" * 70)
    print("TEST 2: Observation Generation")
    print("=" * 70)

    gen = ObservationGenerator(loader)

    # Sample from each difficulty
    for difficulty in ["easy", "medium", "hard"]:
        tasks = loader.list_tasks_by_difficulty(difficulty)
        if tasks:
            task = loader.get_task(tasks[0])
            obs = gen.generate_observation(task, step=0, max_steps=15)

            print(f"\n{difficulty.upper()} Task: {task.id}")
            print(f"  Alert: {obs['alert'][:80]}...")
            print(f"  Affected: {', '.join(obs['affected_services'])}")
            print(f"  Red herrings: {', '.join(obs['red_herrings']) if obs['red_herrings'] else 'None'}")
            print(f"  Monitored services: {list(obs['service_metrics'].keys())}")

            # Show sample metrics
            for svc in list(obs['service_metrics'].keys())[:2]:
                metrics = obs['service_metrics'][svc]
                print(f"    {svc}:")
                print(f"      latency: {metrics.get('latency_p99_ms', 'N/A')}ms")
                print(f"      error_rate: {metrics.get('error_rate', 'N/A')}")
                print(f"      cpu: {metrics.get('cpu_pct', 'N/A')}%")


def test_cascade_detection(loader):
    """Test cascade target detection."""
    print("\n" + "=" * 70)
    print("TEST 3: Cascade Propagation")
    print("=" * 70)

    # Find a task with cascades
    for task_id, task in loader.tasks.items():
        if len(task.cascade_targets) > 0:
            print(f"\nTask: {task_id}")
            print(f"  Root cause: {task.root_cause[:80]}...")
            print(f"  Affected services: {task.affected_services}")
            print(f"  Cascade targets: {len(task.cascade_targets)} services")
            if len(task.cascade_targets) <= 10:
                print(f"    {', '.join(task.cascade_targets)}")
            else:
                targets = list(task.cascade_targets)
                print(f"    {', '.join(targets[:5])}... and {len(targets) - 5} more")
            break


def test_red_herrings(loader):
    """Test red herring detection."""
    print("\n" + "=" * 70)
    print("TEST 4: Red Herring Detection")
    print("=" * 70)

    # Find tasks with red herrings
    herring_tasks = [
        task for task in loader.tasks.values()
        if len(task.red_herrings) > 0
    ]

    print(f"Found {len(herring_tasks)} tasks with red herrings")

    for task in herring_tasks[:3]:
        print(f"\nTask: {task.id}")
        print(f"  Actual fault: {task.root_cause[:60]}...")
        print(f"  Root cause service: {task.affected_services}")
        print(f"  Red herring service: {task.red_herrings}")
        print(f"  Why it's a red herring:")
        if task.id in ["task_cascade_db_medium"]:
            print(f"    order-service shows high CPU (retrying slow DB queries)")
        elif task.id in ["task_memory_leak_medium"]:
            print(f"    api-gateway shows 504s (victim of cascading GC pauses)")
        else:
            print(f"    Shows elevated metrics but is not the root cause")


def test_environment_episode():
    """Test end-to-end environment episode."""
    print("\n" + "=" * 70)
    print("TEST 5: End-to-End Episode")
    print("=" * 70)

    env = IntegratedIncidentEnv(mode="train")

    # Run episode
    task_id = "task_cpu_spike_auth"
    print(f"\nRunning episode: {task_id}")

    obs = env.reset(task_id, seed=42)
    print(f"  Initial alert: {obs.alert[:70]}...")

    steps_data = []
    cumulative = 0.0

    actions = [
        Action(action_type="check_metrics", target="auth-service"),
        Action(action_type="read_logs", target="auth-service"),
        Action(action_type="restart_service", target="auth-service"),
    ]

    for action in actions:
        obs, reward, done, info = env.step(action)
        cumulative += reward.value
        steps_data.append({
            "action": f"{action.action_type}({action.target})",
            "reward": reward.value,
            "reason": reward.reason[:50],
            "done": done,
            "cumulative": round(cumulative, 3),
        })

        step_num = info.get('step', 0)
        max_steps = info.get('max_steps', 15)
        print(f"\n  Step {step_num}/{max_steps}:")
        print(f"    Action: {action.action_type}({action.target})")
        print(f"    Reward: {reward.value:+.3f} ({reward.reason[:40]}...)")
        print(f"    Cumulative: {cumulative:+.3f}")

        if done:
            print(f"\n  Episode ended: {done}")
            print(f"  Final score: {env.grade():.3f}")
            break


def test_medium_cascade_task():
    """Test a medium task with cascading failure."""
    print("\n" + "=" * 70)
    print("TEST 6: Cascade Investigation (Medium Task)")
    print("=" * 70)

    env = IntegratedIncidentEnv(mode="train")
    loader = TaskLoader()

    # Find a cascade task
    cascade_tasks = [
        t for t in loader.list_tasks_by_difficulty("medium")
        if loader.get_task(t).cascade_targets
    ]

    if cascade_tasks:
        task_id = cascade_tasks[0]
        print(f"\nTask: {task_id}")

        obs = env.reset(task_id, seed=42)
        task = loader.get_task(task_id)

        print(f"  Difficulty: {task.difficulty}")
        print(f"  Root cause: {task.affected_services}")
        print(f"  Red herrings: {task.red_herrings if task.red_herrings else 'None'}")
        print(f"  Cascade targets: {len(task.cascade_targets)} services")

        # Strategy: Check root cause, then red herring, then declare RCA
        print("\n  Investigation sequence:")

        # Check root cause
        root_cause = task.affected_services[0]
        obs, reward, done, info = env.step(
            Action(action_type="check_metrics", target=root_cause)
        )
        print(f"    1. Check {root_cause}: {reward.value:+.3f}")

        # Check red herring (if exists)
        if task.red_herrings:
            red_herring = task.red_herrings[0]
            obs, reward, done, info = env.step(
                Action(action_type="check_metrics", target=red_herring)
            )
            print(f"    2. Check {red_herring} (red herring): {reward.value:+.3f}")

        # Check logs from root cause
        obs, reward, done, info = env.step(
            Action(action_type="read_logs", target=root_cause)
        )
        print(f"    3. Read logs from {root_cause}: {reward.value:+.3f}")

        # Declare RCA
        obs, reward, done, info = env.step(
            Action(action_type="declare_rca", target=root_cause)
        )
        print(f"    4. Declare RCA: {reward.value:+.3f}")
        print(f"\n  Final score: {env.grade():.3f}")


def test_hard_multi_fault():
    """Test a hard task with multiple root causes."""
    print("\n" + "=" * 70)
    print("TEST 7: Multi-Fault Hard Task")
    print("=" * 70)

    loader = TaskLoader()
    env = IntegratedIncidentEnv(mode="train")

    # Find tasks with multiple affected services
    multi_fault_tasks = [
        t for t in loader.list_tasks_by_difficulty("hard")
        if len(loader.get_task(t).affected_services) > 1
    ]

    if multi_fault_tasks:
        task_id = multi_fault_tasks[0]
        task = loader.get_task(task_id)

        print(f"\nTask: {task_id}")
        print(f"  Root causes (multiple): {', '.join(task.affected_services)}")
        print(f"  Red herrings: {', '.join(task.red_herrings) if task.red_herrings else 'None'}")

        obs = env.reset(task_id, seed=42)
        print(f"  Alert: {obs.alert[:80]}...")

        # Investigate each affected service
        print("\n  Investigation:")
        for affected_svc in task.affected_services:
            obs, reward, done, info = env.step(
                Action(action_type="check_metrics", target=affected_svc)
            )
            print(f"    {affected_svc}: {reward.value:+.3f}")

        # Declare RCA for first affected service
        rca_target = task.affected_services[0]
        obs, reward, done, info = env.step(
            Action(action_type="declare_rca", target=rca_target)
        )
        print(f"\n  RCA declared: {rca_target}")
        print(f"  Correct: {reward.value > 0}")
        print(f"  Score: {env.grade():.3f}")


def main():
    """Run all integration tests."""
    print("\n" + "#" * 70)
    print("# INTEGRATION TEST SUITE")
    print("# Task-Service Graph Binding")
    print("#" * 70)

    try:
        loader = _load_and_print_tasks()
        test_observation_generation(loader)
        test_cascade_detection(loader)
        test_red_herrings(loader)
        test_environment_episode()
        test_medium_cascade_task()
        test_hard_multi_fault()

        print("\n" + "#" * 70)
        print("# ALL TESTS PASSED ✓")
        print("#" * 70)
        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
