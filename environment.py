import random
from typing import Any, Dict, Optional, Tuple
from models import Action, Observation, Reward

# ── Task definitions ──────────────────────────────────────────────────────────
# 9 tasks total: 3 easy, 3 medium, 3 hard
# New tasks drawn from real incidents at Netflix, Stripe, GitHub, Cloudflare, Meta

TASKS = {
    # ── NEW 9 TASKS (updated for current benchmark) ─────────────────────────

    "task_cpu_spike": {
        "name": "Auth service CPU hard loop",
        "difficulty": "easy",
        "max_steps": 10,
        "description": "A hot loop in JWT validation is pegging auth-service CPU at 99%.",
        "alert": "ALERT: Login latency p99 > 8s. Auth service CPU at 99%. Users cannot sign in.",
        "fault_service": "auth-service",
        "fault_type": "cpu_spike",
        "red_herrings": [],
        "ideal_steps": 5,
    },

    "task_db_connection_leak": {
        "name": "Database connection pool exhaustion",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Connection pool leak in order-service causing cascading failures.",
        "alert": "ALERT: Database connection timeouts. Order creation failing 100%. Latency spiking.",
        "fault_service": "order-service",
        "fault_type": "connection_pool_exhausted",
        "red_herrings": ["postgres-db"],
        "ideal_steps": 6,
    },

    "task_redis_memory_eviction": {
        "name": "Redis cache memory eviction cascade",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Redis memory threshold hit, evicting keys. Cache hit rate collapsing.",
        "alert": "ALERT: Cache miss rate 89%. redis-cache evicting keys. Session data loss. API latency 5000ms+.",
        "fault_service": "redis-cache",
        "fault_type": "memory_eviction",
        "red_herrings": ["api-gateway"],
        "ideal_steps": 5,
    },

    "task_api_rate_limit": {
        "name": "API rate limit misconfiguration",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Rate limiter threshold set too low, blocking legitimate traffic.",
        "alert": "ALERT: 429 Too Many Requests from api-gateway. Traffic being throttled. User impact increasing.",
        "fault_service": "api-gateway",
        "fault_type": "rate_limit_exceeded",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
    },

    "task_deadlock_order_service": {
        "name": "Database deadlock in order-service",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Concurrent order transactions causing PostgreSQL deadlock.",
        "alert": "ALERT: Database deadlock detected. orders_db throwing deadlock errors. Transactions rolling back.",
        "fault_service": "postgres-db",
        "fault_type": "deadlock",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
    },

    "task_ssl_cert_expired": {
        "name": "TLS certificate expiration",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "SSL certificate for api-gateway expired, causing TLS handshake failures.",
        "alert": "ALERT: TLS handshake failures on api-gateway. x509 certificate expired 3 days ago.",
        "fault_service": "api-gateway",
        "fault_type": "cert_expired",
        "red_herrings": [],
        "ideal_steps": 4,
    },

    "task_slow_query_postgres": {
        "name": "Slow PostgreSQL query degradation",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Missing database index causing full table scan on high-traffic query.",
        "alert": "ALERT: postgres-db query latency 8000ms+. Sequential scan on large table. order-service timing out.",
        "fault_service": "postgres-db",
        "fault_type": "slow_query",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
    },

    "task_auth_service_500": {
        "name": "Auth service internal server error",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Null pointer exception in auth token validation handler.",
        "alert": "ALERT: auth-service returning 500 errors. Token validation failing. Login completely down.",
        "fault_service": "auth-service",
        "fault_type": "null_pointer",
        "red_herrings": [],
        "ideal_steps": 5,
    },

    "task_k8s_pod_crashloop": {
        "name": "Kubernetes pod crash loop",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "notification-service pod in crash loop due to unhandled exception.",
        "alert": "ALERT: notification-service pod crashing (exit code 1). Crash loop detected. Email notifications blocked.",
        "fault_service": "notification-service",
        "fault_type": "crash_loop",
        "red_herrings": [],
        "ideal_steps": 5,
    },

    "task_disk_full": {
        "name": "Disk full — postgres WAL overflow",
        "difficulty": "easy",
        "max_steps": 10,
        "description": "The database WAL log grew unbounded after auto-vacuum was disabled. Disk hit 100% — all INSERT/UPDATE fail with ENOSPC.",
        "alert": "ALERT: postgres-db disk at 100%. WAL at 48GB. All write operations failing with ENOSPC.",
        "fault_service": "postgres-db",
        "fault_type": "disk_full",
        "red_herrings": [],
        "ideal_steps": 4,
    },

    "task_memory_leak": {
        "name": "Memory leak — notification service GC pauses",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "A memory leak in the email template renderer caused notification-service to grow from 400MB to 3.8GB. GC pauses now take 10+ seconds, cascading timeouts to api-gateway.",
        "alert": "ALERT: notification-service heap at 98%. GC pauses >11s. Email delivery stalling. API timeouts cascading.",
        "fault_service": "notification-service",
        "fault_type": "memory_leak",
        "red_herrings": [],
        "ideal_steps": 6,
    },

    "task_thread_starvation": {
        "name": "Thread pool exhaustion — auth service OAuth sync calls",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "A new OAuth integration added synchronous HTTP calls inside auth-service request handler. With 200 concurrent logins, all threads blocked waiting on I/O.",
        "alert": "ALERT: auth-service thread pool at 100% (200/200 active). Login latency 30s+. OAuth timeout cascade detected.",
        "fault_service": "auth-service",
        "fault_type": "thread_pool_exhausted",
        "red_herrings": [],
        "ideal_steps": 6,
    },

    "task_canary_poison": {
        "name": "Canary misconfiguration — api-gateway v2.1 strips auth headers",
        "difficulty": "hard",
        "max_steps": 20,
        "description": "A canary deployment of api-gateway v2.1 receives 10% of traffic. The canary build strips the Authorization header before forwarding.",
        "alert": "ALERT: 10% of requests returning 401 Unauthorized. Canary deployment v2.1 detected. Authorization header missing on canary traffic.",
        "fault_service": "api-gateway",
        "fault_type": "canary_misconfiguration",
        "red_herrings": ["order-service", "auth-service"],
        "ideal_steps": 5,
    },

    "task_clock_skew": {
        "name": "Clock skew — auth service NTP drift causes token rejections",
        "difficulty": "hard",
        "max_steps": 20,
        "description": "NTP daemon on auth-service's host was killed. Auth-service clock drifted 8 minutes ahead. JWTs it issues have future iat timestamps — other services reject them.",
        "alert": "ALERT: 25% of requests returning 401 from order-service. Cache miss rate 68%. JWT iat timestamps in future. Clock skew suspected.",
        "fault_service": "auth-service",
        "fault_type": "clock_skew",
        "red_herrings": ["redis-cache", "order-service"],
        "ideal_steps": 6,
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
    fault_svc   = task["fault_service"]
    fault_type  = task["fault_type"]
    red_herrings = task["red_herrings"]

    base = {
        "latency_p99_ms": random.randint(80, 200),
        "error_rate":     round(random.uniform(0.001, 0.015), 3),
        "cpu_pct":        random.randint(10, 35),
        "memory_pct":     random.randint(30, 55),
        "request_rate":   random.randint(200, 800),
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
                         "error_rate": 0.10,
                         "cpu_pct": random.randint(15, 30), "memory_pct": 40,
                         "canary_traffic_pct": 10, "canary_error_rate": 1.0})
        elif fault_type == "clock_skew":
            base.update({"latency_p99_ms": random.randint(300, 900),
                         "error_rate": round(random.uniform(0.20, 0.30), 3),
                         "cpu_pct": random.randint(25, 45), "memory_pct": 38,
                         "clock_drift_seconds": 480, "jwt_rejected_rate": 0.25})

    elif service in red_herrings:
        # looks suspicious but is not the cause
        if fault_type == "canary_misconfiguration":
            # order-service and auth-service show errors from bad routing
            base.update({"error_rate": round(random.uniform(0.08, 0.12), 3),
                         "latency_p99_ms": random.randint(400, 800)})
        elif fault_type == "clock_skew":
            # redis shows high miss rate; order shows auth rejections
            if service == "redis-cache":
                base.update({"cache_miss_rate": 0.68, "cpu_pct": random.randint(30, 55)})
            else:
                base.update({"error_rate": round(random.uniform(0.20, 0.28), 3),
                             "latency_p99_ms": random.randint(500, 1200)})
        else:
            base["cpu_pct"] = random.randint(85, 96)

    elif service == "api-gateway":
        # gateway always shows symptoms as it's the victim
        base.update({"latency_p99_ms": random.randint(3000, 5000),
                     "error_rate": round(random.uniform(0.3, 0.5), 3)})
    return base


def _make_logs(service: str, task: dict) -> str:
    fault_svc  = task["fault_service"]
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
        elif fault_type == "cpu_spike":
            return (
                f"[ERROR] {service}: thread saturation — 200/200 threads active\n"
                f"[ERROR] {service}: CPU 99% — hot loop detected in JWTValidator.validate()\n"
                f"[WARN]  {service}: request queue depth 847, new requests timing out"
            )
        elif fault_type == "disk_full":
            return (
                f"[FATAL] {service}: could not write to file \"pg_wal/000000010000002A\"\n"
                f"[ERROR] {service}: ENOSPC: No space left on device — WAL at 48GB\n"
                f"[ERROR] {service}: auto_vacuum disabled since 2026-04-02 maintenance window"
            )
        elif fault_type == "memory_leak":
            return (
                f"[ERROR] {service}: GC pause > 11240ms — Old generation 98% full\n"
                f"[ERROR] {service}: EmailTemplateCache holding 3.4GB unreferenced strings\n"
                f"[WARN]  {service}: heap used 3.8GB / 4.0GB — approaching OOM threshold"
            )
        elif fault_type == "thread_pool_exhausted":
            return (
                f"[ERROR] {service}: No threads available in pool (200/200 active)\n"
                f"[ERROR] {service}: OAuthIdentityClient timeout after 30000ms (blocked I/O)\n"
                f"[WARN]  {service}: timeout waiting for worker — 847 requests queued"
            )
        elif fault_type == "canary_misconfiguration":
            return (
                f"[ERROR] {service}: canary instance v2.1 stripping Authorization header\n"
                f"[WARN]  {service}: canary routing 10.2% of traffic to v2.1 (misconfigured)\n"
                f"[ERROR] {service}: downstream auth rejections on canary requests"
            )
        elif fault_type == "clock_skew":
            return (
                f"[ERROR] {service}: JWT iat=2026-04-09T11:23:00Z is in the future (clock drift: +8min)\n"
                f"[ERROR] {service}: NTP daemon not running — last sync 6 hours ago\n"
                f"[WARN]  {service}: system clock 480 seconds ahead of UTC"
            )

    elif service in task.get("red_herrings", []):
        fault_type_rh = task["fault_type"]
        if fault_type_rh == "canary_misconfiguration":
            if service == "order-service":
                return (
                    f"[ERROR] {service}: 401 Unauthorized from auth-service (missing token)\n"
                    f"[WARN]  {service}: 10.1% of checkout requests rejected at auth step\n"
                    f"[INFO]  {service}: no deployment changes in last 48h"
                )
            else:  # auth-service
                return (
                    f"[WARN]  {service}: receiving requests without Authorization header\n"
                    f"[ERROR] {service}: 401 returning for 10% of token validation requests\n"
                    f"[INFO]  {service}: auth-service itself functioning normally"
                )
        elif fault_type_rh == "clock_skew":
            if service == "redis-cache":
                return (
                    f"[WARN]  {service}: cache miss rate elevated (68%) — TTL miscalculation\n"
                    f"[INFO]  {service}: redis process healthy, memory 44%\n"
                    f"[INFO]  {service}: no configuration changes detected"
                )
            else:  # order-service
                return (
                    f"[ERROR] {service}: 25% of requests rejected with 401 Unauthorized\n"
                    f"[WARN]  {service}: JWT validation rejecting tokens as 'not yet valid'\n"
                    f"[INFO]  {service}: no deployment or config changes"
                )
        else:
            return (
                f"[WARN]  {service}: CPU spike detected (92%)\n"
                f"[INFO]  {service}: processing requests normally\n"
                f"[INFO]  {service}: no errors in last 5 minutes"
            )

    elif service == "api-gateway":
        return (
            f"[WARN]  {service}: upstream timeout from order-service (4800ms)\n"
            f"[ERROR] {service}: 502 Bad Gateway — notification-service unreachable\n"
            f"[INFO]  {service}: retry storm detected, rate limiting applied"
        )

    return (
        f"[INFO]  {service}: request processed in {random.randint(8, 25)}ms\n"
        f"[INFO]  {service}: health check OK\n"
        f"[DEBUG] {service}: connection pool usage 12/100"
    )


def _make_db_query_result(task: dict) -> str:
    fault_type = task["fault_type"]

    if fault_type == "connection_pool_exhausted":
        return (
            "active_connections | max_connections | waiting_queries\n"
            "-------------------+------------------+----------------\n"
            "        500        |       500        |       847\n"
            "(1 row)\n"
            "WARNING: connection pool at 100% capacity"
        )
    elif fault_type == "disk_full":
        return (
            "SELECT pg_size_pretty(pg_database_size('orders_db')), "
            "pg_size_pretty(pg_tablespace_size('pg_default'));\n"
            " database_size | tablespace_size\n"
            "---------------+----------------\n"
            "   280 GB      |    480 GB\n"
            "(1 row)\n"
            "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir();\n"
            " wal_size\n"
            "----------\n"
            "  48 GB\n"
            "FATAL: ENOSPC — disk at 100% capacity, WAL overflow"
        )
    elif fault_type in ("bad_deployment", "cpu_spike", "memory_leak",
                        "thread_pool_exhausted", "canary_misconfiguration", "clock_skew"):
        return (
            "SELECT * FROM pg_stat_activity WHERE state='idle in transaction';\n"
            " pid  | state  | query_start\n"
            "------+--------+-------------\n"
            "(0 rows)\n"
            "DB appears healthy — problem is upstream, not the database"
        )
    return (
        "query_time_ms | rows_returned\n"
        "--------------+--------------\n"
        "     4.2      |    1000\n"
        "(DB healthy)"
    )


# ── Main environment class ────────────────────────────────────────────────────

class IncidentResponseEnv:

    def __init__(self):
        self._task:                   Optional[dict] = None
        self._task_id:                Optional[str]  = None
        self._step_count:             int            = 0
        self._done:                   bool           = False
        self._cumulative_reward:      float          = 0.0
        self._actions_taken:          set            = set()
        self._relevant_evidence_found: set           = set()

    # ── reset ─────────────────────────────────────────────────────────────────

    def reset(self, task_id: str = "task_cpu_spike", seed: Optional[int] = None) -> Observation:
        if task_id not in TASKS:
            raise KeyError(f"Unknown task_id '{task_id}'. Available: {list(TASKS.keys())}")
        if seed is not None:
            random.seed(seed)
        else:
            random.seed(42)  # deterministic default for evaluator
        self._task_id                 = task_id
        self._task                    = TASKS[task_id].copy()
        self._step_count              = 0
        self._done                    = False
        self._cumulative_reward       = 0.0
        self._actions_taken           = set()
        self._relevant_evidence_found = set()
        return Observation(
            message=(
                f"Incident active. {self._task['description']} "
                f"You have {self._task['max_steps']} steps. Investigate carefully."
            ),
            step=0,
            done=False,
            alert=self._task["alert"],
        )

    # ── step ──────────────────────────────────────────────────────────────────

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        if self._done or self._task is None:
            raise RuntimeError("Episode finished. Call reset() first.")

        self._step_count += 1
        task       = self._task
        fault_svc  = task["fault_service"]
        fault_type = task["fault_type"]
        max_steps  = task["max_steps"]

        reward_value  = 0.001
        reward_reason = "no signal"
        message       = ""
        metrics       = None
        done          = False

        action_key = f"{action.action_type}:{action.target}"

        # ── deduplicate ───────────────────────────────────────────────────────
        if action_key in self._actions_taken and action.action_type != "declare_rca":
            reward_value  = 0.005
            reward_reason = "redundant action — already checked this"
            message       = f"You already checked {action.target} with {action.action_type}. No new information."
        else:
            self._actions_taken.add(action_key)

            # ── read_logs ─────────────────────────────────────────────────────
            if action.action_type == "read_logs":
                logs    = _make_logs(action.target, task)
                message = f"Logs from {action.target}:\n{logs}"
                if action.target == fault_svc:
                    reward_value  = 0.10
                    reward_reason = f"found fault evidence in {action.target} logs"
                    self._relevant_evidence_found.add("logs_fault_svc")
                elif action.target == "api-gateway":
                    reward_value  = 0.05
                    reward_reason = "gateway logs show symptoms (not root cause)"
                    self._relevant_evidence_found.add("logs_gateway")
                else:
                    reward_value  = 0.01
                    reward_reason = "no relevant signal in these logs"

            # ── check_metrics ─────────────────────────────────────────────────
            elif action.action_type == "check_metrics":
                met     = _make_metrics(action.target, task)
                metrics = {action.target: met}
                message = f"Metrics for {action.target}: {met}"
                if action.target == fault_svc:
                    reward_value  = 0.08
                    reward_reason = "fault service metrics show anomaly"
                    self._relevant_evidence_found.add("metrics_fault_svc")
                elif action.target in task["red_herrings"]:
                    reward_value  = 0.02
                    reward_reason = "metrics look suspicious but this is not the fault service"
                else:
                    reward_value  = 0.01
                    reward_reason = "metrics normal"

            # ── check_health ──────────────────────────────────────────────────
            elif action.action_type == "check_health":
                if action.target == fault_svc and fault_type in ("oom_crash", "disk_full", "cpu_spike"):
                    status        = "DOWN"
                    reward_value  = 0.07
                    reward_reason = "found downed service"
                    self._relevant_evidence_found.add("health_fault_svc")
                elif action.target == fault_svc:
                    status        = "DEGRADED"
                    reward_value  = 0.05
                    reward_reason = "service degraded — investigate further"
                    self._relevant_evidence_found.add("health_fault_svc")
                else:
                    status        = random.choice(["UP", "UP", "DEGRADED"])
                    reward_value  = 0.01
                    reward_reason = "service appears healthy"
                message = f"Health check {action.target}: {status}"

            # ── run_db_query ──────────────────────────────────────────────────
            elif action.action_type == "run_db_query":
                result  = _make_db_query_result(task)
                message = f"DB query result:\n{result}"
                if fault_type == "connection_pool_exhausted" and "postgres" in action.target.lower():
                    reward_value  = 0.12
                    reward_reason = "DB query confirms connection pool exhaustion"
                    self._relevant_evidence_found.add("db_query")
                elif fault_type == "disk_full" and "postgres" in action.target.lower():
                    reward_value  = 0.12
                    reward_reason = "DB query confirms WAL disk overflow"
                    self._relevant_evidence_found.add("db_query")
                else:
                    reward_value  = 0.01
                    reward_reason = "DB query ran, limited signal"

            # ── restart_service ───────────────────────────────────────────────
            elif action.action_type == "restart_service":
                _restart_fixes = ("oom_crash", "cpu_spike", "memory_leak", "thread_pool_exhausted")
                if action.target == fault_svc and fault_type in _restart_fixes:
                    reward_value  = 0.30
                    reward_reason = f"correct service restarted — {fault_type} resolved"
                    message       = f"{action.target} restarted successfully. Error rate dropping."
                elif action.target == fault_svc:
                    reward_value  = 0.10
                    reward_reason = "restarted fault service but wrong fix for this fault type"
                    message       = f"{action.target} restarted but issue persists — wrong fix."
                else:
                    reward_value  = 0.001
                    reward_reason = "wrong service restarted — near-zero reward"
                    message       = f"{action.target} restarted but errors persist. Wrong target."

            # ── rollback_deployment ───────────────────────────────────────────
            elif action.action_type == "rollback_deployment":
                _rollback_fixes = ("bad_deployment", "canary_misconfiguration")
                if action.target == fault_svc and fault_type in _rollback_fixes:
                    reward_value  = 0.30
                    reward_reason = f"correct rollback — {fault_type} resolved"
                    message       = f"Rolled back {action.target}. Error rate recovering."
                elif action.target == fault_svc:
                    reward_value  = 0.05
                    reward_reason = "rollback on fault service but not the right fix for this fault type"
                    message       = f"Rolled back {action.target} but issue persists — wrong fix type."
                else:
                    reward_value  = 0.001
                    reward_reason = "rolled back wrong service — near-zero reward"
                    message       = f"Rolled back {action.target} — no improvement. Wrong target."

            # ── declare_rca ───────────────────────────────────────────────────
            elif action.action_type == "declare_rca":
                done            = True
                self._done      = True
                evidence_bonus  = len(self._relevant_evidence_found) * 0.03
                time_bonus      = max(0.01, (max_steps - self._step_count) / max_steps) * 0.40

                if action.target == fault_svc:
                    reward_value  = round(0.50 + time_bonus + evidence_bonus, 3)
                    reward_value  = min(reward_value, 0.990)
                    reward_reason = (
                        f"correct RCA: {fault_svc}. "
                        f"time_bonus={time_bonus:.2f} evidence_bonus={evidence_bonus:.2f}"
                    )
                    message = f"Root cause confirmed: {fault_svc} — {fault_type}. Incident resolved."
                else:
                    reward_value  = 0.001
                    reward_reason = f"wrong RCA. Actual fault: {fault_svc}"
                    message       = f"Incorrect. The fault was in {fault_svc}, not {action.target}."

        # ── time pressure after 50% of steps ─────────────────────────────────
        if not done:
            progress = self._step_count / max_steps
            if progress > 0.5:
                scale        = 0.99 - 0.5 * ((progress - 0.5) / 0.5)
                reward_value = round(reward_value * scale, 4)
                reward_value = max(0.001, reward_value)

            if self._step_count >= max_steps:
                done       = True
                self._done = True
                message   += f"\n[SLA BREACHED] Max steps ({max_steps}) reached."

        reward_value              = round(reward_value, 4)
        self._cumulative_reward  += reward_value
        self._cumulative_reward   = round(max(0.001, min(0.990, self._cumulative_reward)), 4)

        obs = Observation(
            message=message,
            step=self._step_count,
            done=done,
            alert=self._task["alert"] if self._task else "",
            metrics=metrics,
        )
        rew  = Reward(value=reward_value, reason=reward_reason)
        info = {
            "step":               self._step_count,
            "cumulative_reward":  self._cumulative_reward,
            "evidence_found":     list(self._relevant_evidence_found),
        }
        return obs, rew, done, info

    # ── state ─────────────────────────────────────────────────────────────────

    def state(self) -> Dict[str, Any]:
        if self._task is None:
            return {"status": "not_started"}
        return {
            "task_id":              self._task_id,
            "task_name":            self._task["name"],
            "difficulty":           self._task["difficulty"],
            "hidden_fault_service": self._task["fault_service"],
            "hidden_fault_type":    self._task["fault_type"],
            "step_count":           self._step_count,
            "max_steps":            self._task["max_steps"],
            "done":                 self._done,
            "cumulative_reward":    self._cumulative_reward,
            "evidence_found":       list(self._relevant_evidence_found),
        }

    # ── grader ────────────────────────────────────────────────────────────────

    def grade(self) -> float:
        """Deterministic grader — returns float strictly in (0.001, 0.990)."""
        if not self._done:
            return 0.001
        return round(max(0.001, min(0.990, self._cumulative_reward)), 4)
