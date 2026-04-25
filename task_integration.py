"""
Task-Service Integration Layer
===============================

Bridges task definitions (tasks.json) with the service dependency graph (services.py).

Responsibilities:
  1. Load task definitions from JSON
  2. Map tasks to affected services using service graph
  3. Simulate realistic metrics/logs based on fault types
  4. Generate dynamic observations integrating task context + service state

Example:
  task_loader = TaskLoader()
  task = task_loader.get_task("task_cpu_spike_auth")
  observation = task_loader.generate_observation(task, step=0)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from services import (
    SERVICE_REGISTRY,
    SERVICE_GRAPH,
    get_all_dependents_recursive,
    simulate_failure,
)


# ── Task Data Structure ────────────────────────────────────────────────────────

@dataclass
class TaskDefinition:
    """Task definition with enriched metadata."""

    id: str
    domain: str
    alert_message: str
    root_cause: str
    affected_services: List[str]
    red_herrings: List[str]
    resolution_steps: List[str]
    difficulty: str
    
    # Derived during initialization
    cascade_targets: Set[str] = None  # All downstream services
    critical_path_broken: bool = False  # Does this break revenue?


# ── Task Loader ────────────────────────────────────────────────────────────────

class TaskLoader:
    """Load and enrich task definitions from JSON."""

    def __init__(self, tasks_file: str = "tasks.json"):
        """
        Initialize TaskLoader.

        Args:
            tasks_file: Path to tasks.json
        """
        self.tasks_file = Path(tasks_file)
        self.tasks: Dict[str, TaskDefinition] = {}
        self._load_tasks()

    def _load_tasks(self) -> None:
        """Load task definitions from JSON and enrich with service graph data."""
        if not self.tasks_file.exists():
            raise FileNotFoundError(f"tasks.json not found at {self.tasks_file}")

        with open(self.tasks_file, "r") as f:
            raw_tasks = json.load(f)

        for task_data in raw_tasks:
            task_id = task_data["id"]
            
            # Enrich with cascade analysis
            root_cause_service = task_data.get("root_cause", "").split(" ")[0]
            # Extract service name from root cause (e.g., "auth-service" from "auth-service clock drifted...")
            affected_services = set(task_data.get("affected_services", []))
            
            # Add transitive dependents as cascades
            cascade_targets = set()
            for affected_svc in affected_services:
                if affected_svc in SERVICE_GRAPH:
                    cascade_targets.update(
                        get_all_dependents_recursive(affected_svc)
                    )
            
            # Check if critical path is broken
            critical_services = {
                "api-gateway", "auth-service", "order-service", "postgres-db",
                "kafka-broker", "vault", "nginx-ingress", "cdn-edge",
                "config-service", "inventory-service", "k8s-scheduler", "payment-service"
            }
            critical_path_broken = bool(affected_services & critical_services)

            task_def = TaskDefinition(
                id=task_id,
                domain=task_data.get("domain", ""),
                alert_message=task_data.get("alert_message", ""),
                root_cause=task_data.get("root_cause", ""),
                affected_services=list(affected_services),
                red_herrings=task_data.get("red_herrings", []),
                resolution_steps=task_data.get("resolution_steps", []),
                difficulty=task_data.get("difficulty", ""),
                cascade_targets=cascade_targets,
                critical_path_broken=critical_path_broken,
            )
            
            self.tasks[task_id] = task_def

    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        """Get task definition by ID."""
        return self.tasks.get(task_id)

    def list_tasks(self) -> List[str]:
        """List all available task IDs."""
        return list(self.tasks.keys())

    def list_tasks_by_difficulty(self, difficulty: str) -> List[str]:
        """Get task IDs filtered by difficulty."""
        return [
            task_id for task_id, task in self.tasks.items()
            if task.difficulty == difficulty
        ]

    def list_tasks_by_domain(self, domain: str) -> List[str]:
        """Get task IDs filtered by domain."""
        return [
            task_id for task_id, task in self.tasks.items()
            if task.domain == domain
        ]


# ── Metric & Log Simulation ────────────────────────────────────────────────────

class MetricsSimulator:
    """Simulate realistic service metrics based on fault type."""

    # Baseline healthy metrics
    BASELINE_METRICS = {
        "latency_p99_ms": 120,
        "error_rate": 0.002,
        "cpu_pct": 25,
        "memory_pct": 45,
        "request_rate": 450,
        "cache_hit_rate": 0.92,
        "db_connections_used": 45,
        "disk_usage_pct": 65,
    }

    @staticmethod
    def simulate_metrics(
        service: str,
        task: TaskDefinition,
        step: int,
        max_steps: int,
    ) -> Dict[str, Any]:
        """
        Simulate metrics for a service during a task.

        Args:
            service: Service name
            task: Task definition
            step: Current step number
            max_steps: Maximum steps in episode

        Returns:
            Dictionary of simulated metrics
        """
        import random
        
        metrics = MetricsSimulator.BASELINE_METRICS.copy()
        
        # If this is the root cause service, degrade metrics aggressively
        is_root_cause = service in task.affected_services
        is_cascade_victim = service in task.cascade_targets and service not in task.affected_services
        is_red_herring = service in task.red_herrings
        
        if is_root_cause:
            # Severe degradation for root cause service
            metrics.update({
                "latency_p99_ms": random.randint(4000, 9500),
                "error_rate": random.uniform(0.6, 0.95),
                "cpu_pct": random.randint(85, 99),
                "memory_pct": random.randint(75, 98),
                "request_rate": random.randint(10, 100),
            })
            
            # Specific metrics based on fault type
            if "memory" in task.root_cause.lower():
                metrics["memory_pct"] = 98
                metrics["gc_pause_ms"] = random.randint(8000, 15000)
            elif "cpu" in task.root_cause.lower():
                metrics["cpu_pct"] = 99
                metrics["thread_pool_active"] = 200
                metrics["thread_pool_max"] = 200
            elif "disk" in task.root_cause.lower():
                metrics["disk_usage_pct"] = 100
                metrics["error_rate"] = 1.0
                metrics["latency_p99_ms"] = 0
            elif "connection" in task.root_cause.lower():
                metrics["db_connections_used"] = 500
                metrics["db_connections_max"] = 500
                metrics["error_rate"] = 0.9
                
        elif is_cascade_victim:
            # Moderate degradation for cascade victims
            metrics.update({
                "latency_p99_ms": random.randint(2000, 5000),
                "error_rate": random.uniform(0.3, 0.7),
                "cpu_pct": random.randint(60, 85),
            })
            
        elif is_red_herring:
            # Red herrings show slightly elevated metrics but not critical
            metrics.update({
                "latency_p99_ms": random.randint(500, 1500),
                "error_rate": random.uniform(0.05, 0.15),
                "cpu_pct": random.randint(50, 75),
            })
            
        # Progression: get worse as steps increase (if not yet resolved)
        progression_factor = min(step / max(max_steps - 1, 1), 1.0)
        if is_root_cause:
            # Root cause degrades more over time
            metrics["latency_p99_ms"] = int(metrics["latency_p99_ms"] * (0.8 + 0.2 * progression_factor))
            metrics["error_rate"] = min(metrics["error_rate"] * (0.7 + 0.3 * progression_factor), 1.0)
        
        return metrics

    @staticmethod
    def simulate_logs(
        service: str,
        task: TaskDefinition,
        step: int,
    ) -> str:
        """
        Simulate log output for a service.

        Args:
            service: Service name
            task: Task definition
            step: Current step number

        Returns:
            Simulated log string
        """
        is_root_cause = service in task.affected_services
        is_cascade_victim = service in task.cascade_targets and service not in task.affected_services
        is_red_herring = service in task.red_herrings
        
        if is_root_cause:
            # Root cause shows specific error patterns
            if "memory" in task.root_cause.lower():
                return (
                    f"[ERROR] {service}: GC pause > 11000ms — Old generation 98% full\n"
                    f"[ERROR] {service}: Heap usage 3.8GB / 4.0GB\n"
                    f"[WARN]  {service}: Memory leak detected in {task.root_cause.split(':')[0]}"
                )
            elif "cpu" in task.root_cause.lower():
                return (
                    f"[ERROR] {service}: CPU 99% — hot loop detected\n"
                    f"[ERROR] {service}: Thread pool exhausted (200/200 active)\n"
                    f"[WARN]  {service}: Request queue depth growing: {step * 100}"
                )
            elif "disk" in task.root_cause.lower():
                return (
                    f"[FATAL] {service}: ENOSPC — No space left on device\n"
                    f"[ERROR] {service}: Disk at 100% capacity\n"
                    f"[ERROR] {service}: All write operations failing"
                )
            elif "connection" in task.root_cause.lower():
                return (
                    f"[ERROR] {service}: Connection pool exhausted (500/500 active)\n"
                    f"[ERROR] {service}: Timeout waiting for available connection\n"
                    f"[WARN]  {service}: Connection leak detected in transaction handler"
                )
            else:
                return (
                    f"[ERROR] {service}: {task.root_cause}\n"
                    f"[WARN]  {service}: Service degraded\n"
                    f"[INFO]  {service}: {task.alert_message.split('ALERT:')[1].strip()}"
                )
                
        elif is_cascade_victim:
            return (
                f"[WARN]  {service}: Latency spike detected (upstream degradation)\n"
                f"[ERROR] {service}: Timeout waiting for downstream service response\n"
                f"[INFO]  {service}: Cascade detected — this is a victim, not root cause"
            )
            
        elif is_red_herring:
            return (
                f"[WARN]  {service}: Elevated CPU (75%)\n"
                f"[ERROR] {service}: Some errors observed (5-10%)\n"
                f"[INFO]  {service}: No critical issues detected — may be a red herring"
            )
            
        else:
            return (
                f"[INFO]  {service}: Operating normally\n"
                f"[INFO]  {service}: Health check OK\n"
                f"[DEBUG] {service}: Request processing time: {50 + step}ms"
            )


# ── Observation Generator ──────────────────────────────────────────────────────

class ObservationGenerator:
    """Generate rich observations combining task context + service metrics."""

    def __init__(self, task_loader: Optional[TaskLoader] = None):
        """Initialize generator."""
        self.task_loader = task_loader or TaskLoader()
        self.metrics_sim = MetricsSimulator()

    def generate_observation(
        self,
        task: TaskDefinition,
        step: int,
        max_steps: int,
        service_focus: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a rich observation for the agent.

        Args:
            task: Task definition
            step: Current step number
            max_steps: Total steps allowed
            service_focus: If provided, focus on this service's metrics

        Returns:
            Observation dictionary with metrics, logs, alert, etc.
        """
        # Alert message (always shown)
        alert = task.alert_message
        
        # Summary of affected services
        affected_summary = (
            f"Affected services: {', '.join(task.affected_services)}\n"
            f"Red herrings: {', '.join(task.red_herrings) if task.red_herrings else 'none'}\n"
            f"Cascade targets: {len(task.cascade_targets)} services"
        )
        
        # Detailed metrics for all relevant services
        service_metrics = {}
        service_logs = {}
        
        # Focus on affected services + red herrings
        services_to_monitor = set(task.affected_services) | set(task.red_herrings)
        
        # Add api-gateway for context
        if "api-gateway" not in services_to_monitor:
            services_to_monitor.add("api-gateway")
        
        for service in services_to_monitor:
            metrics = self.metrics_sim.simulate_metrics(service, task, step, max_steps)
            logs = self.metrics_sim.simulate_logs(service, task, step)
            
            service_metrics[service] = metrics
            service_logs[service] = logs
        
        # Generate message summarizing current state
        message_lines = [
            f"Step {step}/{max_steps}",
            f"Task: {task.id} ({task.difficulty})",
            "",
            alert,
            "",
            affected_summary,
        ]
        
        if service_focus and service_focus in service_metrics:
            message_lines.append(f"\nFocused on: {service_focus}")
            message_lines.append(service_logs[service_focus])
        
        message = "\n".join(message_lines)
        
        return {
            "message": message,
            "alert": alert,
            "step": step,
            "task_id": task.id,
            "difficulty": task.difficulty,
            "affected_services": task.affected_services,
            "red_herrings": task.red_herrings,
            "cascade_targets": list(task.cascade_targets),
            "critical_path_broken": task.critical_path_broken,
            "service_metrics": service_metrics,
            "service_logs": service_logs,
            "resolution_steps": task.resolution_steps,
        }

    def generate_logs_for_service(
        self,
        service: str,
        task: TaskDefinition,
        step: int,
    ) -> str:
        """Get logs for a specific service."""
        return self.metrics_sim.simulate_logs(service, task, step)

    def generate_metrics_for_service(
        self,
        service: str,
        task: TaskDefinition,
        step: int,
        max_steps: int,
    ) -> Dict[str, Any]:
        """Get metrics for a specific service."""
        return self.metrics_sim.simulate_metrics(service, task, step, max_steps)


# ── Helper Functions ───────────────────────────────────────────────────────────

def load_all_tasks() -> Dict[str, TaskDefinition]:
    """Load all tasks from tasks.json."""
    loader = TaskLoader()
    return loader.tasks


def get_task_by_id(task_id: str) -> Optional[TaskDefinition]:
    """Get task definition by ID."""
    loader = TaskLoader()
    return loader.get_task(task_id)


def validate_task_service_mapping(task: TaskDefinition) -> bool:
    """
    Validate that all services in task are valid.

    Returns True if all services exist in SERVICE_REGISTRY.
    """
    for service in task.affected_services + task.red_herrings:
        if service not in SERVICE_REGISTRY:
            print(f"⚠️  Service not in registry: {service}")
            return False
    return True


# ── Example Usage ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Load and validate tasks
    loader = TaskLoader()
    print(f"📋 Loaded {len(loader.tasks)} tasks from tasks.json")
    print()
    
    # Show sample
    sample_id = "task_cpu_spike_auth"
    if sample_id in loader.tasks:
        task = loader.tasks[sample_id]
        print(f"✓ Task: {task.id}")
        print(f"  Domain: {task.domain}")
        print(f"  Difficulty: {task.difficulty}")
        print(f"  Root cause: {task.root_cause}")
        print(f"  Affected services: {task.affected_services}")
        print(f"  Red herrings: {task.red_herrings}")
        print(f"  Cascade targets: {len(task.cascade_targets)} services")
        print(f"  Critical path broken: {task.critical_path_broken}")
        print()
        
        # Generate sample observation
        obs_gen = ObservationGenerator(loader)
        obs = obs_gen.generate_observation(task, step=0, max_steps=10)
        print("📊 Sample Observation (Step 0):")
        print(obs["message"])
        print()
        print("Service metrics:")
        for svc, metrics in obs["service_metrics"].items():
            print(f"  {svc}: {metrics}")
