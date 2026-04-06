from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models import Action, Observation, ResetRequest, StepResponse
from environment import IncidentResponseEnv

app = FastAPI(
    title="Incident Response Environment",
    description="OpenEnv-compliant production incident response RL environment.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

env = IncidentResponseEnv()


@app.get("/health")
def health():
    return {"status": "ok", "env": "incident-response-env", "version": "1.0.0"}


@app.post("/reset", response_model=Observation)
def reset(request: ResetRequest = ResetRequest()):
    obs = env.reset(task_id=request.task_id, seed=request.seed)
    return obs


@app.post("/step", response_model=StepResponse)
def step(action: Action):
    try:
        obs, rew, done, info = env.step(action)
        return StepResponse(observation=obs, reward=rew, done=done, info=info)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/state")
def state():
    return env.state()


@app.get("/grade")
def grade():
    return {"score": env.grade()}


@app.get("/tasks")
def tasks():
    from environment import TASKS
    return {
        tid: {
            "name": t["name"],
            "difficulty": t["difficulty"],
            "max_steps": t["max_steps"],
            "description": t["description"],
        }
        for tid, t in TASKS.items()
    }