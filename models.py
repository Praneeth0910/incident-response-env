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


class Reward(BaseModel):
    value: float = Field(..., ge=-1.0, le=1.0)
    reason: str


class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any]


class ResetRequest(BaseModel):
    task_id: Literal[
        "task_easy",
        "task_cpu_spike",
        "task_disk_full",
        "task_medium",
        "task_memory_leak",
        "task_thread_starvation",
        "task_hard",
        "task_canary_poison",
        "task_clock_skew",
    ] = "task_easy"
    seed: Optional[int] = None