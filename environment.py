"""
Main environment module â€” modular re-export wrapper.

This module provides backward compatibility by re-exporting from:
  - base_env: Core environment loop (BaseIncidentEnv, TrainingEnv, BenchmarkEnv, IncidentResponseEnv)
  - tasks: Task definitions (TASKS)
  - reward: Reward computation (compute_step_reward)
  - observation: Observation formatting

Architecture:
  base_env.py (core loop)
    - BaseIncidentEnv (abstract)
      â”œâ”€ TrainingEnv: Dense logging, trajectory storage
      â””â”€ BenchmarkEnv: Silent, deterministic evaluation
  tasks.py (task definitions)
  reward.py (reward logic)
  observation.py (observation formatting)

Usage (unchanged from original):
  from environment import TrainingEnv, BenchmarkEnv, IncidentResponseEnv
  env = TrainingEnv()
  obs = env.reset("task_cpu_spike", seed=42)
  obs, reward, done, info = env.step(Action(...))
"""

from base_env import (
    BaseIncidentEnv,
    BenchmarkEnv,
    EpisodeTrajectory,
    IncidentResponseEnv,
    TrainingEnv,
    TrajectoryStep,
)
from models import Action
from services import SERVICE_REGISTRY
from tasks import TASKS

SERVICES = list(SERVICE_REGISTRY.keys())

__all__ = [
    "Action",
    "BaseIncidentEnv",
    "TrainingEnv",
    "BenchmarkEnv",
    "IncidentResponseEnv",
    "TrajectoryStep",
    "EpisodeTrajectory",
    "TASKS",
    "SERVICES",
]

