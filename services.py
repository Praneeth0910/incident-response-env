"""
Service Registry and Dependency Graph
======================================
Comprehensive service inventory with dependency mapping, metrics, and observability signals.

This module provides:
- Service class: Configuration, metrics, logs, dependencies
- SERVICE_REGISTRY: Complete service definitions
- SERVICE_GRAPH: Dependency graph for cascade analysis
- Helper functions: get_dependencies(), get_dependents(), simulate_failure()

Used by:
- environment.py: Task selection and cascade mechanics
- inference.py: Agent reasoning about service relationships
- server/dashboard_impl.py: Dependency visualization
- benchmark_runner.py: Fault injection and cascade testing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

# ── Service Status Definition ──────────────────────────────────────────────────


class ServiceStatus(Enum):
    """Service health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


# ── Service Tier Definition ────────────────────────────────────────────────────


class ServiceTier(Enum):
    """Service tier for difficulty scaling."""
    FOUNDATIONAL = "foundational"  # Core infrastructure, failing = cascades everywhere
    TIER_1 = "tier_1"              # High-impact, medium difficulty
    TIER_2 = "tier_2"              # Application-layer, domain reasoning required
    TIER_3 = "tier_3"              # Expert-level, observability & infrastructure


class FaultType(Enum):
    """Common fault categories across services."""
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONFIGURATION_ERROR = "configuration_error"
    DEPLOYMENT_FAILURE = "deployment_failure"
    CASCADING_TIMEOUT = "cascading_timeout"
    DATA_CORRUPTION = "data_corruption"
    DEPENDENCY_FAILURE = "dependency_failure"
    OBSERVABILITY_FAILURE = "observability_failure"


# ── Service Class Definition ───────────────────────────────────────────────────


@dataclass
class MetricSignal:
    """Metrics that indicate a service issue."""
    name: str
    critical_threshold: float
    unit: str
    example_critical_value: float

    def __str__(self) -> str:
        return f"{self.name} ({self.unit})"


@dataclass
class LogSignal:
    """Log patterns that indicate a service issue."""
    pattern: str
    severity: str  # ERROR, WARN, FATAL
    indicates: str  # Human-readable what it indicates


@dataclass
class Service:
    """
    Service configuration and observability data.

    Attributes:
        name: Service identifier (e.g., 'auth-service')
        tier: Service tier (foundational, tier_1, tier_2, tier_3)
        description: What this service does in the system
        dependencies: Services this service depends on
        critical_path: Is this on the critical path to user revenue?
        metrics: Key metrics indicating health
        logs: Log patterns indicating failures
        fault_types: Possible failure modes
        recovery_actions: Actions that can fix this service
        cascade_targets: Services affected if this fails
        red_herring_targets: Services that look suspect when this fails
        
        # Runtime State (mutable during simulation)
        status: Current health status (healthy/degraded/down)
        current_metrics: Runtime metric values
        error_logs: Logs generated during incident
        failure_start_time: When the service started failing
        root_cause_fault: The fault that caused this service to fail
    """

    name: str
    tier: ServiceTier
    description: str
    dependencies: List[str] = field(default_factory=list)
    critical_path: bool = False
    metrics: Dict[str, MetricSignal] = field(default_factory=dict)
    logs: List[LogSignal] = field(default_factory=list)
    fault_types: List[str] = field(default_factory=list)
    recovery_actions: List[str] = field(default_factory=list)
    cascade_targets: List[str] = field(default_factory=list)
    red_herring_targets: List[str] = field(default_factory=list)
    
    # Runtime state
    status: ServiceStatus = field(default=ServiceStatus.HEALTHY)
    current_metrics: Dict[str, float] = field(default_factory=dict)
    error_logs: List[str] = field(default_factory=list)
    failure_start_time: Optional[datetime] = field(default=None)
    root_cause_fault: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return f"{self.name} ({self.tier.value}) [{self.status.value}]"

    def __repr__(self) -> str:
        return f"Service(name={self.name}, tier={self.tier.value}, status={self.status.value})"

    @property
    def is_critical(self) -> bool:
        """Check if service is on critical path."""
        return self.critical_path

    def get_all_dependents_recursive(self, registry: Dict[str, Service]) -> Set[str]:
        """Get all services (direct and indirect) that depend on this service."""
        dependents = set()
        for svc_name, svc in registry.items():
            if self.name in svc.dependencies:
                dependents.add(svc_name)
                # Recursively find dependents of dependents
                dependents.update(svc.get_all_dependents_recursive(registry))
        return dependents
    
    def reset_state(self) -> None:
        """Reset service to healthy state (used when recovering)."""
        self.status = ServiceStatus.HEALTHY
        self.current_metrics = {}
        self.error_logs = []
        self.failure_start_time = None
        self.root_cause_fault = None


# ── Service Simulator ──────────────────────────────────────────────────────────


class ServiceSimulator:
    """
    Service failure simulation system.
    
    Orchestrates:
    - Failure propagation through dependency graph
    - Metric updates reflecting service degradation
    - Cascading failures to dependent services
    """
    
    def __init__(self, registry: Dict[str, Service]):
        """
        Initialize simulator with service registry.
        
        Args:
            registry: Dict of service_name -> Service
        """
        self.registry = registry
        self.failure_chain: List[str] = []  # Track failure sequence
    
    def propagate_failure(
        self, 
        root_service: str, 
        fault_type: FaultType | str,
        max_cascade_depth: int = 5
    ) -> Dict[str, any]:
        """
        Propagate a service failure through the dependency graph.
        
        Args:
            root_service: Service name where failure originates
            fault_type: Type of fault (resource exhaustion, configuration, etc)
            max_cascade_depth: Maximum cascade propagation depth
        
        Returns:
            Dict with failure analysis:
            - root_service: Service that failed
            - fault_type: Type of fault
            - affected_services: All services affected (transitive)
            - critical_services_affected: Critical path services impacted
            - cascade_chain: Order of failure propagation
        
        Raises:
            KeyError: If root_service not in registry
        """
        if root_service not in self.registry:
            raise KeyError(f"Service '{root_service}' not found in registry")
        
        root_svc = self.registry[root_service]
        affected = set()
        cascade_chain = [root_service]
        
        # Mark root service as down
        root_svc.status = ServiceStatus.DOWN
        root_svc.failure_start_time = datetime.now()
        root_fault = fault_type.value if isinstance(fault_type, FaultType) else str(fault_type)
        root_svc.root_cause_fault = root_fault
        
        # Cascade through dependents
        to_visit = {root_service}
        visited = {root_service}
        depth = 0
        
        while to_visit and depth < max_cascade_depth:
            current_level = to_visit.copy()
            to_visit = set()
            depth += 1
            
            for service_name in current_level:
                # Get all direct dependents of this service
                dependents = self._get_direct_dependents(service_name)
                
                for dependent_name in dependents:
                    if dependent_name not in visited:
                        visited.add(dependent_name)
                        to_visit.add(dependent_name)
                        affected.add(dependent_name)
                        cascade_chain.append(dependent_name)
                        
                        # Mark as degraded (or down if critical dependency failed)
                        dependent_svc = self.registry[dependent_name]
                        if root_svc.critical_path:
                            dependent_svc.status = ServiceStatus.DOWN
                        else:
                            dependent_svc.status = ServiceStatus.DEGRADED
                        
                        dependent_svc.failure_start_time = datetime.now()
                        dependent_svc.root_cause_fault = root_service
        
        affected.discard(root_service)  # Don't include root in affected
        
        # Identify critical services in cascade
        critical_affected = [
            svc_name for svc_name in affected 
            if self.registry[svc_name].critical_path
        ]
        
        return {
            "root_service": root_service,
            "root_fault_type": root_fault,
            "affected_services": affected,
            "affected_count": len(affected),
            "cascade_chain": cascade_chain,
            "critical_services_affected": critical_affected,
            "critical_path_broken": len(critical_affected) > 0,
        }
    
    def update_metrics(
        self, 
        service_name: str, 
        metric_updates: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Update runtime metrics for a service.
        
        Metrics reflect the service's current degraded state during an incident.
        
        Args:
            service_name: Service to update
            metric_updates: Dict of metric_name -> critical_value
        
        Returns:
            Dict of updated metrics
        
        Raises:
            KeyError: If service not found
        
        Example:
            >>> sim.update_metrics("postgres-db", {
            ...     "disk_used_pct": 100.0,
            ...     "active_connections": 500,
            ...     "query_latency_p99_ms": 30000
            ... })
        """
        if service_name not in self.registry:
            raise KeyError(f"Service '{service_name}' not found in registry")
        
        service = self.registry[service_name]
        
        # Update current metrics
        service.current_metrics.update(metric_updates)
        
        # Determine status based on metric violations
        metric_sigs = service.metrics
        violations = 0
        
        for metric_name, critical_value in metric_updates.items():
            if metric_name in metric_sigs:
                threshold = metric_sigs[metric_name].critical_threshold
                if critical_value >= threshold:
                    violations += 1
        
        # Set status based on violation count
        if violations >= len(metric_updates) * 0.5:  # 50% of metrics violated
            service.status = ServiceStatus.DOWN
        elif violations > 0:
            service.status = ServiceStatus.DEGRADED
        
        return service.current_metrics
    
    def add_error_log(self, service_name: str, log_entry: str) -> None:
        """
        Add an error log to a service's error log buffer.
        
        Args:
            service_name: Service to log error for
            log_entry: Error log message
        
        Raises:
            KeyError: If service not found
        """
        if service_name not in self.registry:
            raise KeyError(f"Service '{service_name}' not found in registry")
        
        service = self.registry[service_name]
        timestamp = datetime.now().isoformat()
        service.error_logs.append(f"[{timestamp}] {log_entry}")
    
    def recover_service(self, service_name: str) -> None:
        """
        Recover a service to healthy state.
        
        Args:
            service_name: Service to recover
        
        Raises:
            KeyError: If service not found
        """
        if service_name not in self.registry:
            raise KeyError(f"Service '{service_name}' not found in registry")
        
        self.registry[service_name].reset_state()
    
    def get_cascade_impact(self, root_service: str) -> Dict[str, any]:
        """
        Analyze what services would be affected if root_service fails.
        
        Args:
            root_service: Service to analyze
        
        Returns:
            Dict with cascade analysis:
            - direct_dependents: Services that directly depend on root
            - all_affected: All transitive dependents
            - critical_path_impact: Whether critical services affected
            - impact_severity: Number of services affected
        
        Raises:
            KeyError: If service not found
        """
        if root_service not in self.registry:
            raise KeyError(f"Service '{root_service}' not found in registry")
        
        direct = self._get_direct_dependents(root_service)
        all_affected = self._get_all_dependents_recursive(root_service)
        
        critical_affected = [
            svc for svc in all_affected 
            if self.registry[svc].critical_path
        ]
        
        return {
            "root_service": root_service,
            "direct_dependents": direct,
            "all_affected": all_affected,
            "affected_count": len(all_affected),
            "critical_services_affected": critical_affected,
            "critical_count": len(critical_affected),
            "impact_severity": "critical" if len(critical_affected) > 0 else "moderate" if len(all_affected) > 3 else "low",
        }
    
    def _get_direct_dependents(self, service_name: str) -> Set[str]:
        """Get services that directly depend on this service."""
        dependents = set()
        for svc_name, svc in self.registry.items():
            if service_name in svc.dependencies:
                dependents.add(svc_name)
        return dependents
    
    def _get_all_dependents_recursive(self, service_name: str) -> Set[str]:
        """Get all transitive dependents."""
        visited = set()
        to_visit = {service_name}
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)
            
            dependents = self._get_direct_dependents(current)
            to_visit.update(dependents - visited)
        
        visited.discard(service_name)
        return visited
    
    def reset_all_services(self) -> None:
        """Reset all services to healthy state."""
        for service in self.registry.values():
            service.reset_state()


# ── Service Registry ──────────────────────────────────────────────────────────


SERVICE_REGISTRY: Dict[str, Service] = {
    # ── Foundational Services ──────────────────────────────────────────────
    
    "api-gateway": Service(
        name="api-gateway",
        tier=ServiceTier.FOUNDATIONAL,
        description="Entry point for all user-facing traffic. Routes requests to downstream services.",
        dependencies=["nginx-ingress", "config-service", "jaeger", "prometheus"],
        critical_path=True,
        metrics={
            "latency_p99_ms": MetricSignal("latency_p99_ms", 5000, "ms", 8000),
            "error_rate": MetricSignal("error_rate", 0.05, "percent", 0.50),
            "upstream_timeout_rate": MetricSignal("upstream_timeout_rate", 0.1, "percent", 0.45),
            "active_connections": MetricSignal("active_connections", 8000, "count", 12000),
        },
        logs=[
            LogSignal("[ERROR] api-gateway: upstream timed out", "ERROR", "downstream service not responding"),
            LogSignal("[ERROR] api-gateway: 502 Bad Gateway", "ERROR", "upstream unavailable"),
            LogSignal("[WARN] api-gateway: rate limiting applied", "WARN", "traffic spike detected"),
        ],
        fault_types=["cascading_timeout", "configuration_error"],
        recovery_actions=["rollback_deployment", "restart_service"],
        cascade_targets=["auth-service", "order-service", "search-service"],
        red_herring_targets=["notification-service"],
    ),

    "auth-service": Service(
        name="auth-service",
        tier=ServiceTier.FOUNDATIONAL,
        description="Token validation, JWT processing, authentication/authorization.",
        dependencies=["vault", "postgres-db", "redis-cache", "config-service", "jaeger"],
        critical_path=True,
        metrics={
            "latency_p99_ms": MetricSignal("latency_p99_ms", 2000, "ms", 30000),
            "error_rate": MetricSignal("error_rate", 0.05, "percent", 0.91),
            "cpu_pct": MetricSignal("cpu_pct", 80, "percent", 99),
            "thread_pool_active": MetricSignal("thread_pool_active", 150, "count", 200),
        },
        logs=[
            LogSignal("[ERROR] auth-service: thread saturation", "ERROR", "thread pool exhausted"),
            LogSignal("[ERROR] auth-service: CPU 99% — hot loop", "ERROR", "cpu spike due to bug"),
            LogSignal("[ERROR] auth-service: JWT iat in future (clock drift)", "ERROR", "ntp daemon down"),
        ],
        fault_types=["resource_exhaustion", "clock_skew", "configuration_error"],
        recovery_actions=["restart_service", "rollback_deployment"],
        cascade_targets=["api-gateway", "order-service"],
        red_herring_targets=["redis-cache"],
    ),

    "order-service": Service(
        name="order-service",
        tier=ServiceTier.FOUNDATIONAL,
        description="Order creation, status tracking, payment processing orchestration.",
        dependencies=["postgres-db", "payment-service", "inventory-service", "notification-service", "kafka-broker", "vault"],
        critical_path=True,
        metrics={
            "latency_p99_ms": MetricSignal("latency_p99_ms", 2000, "ms", 8000),
            "error_rate": MetricSignal("error_rate", 0.05, "percent", 0.89),
            "db_connection_pool_usage": MetricSignal("db_connection_pool_usage", 0.8, "ratio", 1.0),
            "message_queue_depth": MetricSignal("message_queue_depth", 5000, "count", 847),
        },
        logs=[
            LogSignal("[ERROR] order-service: connection pool exhausted", "ERROR", "db connection leak"),
            LogSignal("[ERROR] order-service: timeout waiting for connection", "ERROR", "database overloaded"),
            LogSignal("[ERROR] order-service: 401 Unauthorized", "ERROR", "auth service down or clock skew"),
        ],
        fault_types=["resource_exhaustion", "cascading_timeout", "data_corruption"],
        recovery_actions=["restart_service", "rollback_deployment"],
        cascade_targets=["api-gateway", "notification-service"],
        red_herring_targets=["auth-service"],
    ),

    "postgres-db": Service(
        name="postgres-db",
        tier=ServiceTier.FOUNDATIONAL,
        description="Primary relational database. All persistent state.",
        dependencies=["vault", "k8s-scheduler"],
        critical_path=True,
        metrics={
            "disk_used_pct": MetricSignal("disk_used_pct", 85, "percent", 100),
            "wal_size_gb": MetricSignal("wal_size_gb", 40, "GB", 48),
            "active_connections": MetricSignal("active_connections", 450, "count", 500),
            "query_latency_p99_ms": MetricSignal("query_latency_p99_ms", 8000, "ms", 8000),
        },
        logs=[
            LogSignal("[FATAL] postgres-db: ENOSPC — No space left on device", "FATAL", "disk full"),
            LogSignal("[ERROR] postgres-db: deadlock detected", "ERROR", "concurrent transaction conflict"),
            LogSignal("[ERROR] postgres-db: connection pool exhausted", "ERROR", "too many clients"),
        ],
        fault_types=["resource_exhaustion", "data_corruption", "cascading_timeout"],
        recovery_actions=["run_db_query", "restart_service"],
        cascade_targets=["order-service", "auth-service", "inventory-service"],
        red_herring_targets=["api-gateway"],
    ),

    "redis-cache": Service(
        name="redis-cache",
        tier=ServiceTier.FOUNDATIONAL,
        description="In-memory caching for sessions, tokens, rate limit counters.",
        dependencies=["k8s-scheduler"],
        critical_path=False,
        metrics={
            "memory_pct": MetricSignal("memory_pct", 80, "percent", 98),
            "eviction_rate": MetricSignal("eviction_rate", 100, "ops/sec", 10000),
            "cache_miss_rate": MetricSignal("cache_miss_rate", 0.3, "ratio", 0.89),
            "connection_pool_usage": MetricSignal("connection_pool_usage", 0.8, "ratio", 1.0),
        },
        logs=[
            LogSignal("[WARN] redis-cache: cache miss rate elevated", "WARN", "eviction or TTL miscalculation"),
            LogSignal("[ERROR] redis-cache: evicting keys", "ERROR", "memory threshold hit"),
        ],
        fault_types=["resource_exhaustion", "cascading_timeout"],
        recovery_actions=["restart_service"],
        cascade_targets=["auth-service", "api-gateway"],
        red_herring_targets=["order-service"],
    ),

    "notification-service": Service(
        name="notification-service",
        tier=ServiceTier.FOUNDATIONAL,
        description="Email, SMS, push notifications. Async task processing via Celery.",
        dependencies=["celery-worker", "email-service", "kafka-broker", "config-service"],
        critical_path=False,
        metrics={
            "queue_depth": MetricSignal("queue_depth", 1000, "count", 847),
            "processing_rate": MetricSignal("processing_rate", 100, "tasks/sec", 0),
            "gc_pause_ms": MetricSignal("gc_pause_ms", 5000, "ms", 12000),
            "memory_pct": MetricSignal("memory_pct", 80, "percent", 98),
        },
        logs=[
            LogSignal("[ERROR] notification-service: GC pause > 11s", "ERROR", "memory leak"),
            LogSignal("[ERROR] notification-service: pod crashing (exit code 1)", "ERROR", "crash loop"),
        ],
        fault_types=["resource_exhaustion", "deployment_failure"],
        recovery_actions=["restart_service", "rollback_deployment"],
        cascade_targets=["api-gateway"],
        red_herring_targets=["order-service"],
    ),

    # ── Tier 1: High-Impact Infrastructure ──────────────────────────────

    "kafka-broker": Service(
        name="kafka-broker",
        tier=ServiceTier.TIER_1,
        description="Event streaming. Decouples order-service from notification-service.",
        dependencies=["k8s-scheduler", "prometheus"],
        critical_path=True,
        metrics={
            "consumer_lag": MetricSignal("consumer_lag", 100000, "messages", 2147832),
            "messages_per_sec": MetricSignal("messages_per_sec", 1000, "count", 0),
            "active_consumers": MetricSignal("active_consumers", 2, "count", 0),
            "rebalance_count": MetricSignal("rebalance_count", 5, "count/hour", 47),
        },
        logs=[
            LogSignal("[ERROR] kafka-broker: consumer group lag=2,147,832", "ERROR", "consumer stuck"),
            LogSignal("[ERROR] kafka-broker: poison pill at offset 8847293", "ERROR", "malformed event crashes consumers"),
            LogSignal("[WARN] kafka-broker: partition rebalance triggered", "WARN", "consumer group instability"),
        ],
        fault_types=["resource_exhaustion", "configuration_error"],
        recovery_actions=["rollback_deployment", "restart_service"],
        cascade_targets=["notification-service", "order-service"],
        red_herring_targets=["order-service"],
    ),

    "elasticsearch": Service(
        name="elasticsearch",
        tier=ServiceTier.TIER_1,
        description="Full-text search engine. Indexes products, orders, user activity.",
        dependencies=["k8s-scheduler", "prometheus", "jaeger"],
        critical_path=False,
        metrics={
            "cluster_status": MetricSignal("cluster_status", 0, "RED/YELLOW/GREEN", 0),
            "active_shards": MetricSignal("active_shards", 4, "count", 4),
            "unassigned_shards": MetricSignal("unassigned_shards", 0, "count", 1),
            "heap_used_pct": MetricSignal("heap_used_pct", 80, "percent", 95),
            "gc_pause_ms": MetricSignal("gc_pause_ms", 5000, "ms", 12440),
        },
        logs=[
            LogSignal("[ERROR] elasticsearch: shard [products][2] failed", "ERROR", "shard unavailable"),
            LogSignal("[ERROR] elasticsearch: [GC overhead] stop-the-world pause", "ERROR", "GC pressure"),
            LogSignal("[ERROR] elasticsearch: index corruption detected", "ERROR", "data corruption"),
        ],
        fault_types=["resource_exhaustion", "data_corruption"],
        recovery_actions=["rollback_deployment", "restart_service"],
        cascade_targets=["search-service", "api-gateway"],
        red_herring_targets=["order-service"],
    ),

    "nginx-ingress": Service(
        name="nginx-ingress",
        tier=ServiceTier.TIER_1,
        description="Kubernetes ingress controller. SSL termination, rate limiting, routing.",
        dependencies=["k8s-scheduler", "prometheus"],
        critical_path=True,
        metrics={
            "worker_processes_active": MetricSignal("worker_processes_active", 3, "count", 1),
            "worker_processes_expected": MetricSignal("worker_processes_expected", 4, "count", 4),
            "upstream_timeout_rate": MetricSignal("upstream_timeout_rate", 0.1, "percent", 0.45),
            "rate_limited_requests": MetricSignal("rate_limited_requests", 100, "req/sec", 847),
            "connections_active": MetricSignal("connections_active", 8000, "count", 12000),
        },
        logs=[
            LogSignal("[ERROR] nginx-ingress: worker process killed (signal 9) — OOM", "ERROR", "worker crash"),
            LogSignal("[ERROR] nginx-ingress: upstream timed out reading response", "ERROR", "upstream timeout"),
            LogSignal("[WARN] nginx-ingress: limiting requests, excess", "WARN", "rate limit hit"),
        ],
        fault_types=["resource_exhaustion", "configuration_error"],
        recovery_actions=["rollback_deployment", "restart_service"],
        cascade_targets=["api-gateway"],
        red_herring_targets=["auth-service"],
    ),

    "vault": Service(
        name="vault",
        tier=ServiceTier.TIER_1,
        description="Secrets management. Database credentials, API keys, encryption keys.",
        dependencies=["k8s-scheduler", "prometheus"],
        critical_path=True,
        metrics={
            "seal_status": MetricSignal("seal_status", 0, "Sealed/Unsealed", 0),
            "auth_token_ttl_hours": MetricSignal("auth_token_ttl_hours", 2, "hours", 0),
            "secret_read_errors": MetricSignal("secret_read_errors", 5, "errors/min", 847),
        },
        logs=[
            LogSignal("[ERROR] vault: token lease expired", "ERROR", "token TTL exceeded"),
            LogSignal("[ERROR] vault: Vault is sealed", "ERROR", "vault restarted and sealed"),
            LogSignal("[ERROR] vault: permission denied", "ERROR", "policy misconfiguration"),
        ],
        fault_types=["configuration_error", "dependency_failure"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["postgres-db", "auth-service", "payment-service"],
        red_herring_targets=["postgres-db", "auth-service"],
    ),

    "celery-worker": Service(
        name="celery-worker",
        tier=ServiceTier.TIER_1,
        description="Async task queue workers. Process background jobs (emails, notifications).",
        dependencies=["kafka-broker", "email-service", "k8s-scheduler", "prometheus"],
        critical_path=False,
        metrics={
            "queue_depth": MetricSignal("queue_depth", 1000, "tasks", 15847),
            "processing_rate": MetricSignal("processing_rate", 100, "tasks/sec", 0),
            "worker_memory_rss_gb": MetricSignal("worker_memory_rss_gb", 2, "GB", 4.1),
            "stuck_tasks": MetricSignal("stuck_tasks", 0, "count", 847),
        },
        logs=[
            LogSignal("[ERROR] celery-worker: task stuck in STARTED state for 2847s", "ERROR", "deadlock/hang"),
            LogSignal("[ERROR] celery-worker: worker killed by OOM killer", "ERROR", "memory leak"),
            LogSignal("[WARN] celery-worker: queue depth 15847, processing 0 tasks/sec", "WARN", "workers hung"),
        ],
        fault_types=["resource_exhaustion", "deployment_failure"],
        recovery_actions=["restart_service"],
        cascade_targets=["notification-service"],
        red_herring_targets=["notification-service"],
    ),

    # ── Tier 2: Application-Layer Services ──────────────────────────────

    "payment-service": Service(
        name="payment-service",
        tier=ServiceTier.TIER_2,
        description="Payment processing, credit card tokenization, 3rd-party processor webhooks.",
        dependencies=["vault", "postgres-db"],  # Removed order-service to break cycle
        critical_path=True,
        metrics={
            "processor_webhook_latency_ms": MetricSignal("processor_webhook_latency_ms", 5000, "ms", 30000),
            "idempotency_collision_rate": MetricSignal("idempotency_collision_rate", 0.01, "ratio", 0.25),
            "thread_pool_active": MetricSignal("thread_pool_active", 100, "count", 200),
            "conversion_rate": MetricSignal("conversion_rate", 0.8, "ratio", 0.08),
        },
        logs=[
            LogSignal("[ERROR] payment-service: Stripe webhook timeout (30s)", "ERROR", "processor slow"),
            LogSignal("[ERROR] payment-service: idempotency key collision", "ERROR", "duplicate charge"),
            LogSignal("[ERROR] payment-service: currency service down", "ERROR", "intl transactions failing"),
        ],
        fault_types=["cascading_timeout", "configuration_error"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["order-service", "api-gateway"],
        red_herring_targets=["postgres-db"],
    ),

    "inventory-service": Service(
        name="inventory-service",
        tier=ServiceTier.TIER_2,
        description="Stock tracking, oversell prevention, bulk import processing.",
        dependencies=["postgres-db", "redis-cache", "kafka-broker"],
        critical_path=True,
        metrics={
            "stock_accuracy": MetricSignal("stock_accuracy", 0.99, "ratio", 0.75),
            "cache_staleness_minutes": MetricSignal("cache_staleness_minutes", 5, "minutes", 240),
            "table_lock_wait_ms": MetricSignal("table_lock_wait_ms", 100, "ms", 1200000),
        },
        logs=[
            LogSignal("[ERROR] inventory-service: race condition — negative stock", "ERROR", "oversell"),
            LogSignal("[WARN] inventory-service: stale cache — stock incorrect", "WARN", "cache not updated"),
            LogSignal("[ERROR] inventory-service: table lock timeout — bulk import running", "ERROR", "ddl lock"),
        ],
        fault_types=["data_corruption", "cascading_timeout"],
        recovery_actions=["run_db_query", "rollback_deployment"],
        cascade_targets=["order-service"],
        red_herring_targets=["redis-cache"],
    ),

    "search-service": Service(
        name="search-service",
        tier=ServiceTier.TIER_2,
        description="Product search, autocomplete, recommendation filtering.",
        dependencies=["elasticsearch", "redis-cache", "config-service"],
        critical_path=False,
        metrics={
            "query_latency_p99_ms": MetricSignal("query_latency_p99_ms", 2000, "ms", 15000),
            "index_staleness_minutes": MetricSignal("index_staleness_minutes", 60, "minutes", 240),
            "relevancy_score": MetricSignal("relevancy_score", 0.9, "ratio", 0.3),
        },
        logs=[
            LogSignal("[ERROR] search-service: index staleness 4 hours", "ERROR", "indexing pipeline paused"),
            LogSignal("[ERROR] search-service: query explosion — full index scan timeout", "ERROR", "wild card query"),
            LogSignal("[ERROR] search-service: relevancy model corruption", "ERROR", "bad model update"),
        ],
        fault_types=["cascading_timeout", "data_corruption"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["api-gateway"],
        red_herring_targets=["elasticsearch"],
    ),

    "email-service": Service(
        name="email-service",
        tier=ServiceTier.TIER_2,
        description="SMTP relay, transactional email delivery, bounce handling.",
        dependencies=["vault"],
        critical_path=False,
        metrics={
            "queue_depth": MetricSignal("queue_depth", 1000, "emails", 47832),
            "delivery_rate": MetricSignal("delivery_rate", 1000, "emails/sec", 0),
            "bounce_rate": MetricSignal("bounce_rate", 0.05, "ratio", 0.35),
        },
        logs=[
            LogSignal("[ERROR] email-service: SMTP relay connection refused", "ERROR", "relay down"),
            LogSignal("[ERROR] email-service: provider rate limited (429)", "ERROR", "sendgrid limit"),
            LogSignal("[ERROR] email-service: bounce rate spike", "ERROR", "provider suspended"),
        ],
        fault_types=["dependency_failure"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["notification-service"],
        red_herring_targets=[],
    ),

    "user-profile-service": Service(
        name="user-profile-service",
        tier=ServiceTier.TIER_2,
        description="User profiles, preferences, personalization data.",
        dependencies=["postgres-db", "redis-cache", "vault"],
        critical_path=False,
        metrics={
            "cache_hit_rate": MetricSignal("cache_hit_rate", 0.95, "ratio", 0.35),
            "read_replica_lag_seconds": MetricSignal("read_replica_lag_seconds", 5, "seconds", 900),
            "data_freshness_accuracy": MetricSignal("data_freshness_accuracy", 0.99, "ratio", 0.5),
        },
        logs=[
            LogSignal("[ERROR] user-profile-service: cache invalidation failed", "ERROR", "stale data"),
            LogSignal("[ERROR] user-profile-service: schema migration corruption", "ERROR", "data loss"),
            LogSignal("[WARN] user-profile-service: read replica 15min behind", "WARN", "replication lag"),
        ],
        fault_types=["data_corruption", "cascading_timeout"],
        recovery_actions=["run_db_query"],
        cascade_targets=["api-gateway", "auth-service"],
        red_herring_targets=[],
    ),

    # ── Tier 3: Observability & Infrastructure ──────────────────────────

    "prometheus": Service(
        name="prometheus",
        tier=ServiceTier.TIER_3,
        description="Metrics collection, storage, alerting backend.",
        dependencies=[],  # Removed k8s-scheduler to break cycle
        critical_path=False,
        metrics={
            "scrape_success_rate": MetricSignal("scrape_success_rate", 0.99, "ratio", 0.0),
            "metrics_staleness_minutes": MetricSignal("metrics_staleness_minutes", 5, "minutes", 30),
            "time_series_count": MetricSignal("time_series_count", 1000000, "count", 10000000),
            "storage_used_pct": MetricSignal("storage_used_pct", 80, "percent", 95),
        },
        logs=[
            LogSignal("[ERROR] prometheus: scrape target down for 30 minutes", "ERROR", "metrics stale"),
            LogSignal("[ERROR] prometheus: cardinality explosion — 10M time series", "ERROR", "OOM"),
            LogSignal("[ERROR] prometheus: remote_write queue full — dropping metrics", "ERROR", "backpressure"),
        ],
        fault_types=["observability_failure", "resource_exhaustion"],
        recovery_actions=["restart_service", "rollback_deployment"],
        cascade_targets=[],  # Meta: losing observability doesn't directly crash services
        red_herring_targets=[],
    ),

    "jaeger": Service(
        name="jaeger",
        tier=ServiceTier.TIER_3,
        description="Distributed tracing. Trace ingestion, storage, UI.",
        dependencies=["k8s-scheduler", "prometheus"],
        critical_path=False,
        metrics={
            "span_ingestion_rate": MetricSignal("span_ingestion_rate", 50000, "spans/sec", 0),
            "trace_latency_p99_ms": MetricSignal("trace_latency_p99_ms", 5000, "ms", 1800000),
            "sampling_rate": MetricSignal("sampling_rate", 0.01, "ratio", 1.0),
            "storage_used_gb": MetricSignal("storage_used_gb", 100, "GB", 500),
        },
        logs=[
            LogSignal("[ERROR] jaeger: collector 30-min backlog", "ERROR", "ingestion lag"),
            LogSignal("[ERROR] jaeger: sampling rate 100% — OOM", "ERROR", "cardinality explosion"),
            LogSignal("[ERROR] jaeger: Cassandra backend full", "ERROR", "storage full"),
        ],
        fault_types=["observability_failure", "resource_exhaustion"],
        recovery_actions=["rollback_deployment", "restart_service"],
        cascade_targets=[],
        red_herring_targets=[],
    ),

    "config-service": Service(
        name="config-service",
        tier=ServiceTier.TIER_3,
        description="Feature flag service (LaunchDarkly/Flagsmith). Controls feature rollouts.",
        dependencies=["postgres-db", "redis-cache", "k8s-scheduler"],
        critical_path=True,
        metrics={
            "flag_consistency_rate": MetricSignal("flag_consistency_rate", 0.99, "ratio", 0.0),
            "flag_cache_staleness_minutes": MetricSignal("flag_cache_staleness_minutes", 5, "minutes", 360),
            "flag_update_latency_ms": MetricSignal("flag_update_latency_ms", 100, "ms", 5000),
        },
        logs=[
            LogSignal("[ERROR] config-service: down — all flags defaulting to OFF", "ERROR", "complete outage"),
            LogSignal("[ERROR] config-service: bad flag rollout — 100% vs 5%", "ERROR", "wrong percentage"),
            LogSignal("[WARN] config-service: serving 6-hour-old cache", "WARN", "stale flags"),
        ],
        fault_types=["configuration_error", "observability_failure"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["api-gateway", "order-service", "notification-service"],
        red_herring_targets=["order-service"],
    ),

    "cdn-edge": Service(
        name="cdn-edge",
        tier=ServiceTier.TIER_3,
        description="Content delivery network. Serves static assets, handles SSL termination.",
        dependencies=[],
        critical_path=True,
        metrics={
            "origin_pull_traffic_rate": MetricSignal("origin_pull_traffic_rate", 1000, "req/sec", 50000),
            "cache_hit_rate": MetricSignal("cache_hit_rate", 0.95, "ratio", 0.3),
            "ssl_error_rate": MetricSignal("ssl_error_rate", 0.0, "ratio", 0.30),
        },
        logs=[
            LogSignal("[ERROR] cdn-edge: origin pull storm — origin getting 50x traffic", "ERROR", "thundering herd"),
            LogSignal("[ERROR] cdn-edge: cache poisoning — malformed response cached", "ERROR", "data corruption"),
            LogSignal("[ERROR] cdn-edge: SSL offload failure (525)", "ERROR", "cert issue or TLS bug"),
        ],
        fault_types=["cascading_timeout", "data_corruption"],
        recovery_actions=["rollback_deployment"],
        cascade_targets=["api-gateway"],
        red_herring_targets=["api-gateway"],
    ),

    "k8s-scheduler": Service(
        name="k8s-scheduler",
        tier=ServiceTier.TIER_3,
        description="Kubernetes scheduler. Pod scheduling, node resource management.",
        dependencies=["prometheus"],
        critical_path=True,
        metrics={
            "node_ready_count": MetricSignal("node_ready_count", 3, "count", 2),
            "pod_eviction_rate": MetricSignal("pod_eviction_rate", 0, "evictions/hour", 47),
            "pod_pending_count": MetricSignal("pod_pending_count", 0, "count", 8),
            "namespace_cpu_used_pct": MetricSignal("namespace_cpu_used_pct", 80, "percent", 100),
        },
        logs=[
            LogSignal("[ERROR] k8s-scheduler: node tainted (memory-pressure) — evicting pods", "ERROR", "node pressure"),
            LogSignal("[ERROR] k8s-scheduler: namespace quota exceeded", "ERROR", "resource limit hit"),
            LogSignal("[WARN] k8s-scheduler: pod evicted (OOMKilled) — 3rd eviction in 10min", "WARN", "pod crashing"),
        ],
        fault_types=["resource_exhaustion"],
        recovery_actions=["restart_service"],
        cascade_targets=["all"],  # Everything runs on k8s
        red_herring_targets=["notification-service"],
    ),
}


# ── Service Dependency Graph ──────────────────────────────────────────────────

SERVICE_GRAPH: Dict[str, Set[str]] = {
    service.name: set(service.dependencies) for service in SERVICE_REGISTRY.values()
}


# ── Helper Functions ──────────────────────────────────────────────────────────


def get_dependencies(service_name: str) -> Set[str]:
    """
    Get direct dependencies of a service.

    Args:
        service_name: Service to query

    Returns:
        Set of service names this service depends on

    Raises:
        KeyError: If service not found

    Example:
        >>> get_dependencies("order-service")
        {'postgres-db', 'payment-service', 'vault', ...}
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service '{service_name}' not found in registry")

    return SERVICE_GRAPH.get(service_name, set())


def get_all_dependencies_recursive(service_name: str) -> Set[str]:
    """
    Get all dependencies (direct and transitive) of a service.

    Args:
        service_name: Service to query

    Returns:
        Set of all service names this service depends on (directly or indirectly)

    Example:
        >>> get_all_dependencies_recursive("api-gateway")
        {'nginx-ingress', 'config-service', 'vault', 'postgres-db', ...}
    """
    visited = set()
    to_visit = {service_name}

    while to_visit:
        current = to_visit.pop()
        if current in visited:
            continue
        visited.add(current)

        deps = get_dependencies(current)
        to_visit.update(deps - visited)

    visited.discard(service_name)  # Don't include self
    return visited


def get_dependents(service_name: str) -> Set[str]:
    """
    Get services that depend on this service.

    Args:
        service_name: Service to query

    Returns:
        Set of service names that depend on this service

    Example:
        >>> get_dependents("postgres-db")
        {'order-service', 'auth-service', 'inventory-service', ...}
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service '{service_name}' not found in registry")

    dependents = set()
    for svc_name, svc in SERVICE_REGISTRY.items():
        if service_name in svc.dependencies:
            dependents.add(svc_name)

    return dependents


def get_all_dependents_recursive(service_name: str) -> Set[str]:
    """
    Get all services (direct and transitive) that depend on this service.

    Args:
        service_name: Service to query

    Returns:
        Set of all service names that depend on this (directly or indirectly)

    Example:
        >>> get_all_dependents_recursive("postgres-db")
        {'order-service', 'auth-service', 'api-gateway', 'payment-service', ...}
    """
    visited = set()
    to_visit = {service_name}

    while to_visit:
        current = to_visit.pop()
        if current in visited:
            continue
        visited.add(current)

        dependents = get_dependents(current)
        to_visit.update(dependents - visited)

    visited.discard(service_name)  # Don't include self
    return visited


def simulate_failure(service_name: str) -> Dict[str, Any]:
    """
    Simulate the impact of a service failure.

    Args:
        service_name: Service that failed

    Returns:
        Dict with impact analysis:
        - service: The failed service
        - direct_impact: Services that directly depend on it
        - cascade_impact: All services affected (transitive)
        - critical_path_broken: Is critical path affected?
        - recommended_actions: Suggested recovery actions

    Example:
        >>> simulate_failure("postgres-db")
        {
            'service': 'postgres-db',
            'direct_impact': {'order-service', 'auth-service', ...},
            'cascade_impact': {'order-service', 'auth-service', 'api-gateway', ...},
            'critical_path_broken': True,
            'recommended_actions': ['run_db_query', 'restart_service'],
        }
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service '{service_name}' not found in registry")

    service = SERVICE_REGISTRY[service_name]
    direct_impact = get_dependents(service_name)
    cascade_impact = get_all_dependents_recursive(service_name)

    # Check if any cascade target is critical
    critical_path_broken = service.critical_path or any(
        SERVICE_REGISTRY[svc].critical_path for svc in cascade_impact
    )

    return {
        "service": service_name,
        "service_tier": service.tier.value,
        "direct_impact": direct_impact,
        "cascade_impact": cascade_impact,
        "cascade_size": len(cascade_impact),
        "critical_path_broken": critical_path_broken,
        "recommended_actions": service.recovery_actions,
        "affected_critical_services": [
            svc for svc in cascade_impact if SERVICE_REGISTRY[svc].critical_path
        ],
    }


def propagate_failure(
    service_name: str,
    fault_type: FaultType | str = FaultType.DEPENDENCY_FAILURE,
    max_cascade_depth: int = 5,
    registry: Optional[Dict[str, Service]] = None,
) -> Dict[str, Any]:
    """
    Apply a root-cause failure to a service registry and cascade it to dependents.

    This module-level wrapper keeps simple callers from needing to instantiate
    ServiceSimulator directly. Passing a registry gives each environment its own
    isolated service state; omitting it mutates SERVICE_REGISTRY.
    """
    simulator = ServiceSimulator(registry or SERVICE_REGISTRY)
    return simulator.propagate_failure(
        root_service=service_name,
        fault_type=fault_type,
        max_cascade_depth=max_cascade_depth,
    )


def update_metrics(
    service_name: str,
    metric_updates: Dict[str, float],
    registry: Optional[Dict[str, Service]] = None,
) -> Dict[str, float]:
    """
    Update runtime metrics for a service in a registry.

    This is the functional counterpart to ServiceSimulator.update_metrics and is
    useful for reward/observation code that should not own a simulator instance.
    """
    simulator = ServiceSimulator(registry or SERVICE_REGISTRY)
    return simulator.update_metrics(service_name, metric_updates)


def get_service_metrics(service_name: str) -> Dict[str, MetricSignal]:
    """
    Get all metrics for a service.

    Args:
        service_name: Service to query

    Returns:
        Dict of metric_name → MetricSignal

    Raises:
        KeyError: If service not found
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service '{service_name}' not found in registry")

    return SERVICE_REGISTRY[service_name].metrics


def get_service_logs(service_name: str) -> List[LogSignal]:
    """
    Get all log signals for a service.

    Args:
        service_name: Service to query

    Returns:
        List of LogSignal objects

    Raises:
        KeyError: If service not found
    """
    if service_name not in SERVICE_REGISTRY:
        raise KeyError(f"Service '{service_name}' not found in registry")

    return SERVICE_REGISTRY[service_name].logs


def get_critical_path_services() -> Set[str]:
    """
    Get all services on the critical path to user revenue.

    Returns:
        Set of service names where failure = direct revenue impact
    """
    return {
        svc.name for svc in SERVICE_REGISTRY.values() if svc.critical_path
    }


def get_services_by_tier(tier: ServiceTier) -> List[Service]:
    """
    Get all services in a specific tier.

    Args:
        tier: ServiceTier to filter by

    Returns:
        List of Service objects in that tier
    """
    return [svc for svc in SERVICE_REGISTRY.values() if svc.tier == tier]


if __name__ == "__main__":
    # ── Example Usage ──────────────────────────────────────────────────

    print("=" * 80)
    print("SERVICE REGISTRY EXAMPLES")
    print("=" * 80)

    # Example 1: Query dependencies
    print("\n1. postgres-db dependencies:")
    deps = get_dependencies("postgres-db")
    print(f"   Direct deps: {deps}")

    # Example 2: Get dependents (who depends on postgres-db?)
    print("\n2. Who depends on postgres-db?")
    dependents = get_dependents("postgres-db")
    print(f"   Direct dependents: {dependents}")

    # Example 3: Get all transitive dependents
    print("\n3. Full cascade if postgres-db fails:")
    cascade = get_all_dependents_recursive("postgres-db")
    print(f"   Cascade size: {len(cascade)} services")
    print(f"   Affected: {cascade}")

    # Example 4: Simulate failure
    print("\n4. Simulate kafka-broker failure:")
    impact = simulate_failure("kafka-broker")
    print(f"   Critical path broken: {impact['critical_path_broken']}")
    print(f"   Direct impact: {impact['direct_impact']}")
    print(f"   Cascade impact: {len(impact['cascade_impact'])} services")
    print(f"   Recommended actions: {impact['recommended_actions']}")

    # Example 5: Get metrics
    print("\n5. Metrics for api-gateway:")
    metrics = get_service_metrics("api-gateway")
    for name, signal in metrics.items():
        print(f"   {name}: threshold={signal.critical_threshold} {signal.unit}")

    # Example 6: Get services by tier
    print("\n6. Foundational services:")
    foundational = get_services_by_tier(ServiceTier.FOUNDATIONAL)
    for svc in foundational:
        print(f"   - {svc.name}: critical_path={svc.critical_path}")

    # Example 7: Get critical path
    print("\n7. Critical path services:")
    critical = get_critical_path_services()
    print(f"   Count: {len(critical)}")
    print(f"   Services: {sorted(critical)}")

    print("\n" + "=" * 80)
    print(f"Total services: {len(SERVICE_REGISTRY)}")
    print("=" * 80)
