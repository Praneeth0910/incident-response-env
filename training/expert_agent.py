"""
training/expert_agent.py

Rule-based expert agent that follows the optimal investigation path per domain.
Used to generate high-quality SFT training data before RL.
Target: >0.80 episode score on all 20 tasks.
"""

from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from models import Action


@dataclass
class EpisodeTrajectory:
    """Records a complete expert episode."""
    task_id: str
    domain: str
    steps: list[dict]
    total_reward: float
    final_score: float
    rca_correct: bool


class ExpertAgent:
    """
    Knows the fault_type and follows the domain-specific optimal path.
    Never repeats an action. Never fixes before collecting >=3 evidence signals.
    """

    def __init__(self, task: dict):
        self.task = task
        self.domain = task.get("domain", "cicd")
        self.fault_type = task.get("fault_type", "cpu_spike")
        self._step = 0
        self._actions_taken: list[str] = []
        self._plan: list[dict] = self._build_plan()

    def _build_plan(self) -> list[dict]:
        """
        Construct the optimal action sequence for this task.
        Each step is {"action_type": str, "target": str}.
        """
        fault = self.fault_type
        domain = self.domain

        if domain == "cicd":
            return self._cicd_plan(fault)
        return self._kafka_plan(fault)

    def _cicd_plan(self, fault: str) -> list[dict]:
        """Optimal investigation path for CI/CD faults. Handles both single and multi-fault scenarios."""
        svc = self.task.get("fault_service")
        svc2 = self.task.get("fault_service_2")
        fault_type_2 = self.task.get("fault_type_2")
        if not svc:
            raise ValueError(f"Task {self.task.get('name', 'UNKNOWN')} missing required 'fault_service' field")
        
        # Start with observation actions
        base = [
            {"action_type": "read_logs",      "target": svc},
            {"action_type": "check_metrics",  "target": svc},
            {"action_type": "check_health",   "target": svc},
        ]
        
        # Fault-specific evidence gathering (shared between both services if multi-fault)
        fault_evidence = {
            "cpu_spike": [
                {"action_type": "check_health", "target": None},
            ],
            "secret_rotation_break": [
                {"action_type": "read_logs", "target": None},
                {"action_type": "run_db_query", "target": "postgres-db"},
            ],
            "connection_pool_exhausted": [
                {"action_type": "run_db_query", "target": "postgres-db"},
                {"action_type": "read_logs", "target": None},
            ],
            "memory_leak": [
                {"action_type": "check_metrics", "target": None},
                {"action_type": "read_logs", "target": None},
            ],
            "thread_pool_exhausted": [
                {"action_type": "check_metrics", "target": None},
                {"action_type": "check_health", "target": None},
            ],
            "canary_misconfiguration": [
                {"action_type": "check_metrics", "target": None},
                {"action_type": "read_logs", "target": None},
            ],
            "clock_skew": [
                {"action_type": "read_logs", "target": None},
                {"action_type": "check_metrics", "target": None},
            ],
            "disk_full": [
                {"action_type": "run_db_query", "target": "postgres-db"},
                {"action_type": "read_logs", "target": None},
            ],
            "deadlock": [
                {"action_type": "run_db_query", "target": "postgres-db"},
            ],
            "cert_expired": [
                {"action_type": "check_health", "target": None},
            ],
            "slow_query": [
                {"action_type": "run_db_query", "target": "postgres-db"},
            ],
            "null_pointer": [
                {"action_type": "read_logs", "target": None},
            ],
            "crash_loop": [
                {"action_type": "check_health", "target": None},
            ],
            "rate_limit_exceeded": [
                {"action_type": "check_metrics", "target": None},
            ],
            "bad_deployment": [
                {"action_type": "check_health", "target": None},
                {"action_type": "read_logs", "target": None},
            ],
            "memory_eviction": [
                {"action_type": "check_metrics", "target": svc},
                {"action_type": "read_logs", "target": svc},
            ],
        }
        
        # Fixes per fault type (target will be filled in dynamically)
        fixes = {
            "cpu_spike": [
                {"action_type": "restart_service", "target": None},
            ],
            "secret_rotation_break": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "connection_pool_exhausted": [
                {"action_type": "restart_service", "target": None},
            ],
            "memory_leak": [
                {"action_type": "restart_service", "target": None},
            ],
            "thread_pool_exhausted": [
                {"action_type": "restart_service", "target": None},
            ],
            "canary_misconfiguration": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "clock_skew": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "disk_full": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "deadlock": [
                {"action_type": "restart_service", "target": None},
            ],
            "cert_expired": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "slow_query": [
                {"action_type": "restart_service", "target": None},
            ],
            "null_pointer": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "crash_loop": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "rate_limit_exceeded": [
                {"action_type": "restart_service", "target": None},
            ],
            "bad_deployment": [
                {"action_type": "rollback_deployment", "target": None},
            ],
            "memory_eviction": [
                {"action_type": "restart_service", "target": svc},
            ],
        }
        
        plan = []
        
        # Multi-fault scenario: simplified investigation to avoid redundancy penalties
        if svc2 and fault_type_2:
            # First fault: base investigation only + fix
            plan.extend([
                {"action_type": "read_logs",      "target": svc},
                {"action_type": "check_metrics",  "target": svc},
                {"action_type": "check_health",   "target": svc},
            ])
            fixes1 = [{"action_type": act["action_type"], "target": svc if act["target"] is None else act["target"]} 
                      for act in fixes.get(fault, [])]
            plan.extend(fixes1)
            
            # Second fault: base investigation only + fix
            plan.extend([
                {"action_type": "read_logs",      "target": svc2},
                {"action_type": "check_metrics",  "target": svc2},
                {"action_type": "check_health",   "target": svc2},
            ])
            fixes2 = [{"action_type": act["action_type"], "target": svc2 if act["target"] is None else act["target"]} 
                      for act in fixes.get(fault_type_2, [])]
            plan.extend(fixes2)
            
            # Declare RCA with both services (comma-separated)
            fault_components = f"{svc},{svc2}"
            debug_msg = f"Multi-fault scenario: investigating {svc} ({fault}) and {svc2} ({fault_type_2})"
        else:
            # Single-fault scenario: full investigation with fault-specific evidence
            base1 = [
                {"action_type": "read_logs",      "target": svc},
                {"action_type": "check_metrics",  "target": svc},
                {"action_type": "check_health",   "target": svc},
            ]
            evidence1 = [{"action_type": act["action_type"], "target": svc if act["target"] is None else act["target"]} 
                         for act in fault_evidence.get(fault, [])]
            fixes1 = [{"action_type": act["action_type"], "target": svc if act["target"] is None else act["target"]} 
                      for act in fixes.get(fault, [])]
            
            plan.extend(base1 + evidence1 + fixes1)
            fault_components = svc
            debug_msg = f"Single-fault scenario: investigating {svc} ({fault})"
        
        plan.append({"action_type": "declare_rca", "target": fault_components})
        return plan

    def _kafka_plan(self, fault: str) -> list[dict]:
        """Optimal investigation path for Kafka faults."""
        base = [
            {"action_type": "check_metrics", "target": "kafka-broker"},
            {"action_type": "read_logs", "target": "kafka-broker"},
        ]
        random.shuffle(base)
        
        fault_evidence = {
            "partition_corrupt": [
                {"action_type": "read_logs", "target": "kafka-broker"},
                {"action_type": "check_metrics", "target": "kafka-broker"},
            ],
            "zombie_consumer": [
                {"action_type": "read_logs", "target": "kafka-consumer"},
                {"action_type": "check_metrics", "target": "kafka-consumer"},
            ],
            "broker_oom_cascade": [
                {"action_type": "check_metrics", "target": "kafka-broker"},
                {"action_type": "read_logs", "target": "kafka-broker"},
            ],
            "isr_churn": [
                {"action_type": "read_logs", "target": "kafka-broker"},
                {"action_type": "check_metrics", "target": "kafka-broker"},
            ],
            "rebalance_storm": [
                {"action_type": "read_logs", "target": "kafka-consumer"},
                {"action_type": "check_metrics", "target": "kafka-consumer"},
            ],
            "schema_desync": [
                {"action_type": "read_logs", "target": "kafka-consumer"},
                {"action_type": "check_metrics", "target": "kafka-consumer"},
            ],
            "retry_amplification": [
                {"action_type": "check_metrics", "target": "kafka-broker"},
                {"action_type": "read_logs", "target": "kafka-broker"},
            ],
        }
        
        fixes = {
            "partition_corrupt": [
                {"action_type": "restart_service", "target": "kafka-consumer"},
            ],
            "zombie_consumer": [
                {"action_type": "restart_service", "target": "kafka-consumer"},
            ],
            "broker_oom_cascade": [
                {"action_type": "restart_service", "target": "kafka-broker"},
            ],
            "isr_churn": [
                {"action_type": "restart_service", "target": "kafka-broker"},
            ],
            "rebalance_storm": [
                {"action_type": "restart_service", "target": "kafka-consumer"},
            ],
            "schema_desync": [
                {"action_type": "rollback_deployment", "target": "kafka-consumer"},
            ],
            "retry_amplification": [
                {"action_type": "restart_service", "target": "kafka-broker"},
            ],
        }
        
        fault_component = self.task.get("fault_component", "kafka-broker")
        plan = base + fault_evidence.get(fault, []) + fixes.get(fault, [])
        plan.append({"action_type": "declare_rca", "target": fault_component})
        return plan

    def get_next_action(self, observation: dict | str = "", history: Optional[list] = None) -> Optional[Action]:
        """
        Get next action from the plan.
        Skips if action was already taken.
        """
        if history is None:
            history = []
        
        while self._step < len(self._plan):
            step = self._plan[self._step]
            action_key = f"{step['action_type']}:{step['target']}"
            self._step += 1
            
            if action_key not in self._actions_taken:
                self._actions_taken.append(action_key)
                return Action(action_type=step["action_type"], target=step["target"])
        
        return None  # episode complete

    def run_episode(self, env, task_id: str = "task_cpu_spike", seed: Optional[int] = None) -> EpisodeTrajectory:
        """
        Run a full episode with the expert agent.
        Returns a trajectory object.
        """
        # Reset environment with this task
        obs = env.reset(task_id, seed=seed)
        history = []
        total_reward = 0.0
        
        # Main loop
        while True:
            action = self.get_next_action(str(obs), history)
            if action is None:
                break
            
            obs, reward, done, info = env.step(action)
            
            record = {
                "step": len(history) + 1,
                "action": f"{action.action_type}:{action.target}",
                "reward": reward.value,
                "observation": str(obs.message)[:200] if obs else "",
                "judge_score": info.get("judge_score"),
                "judge_feedback": info.get("judge_feedback"),
            }
            history.append(record)
            total_reward += reward.value
            
            if done:
                break
        
        # Compute final grade
        final_score = env.grade()
        
        # Check if RCA was correct
        rca_correct = env._rca_correct if hasattr(env, "_rca_correct") else False
        
        return EpisodeTrajectory(
            task_id=task_id,
            domain=self.domain,
            steps=history,
            total_reward=total_reward,
            final_score=final_score,
            rca_correct=rca_correct,
        )


def run_expert_on_all_tasks(env, tasks: Dict[str, dict]) -> List[EpisodeTrajectory]:
    """
    Run expert agent on all tasks and return trajectories.
    Used for SFT dataset generation.
    """
    trajectories = []
    for task_id, task in tasks.items():
        try:
            expert = ExpertAgent(task)
            traj = expert.run_episode(env, task_id)
            trajectories.append(traj)
            print(f"{task_id}: score={traj.final_score:.3f} reward={traj.total_reward:.3f} rca={traj.rca_correct}")
        except Exception as e:
            print(f"{task_id}: FAILED - {e}")
    
    return trajectories
