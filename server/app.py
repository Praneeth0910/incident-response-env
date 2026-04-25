"""
server/app.py
=============
FastAPI application — OpenEnv-compliant REST API + Gradio dashboard.

Endpoints
---------
GET  /health           → health check
POST /reset            → start episode
POST /step             → take action
GET  /state            → ground truth state (debug)
GET  /grade            → episode score  { "score": float }
GET  /tasks            → list tasks with basic metadata
GET  /tasks/{task_id}  → get full task details (for dashboard detail panel)

The Gradio dashboard is mounted at /dashboard via gr.mount_gradio_app.
Root / redirects to /dashboard/.
"""
from __future__ import annotations

import sys
import os
import traceback
from typing import Optional

# Ensure both project root and server/ are on path so imports work locally and in Docker
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_server_dir = os.path.dirname(os.path.abspath(__file__))
for _path in (_root, _server_dir):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
import gradio as gr

from environment import IncidentResponseEnv, TASKS
from models import Action, ResetRequest, StepResponse, TaskDetail

# ── FastAPI core app ──────────────────────────────────────────────────────────
_app = FastAPI(
    title="Incident Response RL Environment",
    description="OpenEnv-compliant RL benchmark for LLM SRE incident response.",
    version="1.0.0",
)

# Single shared env instance (one episode at a time)
_env: IncidentResponseEnv = IncidentResponseEnv()


@_app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard/")


@_app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@_app.post("/reset")
async def reset(body: Optional[ResetRequest] = None):
    try:
        task_id = body.task_id if body else "task_cpu_spike"
        seed = body.seed if body else None
        obs = _env.reset(task_id=task_id, seed=seed)
        return obs.model_dump()
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown task_id: {task_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@_app.post("/step")
async def step(action: Action):
    try:
        obs, reward, done, info = _env.step(action)
        return StepResponse(observation=obs, reward=reward, done=done, info=info).model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@_app.get("/state")
async def state():
    try:
        return _env.state()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@_app.get("/grade")
async def grade():
    try:
        score = _env.grade()
        state = _env.state()
        return {
            "score": score,
            "rca_declared": getattr(_env, "_rca_declared", False),
            "rca_correct": getattr(_env, "_rca_correct", False),
            "evidence_found": state.get("evidence_found", []),
            "step_count": state.get("step_count", 0),
            "max_steps": state.get("max_steps"),
            "task_id": state.get("task_id"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@_app.get("/tasks")
async def task_list():
    return {
        "tasks": [
            {
                "id": tid,
                "name": meta["name"],
                "difficulty": meta["difficulty"],
                "max_steps": meta["max_steps"],
                "ideal_steps": meta["ideal_steps"],
                "description": meta["description"],
            }
            for tid, meta in TASKS.items()
        ]
    }


@_app.get("/tasks/{task_id}", response_model=TaskDetail)
async def task_detail(task_id: str):
    """Get full task metadata including description, difficulty, ideal_steps."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    meta = TASKS[task_id]
    return TaskDetail(
        id=task_id,
        name=meta["name"],
        difficulty=meta["difficulty"],
        max_steps=meta["max_steps"],
        description=meta["description"],
        ideal_steps=meta["ideal_steps"],
        fault_service=meta["fault_service"],
        fault_type=meta["fault_type"],
        red_herrings=meta["red_herrings"],
        alert=meta["alert"],
    )


# ── Mount Gradio dashboard ────────────────────────────────────────────────────
try:
    from dashboard_impl import create_dashboard
    _gradio_ui = create_dashboard(_env)
    app = gr.mount_gradio_app(_app, _gradio_ui, path="/dashboard")
    print("[INFO] Gradio dashboard mounted at /dashboard", flush=True)
except Exception as _mount_err:
    print(f"[WARN] Dashboard could not be mounted: {_mount_err}", flush=True)
    traceback.print_exc()
    app = _app


# ── Entry point for command-line and deployment ───────────────────────────────
def main():
    """Main entry point for uvicorn and setuptools scripts."""
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()