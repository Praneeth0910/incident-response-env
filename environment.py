import random
from typing import Any, Dict, Optional, Tuple
from models import Action, Observation, Reward

# ── Task definitions ──────────────────────────────────────────────────────────

TASKS = {
    "task_easy": {
        "name": "OOM crash — single service",
        "difficulty": "easy",
        "max_steps": 10,
        "description": "Notification service crashed due to out-of-memory error.",
        "alert": "ALERT: High error rate detected. API gateway reporting 500s. Latency p99: 3.8s.",
        "fault_service": "notification-service",
        "fault_type": "oom_crash",
        "red_herrings": [],
        "ideal_steps": 3,
    },
    "task_medium": {
        "name": "Cascading failure from bad deployment",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Bad deployment on order-service caused cascading failures.",
        "alert": "ALERT: Multiple services degraded. Error rate 38%. Users cannot complete orders.",
        "fault_service": "order-service",
        "fault_type": "bad_deployment",
        "red_herrings": ["auth-service"],
        "ideal_steps": 6,
    },
    "task_hard": {
        "name": "Redis connection pool exhaustion with red herring",
        "difficulty": "hard",
        "max_steps": 20,
        "description": "Redis connection pool exhausted. CPU spike on order-service is a red herring.",
        "alert": "ALERT: Cascading timeouts across 4 services. p99 latency: 9.2s. On-call paged.",
        "fault_service": "redis-cache",
        "fault_type": "connection_pool_exhausted",
        "red_herrings": ["order-service"],  # high CPU — distraction
        "ideal_steps": 8,
    },
}

SERVICES = [
    "api-gateway",
    "auth-service",
    "order-service",
    "notification-service",
    "redis-cache",
    "postgres-db",
]

# ── Simulated data generators ─────────────────────────────────────────────────

def _make_metrics(service: str, task: dict) -> Dict[str, Any]:
    fault_svc = task["fault_service"]
    red_herrings = task["red_herrings"]
    base = {
        "latency_p99_ms": random.randint(80, 200),
        "error_rate": round(random.uniform(0.001, 0.015), 3),
        "cpu_pct": random.randint(10, 35),
        "memory_pct": random.randint(30, 55),
        "request_rate": random.randint(200, 800),
    }
    if service == fault_svc:
        if task["fault_type"] == "oom_crash":
            base.update({"latency_p99_ms": 0, "error_rate": 1.0,
                         "cpu_pct": 0, "memory_pct": 99, "request_rate": 0})
        elif task["fault_type"] == "bad_deployment":
            base.update({"latency_p99_ms": 4800, "error_rate": 0.72,
                         "cpu_pct": 28, "memory_pct": 61, "request_rate": 120})
        elif task["fault_type"] == "connection_pool_exhausted":
            base.update({"latency_p99_ms": 8900, "error_rate": 0.89,
                         "cpu_pct": 12, "memory_pct": 44,
                         "active_connections": 500, "max_connections": 500})
    elif service in red_herrings:
        # looks suspicious but is not the cause
        base["cpu_pct"] = random.randint(85, 96)
    elif service == "api-gateway":
        # gateway always looks bad — it's the victim
        base.update({"latency_p99_ms": random.randint(3000, 5000),
                     "error_rate": round(random.uniform(0.3, 0.5), 3)})
    return base


def _make_logs(service: str, task: dict) -> str:
    fault_svc = task["fault_service"]
    fault_type = task["fault_type"]
    if service == fault_svc:
        if fault_type == "oom_crash":
            return (
                f"[ERROR] {service}: java.lang.OutOfMemoryError: Java heap space\n"
                f"[ERROR] {service}: Killed by OOM killer (signal 9)\n"
                f"[WARN]  {service}: Health check timed out after 30s"
            )
        elif fault_type == "bad_deployment":
            return (
                f"[ERROR] {service}: connection refused to postgres:5432\n"
                f"[ERROR] {service}: deployment v2.4.1 — env var DB_HOST missing\n"
                f"[WARN]  {service}: retry 3/3 failed, circuit breaker open"
            )
        elif fault_type == "connection_pool_exhausted":
            return (
                f"[ERROR] {service}: connection pool exhausted (500/500 active)\n"
                f"[ERROR] {service}: timeout waiting for connection after 5000ms\n"
                f"[WARN]  {service}: connection leak detected in session handler"
            )
    elif service == "api-gateway":
        return (
            f"[WARN]  {service}: upstream timeout from order-service (4800ms)\n"
            f"[ERROR] {service}: 502 Bad Gateway — notification-service unreachable\n"
            f"[INFO]  {service}: retry storm detected, rate limiting applied"
        )
    return (
        f"[INFO]  {service}: request processed in {random.randint(8,25)}ms\n"
        f"[INFO]  {service}: health check OK\n"
        f"[DEBUG] {service}: connection pool usage 12/100"
    )


def _make_db_query_result(task: dict) -> str:
    if task["fault_type"] == "connection_pool_exhausted":
        return (
            "active_connections | max_connections | waiting_queries\n"
            "-------------------+------------------+----------------\n"
            "        500        |       500        |       847\n"
            "(1 row)\n"
            "WARNING: connection pool at 100% capacity"
        )
    elif task["fault_type"] == "bad_deployment":
        return (
            "SELECT * FROM pg_stat_activity WHERE state='idle in transaction';\n"
            " pid  | state  | query_start\n"
            "------+--------+-------------\n"
            "(0 rows)\n"
            "DB appears healthy — problem is upstream"
        )
    return "query_time_ms | rows_returned\n--------------+--------------\n     4.2      |    1000\n(DB healthy)"


# ── Main environment class ────────────────────────────────────────────────────

class IncidentResponseEnv:

    def __init__(self):
        self._task: Optional[dict] = None
        self._task_id: Optional[str] = None
        self._step_count: int = 0
        self._done: bool = False
        self._cumulative_reward: float = 0.0
        self._actions_taken: set = set()
        self._relevant_evidence_found: set = set()

    # ── reset ─────────────────────────────────────────────────────────────────

    def reset(self, task_id: str = "task_easy", seed: Optional[int] = None) -> Observation:
        if seed is not None:
            random.seed(seed)
        self._task_id = task_id
        self._task = TASKS[task_id].copy()
        self._step_count = 0
        self._done = False
        self._cumulative_reward = 0.0
        self._actions_taken = set()
        self._relevant_evidence_found = set()
        return Observation(
            message=(
                f"Incident active. {self._task['description']} "
                f"You have {self._task['max_steps']} steps. Investigate carefully."
            ),
            step=0,
            done=False,
            alert=self._task["alert"] if self._task else "",
        )

    # ── step ──────────────────────────────────────────────────────────────────

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        if self._done or self._task is None:
            raise RuntimeError("Episode finished. Call reset() first.")

        self._step_count += 1
        task = self._task
        if task is None:
            raise RuntimeError("Task is not initialized. Call reset() first.")
        fault_svc = task["fault_service"]
        fault_type = task["fault_type"]
        max_steps = task["max_steps"]

        reward_value = 0.0
        reward_reason = "no signal"
        message = ""
        metrics = None
        done = False

        action_key = f"{action.action_type}:{action.target}"

        # ── deduplicate ───────────────────────────────────────────────────────
        if action_key in self._actions_taken and action.action_type != "declare_rca":
            reward_value = -0.05
            reward_reason = "redundant action — already checked this"
            message = f"You already checked {action.target} with {action.action_type}. No new information."
        else:
            self._actions_taken.add(action_key)

            # ── read_logs ─────────────────────────────────────────────────────
            if action.action_type == "read_logs":
                logs = _make_logs(action.target, task)
                message = f"Logs from {action.target}:\n{logs}"
                if action.target == fault_svc:
                    reward_value = 0.10
                    reward_reason = f"found fault evidence in {action.target} logs"
                    self._relevant_evidence_found.add("logs_fault_svc")
                elif action.target == "api-gateway":
                    reward_value = 0.05
                    reward_reason = "gateway logs show symptoms (not root cause)"
                    self._relevant_evidence_found.add("logs_gateway")
                else:
                    reward_value = 0.0
                    reward_reason = "no relevant signal in these logs"

            # ── check_metrics ─────────────────────────────────────────────────
            elif action.action_type == "check_metrics":
                met = _make_metrics(action.target, task)
                metrics = {action.target: met}
                message = f"Metrics for {action.target}: {met}"
                if action.target == fault_svc:
                    reward_value = 0.08
                    reward_reason = f"fault service metrics show anomaly"
                    self._relevant_evidence_found.add("metrics_fault_svc")
                elif action.target in task["red_herrings"]:
                    reward_value = 0.02
                    reward_reason = "metrics look suspicious but this is not the fault service"
                else:
                    reward_value = 0.0
                    reward_reason = "metrics normal"

            # ── check_health ──────────────────────────────────────────────────
            elif action.action_type == "check_health":
                if action.target == fault_svc and fault_type == "oom_crash":
                    status = "DOWN"
                    reward_value = 0.07
                    reward_reason = "found downed service"
                    self._relevant_evidence_found.add("health_fault_svc")
                elif action.target == fault_svc:
                    status = "DEGRADED"
                    reward_value = 0.05
                    reward_reason = "service degraded — investigate further"
                    self._relevant_evidence_found.add("health_fault_svc")
                else:
                    status = random.choice(["UP", "UP", "DEGRADED"])
                    reward_value = 0.0
                    reward_reason = "service appears healthy"
                message = f"Health check {action.target}: {status}"

            # ── run_db_query ──────────────────────────────────────────────────
            elif action.action_type == "run_db_query":
                result = _make_db_query_result(task)
                message = f"DB query result:\n{result}"
                if fault_type == "connection_pool_exhausted" and "postgres" in action.target.lower():
                    reward_value = 0.12
                    reward_reason = "DB query confirms connection pool exhaustion"
                    self._relevant_evidence_found.add("db_query")
                else:
                    reward_value = 0.01
                    reward_reason = "DB query ran, limited signal"

            # ── restart_service ───────────────────────────────────────────────
            elif action.action_type == "restart_service":
                if action.target == fault_svc and fault_type in ("oom_crash",):
                    reward_value = 0.30
                    reward_reason = f"correct service restarted — {fault_type} resolved"
                    message = f"{action.target} restarted successfully. Error rate dropping."
                elif action.target == fault_svc:
                    reward_value = 0.10
                    reward_reason = "restarted fault service but wrong fix for this fault type"
                    message = f"{action.target} restarted but issue persists — wrong fix."
                else:
                    reward_value = -0.20
                    reward_reason = "wrong service restarted — wasted time, cascading risk"
                    message = f"{action.target} restarted but errors persist. Cascading risk increased."

            # ── rollback_deployment ───────────────────────────────────────────
            elif action.action_type == "rollback_deployment":
                if action.target == fault_svc and fault_type == "bad_deployment":
                    reward_value = 0.30
                    reward_reason = "correct rollback — bad deployment resolved"
                    message = f"Rolled back {action.target} to v2.4.0. Error rate recovering."
                elif action.target == fault_svc:
                    reward_value = 0.05
                    reward_reason = "rollback on fault service but not the right fix"
                    message = f"Rollback completed but issue persists."
                else:
                    reward_value = -0.15
                    reward_reason = "rolled back wrong service"
                    message = f"Rolled back {action.target} — no improvement. Wrong target."

            # ── declare_rca ───────────────────────────────────────────────────
            elif action.action_type == "declare_rca":
                done = True
                self._done = True
                evidence_bonus = len(self._relevant_evidence_found) * 0.03
                time_bonus = max(0.0, (max_steps - self._step_count) / max_steps) * 0.4

                if action.target == fault_svc:
                    reward_value = round(0.50 + time_bonus + evidence_bonus, 3)
                    reward_value = min(reward_value, 1.0)
                    reward_reason = (
                        f"correct RCA: {fault_svc}. "
                        f"time_bonus={time_bonus:.2f} evidence_bonus={evidence_bonus:.2f}"
                    )
                    message = f"Root cause confirmed: {fault_svc} — {fault_type}. Incident resolved."
                else:
                    reward_value = 0.0
                    reward_reason = f"wrong RCA. Actual fault: {fault_svc}"
                    message = f"Incorrect. The fault was in {fault_svc}, not {action.target}."

        # ── time pressure after 50% of steps ─────────────────────────────────
        if not done:
            progress = self._step_count / max_steps
            if progress > 0.5:
                time_penalty = -0.01 * ((progress - 0.5) / 0.5)
                reward_value += time_penalty

            if self._step_count >= max_steps:
                done = True
                self._done = True
                message += f"\n[SLA BREACHED] Max steps ({max_steps}) reached."

        reward_value = round(reward_value, 4)
        self._cumulative_reward += reward_value
        self._cumulative_reward = round(
            max(-1.0, min(1.0, self._cumulative_reward)), 4
        )

        obs = Observation(
            message=message,
            step=self._step_count,
            done=done,
            alert=self._task["alert"] if self._task else "",
            metrics=metrics,
        )
        rew = Reward(value=reward_value, reason=reward_reason)
        info = {
            "step": self._step_count,
            "cumulative_reward": self._cumulative_reward,
            "evidence_found": list(self._relevant_evidence_found),
        }
        return obs, rew, done, info

    # ── state ─────────────────────────────────────────────────────────────────

    def state(self) -> Dict[str, Any]:
        if self._task is None:
            return {"status": "not_started"}
        return {
            "task_id": self._task_id,
            "task_name": self._task["name"],
            "difficulty": self._task["difficulty"],
            "hidden_fault_service": self._task["fault_service"],
            "hidden_fault_type": self._task["fault_type"],
            "step_count": self._step_count,
            "max_steps": self._task["max_steps"],
            "done": self._done,
            "cumulative_reward": self._cumulative_reward,
            "evidence_found": list(self._relevant_evidence_found),
        }

    # ── grader ────────────────────────────────────────────────────────────────

    def grade(self) -> float:
        """Deterministic grader — returns float in [0.0, 1.0]."""
        if not self._done:
            return 0.0
        score = max(0.0, min(1.0, self._cumulative_reward))
        return round(score, 4)