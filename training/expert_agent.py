"""
training/expert_agent.py

Rule-based expert agent that follows the optimal investigation path per domain.
Used to generate high-quality SFT training data before RL.
Target: >0.80 episode score on all 20 tasks.
"""

from __future__ import annotations
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
        """Optimal investigation path for CI/CD faults."""
        # Start with observation actions
        base = [
            {"action_type": "read_logs",      "target": "auth-service"},
            {"action_type": "check_metrics",  "target": "auth-service"},
            {"action_type": "check_health",   "target": "auth-service"},
        ]
        
        # Fault-specific evidence gathering
        fault_evidence = {
            "cpu_spike": [
                {"action_type": "check_health", "target": "auth-service"},
            ],
            "secret_rotation_break": [
                {"action_type": "read_logs", "target": "order-service"},
                {"action_type": "run_db_query", "target": "postgres-db"},
            ],
            "connection_pool_exhausted": [
                {"action_type": "run_db_query", "target": "postgres-db"},
                {"action_type": "read_logs", "target": "order-service"},
            ],
            "memory_leak": [
                {"action_type": "check_metrics", "target": "notification-service"},
                {"action_type": "read_logs", "target": "notification-service"},
            ],
            "thread_pool_exhausted": [
                {"action_type": "check_metrics", "target": "auth-service"},
                {"action_type": "check_health", "target": "auth-service"},
            ],
            "canary_misconfiguration": [
                {"action_type": "check_metrics", "target": "api-gateway"},
                {"action_type": "read_logs", "target": "api-gateway"},
            ],
            "clock_skew": [
                {"action_type": "read_logs", "target": "auth-service"},
                {"action_type": "check_metrics", "target": "auth-service"},
            ],
            "disk_full": [
                {"action_type": "run_db_query", "target": "postgres-db"},
                {"action_type": "read_logs", "target": "postgres-db"},
            ],
        }
        
        # Fixes per fault type
        fixes = {
            "cpu_spike": [
                {"action_type": "restart_service", "target": "auth-service"},
            ],
            "secret_rotation_break": [
                {"action_type": "rollback_deployment", "target": "order-service"},
            ],
            "connection_pool_exhausted": [
                {"action_type": "restart_service", "target": "order-service"},
            ],
            "memory_leak": [
                {"action_type": "restart_service", "target": "notification-service"},
            ],
            "thread_pool_exhausted": [
                {"action_type": "restart_service", "target": "auth-service"},
            ],
            "canary_misconfiguration": [
                {"action_type": "rollback_deployment", "target": "api-gateway"},
            ],
            "clock_skew": [
                {"action_type": "rollback_deployment", "target": "auth-service"},
            ],
            "disk_full": [
                {"action_type": "rollback_deployment", "target": "postgres-db"},
            ],
        }
        
        fault_component = self.task.get("fault_service", "auth-service")
        plan = base + fault_evidence.get(fault, []) + fixes.get(fault, [])
        plan.append({"action_type": "declare_rca", "target": fault_component})
        return plan

    def _kafka_plan(self, fault: str) -> list[dict]:
        """Optimal investigation path for Kafka faults."""
        base = [
            {"action_type": "check_metrics", "target": "kafka-broker"},
            {"action_type": "read_logs", "target": "kafka-broker"},
        ]
        
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

    def get_next_action(self, observation: dict | str = "", history: list = None) -> Optional[Action]:
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

    def run_episode(self, env) -> EpisodeTrajectory:
        """
        Run a full episode with the expert agent.
        Returns a trajectory object.
        """
        # Reset environment with this task
        obs = env.reset(self.task.get("id", "task_cpu_spike"))
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
            task_id=self.task.get("id", "unknown"),
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
            traj = expert.run_episode(env)
            trajectories.append(traj)
            print(f"{task_id}: score={traj.final_score:.3f} reward={traj.total_reward:.3f} rca={traj.rca_correct}")
        except Exception as e:
            print(f"{task_id}: FAILED - {e}")
    
    return trajectories
