"""
Reward computation module.
Separated from environment — contains all reward logic and bonuses.
"""

import random
from typing import Any, Dict, Set, Tuple

from models import Action, Observation, Reward


def _compute_sequence_bonus(evidence_found: Set[str], action_type: str) -> float:
    """Bonus multiplier for following correct investigation sequence."""
    has_logs = "logs_fault_svc" in evidence_found or "logs_gateway" in evidence_found
    has_metrics = "metrics_fault_svc" in evidence_found
    has_health = "health_fault_svc" in evidence_found

    if action_type == "restart_service" or action_type == "rollback_deployment":
        evidence_count = sum([has_logs, has_metrics, has_health])
        if evidence_count >= 2:
            return 1.0
        elif evidence_count == 1:
            return 0.6
        else:
            return 0.2

    if action_type == "declare_rca":
        evidence_count = sum([has_logs, has_metrics, has_health])
        if evidence_count >= 3:
            return 1.0
        elif evidence_count == 2:
            return 0.8
        elif evidence_count == 1:
            return 0.5
        else:
            return 0.1

    return 1.0


def _compute_redundancy_penalty(step_count: int, max_steps: int) -> float:
    """Penalty for repeating actions escalates as episode progresses."""
    progress = step_count / max_steps
    if progress < 0.3:
        return -0.08
    elif progress < 0.6:
        return -0.12
    else:
        return -0.20


def _make_metrics(service: str, task: Dict[str, Any],
                  cascade_triggered: bool = False,
                  cascade_service: str = "") -> Dict[str, Any]:
    """Generate realistic metrics for a service based on task state."""
    fault_svc = task["fault_service"]
    fault_type = task["fault_type"]
    red_herrings = task["red_herrings"]

    base = {
        "latency_p99_ms": random.randint(80, 200),
        "error_rate": round(random.uniform(0.001, 0.015), 3),
        "cpu_pct": random.randint(10, 35),
        "memory_pct": random.randint(30, 55),
        "request_rate": random.randint(200, 800),
    }

    if service == fault_svc:
        if fault_type == "oom_crash":
            base.update({"latency_p99_ms": 0, "error_rate": 1.0,
                         "cpu_pct": 0, "memory_pct": 99, "request_rate": 0})
        elif fault_type == "bad_deployment":
            base.update({"latency_p99_ms": 4800, "error_rate": 0.72,
                         "cpu_pct": 28, "memory_pct": 61, "request_rate": 120})
        elif fault_type == "connection_pool_exhausted":
            base.update({"latency_p99_ms": 8900, "error_rate": 0.89,
                         "cpu_pct": 12, "memory_pct": 44,
                         "active_connections": 500, "max_connections": 500})
        elif fault_type == "cpu_spike":
            base.update({"latency_p99_ms": 9200, "error_rate": 0.91,
                         "cpu_pct": 99, "memory_pct": 42, "request_rate": 12,
                         "thread_pool_active": 200, "thread_pool_max": 200})
        elif fault_type == "disk_full":
            base.update({"latency_p99_ms": 0, "error_rate": 1.0,
                         "cpu_pct": 8, "memory_pct": 35,
                         "disk_used_pct": 100, "wal_size_gb": 48, "request_rate": 0})
        elif fault_type == "memory_leak":
            base.update({"latency_p99_ms": random.randint(8000, 12000),
                         "error_rate": round(random.uniform(0.4, 0.7), 3),
                         "cpu_pct": random.randint(60, 80), "memory_pct": 98,
                         "gc_pause_ms": random.randint(8000, 14000),
                         "heap_used_gb": 3.8, "heap_max_gb": 4.0})
        elif fault_type == "thread_pool_exhausted":
            base.update({"latency_p99_ms": 30000, "error_rate": 0.85,
                         "cpu_pct": 22, "memory_pct": 48,
                         "thread_pool_active": 200, "thread_pool_max": 200,
                         "thread_pool_queue": 847})
        elif fault_type == "canary_misconfiguration":
            base.update({"latency_p99_ms": random.randint(200, 600),
                         "error_rate": 0.10, "cpu_pct": random.randint(15, 30),
                         "memory_pct": 40, "canary_traffic_pct": 10,
                         "canary_error_rate": 1.0})
        elif fault_type == "clock_skew":
            base.update({"latency_p99_ms": random.randint(300, 900),
                         "error_rate": round(random.uniform(0.20, 0.30), 3),
                         "cpu_pct": random.randint(25, 45), "memory_pct": 38,
                         "clock_drift_seconds": 480, "jwt_rejected_rate": 0.25})

    elif cascade_triggered and service == cascade_service:
        base.update({
            "latency_p99_ms": random.randint(3000, 7000),
            "error_rate": round(random.uniform(0.35, 0.65), 3),
            "cpu_pct": random.randint(65, 88),
        })

    elif service in red_herrings:
        if fault_type == "canary_misconfiguration":
            base.update({"error_rate": round(random.uniform(0.08, 0.12), 3),
                         "latency_p99_ms": random.randint(400, 800)})
        elif fault_type == "clock_skew":
            if service == "redis-cache":
                base.update({"cache_miss_rate": 0.68, "cpu_pct": random.randint(30, 55)})
            else:
                base.update({"error_rate": round(random.uniform(0.20, 0.28), 3),
                             "latency_p99_ms": random.randint(500, 1200)})
        else:
            base["cpu_pct"] = random.randint(85, 96)

    elif service == "api-gateway":
        base.update({"latency_p99_ms": random.randint(3000, 5000),
                     "error_rate": round(random.uniform(0.3, 0.5), 3)})
    return base


def _make_logs(service: str, task: Dict[str, Any],
               cascade_triggered: bool = False,
               cascade_service: str = "") -> str:
    """Generate realistic log output for a service."""
    fault_svc = task["fault_service"]
    fault_type = task["fault_type"]

    if cascade_triggered and service == cascade_service:
        return (
            f"[ERROR] {service}: cascading degradation from upstream fault\n"
            f"[WARN]  {service}: latency spiking — connections timing out\n"
            f"[INFO]  {service}: this service is a VICTIM, not the root cause"
        )

    if service == fault_svc:
        if fault_type == "oom_crash":
            return (f"[ERROR] {service}: java.lang.OutOfMemoryError: Java heap space\n"
                    f"[ERROR] {service}: Killed by OOM killer (signal 9)\n"
                    f"[WARN]  {service}: Health check timed out after 30s")
        elif fault_type == "bad_deployment":
            return (f"[ERROR] {service}: connection refused to postgres:5432\n"
                    f"[ERROR] {service}: deployment v2.4.1 — env var DB_HOST missing\n"
                    f"[WARN]  {service}: retry 3/3 failed, circuit breaker open")
        elif fault_type == "connection_pool_exhausted":
            return (f"[ERROR] {service}: connection pool exhausted (500/500 active)\n"
                    f"[ERROR] {service}: timeout waiting for connection after 5000ms\n"
                    f"[WARN]  {service}: connection leak detected in session handler")
        elif fault_type == "cpu_spike":
            return (f"[ERROR] {service}: thread saturation — 200/200 threads active\n"
                    f"[ERROR] {service}: CPU 99% — hot loop detected in JWTValidator.validate()\n"
                    f"[WARN]  {service}: request queue depth 847, new requests timing out")
        elif fault_type == "disk_full":
            return (f"[FATAL] {service}: could not write to file \"pg_wal/000000010000002A\"\n"
                    f"[ERROR] {service}: ENOSPC: No space left on device — WAL at 48GB\n"
                    f"[ERROR] {service}: auto_vacuum disabled since 2026-04-02 maintenance window")
        elif fault_type == "memory_leak":
            return (f"[ERROR] {service}: GC pause > 11240ms — Old generation 98% full\n"
                    f"[ERROR] {service}: EmailTemplateCache holding 3.4GB unreferenced strings\n"
                    f"[WARN]  {service}: heap used 3.8GB / 4.0GB — approaching OOM threshold")
        elif fault_type == "thread_pool_exhausted":
            return (f"[ERROR] {service}: No threads available in pool (200/200 active)\n"
                    f"[ERROR] {service}: OAuthIdentityClient timeout after 30000ms (blocked I/O)\n"
                    f"[WARN]  {service}: timeout waiting for worker — 847 requests queued")
        elif fault_type == "canary_misconfiguration":
            return (f"[ERROR] {service}: canary instance v2.1 stripping Authorization header\n"
                    f"[WARN]  {service}: canary routing 10.2% of traffic to v2.1 (misconfigured)\n"
                    f"[ERROR] {service}: downstream auth rejections on canary requests")
        elif fault_type == "clock_skew":
            return (f"[ERROR] {service}: JWT iat=2026-04-09T11:23:00Z is in the future (clock drift: +8min)\n"
                    f"[ERROR] {service}: NTP daemon not running — last sync 6 hours ago\n"
                    f"[WARN]  {service}: system clock 480 seconds ahead of UTC")

    elif service in task.get("red_herrings", []):
        fault_type_rh = task["fault_type"]
        if fault_type_rh == "canary_misconfiguration":
            if service == "order-service":
                return (f"[ERROR] {service}: 401 Unauthorized from auth-service (missing token)\n"
                        f"[WARN]  {service}: 10.1% of checkout requests rejected at auth step\n"
                        f"[INFO]  {service}: no deployment changes in last 48h")
            else:
                return (f"[WARN]  {service}: receiving requests without Authorization header\n"
                        f"[ERROR] {service}: 401 returning for 10% of token validation requests\n"
                        f"[INFO]  {service}: auth-service itself functioning normally")
        elif fault_type_rh == "clock_skew":
            if service == "redis-cache":
                return (f"[WARN]  {service}: cache miss rate elevated (68%) — TTL miscalculation\n"
                        f"[INFO]  {service}: redis process healthy, memory 44%\n"
                        f"[INFO]  {service}: no configuration changes detected")
            else:
                return (f"[ERROR] {service}: 25% of requests rejected with 401 Unauthorized\n"
                        f"[WARN]  {service}: JWT validation rejecting tokens as 'not yet valid'\n"
                        f"[INFO]  {service}: no deployment or config changes")
        else:
            return (f"[WARN]  {service}: CPU spike detected (92%)\n"
                    f"[INFO]  {service}: processing requests normally\n"
                    f"[INFO]  {service}: no errors in last 5 minutes")

    elif service == "api-gateway":
        return (f"[WARN]  {service}: upstream timeout from order-service (4800ms)\n"
                f"[ERROR] {service}: 502 Bad Gateway — notification-service unreachable\n"
                f"[INFO]  {service}: retry storm detected, rate limiting applied")

    return (f"[INFO]  {service}: request processed in {random.randint(8, 25)}ms\n"
            f"[INFO]  {service}: health check OK\n"
            f"[DEBUG] {service}: connection pool usage 12/100")


def _make_db_query_result(task: Dict[str, Any]) -> str:
    """Generate DB query results based on fault type."""
    fault_type = task["fault_type"]
    if fault_type == "connection_pool_exhausted":
        return ("active_connections | max_connections | waiting_queries\n"
                "-------------------+------------------+----------------\n"
                "        500        |       500        |       847\n"
                "(1 row)\nWARNING: connection pool at 100% capacity")
    elif fault_type == "disk_full":
        return ("SELECT pg_size_pretty(pg_database_size('orders_db'));\n"
                " database_size\n--------------\n   280 GB\n"
                "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir();\n"
                " wal_size\n----------\n  48 GB\n"
                "FATAL: ENOSPC — disk at 100% capacity, WAL overflow")
    elif fault_type == "deadlock":
        return ("SELECT pid, wait_event_type, query FROM pg_stat_activity WHERE wait_event_type='Lock';\n"
                " pid  | wait_event_type | query\n"
                "------+-----------------+------------------------\n"
                " 4821 | Lock            | UPDATE inventory SET...\n"
                " 4822 | Lock            | UPDATE order_status SET...\n"
                "DEADLOCK DETECTED: circular dependency between pids 4821 and 4822")
    return ("query_time_ms | rows_returned\n"
            "--------------+--------------\n"
            "     4.2      |    1000\n(DB healthy)")


def compute_step_reward(
    action: Action,
    task: Dict[str, Any],
    step_count: int,
    cascade_triggered: bool,
    actions_taken: Set[str],
    evidence_found: Set[str],
) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
    """
    Compute reward and observation for a single step.
    
    This is the core reward logic extracted from BaseIncidentEnv.step().
    Returns (observation, reward, done, info).
    """
    fault_svc = task["fault_service"]
    fault_type = task["fault_type"]
    max_steps = task["max_steps"]
    cascade_svc = task.get("cascade_service", "")

    reward_value = 0.0
    reward_reason = "no signal"
    message = ""
    metrics = None
    done = False

    action_key = f"{action.action_type}:{action.target}"

    # ── REDUNDANT ACTION
    if action_key in actions_taken and action.action_type != "declare_rca":
        reward_value = _compute_redundancy_penalty(step_count, max_steps)
        reward_reason = f"redundant action — already checked {action.target}"
        message = f"You already checked {action.target} with {action.action_type}. No new information."

    else:
        actions_taken.add(action_key)

        # ── read_logs
        if action.action_type == "read_logs":
            logs = _make_logs(action.target, task, cascade_triggered, cascade_svc)
            message = f"Logs from {action.target}:\n{logs}"

            if action.target == fault_svc:
                reward_value = 0.15
                reward_reason = f"strong evidence found in {action.target} logs"
                evidence_found.add("logs_fault_svc")
            elif action.target == "api-gateway":
                reward_value = 0.05
                reward_reason = "gateway logs show symptoms — it is a VICTIM"
                evidence_found.add("logs_gateway")
            else:
                reward_value = -0.02
                reward_reason = f"no relevant signal in {action.target} logs"

        # ── check_metrics
        elif action.action_type == "check_metrics":
            met = _make_metrics(action.target, task, cascade_triggered, cascade_svc)
            metrics = {action.target: met}
            message = f"Metrics for {action.target}: {met}"

            if action.target == fault_svc:
                reward_value = 0.12
                reward_reason = "fault service metrics show anomaly"
                evidence_found.add("metrics_fault_svc")
            elif action.target in task["red_herrings"]:
                reward_value = -0.05
                reward_reason = f"{action.target} looks suspicious but is NOT root cause — red herring!"
            else:
                reward_value = -0.03
                reward_reason = f"metrics for {action.target} are normal"

        # ── check_health
        elif action.action_type == "check_health":
            if action.target == fault_svc and fault_type in ("oom_crash", "disk_full", "cpu_spike"):
                status = "DOWN"
                reward_value = 0.10
                reward_reason = "found downed service"
                evidence_found.add("health_fault_svc")
            elif action.target == fault_svc:
                status = "DEGRADED"
                reward_value = 0.08
                reward_reason = "service degraded"
                evidence_found.add("health_fault_svc")
            elif action.target == "api-gateway":
                status = "DEGRADED"
                reward_value = 0.02
                reward_reason = "api-gateway is always a victim"
            else:
                status = random.choice(["UP", "UP", "DEGRADED"])
                reward_value = -0.02
                reward_reason = f"{action.target} appears healthy"
            message = f"Health check {action.target}: {status}"

        # ── run_db_query
        elif action.action_type == "run_db_query":
            result = _make_db_query_result(task)
            message = f"DB query result:\n{result}"

            if (fault_type in ("connection_pool_exhausted", "disk_full", "deadlock")
                    and "postgres" in action.target.lower()):
                reward_value = 0.18
                reward_reason = "DB query confirms root cause"
                evidence_found.add("db_query")
            else:
                reward_value = -0.05
                reward_reason = "DB query ran but not database-related fault"

        # ── restart_service
        elif action.action_type == "restart_service":
            _restart_fixes = ("oom_crash", "cpu_spike", "memory_leak",
                              "thread_pool_exhausted", "crash_loop", "null_pointer")
            seq_bonus = _compute_sequence_bonus(evidence_found, "restart_service")

            if action.target == fault_svc and fault_type in _restart_fixes:
                base_reward = 0.35
                reward_value = round(base_reward * seq_bonus, 4)
                reward_reason = f"correct service restarted"
                message = f"{action.target} restarted successfully. Error rate dropping."
            elif action.target == fault_svc:
                reward_value = -0.10
                reward_reason = f"restart is wrong fix for {fault_type}"
                message = f"{action.target} restarted but issue persists"
            else:
                reward_value = -0.30
                reward_reason = f"WRONG SERVICE restarted"
                message = f"{action.target} restarted — ERROR PERSISTS. Wrong target."

        # ── rollback_deployment
        elif action.action_type == "rollback_deployment":
            _rollback_fixes = ("bad_deployment", "canary_misconfiguration",
                               "cert_expired", "rate_limit_exceeded", "slow_query", "clock_skew")
            seq_bonus = _compute_sequence_bonus(evidence_found, "rollback_deployment")

            if action.target == fault_svc and fault_type in _rollback_fixes:
                base_reward = 0.35
                reward_value = round(base_reward * seq_bonus, 4)
                reward_reason = f"correct rollback"
                message = f"Rolled back {action.target}. Error rate recovering."
            elif action.target == fault_svc:
                reward_value = -0.10
                reward_reason = f"rollback is wrong fix for {fault_type}"
                message = f"Rolled back {action.target} but issue persists"
            else:
                reward_value = -0.30
                reward_reason = f"WRONG SERVICE rolled back"
                message = f"Rolled back {action.target} — no improvement. Wrong target."

        # ── declare_rca
        elif action.action_type == "declare_rca":
            done = True
            declared_services = set(s.strip() for s in action.target.split(","))
            fault_services = {fault_svc}
            if task.get("fault_service_2"):
                fault_services.add(task["fault_service_2"])

            seq_bonus = _compute_sequence_bonus(evidence_found, "declare_rca")
            evidence_bonus = len(evidence_found) * 0.04
            time_bonus = max(0.0, (max_steps - step_count) / max_steps) * 0.40

            if declared_services == fault_services:
                rca_base = 0.50
                reward_value = round(
                    rca_base * seq_bonus + time_bonus + evidence_bonus, 3
                )
                reward_value = min(reward_value, 0.999)
                reward_reason = f"CORRECT RCA: {fault_svc}!"
                message = f"Root cause confirmed: {', '.join(declared_services)} — Incident resolved.\n[END]"
            elif declared_services & fault_services:
                reward_value = 0.10
                reward_reason = f"partial RCA"
                message = f"Partial credit. You found {declared_services}.\n[END]"
            else:
                reward_value = -0.40
                reward_reason = f"WRONG RCA declared"
                message = f"INCORRECT. The fault was in {', '.join(fault_services)}.\n[END]"

    reward_value = round(reward_value, 4)

    obs = Observation(
        message=message,
        step=step_count,
        done=done,
        alert=task["alert"],
        metrics=metrics,
    )
    rew = Reward(value=max(-1.0, min(1.0, reward_value)), reason=reward_reason)
    info = {"step": step_count}
    
    return obs, rew, done, info
