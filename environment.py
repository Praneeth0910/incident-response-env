import random
import uuid
from typing import Any, Dict, Optional, Tuple
from models import Action, Observation, Reward

# Judge integration
from judge.llm_client import LLMClient
from judge.llm_judge import AdversarialJudge
from reward import EvidenceTracker, compute_step_reward, compute_rca_reward

# ── Task definitions ──────────────────────────────────────────────────────────

TASKS = {
    "task_cpu_spike": {
        "name": "Auth service CPU hard loop",
        "domain": "cicd",
        "difficulty": "easy",
        "max_steps": 10,
        "description": "A hot loop in JWT validation is pegging auth-service CPU at 99%.",
        "alert": "ALERT: Login latency p99 > 8s. Auth service CPU at 99%. Users cannot sign in.",
        "fault_service": "auth-service",
        "fault_type": "cpu_spike",
        "red_herrings": [],
        "ideal_steps": 5,
        "cascade_step": None,
        "cascade_service": None,
        "cascade_fault": None,
    },
    "task_db_connection_leak": {
        "name": "Database connection pool exhaustion",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Connection pool leak in order-service causing cascading failures.",
        "alert": "ALERT: Database connection timeouts. Order creation failing 100%. Latency spiking.",
        "fault_service": "order-service",
        "fault_type": "connection_pool_exhausted",
        "red_herrings": ["postgres-db"],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "api-gateway",
        "cascade_fault": "upstream_timeout",
    },
    "task_redis_memory_eviction": {
        "name": "Redis cache memory eviction cascade",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Redis memory threshold hit, evicting keys. Cache hit rate collapsing.",
        "alert": "ALERT: Cache miss rate 89%. redis-cache evicting keys. Session data loss. API latency 5000ms+.",
        "fault_service": "redis-cache",
        "fault_type": "memory_eviction",
        "red_herrings": ["api-gateway"],
        "ideal_steps": 5,
        "cascade_step": 9,
        "cascade_service": "order-service",
        "cascade_fault": "downstream_victim",
    },
    "task_api_rate_limit": {
        "name": "API rate limit misconfiguration",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Rate limiter threshold set too low, blocking legitimate traffic.",
        "alert": "ALERT: 429 Too Many Requests from api-gateway. Traffic being throttled. User impact increasing.",
        "fault_service": "api-gateway",
        "fault_type": "rate_limit_exceeded",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "auth-service",
        "cascade_fault": "rate_limit_victim",
    },
    "task_deadlock_order_service": {
        "name": "Database deadlock in order-service",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Concurrent order transactions causing PostgreSQL deadlock.",
        "alert": "ALERT: Database deadlock detected. orders_db throwing deadlock errors. Transactions rolling back.",
        "fault_service": "postgres-db",
        "fault_type": "deadlock",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "notification-service",
        "cascade_fault": "connection_exhausted",
    },
    "task_ssl_cert_expired": {
        "name": "TLS certificate expiration",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "SSL certificate for api-gateway expired, causing TLS handshake failures.",
        "alert": "ALERT: TLS handshake failures on api-gateway. x509 certificate expired 3 days ago.",
        "fault_service": "api-gateway",
        "fault_type": "cert_expired",
        "red_herrings": [],
        "ideal_steps": 4,
        "cascade_step": 9,
        "cascade_service": "auth-service",
        "cascade_fault": "handshake_victim",
    },
    "task_slow_query_postgres": {
        "name": "Slow PostgreSQL query degradation",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Missing database index causing full table scan on high-traffic query.",
        "alert": "ALERT: postgres-db query latency 8000ms+. Sequential scan on large table. order-service timing out.",
        "fault_service": "postgres-db",
        "fault_type": "slow_query",
        "red_herrings": ["order-service"],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "notification-service",
        "cascade_fault": "query_timeout_victim",
    },
    "task_auth_service_500": {
        "name": "Auth service internal server error",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Null pointer exception in auth token validation handler.",
        "alert": "ALERT: auth-service returning 500 errors. Token validation failing. Login completely down.",
        "fault_service": "auth-service",
        "fault_type": "null_pointer",
        "red_herrings": [],
        "ideal_steps": 5,
        "cascade_step": 9,
        "cascade_service": "order-service",
        "cascade_fault": "auth_timeout_victim",
    },
    "task_k8s_pod_crashloop": {
        "name": "Kubernetes pod crash loop",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "notification-service pod in crash loop due to unhandled exception.",
        "alert": "ALERT: notification-service pod crashing (exit code 1). Crash loop detected. Email notifications blocked.",
        "fault_service": "notification-service",
        "fault_type": "crash_loop",
        "red_herrings": [],
        "ideal_steps": 5,
        "cascade_step": 9,
        "cascade_service": "api-gateway",
        "cascade_fault": "notification_unavailable_victim",
    },
    "task_disk_full": {
        "name": "Disk full — postgres WAL overflow",
        "domain": "cicd",
        "difficulty": "easy",
        "max_steps": 10,
        "description": "The database WAL log grew unbounded. Disk hit 100% — all INSERT/UPDATE fail with ENOSPC.",
        "alert": "ALERT: postgres-db disk at 100%. WAL at 48GB. All write operations failing with ENOSPC.",
        "fault_service": "postgres-db",
        "fault_type": "disk_full",
        "red_herrings": [],
        "ideal_steps": 4,
        "cascade_step": None,
        "cascade_service": None,
        "cascade_fault": None,
    },
    "task_memory_leak": {
        "name": "Memory leak — notification service GC pauses",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "Memory leak in email template renderer. GC pauses now take 10+ seconds.",
        "alert": "ALERT: notification-service heap at 98%. GC pauses >11s. Email delivery stalling. API timeouts cascading.",
        "fault_service": "notification-service",
        "fault_type": "memory_leak",
        "red_herrings": [],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "api-gateway",
        "cascade_fault": "upstream_timeout",
    },
    "task_thread_starvation": {
        "name": "Thread pool exhaustion — auth service OAuth sync calls",
        "domain": "cicd",
        "difficulty": "medium",
        "max_steps": 15,
        "description": "New OAuth integration added synchronous HTTP calls inside auth-service request handler.",
        "alert": "ALERT: auth-service thread pool at 100% (200/200 active). Login latency 30s+. OAuth timeout cascade detected.",
        "fault_service": "auth-service",
        "fault_type": "thread_pool_exhausted",
        "red_herrings": [],
        "ideal_steps": 6,
        "cascade_step": 9,
        "cascade_service": "order-service",
        "cascade_fault": "auth_timeout_victim",
    },
    "task_canary_poison": {
        "name": "Canary misconfiguration — api-gateway v2.1 strips auth headers",
        "domain": "cicd",
        "difficulty": "hard",
        "max_steps": 20,
        "description": "A canary deployment of api-gateway v2.1 receives 10% of traffic and strips the Authorization header.",
        "alert": "ALERT: 10% of requests returning 401 Unauthorized. Canary deployment v2.1 detected. Authorization header missing on canary traffic.",
        "fault_service": "api-gateway",
        "fault_type": "canary_misconfiguration",
        "red_herrings": ["order-service", "auth-service"],
        "ideal_steps": 5,
        "cascade_step": 6,
        "cascade_service": "order-service",
        "cascade_fault": "canary_victim",
    },
    "task_clock_skew": {
        "name": "Clock skew — auth service NTP drift causes token rejections",
        "domain": "cicd",
        "difficulty": "hard",
        "max_steps": 20,
        "description": "NTP daemon on auth-service host killed. Auth-service clock drifted 8 minutes ahead.",
        "alert": "ALERT: 25% of requests returning 401 from order-service. Cache miss rate 68%. JWT iat timestamps in future. Clock skew suspected.",
        "fault_service": "auth-service",
        "fault_type": "clock_skew",
        "red_herrings": ["redis-cache", "order-service"],
        "ideal_steps": 6,
        "cascade_step": 6,
        "cascade_service": "redis-cache",
        "cascade_fault": "token_cache_miss",
    },
    "task_expert": {
        "name": "Multi-root-cause: Redis + Auth config failure",
        "domain": "cicd",
        "difficulty": "hard",
        "max_steps": 25,
        "description": (
            "Two independent failures: Redis connection pool exhausted "
            "AND auth-service misconfigured after canary deploy. Both must be identified."
        ),
        "alert": (
            "ALERT: Login failures 62%. Order completions 0%. "
            "On-call paged. Multiple cascading signals."
        ),
        "fault_service": "redis-cache",
        "fault_type": "connection_pool_exhausted",
        "fault_service_2": "auth-service",
        "fault_type_2": "bad_deployment",
        "red_herrings": ["order-service", "notification-service"],
        "ideal_steps": 12,
        "cascade_step": 8,
        "cascade_service": "api-gateway",
        "cascade_fault": "upstream_overload",
    },
    "task_expert_long_horizon": {
        "name": "Long-horizon cascade: Query degradation with latent secondary fault",
        "domain": "cicd",
        "difficulty": "hard",
        "max_steps": 50,
        "description": (
            "LONG-HORIZON TEST (50 steps). postgres-db slow_query causes gradual degradation. "
            "Quick restart (step ~10) seems to fix it, but introduces a secondary bug in the query planner. "
            "At step 35+, a cascade triggers in order-service. Agent must track state over extended episode, "
            "detect the secondary fault, and implement the correct fix. Tests if agent avoids jumping to "
            "quick conclusions and maintains context across 50-step trajectory."
        ),
        "alert": (
            "ALERT: Order creation latency p99: 500ms → 2000ms → 8000ms (steadily worsening). "
            "postgres-db query time spiking. Partial order backlog forming."
        ),
        "fault_service": "postgres-db",
        "fault_type": "slow_query",
        "fault_service_2": None,
        "fault_type_2": None,
        "red_herrings": ["api-gateway", "redis-cache"],
        "ideal_steps": 25,
        "cascade_step": 35,
        "cascade_service": "order-service",
        "cascade_fault": "downstream_timeout",
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

def _make_metrics(service: str, task: dict,
                  cascade_triggered: bool = False,
                  cascade_service: str = "") -> Dict[str, Any]:
    fault_svc    = task["fault_service"]
    fault_type   = task["fault_type"]
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
            latency = random.randint(2000, 10000)
            error_rate = round(random.uniform(0.1, 0.95), 2)
            cpu = random.randint(85, 100)
            thread = random.randint(150, 250)
            base.update({"latency_p99_ms": latency, "error_rate": error_rate,
                         "cpu_pct": cpu, "memory_pct": 42, "request_rate": random.randint(10, 50),
                         "thread_pool_active": thread, "thread_pool_max": 200})
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
            "error_rate":     round(random.uniform(0.35, 0.65), 3),
            "cpu_pct":        random.randint(65, 88),
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


def _make_logs(service: str, task: dict,
               cascade_triggered: bool = False,
               cascade_service: str = "") -> str:
    fault_svc  = task["fault_service"]
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
            cpu = random.randint(85, 100)
            thread = random.randint(150, 250)
            logs = (f"[ERROR] {service}: thread saturation — {thread}/200 threads active\n"
                    f"[ERROR] {service}: CPU {cpu}% — hot loop detected in JWTValidator.validate()\n"
                    f"[WARN]  {service}: request queue depth {random.randint(500, 1000)}, new requests timing out")
            if random.random() < 0.3:
                logs += "\n[DEBUG] cache miss spike observed"
            return logs
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


def _make_db_query_result(task: dict) -> str:
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


# ═══════════════════════════════════════════════════════════════════════════════
# ███  POWERFUL REWARD FUNCTION — DESIGNED FOR SHARP RL LEARNING  ███
# ═══════════════════════════════════════════════════════════════════════════════
#
# PHILOSOPHY:
#   A reward function that makes an LLM learn to think like a real SRE.
#   Four principles drive every design decision:
#
#   1. REAL PENALTIES for wrong actions — bad guesses must HURT, not give
#      tiny positive floors. The LLM must learn that wrong interventions
#      have consequences.
#
#   2. SEQUENCE MATTERS — rewards increase if the agent follows the correct
#      investigation order: observe → hypothesize → confirm → fix → declare.
#      Skipping steps or acting randomly gets lower rewards even if "correct".
#
#   3. EFFICIENCY BONUS — solving it faster with fewer steps gives a bigger
#      reward. Every wasted step costs the agent.
#
#   4. EXPLORATION DIVERSITY — checking the same thing twice gets punished
#      harder as the episode progresses, teaching the agent to be decisive.
#
# REWARD RANGES (summary):
#   read_logs (fault svc)        → +0.15  (strong log evidence)
#   read_logs (api-gateway)      → +0.05  (symptom only)
#   read_logs (other)            → -0.02  (wasted step)
#   check_metrics (fault svc)    → +0.12  (anomaly confirmed)
#   check_metrics (red herring)  → -0.05  (misled — learn to resist)
#   check_metrics (other)        → -0.03  (wasted step)
#   check_health (fault svc)     → +0.10  (service status found)
#   check_health (other)         → -0.02  (wasted step)
#   run_db_query (confirming)    → +0.18  (strongest single evidence)
#   run_db_query (not relevant)  → -0.05  (wrong tool for this task)
#   restart_service (correct)    → +0.35  (correct fix)
#   restart_service (wrong)      → -0.30  (real penalty — wrong intervention)
#   rollback_deployment (correct)→ +0.35  (correct fix)
#   rollback_deployment (wrong)  → -0.30  (real penalty)
#   redundant action             → -0.08 to -0.20 (escalating penalty)
#   declare_rca (correct)        → +0.50 + time bonus + sequence bonus
#   declare_rca (wrong)          → -0.40  (big penalty — overconfident guess)
#
# FINAL SCORE: clamped to [-1.0, 1.0] during episode,
#              then grade() maps to [0.001, 0.999] for competition

def _compute_sequence_bonus(evidence_found: set, action_type: str) -> float:
    """
    Bonus multiplier for following the correct investigation sequence.
    A good SRE observes → measures → confirms → fixes → declares.
    Acting out of order reduces the reward signal.
    """
    has_logs    = "logs_fault_svc" in evidence_found or "logs_gateway" in evidence_found
    has_metrics = "metrics_fault_svc" in evidence_found
    has_health  = "health_fault_svc" in evidence_found

    if action_type == "restart_service" or action_type == "rollback_deployment":
        # Should have at least 2 evidence types before intervening
        evidence_count = sum([has_logs, has_metrics, has_health])
        if evidence_count >= 2:
            return 1.0    # full reward — well investigated
        elif evidence_count == 1:
            return 0.6    # partial — rushed but had some evidence
        else:
            return 0.0    # blind action — no reward at all

    if action_type == "declare_rca":
        evidence_count = sum([has_logs, has_metrics, has_health])
        if evidence_count >= 3:
            return 1.0    # full bonus — thorough
        elif evidence_count == 2:
            return 0.8
        elif evidence_count == 1:
            return 0.5
        else:
            return 0.1    # blind guess

    return 1.0


def _compute_redundancy_penalty(step_count: int, max_steps: int) -> float:
    """
    Penalty for repeating actions escalates as the episode progresses.
    Early repeat: mild warning. Late repeat: harsh punishment.
    This teaches the LLM to commit to decisions under time pressure.
    """
    progress = step_count / max_steps
    if progress < 0.3:
        return -0.08   # early repeat: gentle nudge
    elif progress < 0.6:
        return -0.12   # mid-episode repeat: real cost
    else:
        return -0.20   # late repeat: serious punishment — be decisive!


class IncidentResponseEnv:

    def __init__(self):
        self._task:                    Optional[dict] = None
        self._task_id:                 Optional[str]  = None
        self._step_count:              int            = 0
        self._done:                    bool           = False
        self._cumulative_reward:       float          = 0.0
        self._actions_taken:           set            = set()
        self._relevant_evidence_found: set            = set()
        self._run_id:                  str            = ""
        self._cascade_triggered:       bool           = False
        self._rca_declared:            bool           = False
        self._rca_correct:             bool           = False
        # New: track wrong interventions for grade penalty
        self._wrong_interventions:     int            = 0
        # LLM judge + history for phase-aware evaluation
        self._llm_client: Optional[LLMClient] = None
        self._judge: Optional[AdversarialJudge] = None
        self._history: list[dict] = []
        # Evidence tracker for Phase 4 reward functions
        self._evidence: Optional[EvidenceTracker] = None

    def reset(self, task_id: str = "task_cpu_spike", seed: Optional[int] = None) -> Observation:
        if task_id not in TASKS:
            raise KeyError(f"Unknown task_id '{task_id}'. Available: {list(TASKS.keys())}")
        if seed is not None:
            random.seed(seed)
        else:
            random.seed(42)
        self._task_id                  = task_id
        self._task                     = TASKS[task_id].copy()
        if "domain" not in self._task:
            raise ValueError(f"Task schema validation failed: '{task_id}' is missing the required 'domain' key.")
        self._step_count               = 0
        self._done                     = False
        self._cumulative_reward        = 0.0
        self._actions_taken            = set()
        self._relevant_evidence_found  = set()
        self._run_id                   = str(uuid.uuid4())
        self._cascade_triggered        = False
        self._rca_declared             = False
        self._rca_correct              = False
        self._wrong_interventions      = 0
        # Initialize or reset judge client and history
        # Initialize per-episode evidence tracker used by reward.py
        self._evidence = EvidenceTracker()
        try:
            self._llm_client = LLMClient()
            self._judge = AdversarialJudge(self._llm_client)
        except (ImportError, ConnectionError) as e:
            import logging
            # If judge can't be constructed (missing deps), leave as None
            logging.warning(f"LLM judge not initialized: {e}")
            self._llm_client = None
            self._judge = None
        self._history = []
        return Observation(
            message=(
                f"Incident active. "
                f"You have {self._task['max_steps']} steps. Investigate carefully."
            ),
            step=0,
            done=False,
            alert=self._task["alert"],
            info={"run_id": self._run_id},
        )

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, Any]]:
        if self._done or self._task is None:
            raise RuntimeError("Episode finished. Call reset() first.")

        self._step_count += 1
        task       = self._task
        fault_svc  = task["fault_service"]
        fault_type = task["fault_type"]
        max_steps  = task["max_steps"]

        reward_value  = 0.0
        reward_reason = "no signal"
        message       = ""
        metrics       = None
        done          = False

        action_key = f"{action.action_type}:{action.target}"
        was_redundant = False

        # Compute redundancy flag once, used by both inline and centralized reward paths
        was_redundant = action_key in self._actions_taken and action.action_type != "declare_rca"

        # ── REDUNDANT ACTION — escalating penalty ─────────────────────────────
        if was_redundant:
            reward_value  = _compute_redundancy_penalty(self._step_count, max_steps)
            reward_reason = (
                f"redundant action — already checked {action.target} with "
                f"{action.action_type}. Penalty escalates as episode progresses."
            )
            message = (
                f"You already checked {action.target} with {action.action_type}. "
                f"No new information. Penalty: {reward_value:+.2f}"
            )

        else:
            self._actions_taken.add(action_key)

            # ── read_logs ─────────────────────────────────────────────────────
            if action.action_type == "read_logs":
                logs    = _make_logs(action.target, task,
                                     self._cascade_triggered,
                                     task.get("cascade_service", ""))
                message = f"Logs from {action.target}:\n{logs}"

                if action.target == fault_svc:
                    reward_value  = 0.15
                    reward_reason = f"strong evidence found in {action.target} logs"
                    self._relevant_evidence_found.add("logs_fault_svc")
                elif action.target == "api-gateway":
                    reward_value  = 0.05
                    reward_reason = "gateway logs show symptoms — it is a VICTIM, not root cause"
                    self._relevant_evidence_found.add("logs_gateway")
                else:
                    # Checking irrelevant services costs a small penalty
                    reward_value  = -0.02
                    reward_reason = f"no relevant signal in {action.target} logs — wasted step"

            # ── check_metrics ─────────────────────────────────────────────────
            elif action.action_type == "check_metrics":
                met     = _make_metrics(action.target, task,
                                        self._cascade_triggered,
                                        task.get("cascade_service", ""))
                metrics = {action.target: met}
                message = f"Metrics for {action.target}: {met}"

                if action.target == fault_svc:
                    reward_value  = 0.12
                    reward_reason = "fault service metrics show anomaly — strong signal"
                    self._relevant_evidence_found.add("metrics_fault_svc")
                elif action.target in task["red_herrings"]:
                    # Penalise falling for red herrings — this is the key learning signal
                    reward_value  = -0.05
                    reward_reason = (
                        f"{action.target} looks suspicious but is NOT the root cause — "
                        f"red herring! Learn to cross-reference with logs before acting."
                    )
                else:
                    reward_value  = -0.03
                    reward_reason = f"metrics for {action.target} are normal — wasted step"

            # ── check_health ──────────────────────────────────────────────────
            elif action.action_type == "check_health":
                if action.target == fault_svc and fault_type in ("oom_crash", "disk_full", "cpu_spike"):
                    status        = "DOWN"
                    reward_value  = 0.10
                    reward_reason = "found downed service — clear signal"
                    self._relevant_evidence_found.add("health_fault_svc")
                elif action.target == fault_svc:
                    status        = "DEGRADED"
                    reward_value  = 0.08
                    reward_reason = "service degraded — investigate further with logs/metrics"
                    self._relevant_evidence_found.add("health_fault_svc")
                elif action.target == "api-gateway":
                    status        = "DEGRADED"
                    reward_value  = 0.02
                    reward_reason = "api-gateway is always a victim — check upstream services"
                else:
                    status        = random.choice(["UP", "UP", "DEGRADED"])
                    reward_value  = -0.02
                    reward_reason = f"{action.target} appears healthy — wasted step"
                message = f"Health check {action.target}: {status}"

            # ── run_db_query ──────────────────────────────────────────────────
            elif action.action_type == "run_db_query":
                result  = _make_db_query_result(task)
                message = f"DB query result:\n{result}"

                if fault_type in ("connection_pool_exhausted", "disk_full", "deadlock") \
                        and "postgres" in action.target.lower():
                    reward_value  = 0.18
                    reward_reason = "DB query confirms root cause — highest-value evidence type"
                    self._relevant_evidence_found.add("db_query")
                else:
                    reward_value  = -0.05
                    reward_reason = (
                        "DB query ran but this fault is not database-related — "
                        "wrong tool for this task. Read logs first."
                    )

            # ── restart_service ───────────────────────────────────────────────
            elif action.action_type == "restart_service":
                _restart_fixes  = ("oom_crash", "cpu_spike", "memory_leak",
                                    "thread_pool_exhausted", "crash_loop",
                                    "null_pointer")
                seq_bonus = _compute_sequence_bonus(
                    self._relevant_evidence_found, "restart_service"
                )
                
                # Support multi-fault scenarios
                fault_svc_2 = task.get("fault_service_2")
                fault_type_2 = task.get("fault_type_2")
                
                # Check if this is a correct fix for either fault service
                is_correct_fix = False
                matched_fault_type = None
                if action.target == fault_svc and fault_type in _restart_fixes:
                    is_correct_fix = True
                    matched_fault_type = fault_type
                elif fault_svc_2 and action.target == fault_svc_2 and fault_type_2 in _restart_fixes:
                    is_correct_fix = True
                    matched_fault_type = fault_type_2
                
                if is_correct_fix:
                    base_reward   = 0.35
                    reward_value  = round(base_reward * seq_bonus, 4)
                    reward_reason = (
                        f"correct service restarted — {matched_fault_type} resolved. "
                        f"Sequence bonus: {seq_bonus:.1f}x "
                        f"({'well investigated' if seq_bonus >= 0.8 else 'rushed — investigate more first'})"
                    )
                    message = f"{action.target} restarted successfully. Error rate dropping."
                elif action.target == fault_svc or (fault_svc_2 and action.target == fault_svc_2):
                    reward_value  = -0.10
                    reward_reason = (
                        f"restarted {action.target} but restart is wrong fix for this fault. "
                        f"Use rollback_deployment for deployment faults."
                    )
                    message = f"{action.target} restarted but issue persists — wrong fix type."
                    self._wrong_interventions += 1
                else:
                    # REAL PENALTY for wrong service — this is what teaches the LLM
                    reward_value  = -0.30
                    reward_reason = (
                        f"WRONG SERVICE restarted — {action.target} is not the fault. "
                        f"This is a serious error. Gather evidence before acting."
                    )
                    message = f"{action.target} restarted — ERROR PERSISTS. Wrong target."
                    self._wrong_interventions += 1

            # ── rollback_deployment ───────────────────────────────────────────
            elif action.action_type == "rollback_deployment":
                _rollback_fixes = ("bad_deployment", "canary_misconfiguration",
                                   "secret_rotation_break", "clock_skew", "disk_full",
                                   "cert_expired", "null_pointer", "crash_loop")
                seq_bonus = _compute_sequence_bonus(
                    self._relevant_evidence_found, "rollback_deployment"
                )
                
                # Support multi-fault scenarios
                fault_svc_2 = task.get("fault_service_2")
                fault_type_2 = task.get("fault_type_2")
                
                # Check if this is a correct fix for either fault service
                is_correct_fix = False
                matched_fault_type = None
                if action.target == fault_svc and fault_type in _rollback_fixes:
                    is_correct_fix = True
                    matched_fault_type = fault_type
                elif fault_svc_2 and action.target == fault_svc_2 and fault_type_2 in _rollback_fixes:
                    is_correct_fix = True
                    matched_fault_type = fault_type_2
                
                if is_correct_fix:
                    base_reward   = 0.35
                    reward_value  = round(base_reward * seq_bonus, 4)
                    reward_reason = (
                        f"correct rollback — {matched_fault_type} resolved. "
                        f"Sequence bonus: {seq_bonus:.1f}x"
                    )
                    message = f"Rolled back {action.target}. Error rate recovering."
                elif action.target == fault_svc or (fault_svc_2 and action.target == fault_svc_2):
                    reward_value  = -0.10
                    reward_reason = (
                        f"rollback on {action.target} but rollback is wrong fix for this fault. "
                        f"Use restart_service for runtime faults."
                    )
                    message = f"Rolled back {action.target} but issue persists — wrong fix type."
                    self._wrong_interventions += 1
                else:
                    reward_value  = -0.30
                    reward_reason = (
                        f"WRONG SERVICE rolled back — {action.target} is not the fault. "
                        f"Serious error. Read logs and metrics before intervening."
                    )
                    message = f"Rolled back {action.target} — no improvement. Wrong target."
                    self._wrong_interventions += 1

            # ── declare_rca ───────────────────────────────────────────────────
            elif action.action_type == "declare_rca":
                done            = True
                self._done      = True
                self._rca_declared = True

                declared_services = set(s.strip() for s in action.target.split(","))
                fault_services    = {fault_svc}
                if task.get("fault_service_2"):
                    fault_services.add(task["fault_service_2"])

                seq_bonus      = _compute_sequence_bonus(
                    self._relevant_evidence_found, "declare_rca"
                )
                evidence_bonus = len(self._relevant_evidence_found) * 0.04
                time_bonus     = max(0.0, (max_steps - self._step_count) / max_steps) * 0.40

                if declared_services == fault_services:
                    self._rca_correct = True
                    rca_base      = 0.50
                    # Prefer central RCA reward calculation when evidence tracker available
                    if self._evidence is not None and len(declared_services) == 1:
                        declared = next(iter(declared_services))
                        try:
                            reward_value = compute_rca_reward(declared, task, self._step_count, self._evidence)
                        except Exception:
                            reward_value = round(
                                rca_base * seq_bonus + time_bonus + evidence_bonus, 3
                            )
                    else:
                        reward_value = round(
                            rca_base * seq_bonus + time_bonus + evidence_bonus, 3
                        )
                    reward_value  = min(reward_value, 0.999)
                    reward_reason = (
                        f"CORRECT RCA: {fault_svc}! "
                        f"evidence_bonus={evidence_bonus:.2f} "
                        f"time_bonus={time_bonus:.2f} "
                        f"sequence_bonus={seq_bonus:.2f}"
                    )
                    message = f"Root cause confirmed: {', '.join(declared_services)} — Incident resolved.\n[END]"
                elif declared_services & fault_services:
                    self._rca_correct = False
                    reward_value  = 0.10
                    reward_reason = (
                        f"partial RCA: found {declared_services}, "
                        f"missed {fault_services - declared_services}"
                    )
                    message = f"Partial credit. You found {declared_services} but missed {fault_services - declared_services}.\n[END]"
                else:
                    # REAL PENALTY for confident wrong answer
                    self._rca_correct = False
                    reward_value  = -0.40
                    reward_reason = (
                        f"WRONG RCA declared. Actual fault: {fault_services}. "
                        f"You declared: {declared_services}. "
                        f"This is the worst outcome — overconfident wrong answer."
                    )
                    message = f"INCORRECT. The fault was in {', '.join(fault_services)}, not {action.target}.\n[END]"

        # --- Centralized step reward (Phase 4): let reward.py compute step rewards
        try:
            # Only compute central rewards for non-redundant actions
            if not was_redundant and action.action_type != "declare_rca":
                # Domain-specific action mappings for reward computation
                cicd_reward_map = {
                    "read_logs": "read_job_logs",
                    "check_metrics": "get_cluster_metrics",
                    "check_health": "check_runner_status",
                    "run_db_query": "run_db_query",
                    "restart_service": "restart_service",
                    "rollback_deployment": "rollback_deployment",
                    "declare_rca": "declare_rca",
                }
                kafka_reward_map = {
                    "read_logs": "read_consumer_logs",
                    "check_metrics": "get_cluster_metrics",
                    "check_health": "check_isr_status",
                    "declare_rca": "declare_rca",
                }
                task_domain = task.get("domain", "cicd")
                action_map_reward = cicd_reward_map if task_domain == "cicd" else kafka_reward_map
                reward_action = action_map_reward.get(action.action_type, action.action_type)
                try:
                    # normalize history entries to reward-action names for redundancy detection
                    actions_conv = [action_map_reward.get(k.split(':', 1)[0], k.split(':', 1)[0]) for k in self._actions_taken]
                    computed = compute_step_reward(reward_action, task, self._step_count, actions_conv, self._evidence, observation=message)
                    if isinstance(computed, float) and computed != 0.0:
                        reward_value = round(computed, 4)
                        reward_reason = f"reward.py computed ({reward_action})"
                except Exception as e:
                    print(f"[ERROR] reward.py compute_step_reward failed: {e}")
        except Exception as e:
            print(f"[ERROR] Critical failure in phase 4 centralized reward block: {e}")

        # ── cascade mechanic ──────────────────────────────────────────────────
        cascade_step = task.get("cascade_step")
        cascade_svc  = task.get("cascade_service")
        if (cascade_step is not None and not self._cascade_triggered
                and self._step_count >= cascade_step and not done):
            self._cascade_triggered = True
            cascade_note = (
                f"\n[CASCADE] {cascade_svc} is now DEGRADED — "
                f"new errors propagating. Investigate urgently."
            )
            message += cascade_note

        # ── time pressure after 50% of steps ─────────────────────────────────
        if not done:
            progress = self._step_count / max_steps
            if progress > 0.5:
                # Only scale UP negative rewards for urgency
                # Positive rewards are NOT scaled down - doing the right thing late
                # is still better than doing nothing. Time bonus in declare_rca
                # already incentivizes efficiency.
                if reward_value < 0:
                    # Negative rewards get WORSE under time pressure
                    scale        = 1.0 + 0.3 * ((progress - 0.5) / 0.5)
                    reward_value = round(reward_value * scale, 4)

            if self._step_count >= max_steps:
                done       = True
                self._done = True
                message    = message + f"\n[SLA BREACHED] Max steps ({max_steps}) reached.\n[END]"

        reward_value             = round(reward_value, 4)
        self._cumulative_reward += reward_value
        # Cumulative clamped to [-1.0, 1.0] during episode
        self._cumulative_reward  = round(max(-1.0, min(1.0, self._cumulative_reward)), 4)

        obs = Observation(
            message=message,
            step=self._step_count,
            done=done,
            alert=self._task["alert"] if self._task else "",
            metrics=metrics,
        )
        rew  = Reward(value=max(-1.0, min(1.0, reward_value)), reason=reward_reason)
        info = {
            "step":                  self._step_count,
            "cumulative_reward":     self._cumulative_reward,
            "evidence_found":        list(self._relevant_evidence_found),
            "wrong_interventions":   self._wrong_interventions,
        }

        # Run the LLM judge (best-effort). Map local action types to judge action names.
        try:
            if self._judge is not None:
                # Domain-specific action mappings: environment actions → judge-expected actions
                cicd_action_map = {
                    "read_logs": "read_job_logs",
                    "check_metrics": "check_runner_status",
                    "check_health": "check_runner_status",
                    "run_db_query": "read_audit_log",
                    "restart_service": "restart_service",
                    "rollback_deployment": "rollback_workflow",
                    "declare_rca": "declare_rca",
                }
                kafka_action_map = {
                    "read_logs": "read_consumer_logs",
                    "check_metrics": "get_cluster_metrics",
                    "check_health": "check_isr_status",
                    "run_db_query": "describe_consumer_group",
                    "restart_service": "restart_consumer_group",
                    "rollback_deployment": "skip_offset",
                    "declare_rca": "declare_rca",
                }
                
                task_domain = task.get("domain", "cicd")
                action_map = cicd_action_map if task_domain == "cicd" else kafka_action_map
                judge_action = action_map.get(action.action_type, action.action_type)
                
                task_context = {
                    "domain": task_domain,
                    "alert_message": task.get("alert"),
                    "root_cause": task.get("description"),
                    "fault_type": task.get("fault_type"),
                    "fault_component": task.get("fault_service"),
                    # ideal_steps is an int in TASKS; judge expects a list for resolution_steps
                    "resolution_steps": [str(task.get("ideal_steps", ""))],
                    "difficulty": task.get("difficulty"),
                    "max_steps": task.get("max_steps"),
                    "red_herrings": task.get("red_herrings", []),
                }
                res = self._judge.evaluate(judge_action, message, task_context, self._history)
                judge_score = None
                judge_feedback = None
                judge_missed = None
                if isinstance(res, tuple):
                    if len(res) == 3:
                        judge_score, judge_feedback, judge_missed = res
                    elif len(res) == 2:
                        judge_score, judge_feedback = res
                else:
                    try:
                        judge_score = float(res)
                    except Exception:
                        judge_score = None

                info["judge_score"] = judge_score
                info["judge_feedback"] = judge_feedback
                info["judge_missed_signal"] = judge_missed
                # Append to local history for future phase-aware judgements
                self._history.append({
                    "step": self._step_count,
                    "action": judge_action,
                    "reward": reward_value,
                    "judge_score": judge_score,
                    "judge_missed": judge_missed,
                })
        except Exception:
            # Never let judge failures break the environment
            info["judge_score"] = None
            info["judge_feedback"] = None
            info["judge_missed_signal"] = None
        return obs, rew, done, info

    def raw_state(self) -> Dict[str, Any]:
        """Full internal state, including hidden ground truth labels. Use for debugging/logging, not agent obs."""
        if self._task is None:
            return {"status": "not_started"}
        return {
            "task_id":              self._task_id,
            "current_task_name":    self._task["name"],
            "difficulty":           self._task["difficulty"],
            "hidden_fault_service": self._task["fault_service"],
            "hidden_fault_type":    self._task["fault_type"],
            "step_count":           self._step_count,
            "max_steps":            self._task["max_steps"],
            "done":                 self._done,
            "cumulative_reward":    self._cumulative_reward,
            "evidence_found":       [k for k, v in vars(self._evidence).items() if v] if self._evidence else [],
            "wrong_interventions":  self._wrong_interventions,
        }

    def state(self) -> Dict[str, Any]:
        """Sanitized state for agent observation or UI representation."""
        if self._task is None:
            return {"status": "not_started"}
        s = self.raw_state()
        s.pop("hidden_fault_service", None)
        s.pop("hidden_fault_type", None)
        return s

    def grade(self) -> float:
        """
        Final scoring gate — gated on RCA correctness.

        Wrong RCA caps score at 0.15 regardless of investigation quality.
        Correct RCA: scaled cumulative + wrong_intervention penalty.
        This ensures the LLM cannot "game" the score by collecting
        evidence and then guessing randomly.
        """
        if not self._done or not self._rca_declared:
            return 0.001

        if not self._rca_correct:
            # Wrong RCA: partial credit for investigation only, heavily capped
            evidence_credit = (self._evidence.evidence_count_cicd() if self._task.get("domain", "cicd") == "cicd" else self._evidence.evidence_count_kafka()) * 0.03
            return round(min(0.15, max(0.001, evidence_credit)), 4)

        # Correct RCA: use cumulative reward, penalise wrong interventions
        raw = self._cumulative_reward
        # Each wrong intervention (restart/rollback wrong service) subtracts 0.10
        intervention_penalty = self._wrong_interventions * 0.10
        score = raw - intervention_penalty
        # Map from [-1, 1] to [0.001, 0.999]
        normalized = (score + 1.0) / 2.0
        return round(min(0.999, max(0.001, normalized)), 4)