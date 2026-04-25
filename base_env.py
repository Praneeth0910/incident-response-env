"""
Base environment with core RL loop (reset, step, state, grade).
Handles episode state management, action validation, trajectory tracking.
"""

from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple

from models import Action, Observation, Reward
from services import SERVICE_REGISTRY, Service, ServiceSimulator, ServiceStatus


@dataclass
class TrajectoryStep:
    """Single step in an episode trajectory."""
    step_num: int
    observation: Observation
    action: Action
    reward: Reward
    next_observation: Observation
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_num": self.step_num,
            "observation": self.observation.model_dump() if hasattr(self.observation, 'model_dump') else dict(self.observation),
            "action": self.action.model_dump() if hasattr(self.action, 'model_dump') else dict(self.action),
            "reward": {"value": self.reward.value, "reason": self.reward.reason},
            "next_observation": self.next_observation.model_dump() if hasattr(self.next_observation, 'model_dump') else dict(self.next_observation),
            "done": self.done,
            "info": self.info,
        }


@dataclass
class EpisodeTrajectory:
    """Complete episode trajectory for training/analysis."""
    episode_id: str
    task_id: str
    seed: Optional[int]
    steps: list[TrajectoryStep] = field(default_factory=list)
    cumulative_reward: float = 0.0
    final_score: float = 0.001
    success: bool = False
    duration_seconds: float = 0.0

    def add_step(self, step: TrajectoryStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task_id": self.task_id,
            "seed": self.seed,
            "steps": [s.to_dict() for s in self.steps],
            "cumulative_reward": self.cumulative_reward,
            "final_score": self.final_score,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "num_steps": len(self.steps),
        }

    @property
    def num_steps(self) -> int:
        return len(self.steps)

    @property
    def actions_taken(self) -> list[str]:
        return [f"{s.action.action_type}({s.action.target})" for s in self.steps]


class BaseIncidentEnv(ABC):
    """
    Abstract base class for incident response environments.
    
    Manages episode state, reset/step/grade, and delegates reward computation 
    to reward module and observation generation to observation module.
    """

    def __init__(self, mode: str = "train"):
        assert mode in ("train", "bench"), f"Invalid mode: {mode}"
        self._mode = mode
        self._task: Optional[Dict[str, Any]] = None
        self._task_id: Optional[str] = None
        self._step_count: int = 0
        self._cumulative_reward: float = 0.0
        self._done: bool = False
        self._actions_taken: Set[str] = set()
        self._relevant_evidence_found: Set[str] = set()
        self._run_id: str = ""
        self._cascade_triggered: bool = False
        self._rca_declared: bool = False
        self._rca_correct: bool = False
        self._wrong_interventions: int = 0
        self._service_registry: Dict[str, Service] = {}
        self._service_simulator: Optional[ServiceSimulator] = None
        self._active_fault_services: Set[str] = set()
        self._cascade_impact: Dict[str, Any] = {}

        self._current_trajectory: Optional[EpisodeTrajectory] = None
        self._episode_steps: list[TrajectoryStep] = []

    @abstractmethod
    def _log_step(self, step_num: int, observation: Observation, action: Action, 
                  reward: Reward, done: bool) -> None:
        """Log step information per environment mode."""
        pass

    def reset(self, task_id: str = "task_cpu_spike", seed: Optional[int] = None) -> Observation:
        """Reset environment and start new episode."""
        from tasks import TASKS
        
        if task_id not in TASKS:
            raise KeyError(f"Unknown task_id '{task_id}'")

        if seed is not None:
            random.seed(seed)
        else:
            random.seed(42)

        self._task_id = task_id
        self._task = TASKS[task_id].copy()
        self._step_count = 0
        self._cumulative_reward = 0.0
        self._done = False
        self._actions_taken = set()
        self._relevant_evidence_found = set()
        self._run_id = str(uuid.uuid4())
        self._cascade_triggered = False
        self._rca_declared = False
        self._rca_correct = False
        self._wrong_interventions = 0
        self._reset_service_simulation()
        self._propagate_task_faults()

        if self._mode == "train":
            self._current_trajectory = EpisodeTrajectory(
                episode_id=str(uuid.uuid4()),
                task_id=task_id,
                seed=seed,
            )
            self._episode_steps = []

        return Observation(
            message=(
                f"Incident active. {self._task['description']} "
                f"You have {self._task['max_steps']} steps. Investigate carefully."
            ),
            step=0,
            done=False,
            alert=self._task["alert"],
            info={"run_id": self._run_id},
        )

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        """Take one step in the environment."""
        if self._done or self._task is None:
            raise RuntimeError("Episode finished. Call reset() first.")

        self._step_count += 1

        from reward import compute_step_reward
        
        observation, reward, done, info = compute_step_reward(
            action=action,
            task=self._task,
            step_count=self._step_count,
            cascade_triggered=self._cascade_triggered,
            actions_taken=self._actions_taken,
            evidence_found=self._relevant_evidence_found,
        )

        self._cumulative_reward += reward.value
        self._cumulative_reward = round(max(-1.0, min(1.0, self._cumulative_reward)), 4)
        self._done = done

        self._apply_action_to_service_state(action, observation, reward)

        # Handle cascade mechanics
        cascade_step = self._task.get("cascade_step")
        if (cascade_step is not None and not self._cascade_triggered 
                and self._step_count >= cascade_step and not done):
            self._cascade_triggered = True
            cascade_svc = self._task.get("cascade_service")
            self._trigger_cascade_service(cascade_svc)
            cascade_note = (
                f"\n[CASCADE] {cascade_svc} is now DEGRADED — "
                f"new errors propagating. Investigate urgently."
            )
            observation.message += cascade_note

        # Time pressure penalty after 50% progress
        if not done:
            progress = self._step_count / self._task["max_steps"]
            if progress > 0.5:
                if reward.value > 0:
                    scale = 0.99 - 0.4 * ((progress - 0.5) / 0.5)
                    reward.value = round(reward.value * scale, 4)
                else:
                    scale = 1.0 + 0.3 * ((progress - 0.5) / 0.5)
                    reward.value = round(reward.value * scale, 4)

            if self._step_count >= self._task["max_steps"]:
                done = True
                self._done = True
                observation.message += f"\n[SLA BREACHED] Max steps ({self._task['max_steps']}) reached.\n[END]"

        if action.action_type == "declare_rca":
            self._rca_declared = True
            declared_services = {
                svc.strip() for svc in action.target.split(",") if svc.strip()
            }
            self._rca_correct = declared_services == self._active_fault_services

        self._log_step(self._step_count, observation, action, reward, done)

        info["cumulative_reward"] = self._cumulative_reward
        info["step"] = self._step_count
        info["evidence_found"] = list(self._relevant_evidence_found)
        info["wrong_interventions"] = self._wrong_interventions

        return observation, reward, done, info

    def state(self) -> Dict[str, Any]:
        """Get ground-truth state (for debugging/analysis)."""
        if self._task is None:
            return {"status": "not_started"}
        return {
            "task_id": self._task_id,
            "current_task_name": self._task["name"],
            "difficulty": self._task["difficulty"],
            "hidden_fault_service": self._task["fault_service"],
            "hidden_fault_type": self._task["fault_type"],
            "step_count": self._step_count,
            "max_steps": self._task["max_steps"],
            "done": self._done,
            "cumulative_reward": self._cumulative_reward,
            "evidence_found": list(self._relevant_evidence_found),
            "wrong_interventions": self._wrong_interventions,
            "service_statuses": {
                name: service.status.value
                for name, service in sorted(self._service_registry.items())
            },
            "service_metrics": {
                name: service.current_metrics
                for name, service in sorted(self._service_registry.items())
                if service.current_metrics
            },
            "service_error_logs": {
                name: service.error_logs
                for name, service in sorted(self._service_registry.items())
                if service.error_logs
            },
            "cascade_impact": self._cascade_impact,
        }

    def grade(self) -> float:
        """Compute final episode score in [0.001, 0.999]."""
        if not self._done or not self._rca_declared:
            return 0.001

        if not self._rca_correct:
            evidence_credit = len(self._relevant_evidence_found) * 0.03
            return round(min(0.15, max(0.001, evidence_credit)), 4)

        raw = self._cumulative_reward
        intervention_penalty = self._wrong_interventions * 0.10
        score = raw - intervention_penalty
        normalized = (score + 1.0) / 2.0
        return round(min(0.999, max(0.001, normalized)), 4)

    def get_trajectory(self) -> Optional[EpisodeTrajectory]:
        """Get current episode trajectory (training mode only)."""
        if self._mode != "train" or not self._done:
            return None

        if self._current_trajectory is None:
            return None

        self._current_trajectory.cumulative_reward = self._cumulative_reward
        self._current_trajectory.final_score = self.grade()
        self._current_trajectory.success = self.grade() >= 0.6
        self._current_trajectory.steps = self._episode_steps

        return self._current_trajectory

    def clear_trajectory(self) -> None:
        """Clear episode trajectory (for memory management)."""
        self._episode_steps = []
        self._current_trajectory = None

    def _reset_service_simulation(self) -> None:
        """Create isolated mutable service state for this episode."""
        self._service_registry = deepcopy(SERVICE_REGISTRY)
        self._service_simulator = ServiceSimulator(self._service_registry)
        self._active_fault_services = set()
        self._cascade_impact = {}

    def _propagate_task_faults(self) -> None:
        """Initialize service graph state from the hidden task root cause(s)."""
        if self._task is None or self._service_simulator is None:
            return

        fault_specs = [(self._task.get("fault_service"), self._task.get("fault_type"))]
        if self._task.get("fault_service_2"):
            fault_specs.append((self._task.get("fault_service_2"), self._task.get("fault_type_2")))

        affected_services: Set[str] = set()
        cascade_chain: list[str] = []
        critical_services: Set[str] = set()

        for service_name, fault_type in fault_specs:
            if not service_name or service_name not in self._service_registry:
                continue

            self._active_fault_services.add(service_name)
            impact = self._service_simulator.propagate_failure(
                root_service=service_name,
                fault_type=fault_type or "dependency_failure",
            )
            affected_services.update(impact["affected_services"])
            cascade_chain.extend(impact["cascade_chain"])
            critical_services.update(impact["critical_services_affected"])

        self._cascade_impact = {
            "root_services": sorted(self._active_fault_services),
            "affected_services": sorted(affected_services),
            "affected_count": len(affected_services),
            "cascade_chain": cascade_chain,
            "critical_services_affected": sorted(critical_services),
            "critical_path_broken": bool(critical_services),
        }

    def _trigger_cascade_service(self, service_name: Optional[str]) -> None:
        """Mark a timed cascade victim in the same service graph state."""
        if not service_name or service_name not in self._service_registry:
            return

        service = self._service_registry[service_name]
        if service.status == ServiceStatus.HEALTHY:
            service.status = ServiceStatus.DEGRADED
        service.root_cause_fault = self._task.get("cascade_fault") if self._task else None

    def _apply_action_to_service_state(
        self,
        action: Action,
        observation: Observation,
        reward: Reward,
    ) -> None:
        """Keep the runtime service graph aligned with observations/actions."""
        if self._service_simulator is None:
            return

        if action.action_type == "check_metrics" and observation.metrics:
            for service_name, metrics in observation.metrics.items():
                if service_name not in self._service_registry or not isinstance(metrics, dict):
                    continue

                numeric_metrics = {
                    metric: float(value)
                    for metric, value in metrics.items()
                    if isinstance(value, (int, float))
                }
                self._service_simulator.update_metrics(service_name, numeric_metrics)

        elif action.action_type == "read_logs" and action.target in self._service_registry:
            self._service_simulator.add_error_log(action.target, observation.message)

        elif action.action_type in {"restart_service", "rollback_deployment"}:
            if action.target in self._active_fault_services and reward.value > 0:
                self._service_simulator.recover_service(action.target)
            elif reward.value < 0:
                self._wrong_interventions += 1


class TrainingEnv(BaseIncidentEnv):
    """Training-mode environment with trajectory logging."""

    def __init__(self):
        super().__init__(mode="train")

    def _log_step(self, step_num: int, observation: Observation, action: Action, 
                  reward: Reward, done: bool) -> None:
        """Log step to trajectory (training mode)."""
        if self._current_trajectory is None:
            return

        trajectory_step = TrajectoryStep(
            step_num=step_num,
            observation=observation,
            action=action,
            reward=reward,
            next_observation=observation,
            done=done,
            info=self.state(),
        )
        self._episode_steps.append(trajectory_step)


class BenchmarkEnv(BaseIncidentEnv):
    """Benchmark-mode environment with minimal logging."""

    def __init__(self):
        super().__init__(mode="bench")

    def _log_step(self, step_num: int, observation: Observation, action: Action, 
                  reward: Reward, done: bool) -> None:
        """Silent logging (benchmark mode)."""
        pass


# Backward compatibility
IncidentResponseEnv = TrainingEnv
