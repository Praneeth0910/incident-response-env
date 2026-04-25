"""
Integrated Environment with Task-Service Graph Binding
======================================================

Enhanced environment that integrates task_integration.py with the base environment.

Features:
  - Dynamically loads tasks from tasks.json
  - Maps tasks to service graph automatically
  - Generates realistic metrics/logs based on service state
  - Provides rich observations with cascade information

Usage:
  from environment_integrated import IntegratedIncidentEnv
  
  env = IntegratedIncidentEnv(mode="train")
  obs = env.reset("task_cpu_spike_auth")
  obs, reward, done, info = env.step(Action(action_type="read_logs", target="auth-service"))
"""

from __future__ import annotations

import random
import uuid
from typing import Any, Dict, Optional, Set, Tuple

from models import Action, Observation, Reward
from task_integration import (
    ObservationGenerator,
    TaskDefinition,
    TaskLoader,
)
from services import get_all_dependents_recursive


class IntegratedIncidentEnv:
    """
    Incident response environment with integrated task-service binding.
    
    Extends the base environment with dynamic task loading and realistic
    service metrics simulation based on the dependency graph.
    """

    def __init__(self, mode: str = "train"):
        """
        Initialize integrated environment.

        Args:
            mode: "train" (dense logging) or "bench" (minimal logging)
        """
        self._mode = mode
        self.task_loader = TaskLoader()
        self.obs_generator = ObservationGenerator(self.task_loader)
        
        # Episode state
        self._task: Optional[TaskDefinition] = None
        self._task_id: Optional[str] = None
        self._step_count: int = 0
        self._max_steps: int = 20
        self._done: bool = False
        self._cumulative_reward: float = 0.0
        self._actions_taken: Set[str] = set()
        self._run_id: str = ""
        
        # RCA tracking
        self._rca_declared: bool = False
        self._rca_target: Optional[str] = None
        self._rca_correct: bool = False

    def reset(self, task_id: str = "task_cpu_spike_auth", seed: Optional[int] = None) -> Observation:
        """
        Reset environment and start new episode with task from JSON.

        Args:
            task_id: Task ID from tasks.json (e.g., "task_cpu_spike_auth")
            seed: Random seed for reproducibility

        Returns:
            Initial observation

        Raises:
            ValueError: If task_id not found in tasks.json
        """
        # Load task from JSON
        task = self.task_loader.get_task(task_id)
        if task is None:
            available = self.task_loader.list_tasks()
            raise ValueError(
                f"Unknown task_id '{task_id}'. Available:\n"
                f"  {', '.join(available[:5])}... and {len(available) - 5} more"
            )

        if seed is not None:
            random.seed(seed)

        # Reset state
        self._task = task
        self._task_id = task_id
        self._step_count = 0
        self._done = False
        self._cumulative_reward = 0.0
        self._actions_taken = set()
        self._run_id = str(uuid.uuid4())
        self._rca_declared = False
        self._rca_target = None
        self._rca_correct = False
        
        # Set max steps based on difficulty
        difficulty_steps = {
            "easy": 10,
            "medium": 15,
            "hard": 20,
        }
        self._max_steps = difficulty_steps.get(task.difficulty, 15)

        # Generate initial observation
        initial_obs = self.obs_generator.generate_observation(
            task,
            step=0,
            max_steps=self._max_steps,
        )

        return Observation(
            message=(
                f"🔴 INCIDENT ACTIVE\n\n"
                f"Task: {task.id} ({task.difficulty})\n"
                f"You have {self._max_steps} steps.\n\n"
                f"{initial_obs['alert']}\n\n"
                f"Affected services: {', '.join(task.affected_services)}\n"
                f"Critical path broken: {task.critical_path_broken}"
            ),
            step=0,
            done=False,
            alert=initial_obs["alert"],
            info={
                "run_id": self._run_id,
                "task_id": task_id,
                "difficulty": task.difficulty,
                "max_steps": self._max_steps,
                "affected_services": task.affected_services,
                "cascade_targets": list(task.cascade_targets),
                "critical_path_broken": task.critical_path_broken,
            },
        )

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        """
        Take one step in the environment.

        Args:
            action: Action to take (read_logs, check_metrics, check_health, run_db_query, restart_service, rollback_deployment, declare_rca)

        Returns:
            (observation, reward, done, info)
        """
        if self._done or self._task is None:
            raise RuntimeError("Episode finished or not reset. Call reset() first.")

        self._step_count += 1
        task = self._task

        # Compute reward and observation based on action
        observation, reward, done, info = self._compute_step(action)

        # Update state
        self._cumulative_reward += reward.value
        self._cumulative_reward = round(max(-1.0, min(1.0, self._cumulative_reward)), 4)
        self._done = done

        # Check if episode ended due to max steps
        if self._step_count >= self._max_steps and not self._rca_declared:
            done = True
            self._done = True
            reward.reason = "Max steps reached without declaring RCA"

        info["cumulative_reward"] = self._cumulative_reward
        info["step"] = self._step_count
        info["max_steps"] = self._max_steps

        return observation, reward, done, info

    def _compute_step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict]:
        """Compute reward and observation for action."""
        task = self._task
        action_key = f"{action.action_type}:{action.target}"

        # Check for redundant action
        if action_key in self._actions_taken and action.action_type != "declare_rca":
            reward = Reward(
                value=-0.08,
                reason=f"Redundant action — already checked {action.target}",
            )
            message = f"⚠️  Already checked {action.target} with {action.action_type}"
            observation = self._make_observation(message)
            return observation, reward, False, {}

        self._actions_taken.add(action_key)

        # Route to action handler
        if action.action_type == "read_logs":
            return self._handle_read_logs(action, task)
        elif action.action_type == "check_metrics":
            return self._handle_check_metrics(action, task)
        elif action.action_type == "check_health":
            return self._handle_check_health(action, task)
        elif action.action_type == "run_db_query":
            return self._handle_run_db_query(action, task)
        elif action.action_type == "restart_service":
            return self._handle_restart_service(action, task)
        elif action.action_type == "rollback_deployment":
            return self._handle_rollback_deployment(action, task)
        elif action.action_type == "declare_rca":
            return self._handle_declare_rca(action, task)
        else:
            reward = Reward(value=-0.05, reason="Unknown action type")
            observation = self._make_observation("Unknown action")
            return observation, reward, False, {}

    def _handle_read_logs(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle read_logs action."""
        logs = self.obs_generator.generate_logs_for_service(
            action.target, task, self._step_count
        )
        message = f"Logs from {action.target}:\n{logs}"
        
        # Reward based on relevance
        if action.target in task.affected_services:
            reward = Reward(
                value=0.15,
                reason=f"Strong evidence in {action.target} logs — root cause service"
            )
        elif action.target in task.red_herrings:
            reward = Reward(
                value=-0.05,
                reason=f"{action.target} is a red herring — not the root cause"
            )
        else:
            reward = Reward(
                value=-0.02,
                reason=f"No relevant signal in {action.target} logs"
            )

        observation = self._make_observation(message)
        return observation, reward, False, {}

    def _handle_check_metrics(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle check_metrics action."""
        metrics = self.obs_generator.generate_metrics_for_service(
            action.target, task, self._step_count, self._max_steps
        )
        message = f"Metrics for {action.target}:\n"
        message += "\n".join(f"  {k}: {v}" for k, v in metrics.items())

        # Reward based on relevance
        if action.target in task.affected_services:
            reward = Reward(
                value=0.12,
                reason=f"Fault service metrics show anomaly"
            )
        elif action.target in task.red_herrings:
            reward = Reward(
                value=-0.05,
                reason=f"{action.target} looks suspicious but is a red herring"
            )
        else:
            reward = Reward(
                value=-0.03,
                reason=f"{action.target} metrics appear normal"
            )

        observation = self._make_observation(message)
        return observation, reward, False, {}

    def _handle_check_health(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle check_health action."""
        if action.target in task.affected_services:
            status = "DEGRADED" if random.random() > 0.3 else "DOWN"
            reward = Reward(
                value=0.10,
                reason=f"Found {status} service — clear signal"
            )
        else:
            status = "UP"
            reward = Reward(
                value=-0.02,
                reason=f"{action.target} appears healthy — not the fault"
            )

        message = f"Health check {action.target}: {status}"
        observation = self._make_observation(message)
        return observation, reward, False, {}

    def _handle_run_db_query(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle run_db_query action."""
        message = (
            f"DB query result from {action.target}:\n"
            f"Query executed successfully\n"
            f"Rows returned: 1000\n"
        )

        if "postgres" in action.target.lower() and "db" in action.target.lower():
            if any("database" in s.lower() or "postgres" in s.lower() for s in task.affected_services):
                reward = Reward(
                    value=0.18,
                    reason="DB query confirms root cause — highest-value evidence"
                )
            else:
                reward = Reward(
                    value=-0.05,
                    reason="DB query ran but this fault is not database-related"
                )
        else:
            reward = Reward(
                value=-0.05,
                reason="DB query only works on database services"
            )

        observation = self._make_observation(message)
        return observation, reward, False, {}

    def _handle_restart_service(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle restart_service action."""
        restart_fixes = {"cpu_spike", "oom_crash", "memory_leak", "crash_loop"}

        # Check if restart is appropriate for this fault
        if action.target in task.affected_services:
            # Extract fault type from root cause
            fault_type_match = None
            for keyword in restart_fixes:
                if keyword in task.root_cause.lower():
                    fault_type_match = keyword
                    break

            if fault_type_match:
                reward = Reward(
                    value=0.35,
                    reason=f"Correct service restarted — {fault_type_match} resolved"
                )
                message = f"✓ {action.target} restarted successfully\nError rate dropping"
                done = True
            else:
                reward = Reward(
                    value=-0.10,
                    reason="Restarted service but wrong fix type for this fault"
                )
                message = f"✗ {action.target} restarted but issue persists"
                done = False
        else:
            reward = Reward(
                value=-0.12,
                reason=f"Restarted {action.target} but it's not the fault service"
            )
            message = f"✗ {action.target} is not the root cause"
            done = False

        observation = self._make_observation(message)
        return observation, reward, done, {}

    def _handle_rollback_deployment(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle rollback_deployment action."""
        rollback_fixes = {
            "bad_deployment", "canary_poison", "cert_expired",
            "cert_rotation", "config_drift"
        }

        if action.target in task.affected_services:
            fault_type_match = None
            for keyword in rollback_fixes:
                if keyword in task.root_cause.lower():
                    fault_type_match = keyword
                    break

            if fault_type_match:
                reward = Reward(
                    value=0.35,
                    reason=f"Correct rollback — {fault_type_match} resolved"
                )
                message = f"✓ {action.target} rolled back to previous version\nRecovering"
                done = True
            else:
                reward = Reward(
                    value=-0.10,
                    reason="Rolled back but wrong fix type for this fault"
                )
                message = f"✗ {action.target} rolled back but issue persists"
                done = False
        else:
            reward = Reward(
                value=-0.12,
                reason=f"Rolled back {action.target} but it's not the root cause"
            )
            message = f"✗ {action.target} is not the root cause"
            done = False

        observation = self._make_observation(message)
        return observation, reward, done, {}

    def _handle_declare_rca(
        self, action: Action, task: TaskDefinition
    ) -> Tuple[Observation, Reward, bool, Dict]:
        """Handle declare_rca action."""
        self._rca_declared = True
        self._rca_target = action.target

        # Check if RCA is correct
        is_correct = action.target in task.affected_services
        self._rca_correct = is_correct

        if is_correct:
            reward = Reward(
                value=0.25,
                reason=f"Correct RCA declared: {action.target} is root cause"
            )
            message = (
                f"✓ CORRECT RCA\n"
                f"Root cause: {action.target}\n"
                f"Actual fault: {task.root_cause}\n\n"
                f"Resolution steps needed:\n"
                + "\n".join(f"  - {step}" for step in task.resolution_steps[:3])
            )
            done = True
            final_score = self._compute_final_score(True)
        else:
            reward = Reward(
                value=-0.30,
                reason=f"Incorrect RCA declared: {action.target} is not the root cause"
            )
            message = (
                f"✗ INCORRECT RCA\n"
                f"You declared: {action.target}\n"
                f"Actual root cause: {', '.join(task.affected_services)}\n"
                f"Actual fault: {task.root_cause}"
            )
            done = True
            final_score = self._compute_final_score(False)

        observation = self._make_observation(message)
        return observation, reward, done, {"final_score": final_score}

    def _make_observation(self, message: str) -> Observation:
        """Create observation object."""
        return Observation(
            message=message,
            step=self._step_count,
            done=self._done,
            alert=self._task.alert_message if self._task else "",
            info={
                "task_id": self._task_id,
                "steps_used": self._step_count,
                "steps_remaining": self._max_steps - self._step_count,
            },
        )

    def _compute_final_score(self, rca_correct: bool) -> float:
        """Compute final episode score."""
        if not rca_correct:
            return 0.001
        
        # Score based on steps used
        steps_ratio = self._step_count / self._max_steps
        base_score = max(0.6, 1.0 - (steps_ratio * 0.3))
        
        # Bonus for efficiency on easy tasks
        if self._task.difficulty == "easy" and self._step_count <= 3:
            base_score = min(0.999, base_score * 1.2)
        
        return round(min(0.999, base_score), 3)

    def grade(self) -> float:
        """Get final episode grade."""
        if not self._rca_correct:
            return 0.001
        return self._compute_final_score(True)


# ── Example Usage ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Testing IntegratedIncidentEnv\n")
    
    # Create environment
    env = IntegratedIncidentEnv(mode="train")
    
    # Reset with first task
    obs = env.reset("task_cpu_spike_auth", seed=42)
    print(f"Initial observation:\n{obs.message}\n")
    
    # Take some actions
    print("Taking actions...")
    print("-" * 60)
    
    actions = [
        Action(action_type="check_metrics", target="auth-service"),
        Action(action_type="read_logs", target="auth-service"),
        Action(action_type="restart_service", target="auth-service"),
    ]
    
    for action in actions:
        obs, reward, done, info = env.step(action)
        print(f"Action: {action.action_type}({action.target})")
        print(f"Reward: {reward.value:+.2f} — {reward.reason}")
        print(f"Done: {done}")
        print()
        
        if done:
            break
    
    print(f"\nFinal score: {env.grade():.3f}")
