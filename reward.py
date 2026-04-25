"""
reward.py

Domain-aware reward function for CI/CD and Kafka SRE training.
Implements an `EvidenceTracker` dataclass and domain-dispatched step/rca reward
calculators. This file follows the design in roadmap_regenerated.md.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class EvidenceTracker:
    # CI/CD
    logs_read: bool = False
    secrets_inspected: bool = False
    audit_log_read: bool = False
    action_integrity_checked: bool = False
    runner_status_checked: bool = False
    # Kafka
    per_partition_lag_checked: bool = False
    partition_inspected: bool = False
    broker_logs_read: bool = False
    consumer_group_described: bool = False
    schema_checked: bool = False

    def evidence_count_cicd(self) -> int:
        return sum([
            self.logs_read,
            self.secrets_inspected,
            self.audit_log_read,
            self.action_integrity_checked,
        ])

    def evidence_count_kafka(self) -> int:
        return sum([
            self.per_partition_lag_checked,
            self.partition_inspected,
            self.broker_logs_read,
            self.consumer_group_described,
            self.schema_checked,
        ])


_CICD_FIX_ACTIONS = {"rollback_workflow", "rotate_secret", "pin_action_to_sha", "isolate_runner"}
_KAFKA_FIX_ACTIONS = {"skip_offset", "restart_consumer_group", "increase_broker_heap"}


def compute_step_reward(
    action: str,
    task: Dict,
    step_count: int,
    actions_taken: list[str],
    evidence: EvidenceTracker,
    observation: str | Dict = "",
) -> float:
    domain = task.get("domain", "cicd")
    fault = task.get("fault_type", "")
    max_s = task.get("max_steps", 15)
    is_redundant = actions_taken.count(action) > 1

    if is_redundant:
        penalty = -0.08 if step_count < max_s * 0.5 else -0.20
        return penalty

    if domain == "cicd":
        return _cicd_reward(action, fault, step_count, max_s, evidence)
    return _kafka_reward(action, fault, step_count, max_s, evidence)


def _cicd_reward(action, fault, step_count, max_s, ev: EvidenceTracker) -> float:
    reward = 0.0
    # Evidence gathering
    if action == "read_job_logs":
        ev.logs_read = True
        reward = 0.12
    elif action == "inspect_secret" and fault in ("secret_rotation_break", "oidc_token_failure"):
        ev.secrets_inspected = True
        reward = 0.15
    elif action == "check_action_integrity":
        ev.action_integrity_checked = True
        reward = 0.18
    elif action == "read_audit_log" and not ev.audit_log_read:
        ev.audit_log_read = True
        reward = 0.10
    elif action == "check_runner_status":
        ev.runner_status_checked = True
        reward = 0.12 if fault in ("runner_queue_flood", "runner_compromise") else 0.04
    elif action == "check_pipeline_status":
        reward = 0.04

    # Fix actions
    elif action in _CICD_FIX_ACTIONS:
        ev_count = ev.evidence_count_cicd()
        multipliers = {0: 0.1, 1: 0.5}
        mult = multipliers.get(ev_count, 1.0)
        base = 0.30
        reward = base * mult
        if ev_count == 0:
            reward -= 0.20

    return max(-1.0, min(1.0, reward))


def _kafka_reward(action, fault, step_count, max_s, ev: EvidenceTracker) -> float:
    reward = 0.0
    if action == "get_cluster_metrics":
        reward = 0.05
    elif action == "check_consumer_lag":
        ev.per_partition_lag_checked = True
        reward = 0.15
    elif action == "inspect_partition":
        if not ev.per_partition_lag_checked:
            reward = 0.10
        else:
            ev.partition_inspected = True
            reward = 0.20
    elif action == "read_broker_logs":
        ev.broker_logs_read = True
        reward = 0.15 if fault in ("broker_oom_cascade", "isr_churn", "retry_amplification") else 0.06
    elif action == "describe_consumer_group":
        ev.consumer_group_described = True
        reward = 0.15 if fault in ("zombie_consumer", "rebalance_storm") else 0.06
    elif action == "read_consumer_logs":
        reward = 0.10
    elif action == "check_schema_registry":
        ev.schema_checked = True
        reward = 0.18 if fault == "schema_desync" else 0.04

    elif action == "skip_offset":
        if not ev.partition_inspected:
            reward = -0.30
        elif not ev.per_partition_lag_checked:
            reward = -0.15
        else:
            reward = 0.25
    elif action in _KAFKA_FIX_ACTIONS:
        ev_count = ev.evidence_count_kafka()
        if ev_count < 2:
            reward = -0.10
        else:
            reward = 0.20

    return max(-1.0, min(1.0, reward))


def compute_rca_reward(declared_component: str, task: Dict, step_count: int, evidence: EvidenceTracker) -> float:
    # Support either 'fault_component' or legacy 'fault_service' keys in TASKS
    correct = task.get("fault_component") or task.get("fault_service", "")
    max_s = task.get("max_steps", 15)

    if declared_component.lower() != correct.lower():
        return -0.40

    domain = task.get("domain", "cicd")
    ev_count = evidence.evidence_count_cicd() if domain == "cicd" else evidence.evidence_count_kafka()
    base = 0.50
    evidence_bonus = min(ev_count * 0.05, 0.20)
    efficiency = max(0, (max_s - step_count) / max_s) * 0.30
    return min(0.999, base + evidence_bonus + efficiency)
