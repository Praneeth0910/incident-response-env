# server/routes.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import traceback

from .environment import IncidentEnvironment
from .inference import run_inference

router = APIRouter()

# ── Request / Response Schemas ──────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_difficulty: str = "easy"   # "easy" | "medium" | "hard"
    seed: Optional[int] = None

class StepRequest(BaseModel):
    action: int

class InferenceRequest(BaseModel):
    observation: Dict[str, Any]
    difficulty: str = "easy"

# ── Shared env state (single-user dev server) ────────────────────────────────

_env: Optional[IncidentEnvironment] = None


def _get_env() -> IncidentEnvironment:
    global _env
    if _env is None:
        raise HTTPException(status_code=400, detail="Environment not initialised. Call /reset first.")
    return _env


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/health")
def health_check():
    """Liveness probe — Hugging Face Spaces hits this."""
    return {"status": "ok"}


@router.post("/reset")
def reset_environment(req: ResetRequest):
    """
    Initialise (or re-initialise) the incident environment.
    Returns the first observation so the dashboard can render it immediately.
    """
    global _env
    try:
        _env = IncidentEnvironment(difficulty=req.task_difficulty, seed=req.seed)
        obs = _env.reset()
        return {
            "observation": obs,
            "difficulty": req.task_difficulty,
            "seed": req.seed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}\n{traceback.format_exc()}")


@router.post("/step")
def step_environment(req: StepRequest):
    """
    Apply one action to the environment.
    Returns (obs, reward, done, info) — same shape as Gym's env.step().
    """
    env = _get_env()
    try:
        obs, reward, done, info = env.step(req.action)
        return {
            "observation": obs,
            "reward": reward,
            "done": done,
            "info": info,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step failed: {e}\n{traceback.format_exc()}")


@router.get("/state")
def get_state():
    """Return current environment state without advancing it."""
    env = _get_env()
    return {
        "observation": env.current_observation(),
        "step_count": env.step_count,
        "done": env.is_done(),
    }


@router.post("/infer")
def infer_action(req: InferenceRequest):
    """
    Run the trained policy on a raw observation dict.
    Used by the dashboard's QUICK ACTIONS buttons.
    """
    try:
        action, confidence, log = run_inference(req.observation, difficulty=req.difficulty)
        return {
            "action": action,
            "confidence": confidence,
            "log": log,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}\n{traceback.format_exc()}")


@router.post("/run_episode")
def run_full_episode(req: ResetRequest):
    """
    Reset + run until done. Returns the full episode trajectory.
    Useful for benchmark_runner.py.
    """
    global _env
    try:
        _env = IncidentEnvironment(difficulty=req.task_difficulty, seed=req.seed)
        obs = _env.reset()

        trajectory = []
        done = False

        while not done:
            action, confidence, log = run_inference(obs, difficulty=req.task_difficulty)
            obs, reward, done, info = _env.step(action)
            trajectory.append({
                "action": action,
                "confidence": confidence,
                "reward": reward,
                "done": done,
                "info": info,
                "log": log,
            })

        return {
            "trajectory": trajectory,
            "total_steps": len(trajectory),
            "total_reward": sum(t["reward"] for t in trajectory),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Episode failed: {e}\n{traceback.format_exc()}")