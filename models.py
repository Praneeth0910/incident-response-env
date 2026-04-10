from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class Action(BaseModel):
    action_type: Literal[
        "read_logs",
        "check_metrics",
        "check_health",
        "run_db_query",
        "restart_service",
        "rollback_deployment",
        "declare_rca",
    ]
    target: str = Field(..., description="Service name or fault type for declare_rca")


class Observation(BaseModel):
    message: str
    step: int
    done: bool
    alert: str
    metrics: Optional[Dict[str, Any]] = None
    info: Optional[Dict[str, Any]] = None


class Reward(BaseModel):
    value: float = Field(..., ge=-1.0, le=1.0)
    reason: str


class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any]


class TaskDetail(BaseModel):
    """Full task metadata for dashboard detail panels."""
    id: str = Field(..., description="Task ID")
    name: str
    difficulty: Literal["easy", "medium", "hard"]
    max_steps: int
    description: str
    ideal_steps: int
    fault_service: str
    fault_type: str
    red_herrings: list[str]
    alert: str


class ResetRequest(BaseModel):
    task_id: Literal[
        "task_cpu_spike",
        "task_db_connection_leak",
        "task_redis_memory_eviction",
        "task_api_rate_limit",
        "task_deadlock_order_service",
        "task_ssl_cert_expired",
        "task_slow_query_postgres",
        "task_auth_service_500",
        "task_k8s_pod_crashloop",
        "task_disk_full",
        "task_memory_leak",
        "task_thread_starvation",
        "task_canary_poison",
        "task_clock_skew",
    ] = "task_cpu_spike"
    seed: Optional[int] = None